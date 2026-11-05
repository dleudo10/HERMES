# from django.db import models
# from .batch import Batch


# class BatchPatient(models.Model):
#     """
#     Cada fila del Excel debe convertirse en un registro independiente.
#     """

#     batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="patients")
#     row_number = models.PositiveIntegerField()
#     document_type = models.CharField(max_length=50)
#     document_number = models.CharField(max_length=50)
#     patient_name = models.CharField(max_length=250)
#     email = models.EmailField(max_length=254)

#     is_valid = models.BooleanField(default=False)
#     validation_message = models.TextField(null=True, blank=True)

#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         db_table = "batch_patient"
#         ordering = ["row_number"]
#         constraints = [
#             models.UniqueConstraint(
#                 fields=["batch", "row_number"], name="unique_batch_patient_row"
#             )
#         ]

#     def __str__(self):
#         return f"{self.document_number} - {self.patient_name}"


from django.db import models
from .batch import Batch


class BatchPatient(models.Model):
    """
    Conserva una fila del Excel original y agrega los
    metadatos necesarios para gestionar su procesamiento.
    """

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="patients")

    row_number = models.PositiveIntegerField()

    # ---------------------------------------------
    # COLUMNAS ORIGINALES DEL EXCEL
    # ---------------------------------------------

    sede_atencion = models.CharField(
        max_length=50, blank=True, null=True, db_column="Sede_Atencion"
    )

    sede_asignacion = models.CharField(
        max_length=50, blank=True, null=True, db_column="Sede_asignacion"
    )

    consul = models.CharField(max_length=50, blank=True, null=True, db_column="Consul")

    consultorio = models.CharField(
        max_length=500, blank=True, null=True, db_column="Consultorio"
    )

    cit_num = models.CharField(max_length=50, blank=True, null=True, db_column="CitNum")

    ingreso = models.CharField(
        max_length=50, blank=True, null=True, db_column="Ingreso"
    )

    cod_espec = models.CharField(
        max_length=50, blank=True, null=True, db_column="CodEspec"
    )

    especialidad = models.CharField(
        max_length=250, blank=True, null=True, db_column="Especialidad"
    )

    cod_medico = models.CharField(
        max_length=50, blank=True, null=True, db_column="CodMedico"
    )

    nombre_medico = models.CharField(
        max_length=250, blank=True, null=True, db_column="NombreMedico"
    )

    estado = models.CharField(max_length=100, blank=True, null=True, db_column="Estado")

    cit_folio = models.CharField(
        max_length=50, blank=True, null=True, db_column="CitFolio"
    )

    tdoc = models.CharField(max_length=50, blank=True, null=True, db_column="tdoc")

    identificacion = models.CharField(
        max_length=50, blank=True, null=True, db_column="identificacion"
    )

    nombre_paciente = models.CharField(
        max_length=250, blank=True, null=True, db_column="NomprePacietne"
    )

    telefono = models.CharField(
        max_length=50, blank=True, null=True, db_column="Telefono"
    )

    fecha_nacimiento = models.CharField(
        max_length=50, blank=True, null=True, db_column="FechaNacimiento"
    )

    edad = models.CharField(max_length=50, blank=True, null=True, db_column="Edad")

    fecha_real_solicitud = models.CharField(
        max_length=50, blank=True, null=True, db_column="FecharealSol"
    )

    hora_cita = models.CharField(
        max_length=50, blank=True, null=True, db_column="CitHorIPa"
    )

    fecha_cita = models.CharField(
        max_length=50, blank=True, null=True, db_column="Fecha_Cita"
    )

    ingreso_salida_dx = models.CharField(
        max_length=100, blank=True, null=True, db_column="IngSalDx"
    )

    nombre_diagnostico = models.CharField(
        max_length=500, blank=True, null=True, db_column="NombreDiag"
    )

    cod_cups = models.CharField(
        max_length=100, blank=True, null=True, db_column="CodCUPS"
    )

    procedimiento = models.CharField(
        max_length=1000, blank=True, null=True, db_column="prnomb"
    )

    contrato = models.CharField(
        max_length=100, blank=True, null=True, db_column="Contrato"
    )

    nombre_contrato = models.CharField(
        max_length=500, blank=True, null=True, db_column="NombreContrato"
    )

    sexo = models.CharField(max_length=20, blank=True, null=True, db_column="MPSexo")

    autorizacion = models.CharField(
        max_length=250, blank=True, null=True, db_column="Aut"
    )

    autorizador = models.CharField(
        max_length=250, blank=True, null=True, db_column="Autorizador"
    )

    email = models.CharField(max_length=254, blank=True, null=True, db_column="Email")

    # ---------------------------------------------
    # CONTROL DE HERMES
    # ---------------------------------------------

    is_valid = models.BooleanField(default=False)

    validation_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "batch_patient"
        ordering = ["row_number"]

        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_number"], name="unique_batch_patient_row"
            )
        ]

        indexes = [
            models.Index(fields=["batch", "is_valid"], name="idx_batch_patient_valid"),
            models.Index(
                fields=["identificacion", "ingreso"], name="idx_patient_admission"
            ),
        ]

    def __str__(self):
        return f"{self.identificacion} - {self.nombre_paciente}"
