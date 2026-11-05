from django.db import transaction
from django.utils import timezone

from ..models import Batch, BatchPatient, BatchStatus, Extraction, ExtractionStatus


class BatchProcessingService:
    """
    Prepara y administra la transición de un lote
    desde READY hasta PROCESSING.
    """
    
    @staticmethod
    @transaction.atomic
    def get_patients_to_process(batch_code: str):
        batch = Batch.objects.select_for_update().get(
            code=batch_code
        )

        patients = BatchPatient.objects.filter(
            batch=batch,
            is_valid=True,
        ).order_by("row_number")

        result = []

        for patient in patients:
            extraction, created = Extraction.objects.get_or_create(
                batch_patient=patient,
                defaults={
                    "status": ExtractionStatus.PENDING,
                },
            )

            if extraction.status in (
                ExtractionStatus.COMPLETED,
                ExtractionStatus.CANCELLED,
                ExtractionStatus.PROCESSING,
            ):
                continue

            if extraction.attempts >= Extraction.MAX_ATTEMPTS:
                continue

            result.append({
                "batch_patient_id": patient.id,
                "extraction_id": extraction.id,
                "row_number": patient.row_number,
                "document": patient.identificacion.strip(),
                "type_document": patient.tdoc.strip(),
                "date": patient.fecha_cita.strip(),
                "numero_ingreso": patient.ingreso.strip(),
                "numero_folio": patient.cit_folio.strip(),
                "attempts": extraction.attempts,
            })

        return {
            "batch_id": batch.id,
            "batch_code": batch.code,
            "total": len(result),
            "patients": result,
        }


    @staticmethod
    @transaction.atomic
    def prepare_batch(batch_code: str):
        """
        Obtiene los pacientes válidos y reserva el lote
        para evitar que dos ejecuciones lo procesen simultáneamente.
        """

        batch = Batch.objects.select_for_update().get(code=batch_code)

        if batch.status != BatchStatus.READY:
            raise ValueError(
                f"El lote {batch_code} no está disponible. "
                f"Estado actual: {batch.status}"
            )

        patients = list(
            BatchPatient.objects.filter(
                batch=batch,
                is_valid=True,
            )
            .order_by("row_number")
            .values(
                "id",
                "row_number",
                "identificacion",
                "tdoc",
                "fecha_cita",
                "ingreso",
                "cit_folio",
            )
        )

        if not patients:
            raise ValueError(f"El lote {batch_code} no contiene pacientes válidos.")
        
        # Verificar que los datos necesarios para Playwright existan.
        for patient in patients:

            required = [
                "identificacion",
                "tdoc",
                "fecha_cita",
                "ingreso",
                "cit_folio",
            ]

            missing = [
                field
                for field in required
                if not str(patient.get(field) or "").strip()
            ]

            if missing:
                raise ValueError(
                    f"El registro de la fila {patient['row_number']} "
                    f"no tiene los campos necesarios: {missing}"
                )
                
        # Reservar el lote.
        batch.status = BatchStatus.PROCESSING
        
        batch.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return {
            "batch_id": batch.id,
            "batch_code": batch.code,
            "total": len(patients),
            "patients": patients,
        }
        
    @staticmethod
    @transaction.atomic
    def finish_batch(batch_id: int, has_errors: bool = False):
        """
        Finaliza el lote después de intentar procesar sus pacientes.
        """
        
        batch = Batch.objects.select_for_update().get(id=batch_id)
        
        if batch.status != BatchStatus.PROCESSING:
            raise ValueError(
                f"No se puede finalizar el lote en estado {batch.status}."
            )
            
        batch.status = (
            BatchStatus.PARTIALLY_COMPLETED
            if has_errors
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
