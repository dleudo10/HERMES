from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from pathlib import Path

from django.utils import timezone

from ..models import (
    Batch,
    Delivery,
    DeliveryStatus,
    Document,
    DocumentStatus,
    DocumentType,
    Extraction,
    ExtractionStatus,
)
from ..services.normalizer import Normalizer
from .config import MailConfig
from .graph_mailer import GraphMailer
from .pdf_protector import PdfProtector
from .renderer import MessageRenderer

logger = logging.getLogger(__name__)

# Nombre con el que viaja cada PDF. No lleva el documento del paciente
# porque ese número es justamente la contraseña del archivo.
ATTACHMENT_NAMES = {
    DocumentType.FOLIO_RANGE: "Historia_clinica",
    DocumentType.DISABILITIES: "Incapacidad",
    DocumentType.PRESCRIPTIONS: "Formulacion",
    DocumentType.MEDICAL_ORDERS: "Orden_medica",
}


class DeliveryService:
    """
    Envía un correo por ingreso (Extraction COMPLETED) con sus PDFs cifrados.
    La contraseña de cada PDF es el número de documento del paciente.
    """

    def __init__(
        self,
        mailer: GraphMailer,
        renderer: MessageRenderer,
        protector: PdfProtector,
        delay_seconds: float = 0,
        test_recipient: str = "",
    ):
        self.mailer = mailer
        self.renderer = renderer
        self.protector = protector
        self.delay_seconds = delay_seconds
        self.test_recipient = test_recipient

        # Prueba (dry-run o destinatario de prueba): no se guarda nada como
        # enviado, para no bloquear el envío real posterior.
        self.simulate = mailer.dry_run or bool(test_recipient)

    @classmethod
    def from_config(cls, config: MailConfig) -> "DeliveryService":
        return cls(
            mailer=GraphMailer.from_config(config),
            renderer=MessageRenderer(config),
            protector=PdfProtector(enabled=config.encrypt_pdfs),
            delay_seconds=config.delay_seconds,
            test_recipient=config.test_recipient,
        )

    # --------------------------------------------------
    # ENVÍO DE UN LOTE
    # --------------------------------------------------
    def send_batch(self, batch_code: str) -> list[dict]:
        batch = Batch.objects.get(code=batch_code)

        if not self.simulate:
            # Un envío que quedó en PROCESSING pudo haber salido antes de
            # interrumpirse: se marca como incierto y NO se reenvía solo.
            Delivery.objects.filter(
                extraction__batch_patient__batch=batch,
                status=DeliveryStatus.PROCESSING,
            ).update(
                status=DeliveryStatus.UNCERTAIN,
                error_code="INTERRUPTED",
                error_message="La ejecución se interrumpió durante el envío. Verifique en Enviados.",
                failed_at=timezone.now(),
            )

        extractions = (
            Extraction.objects.filter(
                batch_patient__batch=batch,
                status=ExtractionStatus.COMPLETED,
            )
            .select_related("batch_patient")
            .order_by("batch_patient__row_number")
        )

        results = []

        for extraction in extractions:

            if self.simulate:
                delivery = Delivery.objects.filter(extraction=extraction).first()
            else:
                delivery, _ = Delivery.objects.get_or_create(extraction=extraction)

            if delivery is not None:
                if delivery.status in (
                    DeliveryStatus.SENT,
                    DeliveryStatus.UNCERTAIN,
                    DeliveryStatus.CANCELLED,
                ):
                    continue

                if delivery.attempts >= Delivery.MAX_ATTEMPTS:
                    continue

            result = self._send_one(extraction, delivery)
            results.append(result)

            # Pausa para respetar el límite de correos por minuto del buzón.
            if self.delay_seconds and result["status"] in ("SENT", "UNCERTAIN", "FAILED"):
                time.sleep(self.delay_seconds)

        return results

    # --------------------------------------------------
    # ENVÍO DE UN PACIENTE
    # --------------------------------------------------
    def _send_one(self, extraction: Extraction, delivery: Delivery | None) -> dict:
        patient = extraction.batch_patient
        started_at = datetime.now()

        result = {
            "row_number": patient.row_number,
            "document": patient.identificacion,
            "email": None,
            "status": "FAILED",
            "attachments": 0,
            "request_id": None,
            "error": None,
        }

        try:
            email = (patient.email or "").strip().lower()
            result["email"] = email or None

            if not email:
                # Sin correo no se consume un intento: se reevalúa en la próxima corrida.
                result["status"] = "SKIPPED"
                result["error"] = "El paciente no tiene correo"
                self._mark_failed(delivery, "NO_EMAIL", result["error"])
                return result

            to = self.test_recipient or email

            files = self._collect_files(extraction)

            password = self._password(patient.identificacion)
            if not password:
                raise ValueError("El paciente no tiene número de documento para la contraseña")

            subject, body = self.renderer.render(
                patient.nombre_paciente or "", self._parse_date(patient.fecha_cita)
            )
            if self.test_recipient:
                subject = f"[PRUEBA] {subject}"

            # Si falla el cifrado se lanza excepción: nunca se envía un PDF sin proteger.
            attachments = [
                (name, self.protector.protect(path.read_bytes(), password))
                for name, path in files
            ]
            result["attachments"] = len(attachments)

            # Se registra el intento ANTES de enviar: si el proceso se corta a mitad
            # del envío, queda en PROCESSING y se trata como incierto.
            if delivery is not None:
                delivery.status = DeliveryStatus.PROCESSING
                delivery.attempts += 1
                delivery.recipient_email = to
                delivery.attachments_count = len(attachments)
                delivery.started_at = timezone.now()
                delivery.error_code = None
                delivery.error_message = None
                delivery.save()

            send = self.mailer.send(to, subject, body, attachments)

            result["request_id"] = send.request_id
            result["error"] = send.error or None

            if send.ok:
                result["status"] = "DRY_RUN" if send.dry_run else "SENT"

                if delivery is not None:
                    delivery.status = DeliveryStatus.SENT
                    delivery.sent_at = timezone.now()
                    delivery.provider_message_id = send.request_id
                    delivery.save()

            elif send.uncertain:
                result["status"] = "UNCERTAIN"
                self._mark_failed(
                    delivery, send.error.split(":")[0], send.error,
                    status=DeliveryStatus.UNCERTAIN, request_id=send.request_id,
                )

            else:
                result["status"] = "FAILED"
                self._mark_failed(
                    delivery, send.error.split(":")[0] or "SEND_ERROR", send.error,
                    request_id=send.request_id,
                )

        except Exception as error:
            result["status"] = "FAILED"
            result["error"] = str(error)
            logger.exception("Error enviando correo de la fila %s", patient.row_number)
            self._mark_failed(delivery, "UNEXPECTED_ERROR", f"{type(error).__name__}: {error}")

        finally:
            result["duration_seconds"] = (datetime.now() - started_at).total_seconds()

        return result

    # --------------------------------------------------
    # UTILIDADES
    # --------------------------------------------------
    @staticmethod
    def _mark_failed(delivery, code, message, status=DeliveryStatus.FAILED, request_id=None):
        if delivery is None:
            return

        delivery.status = status
        delivery.error_code = (code or "ERROR")[:100]
        delivery.error_message = message
        delivery.failed_at = timezone.now()
        if request_id:
            delivery.provider_message_id = request_id
        delivery.save()

    @staticmethod
    def _collect_files(extraction: Extraction) -> list[tuple[str, Path]]:
        """
        PDFs descargados de la extracción como [(nombre_para_el_correo, ruta)].
        """
        documents = Document.objects.filter(
            extraction=extraction, status=DocumentStatus.DOWNLOADED
        ).order_by("id")

        totals = {}
        for doc in documents:
            totals[doc.type_document] = totals.get(doc.type_document, 0) + 1

        counters = {}
        files = []

        for doc in documents:
            path = Path(doc.file_path)

            if not path.is_file():
                raise FileNotFoundError(f"Falta el archivo en disco: {doc.file_path}")

            base = ATTACHMENT_NAMES.get(doc.type_document, "Documento")
            counters[doc.type_document] = counters.get(doc.type_document, 0) + 1

            if totals[doc.type_document] > 1:
                name = f"{base}_{counters[doc.type_document]}.pdf"
            else:
                name = f"{base}.pdf"

            files.append((name, path))

        if not files:
            raise ValueError("La extracción no tiene documentos descargados")

        return files

    @staticmethod
    def _password(document) -> str:
        """Contraseña del PDF = documento del paciente, como lo guarda el importador."""
        value = str(document or "").strip()

        # Pandas puede entregar 1017123456.0 si la columna se leyó como número.
        if re.fullmatch(r"\d+\.0", value):
            value = value[:-2]

        return Normalizer.alnum(value)

    @staticmethod
    def _parse_date(value) -> date:
        value = str(value or "").strip()

        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
        ):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

        raise ValueError(f"Formato de fecha no válido: {value}")