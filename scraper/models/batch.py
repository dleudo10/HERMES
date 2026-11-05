from django.db import models
import uuid


class BatchStatus(models.TextChoices):
    IMPORTED = "IMPORTED", "Importado"
    VALIDATING = "VALIDATING", "Validando"
    READY = "READY", "Listo para procesar"
    NO_VALID_ROWS = "NO_VALID_ROWS", "Sin registros válidos"
    PROCESSING = "PROCESSING", "Procesando"
    COMPLETED = "COMPLETED", "Completado"
    FAILED = "FAILED", "Fallido"
    CANCELLED = "CANCELLED", "Cancelado"
    PARTIALLY_COMPLETED = "PARTIAL", "Completado con errores"


class Batch(models.Model):
    """
    Representa una importación de un archivo Excel.
    """

    code = models.CharField(max_length=250, unique=True, verbose_name="Código")
    original_filename = models.CharField(
        max_length=250, verbose_name="Nombre del archivo original", unique=True
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name="Hash del archivo",
    )
    total_rows = models.PositiveIntegerField(
        default=0, verbose_name="Total de registros"
    )
    valid_rows = models.PositiveIntegerField(
        default=0, verbose_name="Registros inválidos"
    )
    invalid_rows = models.PositiveIntegerField(
        default=0, verbose_name="Registros inválidos"
    )
    status = models.CharField(
        max_length=20,
        choices=BatchStatus.choices,
        default=BatchStatus.IMPORTED,
        verbose_name="Estado",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Fecha de creación"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Última actualización"
    )
    finished_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha de finalización"
    )

    class Meta:
        db_table = "batch"
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    @property
    def is_completed(self):
        return self.status == BatchStatus.COMPLETED

    @staticmethod
    def generate_code():
        return f"HER-{uuid.uuid4().hex[:12].upper()}"
