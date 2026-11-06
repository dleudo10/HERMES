from django.db import models
from .extraction import Extraction


class DocumentType(models.TextChoices):
    FOLIO_RANGE = "FOLIO_RANGE", "Rango de folios"
    DISABILITIES = "DISABILITIES", "Incapacidades"
    PRESCRIPTIONS = "PRESCRIPTIONS", "Formulaciones"
    MEDICAL_ORDERS = "MEDICAL_ORDERS", "Órdenes médicas"


class DocumentStatus(models.TextChoices):
    DOWNLOADED = "DOWNLOADED", "Descargado"
    NOT_FOUND = "NOT_FOUND", "No encontrado"
    FAILED = "FAILED", "Error al descargar"


class Document(models.Model):
    """
    Resultado de cada tipo de documento para una extracción.

    - DOWNLOADED: una fila por archivo descargado (un paciente puede tener
      varias incapacidades, formulaciones u órdenes del mismo tipo).
    - NOT_FOUND: el sistema no tiene ese documento para el paciente.
      El motivo queda en `message`.
    - FAILED: hubo un error técnico al intentar descargarlo.
    """

    extraction = models.ForeignKey(
        Extraction,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    type_document = models.CharField(
        max_length=50,
        choices=DocumentType.choices,
    )

    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DOWNLOADED,
    )

    message = models.TextField(null=True, blank=True)

    original_filename = models.CharField(max_length=250, blank=True, default="")

    file_path = models.CharField(max_length=500, blank=True, default="")

    mime_type = models.CharField(max_length=100, blank=True, default="")

    file_size = models.PositiveBigIntegerField(default=0)

    downloaded_at = models.DateTimeField(null=True, blank=True)

    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "document"
        ordering = ["id"]
        indexes = [
            models.Index(
                fields=["extraction", "type_document"],
                name="idx_document_extraction_type",
            ),
        ]

    def __str__(self):
        return self.original_filename or f"{self.type_document} - {self.status}"