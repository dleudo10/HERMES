
from django.db import transaction
from django.utils import timezone

from ..models import Extraction, ExtractionStatus


class ExtractionService:

    @staticmethod
    @transaction.atomic
    def start(extraction_id: int):
        extraction = Extraction.objects.select_for_update().get(
            id=extraction_id
        )

        if extraction.status in (
            ExtractionStatus.COMPLETED,
            ExtractionStatus.CANCELLED,
            ExtractionStatus.PROCESSING,
        ):
            raise ValueError("La extracción no puede iniciarse.")

        if extraction.attempts >= Extraction.MAX_ATTEMPTS:
            raise ValueError("Se alcanzó el máximo de intentos.")

        extraction.attempts += 1
        extraction.status = ExtractionStatus.PROCESSING
        extraction.started_at = timezone.now()
        extraction.finished_at = None
        extraction.duration_ms = None
        extraction.error_code = None
        extraction.error_message = None

        extraction.save()

        return extraction
