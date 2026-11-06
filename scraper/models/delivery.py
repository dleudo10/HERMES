from django.db import models
from .extraction import Extraction

class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    PROCESSING = "PROCESSING", "Procesando"
    SENT = "SENT", "Enviado"
    FAILED = "FAILED", "Fallido"
    UNCERTAIN = "UNCERTAIN", "Incierto (verificar en Enviados)"
    CANCELLED = "CANCELLED", "Cancelado"


class Delivery(models.Model):
    """
    Un correo por extracción (un ingreso), con todos sus PDFs adjuntos.
    """

    MAX_ATTEMPTS = 3

    id = models.BigAutoField(primary_key=True)

    extraction = models.OneToOneField(
        Extraction, on_delete=models.CASCADE, related_name="delivery"
    )

    recipient_email = models.EmailField(max_length=254, blank=True, default="")

    status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )

    attempts = models.PositiveIntegerField(default=0)

    attachments_count = models.PositiveIntegerField(default=0)

    # Fechas del proceso de entrega
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    # Información de errores
    error_code = models.CharField(max_length=100, null=True, blank=True)

    error_message = models.TextField(null=True, blank=True)

    # Identificador del proveedor de correo (request-id de Graph)
    provider_message_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "delivery"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient_email} - {self.status}"