from django.db import transaction
from django.utils import timezone

from ..models import (
    Batch,
    BatchPatient,
    BatchStatus,
    Extraction,
    ExtractionStatus,
)


class BatchProcessingService:
    """
    Prepara y administra la transición de un lote:
    READY / PARTIAL / FAILED -> PROCESSING -> COMPLETED / PARTIAL / FAILED.
    """

    # Estados desde los que se puede (re)procesar un lote.
    PROCESSABLE_STATUSES = (
        BatchStatus.READY,
        BatchStatus.PARTIALLY_COMPLETED,
        BatchStatus.FAILED,
        BatchStatus.PROCESSING,
    )

    REQUIRED_FIELDS = [
        "identificacion",
        "tdoc",
        "fecha_cita",
        "ingreso",
        "cit_folio",
    ]

    @staticmethod
    @transaction.atomic
    def prepare_batch(batch_code: str):
        """
        Reserva el lote y devuelve los pacientes pendientes.

        Crea la Extraction de cada paciente válido y omite las que ya
        están COMPLETED/CANCELLED o agotaron sus intentos.
        """

        batch = Batch.objects.select_for_update().get(code=batch_code)

        if batch.status not in BatchProcessingService.PROCESSABLE_STATUSES:
            raise ValueError(
                f"El lote {batch_code} no está disponible. "
                f"Estado actual: {batch.status}"
            )

        # Como el lote está reservado por esta ejecución, cualquier extracción
        # que siga en PROCESSING quedó así por una ejecución interrumpida.
        Extraction.objects.filter(
            batch_patient__batch=batch,
            status=ExtractionStatus.PROCESSING,
        ).update(
            status=ExtractionStatus.FAILED,
            error_code="INTERRUPTED",
            error_message="La ejecución anterior se interrumpió.",
            finished_at=timezone.now(),
        )

        valid_patients = BatchPatient.objects.filter(
            batch=batch,
            is_valid=True,
        ).order_by("row_number")

        if not valid_patients.exists():
            raise ValueError(f"El lote {batch_code} no contiene pacientes válidos.")

        pending = []

        for patient in valid_patients:

            extraction, _ = Extraction.objects.get_or_create(
                batch_patient=patient,
                defaults={"status": ExtractionStatus.PENDING},
            )

            if extraction.status in (
                ExtractionStatus.COMPLETED,
                ExtractionStatus.CANCELLED,
            ):
                continue

            if extraction.attempts >= Extraction.MAX_ATTEMPTS:
                continue

            missing = [
                field
                for field in BatchProcessingService.REQUIRED_FIELDS
                if not str(getattr(patient, field) or "").strip()
            ]

            if missing:
                raise ValueError(
                    f"El registro de la fila {patient.row_number} "
                    f"no tiene los campos necesarios: {missing}"
                )

            pending.append({
                "id": patient.id,
                "extraction_id": extraction.id,
                "row_number": patient.row_number,
                "identificacion": patient.identificacion,
                "tdoc": patient.tdoc,
                "fecha_cita": patient.fecha_cita,
                "ingreso": patient.ingreso,
                "cit_folio": patient.cit_folio,
            })

        # Nada pendiente: no se reserva el lote.
        if pending:
            batch.status = BatchStatus.PROCESSING
            batch.finished_at = None

            batch.save(
                update_fields=[
                    "status",
                    "finished_at",
                    "updated_at",
                ]
            )

        return {
            "batch_id": batch.id,
            "batch_code": batch.code,
            "total": len(pending),
            "patients": pending,
        }

    @staticmethod
    @transaction.atomic
    def finish_batch(batch_id: int, has_errors: bool = False):
        """
        Finaliza el lote. Queda COMPLETED solo si TODOS los pacientes válidos
        tienen su extracción COMPLETED (incluyendo corridas anteriores);
        de lo contrario queda PARTIAL.
        """

        batch = Batch.objects.select_for_update().get(id=batch_id)

        if batch.status != BatchStatus.PROCESSING:
            raise ValueError(
                f"No se puede finalizar el lote en estado {batch.status}."
            )

        incomplete = (
            BatchPatient.objects.filter(batch=batch, is_valid=True)
            .exclude(extractions__status=ExtractionStatus.COMPLETED)
            .exists()
        )

        batch.status = (
            BatchStatus.PARTIALLY_COMPLETED
            if (has_errors or incomplete)
            else BatchStatus.COMPLETED
        )

        batch.finished_at = timezone.now()

        batch.save(
            update_fields=[
                "status",
                "finished_at",
                "updated_at",
            ]
        )

        return batch

    @staticmethod
    @transaction.atomic
    def fail_batch(batch_id: int):

        batch = Batch.objects.select_for_update().get(id=batch_id)

        batch.status = BatchStatus.FAILED
        batch.finished_at = timezone.now()

        batch.save(
            update_fields=[
                "status",
                "finished_at",
                "updated_at",
            ]
        )

        return batch