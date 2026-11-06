import socket
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from ..models import Document, DocumentStatus, Extraction, ExtractionStatus


class ExtractionService:
    """
    Administra el ciclo de vida de una Extraction:
    start (intento) -> finish (resultado por documento) | fail (error general).
    """

    # --------------------------------------------------
    # INICIAR UN INTENTO
    # --------------------------------------------------
    @staticmethod
    @transaction.atomic
    def start(extraction_id: int):
        extraction = Extraction.objects.select_for_update().get(id=extraction_id)

        if extraction.status in (
            ExtractionStatus.COMPLETED,
            ExtractionStatus.CANCELLED,
            ExtractionStatus.PROCESSING,
        ):
            raise ValueError("La extracción no puede iniciarse.")

        if extraction.attempts >= Extraction.MAX_ATTEMPTS:
            raise ValueError("Se alcanzó el máximo de intentos.")

        # Cada intento parte limpio: se descartan los registros del anterior.
        extraction.documents.all().delete()

        extraction.attempts += 1
        extraction.status = ExtractionStatus.PROCESSING
        extraction.started_at = timezone.now()
        extraction.finished_at = None
        extraction.duration_ms = None
        extraction.error_code = None
        extraction.error_message = None
        extraction.bot_machine = socket.gethostname()

        extraction.save()

        return extraction

    # --------------------------------------------------
    # FINALIZAR CON RESULTADOS POR TIPO DE DOCUMENTO
    # --------------------------------------------------
    @staticmethod
    @transaction.atomic
    def finish(extraction_id: int, results: list):
        """
        Guarda un Document por cada archivo descargado y un Document por
        cada tipo que no se encontró o falló (con su mensaje).

        Regla: la extracción solo se completa si hay al menos un documento
        descargado. Si hubo errores técnicos en algún tipo y aún quedan
        intentos, queda FAILED para reintentarla.
        """
        extraction = Extraction.objects.select_for_update().get(id=extraction_id)

        now = timezone.now()

        downloaded = 0
        not_found_messages = []
        error_messages = []

        for result in results:
            label = result.type_document

            if result.status == DocumentStatus.DOWNLOADED:
                for file in result.files:
                    path = Path(file)

                    if not path.is_file() or path.stat().st_size == 0:
                        message = f"El archivo no existe o está vacío: {path.name}"

                        Document.objects.create(
                            extraction=extraction,
                            type_document=label,
                            status=DocumentStatus.FAILED,
                            message=message,
                        )
                        error_messages.append(f"{label}: {message}")
                        continue

                    Document.objects.create(
                        extraction=extraction,
                        type_document=label,
                        status=DocumentStatus.DOWNLOADED,
                        original_filename=path.name,
                        file_path=str(path),
                        mime_type="application/pdf",
                        file_size=path.stat().st_size,
                        downloaded_at=now,
                    )
                    downloaded += 1

            elif result.status == DocumentStatus.NOT_FOUND:
                Document.objects.create(
                    extraction=extraction,
                    type_document=label,
                    status=DocumentStatus.NOT_FOUND,
                    message=result.message,
                )
                not_found_messages.append(f"{label}: {result.message}")

            else:
                Document.objects.create(
                    extraction=extraction,
                    type_document=label,
                    status=DocumentStatus.FAILED,
                    message=result.message,
                )
                error_messages.append(f"{label}: {result.message}")

        # ----- Estado final de la extracción -----
        if downloaded == 0:
            status = ExtractionStatus.FAILED

            if error_messages:
                code = "DOCUMENT_ERRORS"
                message = "; ".join(error_messages + not_found_messages)
            else:
                code = "NO_DOCUMENTS"
                message = (
                    "No se encontró ningún documento para el paciente. "
                    + "; ".join(not_found_messages)
                )

        elif error_messages and extraction.attempts < Extraction.MAX_ATTEMPTS:
            # Hay documentos, pero algún tipo falló por error técnico: reintentar.
            status = ExtractionStatus.FAILED
            code = "DOCUMENT_ERRORS"
            message = "; ".join(error_messages)

        else:
            status = ExtractionStatus.COMPLETED
            code = "PARTIAL_DOCUMENTS" if error_messages else None
            message = "; ".join(error_messages) if error_messages else None

        return ExtractionService._close(extraction, status, code, message, now)

    # --------------------------------------------------
    # FINALIZAR CON ERROR GENERAL (paciente/ingreso no encontrado, etc.)
    # --------------------------------------------------
    @staticmethod
    @transaction.atomic
    def fail(extraction_id: int, error_code: str, error_message: str):
        extraction = Extraction.objects.select_for_update().get(id=extraction_id)

        return ExtractionService._close(
            extraction,
            ExtractionStatus.FAILED,
            error_code,
            error_message,
            timezone.now(),
        )

    # --------------------------------------------------
    # UTILIDAD
    # --------------------------------------------------
    @staticmethod
    def _close(extraction, status, code, message, now):
        extraction.status = status
        extraction.error_code = code
        extraction.error_message = message
        extraction.finished_at = now

        if extraction.started_at:
            extraction.duration_ms = int(
                (now - extraction.started_at).total_seconds() * 1000
            )

        extraction.save()

        return extraction