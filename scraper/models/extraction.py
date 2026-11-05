from django.db import models
from .batch_patient import BatchPatient


class ExtractionStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    PROCESSING = "PROCESSING", "Procesando"
    COMPLETED = "COMPLETED", "Completado"
    FAILED = "FAILED", "Fallido"
    CANCELLED = "CANCELLED", "Cancelado"


class Extraction(models.Model):
    """
    Aquí registramos el resultado de la consulta del sistema hospitalario
    """

    batch_patient = models.OneToOneField(
        BatchPatient, on_delete=models.CASCADE, related_name="extractions"
    )

    status = models.CharField(
        max_length=20,
        choices=ExtractionStatus.choices,
        default=ExtractionStatus.PENDING,
    )

    attempts = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    duration_ms = models.PositiveBigIntegerField(null=True, blank=True)

    error_code = models.CharField(max_length=100, null=True, blank=True)

    error_message = models.TextField(null=True, blank=True)

    bot_machine = models.CharField(max_length=150, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    MAX_ATTEMPTS = 5

    @property
    def can_retry(self):
        return (
            self.status == ExtractionStatus.FAILED
            and self.attempts < self.MAX_ATTEMPTS
        )

    class Meta:
        db_table = "extraction"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Extraction #{self.id} - "
            f"{self.batch_patient.identificacion} - {self.status}"
        )
