from django.db import models
from .extraction import Extraction


class DocumentType(models.TextChoices):
    FOLIO_RANGE = "FOLIO_RANGE", "Rango de folios"
    DISABILITIES = "DISABILITIES", "Incapacidades"
    PRESCRIPTIONS = "PRESCRIPTIONS", "Formulaciones"
    MEDICAL_ORDERS = "MEDICAL_ORDERS", "Órdenes médicas"


class Document(models.Model):
    """
    Almacena los metadatos y la ubicación de cada documento descargado.
    """

    extraction = models.ForeignKey(
        Extraction,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    original_filename = models.CharField(max_length=250)

    file_path = models.CharField(max_length=500)

    mime_type = models.CharField(max_length=100)

    file_size = models.PositiveBigIntegerField(default=0)

    type_document = models.CharField(
        max_length=50,
        choices=DocumentType.choices,
    )

    downloaded_at = models.DateTimeField(null=True, blank=True)

    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "document"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["extraction", "type_document"],
                name="unique_extraction_document_type",
            )
        ]

    def __str__(self):
        return self.original_filename
