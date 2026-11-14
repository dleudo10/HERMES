from django.db import models

from .batch import Batch
from .batch_patient import BatchPatient

class ChangeKind(models.TextChoices):
    CREATED = "CREATED", "Fila nueva"
    UPDATED = "UPDATED", "Fila actualizada"
    CONFLICT = "CONFLICT", "Cambio no aplicado"
    
class BatchPatientChange(models.Model):
    """
    Bitácora de auditoria: cada cambio que una re-sincronización del Excel
    aplicó (o rechazó) sobre un BatchPatient
    """
    
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name="changes"
    )
    
    batch_patient = models.ForeignKey(
        BatchPatient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="changes",
    )
    
    row_number = models.PositiveIntegerField()

    kind = models.CharField(max_length=20, choices=ChangeKind.choices)

    # {"campo": {"old": valor_anterior, "new": valor_nuevo}}
    changes = models.JSONField(default=dict)

    reason = models.CharField(max_length=250, blank=True, default="")

    # Hash del Excel con el que se hizo la sincronización.
    file_hash = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "batch_patient_change"
        ordering = ["-created_at", "row_number"]
        indexes = [
            models.Index(fields=["batch", "row_number"], name="idx_change_batch_row"),
        ]

    def __str__(self):
        return f"{self.batch_id} fila {self.row_number} - {self.kind}"