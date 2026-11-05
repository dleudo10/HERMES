from django.db import models
from .document import Document

class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pendiente"
    PROCESSING = "PROCESSING", "Procesando"
    SENT = "SENT", "Enviado"
    FAILED = "FAILED", "Fallido"
    CANCELLED = "CANCELLED", "Cancelado"


class Delivery(models.Model):
    id = models.BigAutoField(primary_key=True)

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="deliveries"
    )

    recipient_email = models.EmailField(max_length=254)

    status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )

    attempts = models.PositiveIntegerField(default=0)

    # Fechas del proceso de entrega
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    # Información de errores
    error_code = models.CharField(max_length=100, null=True, blank=True)

    error_message = models.TextField(null=True, blank=True)

    # Identificador del proveedor de correo
    provider_message_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "delivery"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient_email} - {self.status}"
