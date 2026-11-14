import hashlib
import re

import pandas as pd

from pathlib import Path
from datetime import date, datetime

from django.db import transaction

from ..models import (
    Batch,
    BatchPatient,
    BatchPatientChange,
    BatchStatus,
    ChangeKind,
    Delivery,
    DeliveryStatus,
    Extraction,
    ExtractionStatus,
)
from ..services.normalizer import Normalizer

from .structure_config import (
    COLUMNAS,
    EXCEL_TO_MODEL,
    DOMINIOS_SOSPECHOSOS,
    EMAIL_RE,
    REQUERIDAS,
)


class ExcelCleaner:
    """
    Importa un Excel, conserva sus filas originales,
    valida cada registro y crea un Batch con sus BatchPatient.
    """

    def __init__(
        self,
        file,
        estados,
        especialidades,
        skip_if_bad_email=True,
    ):
        self.file = file

        self.estados = {Normalizer.norm(value) for value in estados}

        self.especialidades = {Normalizer.norm(value) for value in especialidades}

        self.skip_if_bad_email = skip_if_bad_email

    # --------------------------------------------------
    # 1. FLUJO PRINCIPAL
    # --------------------------------------------------

    @transaction.atomic
    def execute(self):
        """
        Ejecuta la importación completa.

        Si ocurre un error durante la persistencia,
        se revierten el Batch y sus BatchPatient.
        """

        # Calcular hash del archivo.
        file_hash = self.calculate_file_hash()

        # Leer Excel.
        df = self.read_excel()

        if df.empty:
            raise ValueError("El archivo Excel no contiene registros.")

        # Resolver columnas.
        columns = self.resolve_columns(df)

        # Crear lote.
        batch = Batch.objects.create(
            code=Batch.generate_code(),
            original_filename=self.get_filename(),
            file_hash=file_hash,
            total_rows=len(df),
            status=BatchStatus.VALIDATING,
        )

        patients = []
        seen = set()

        valid_count = 0

        # Recorrer todas las filas.
        for index, row in df.iterrows():

            row_number = index + 2

            # Obtener los valores originales.
            original_data = self.get_original_data(
                row=row,
                columns=columns["original"],
            )

            # Obtener valores normalizados para validar.
            validation_data = self.get_validation_data(
                row=row,
                columns=columns["validation"],
            )

            # Validar registro.
            errors = self.validate_row(
                data=validation_data,
                seen=seen,
            )

            is_valid = not errors

            if is_valid:
                valid_count += 1

            # Construir registro para persistencia.
            patient_data = {
                model_field: original_data.get(model_field)
                for model_field in EXCEL_TO_MODEL.values()
            }

            patient = BatchPatient(
                batch=batch,
                row_number=row_number,
                **patient_data,
                is_valid=is_valid,
                validation_message="; ".join(errors) if errors else None,
            )

            patients.append(patient)

        # Persistir todas las filas, válidas e inválidas.
        BatchPatient.objects.bulk_create(
            patients,
            batch_size=500,
        )

        # Actualizar estadísticas del lote.
        batch.valid_rows = valid_count
        batch.invalid_rows = len(df) - valid_count

        batch.status = (
            BatchStatus.READY if valid_count > 0 else BatchStatus.NO_VALID_ROWS
        )

        batch.save(
            update_fields=[
                "valid_rows",
                "invalid_rows",
                "status",
                "updated_at",
            ]
        )

        return batch

    # --------------------------------------------------
    # 2. LECTURA DEL EXCEL
    # --------------------------------------------------

    def read_excel(self):

        self.reset_file()

        return pd.read_excel(
            self.file,
            dtype=str,
            sheet_name=0,
        )

    # --------------------------------------------------
    # 3. RESOLUCIÓN DE COLUMNAS
    # --------------------------------------------------

    @staticmethod
    def normalize_header(value):

        return re.sub(
            r"\s+",
            "",
            Normalizer.norm(str(value)),
        )

    def resolve_columns(self, df):

        available = {self.normalize_header(column): column for column in df.columns}

        # Resolver las columnas originales.
        original_columns = {}

        for excel_column, model_field in EXCEL_TO_MODEL.items():

            normalized = self.normalize_header(excel_column)

            original_columns[model_field] = available.get(normalized)

        # Resolver las columnas utilizadas para validar.
        validation_columns = {}

        for canonical, aliases in COLUMNAS.items():

            for alias in aliases:

                normalized = self.normalize_header(alias)

                if normalized in available:
                    validation_columns[canonical] = available[normalized]
                    break

        missing = [column for column in REQUERIDAS if column not in validation_columns]

        if missing:
            raise ValueError(f"Faltan columnas requeridas para validar: {missing}")

        missing_original = [
            excel_column
            for excel_column, model_field in EXCEL_TO_MODEL.items()
            if original_columns[model_field] is None
        ]

        if missing_original:
            raise ValueError(
                f"Faltan columnas originales del Excel: {missing_original}"
            )

        return {
            "original": original_columns,
            "validation": validation_columns,
        }

    # --------------------------------------------------
    # 4. OBTENER DATOS ORIGINALES
    # --------------------------------------------------

    @staticmethod
    def get_original_data(row, columns):

        data = {}

        for model_field, excel_column in columns.items():

            if excel_column is None:
                data[model_field] = None
                continue

            value = row[excel_column]

            if pd.isna(value):
                data[model_field] = None
            else:
                # No aplicar strip, upper ni conversiones.
                data[model_field] = str(value)

        return data

    # --------------------------------------------------
    # 5. OBTENER DATOS PARA VALIDACIÓN
    # --------------------------------------------------

    def get_validation_data(self, row, columns):

        def get(column):

            excel_column = columns.get(column)

            if excel_column is None:
                return ""

            return self.clean_text(row[excel_column])

        return {
            "tdoc": Normalizer.norm(get("tdoc")),
            "documento": self.clean_document(get("documento")),
            "ingreso": get("ingreso"),
            "fecha": get("fecha"),
            "estado": Normalizer.norm(get("estado")),
            "especialidad": Normalizer.norm(get("especialidad")),
            "email": get("email"),
            "nombre": get("nombre"),
            "cit_folio": get("cit_folio"),
        }

    # --------------------------------------------------
    # 6. LIMPIEZA DE TEXTO PARA VALIDACIÓN
    # --------------------------------------------------

    @staticmethod
    def clean_text(value):

        if pd.isna(value):
            return ""

        value = str(value).strip()

        return "" if value.lower() == "nan" else value

    def clean_document(self, value):

        value = self.clean_text(value)

        # Corregir documentos leídos como 123456.0.
        if re.fullmatch(r"\d+\.0", value):
            value = value[:-2]

        return Normalizer.alnum(value)

    # --------------------------------------------------
    # 7. VALIDACIÓN DE CADA FILA
    # --------------------------------------------------

    def validate_row(self, data, seen):

        errors = []

        # Documento.
        if not data["tdoc"] or not data["documento"]:
            errors.append("sin_documento_o_tipo")

        # Estado.
        if not self.validate_status(data["estado"]):
            errors.append("estado_no_habilitado")

        # Especialidad.
        if not self.validate_specialty(data["especialidad"]):
            errors.append("especialidad_no_habilitada")
            
        if not data["cit_folio"]:
            errors.append("folio_invalido")

        # Ingreso.
        admission = self.validate_income(data["ingreso"])

        if admission is None:
            errors.append("ingreso_invalido")

        # Fecha.
        parsed_date = self.parse_date(data["fecha"])

        if parsed_date is None:
            errors.append("fecha_invalida")

        # Correo: vacío no se considera inválido.
        email = data["email"]

        if email:
            _, email_error = self.validate_email(email)

            if email_error and self.skip_if_bad_email:
                errors.append(email_error)

        # Duplicados.
        # Solo se consideran duplicados cuando los datos
        # fundamentales permiten construir una llave válida.
        if data["tdoc"] and data["documento"] and admission is not None:

            key = (
                data["tdoc"],
                data["documento"],
                admission,
            )

            if key in seen:
                errors.append("registro_duplicado")

            elif not errors:
                # Solo una fila válida puede convertirse
                # en la primera aparición de un registro.
                seen.add(key)

        return errors

    # --------------------------------------------------
    # 8. VALIDAR ESTADO Y ESPECIALIDAD
    # --------------------------------------------------

    def validate_status(self, estado):

        return estado in self.estados

    def validate_specialty(self, specialty):

        return specialty in self.especialidades

    # --------------------------------------------------
    # 9. VALIDAR INGRESO
    # --------------------------------------------------

    @staticmethod
    def validate_income(value):

        try:
            number = float(value)

            if not number.is_integer():
                return None

            return int(number)

        except (ValueError, TypeError):
            return None

    # --------------------------------------------------
    # 10. VALIDAR FECHA
    # --------------------------------------------------

    @staticmethod
    def parse_date(value):

        if pd.isna(value):
            return None

        if isinstance(value, (datetime, pd.Timestamp)):
            return value.date()

        if isinstance(value, date):
            return value

        value = str(value).strip()

        formats = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
            "%d-%m-%Y",
        ]

        for fmt in formats:

            try:
                return datetime.strptime(value, fmt).date()

            except ValueError:
                continue

        return None

    # --------------------------------------------------
    # 11. VALIDAR CORREO
    # --------------------------------------------------

    @staticmethod
    def validate_email(value):

        if not value:
            return None, None

        parts = [part for part in re.split(r"[;,\s]+", value) if part]

        unique = {part.lower() for part in parts}

        if len(unique) > 1:
            return None, "email_multiples"

        email = parts[0].lower()

        if not EMAIL_RE.fullmatch(email):
            return None, "email_invalido"

        domain = email.rsplit("@", 1)[1]

        if domain in DOMINIOS_SOSPECHOSOS:

            suggestion = DOMINIOS_SOSPECHOSOS[domain]

            return None, (f"email_dominio_sospechoso:" f"{domain}:posible_{suggestion}")

        return email, None

    # --------------------------------------------------
    # 12. HASH DEL ARCHIVO
    # --------------------------------------------------

    def calculate_file_hash(self):

        sha = hashlib.sha256()

        if isinstance(self.file, (str, Path)):

            with open(self.file, "rb") as file:

                for chunk in iter(
                    lambda: file.read(1024 * 1024),
                    b"",
                ):
                    sha.update(chunk)

        else:

            self.reset_file()

            while True:

                chunk = self.file.read(1024 * 1024)

                if not chunk:
                    break

                sha.update(chunk)

            self.reset_file()

        return sha.hexdigest()

    # --------------------------------------------------
    # 13. UTILIDADES
    # --------------------------------------------------

    def reset_file(self):

        if hasattr(self.file, "seek"):
            self.file.seek(0)

    def get_filename(self):

        if isinstance(self.file, (str, Path)):
            return Path(self.file).name

        return Path(getattr(self.file, "name", "archivo.xlsx")).name
    
    # --------------------------------------------------
    # 14. RE-SINCRONIZACIÓN DE UN LOTE EXISTENTE
    # --------------------------------------------------

    # Si cambia alguno de estos campos en una fila que ya se procesó,
    # el Excel ya no describe el mismo paciente/ingreso.
    IDENTITY_FIELDS = ("tdoc", "identificacion", "ingreso")

    @transaction.atomic
    def sync(self, batch):
        """
        Relee el Excel, revalida TODAS las filas (válidas e inválidas) con la
        configuración actual y actualiza el lote existente. Cada cambio queda
        en BatchPatientChange. Las filas se emparejan por row_number.
        """

        file_hash = self.calculate_file_hash()
        df = self.read_excel()

        if df.empty:
            raise ValueError("El archivo Excel no contiene registros.")

        columns = self.resolve_columns(df)

        existing = {
            patient.row_number: patient
            for patient in BatchPatient.objects.filter(batch=batch)
        }

        stats = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "conflicts": 0,
            "newly_valid": 0,
            "missing_in_file": 0,
        }

        seen = set()
        rows_in_file = set()

        for index, row in df.iterrows():

            row_number = index + 2
            rows_in_file.add(row_number)

            original_data = self.get_original_data(
                row=row,
                columns=columns["original"],
            )

            validation_data = self.get_validation_data(
                row=row,
                columns=columns["validation"],
            )

            errors = self.validate_row(data=validation_data, seen=seen)

            is_valid = not errors
            message = "; ".join(errors) if errors else None

            new_data = {
                model_field: original_data.get(model_field)
                for model_field in EXCEL_TO_MODEL.values()
            }
            new_data["is_valid"] = is_valid
            new_data["validation_message"] = message

            patient = existing.get(row_number)

            # ---------- Fila nueva ----------
            if patient is None:
                patient = BatchPatient.objects.create(
                    batch=batch,
                    row_number=row_number,
                    **new_data,
                )

                self._log(
                    batch,
                    patient,
                    row_number,
                    ChangeKind.CREATED,
                    {
                        "is_valid": {"old": None, "new": is_valid},
                        "validation_message": {"old": None, "new": message},
                    },
                    file_hash,
                )

                stats["created"] += 1

                if is_valid:
                    stats["newly_valid"] += 1

                continue

            # ---------- Fila existente: qué cambió ----------
            diff = {
                field: {"old": getattr(patient, field), "new": value}
                for field, value in new_data.items()
                if getattr(patient, field) != value
            }

            if not diff:
                stats["unchanged"] += 1
                continue

            reason = self._locked_reason(patient, diff)

            if reason:
                self._log_conflict(
                    batch, patient, row_number, diff, reason, file_hash
                )
                stats["conflicts"] += 1
                continue

            was_valid = patient.is_valid

            for field, change in diff.items():
                setattr(patient, field, change["new"])

            patient.save()

            self._log(
                batch,
                patient,
                row_number,
                ChangeKind.UPDATED,
                diff,
                file_hash,
            )

            stats["updated"] += 1

            if is_valid and not was_valid:
                stats["newly_valid"] += 1

        stats["missing_in_file"] = len(set(existing) - rows_in_file)

        # ---------- Contadores y estado del lote ----------
        patients = BatchPatient.objects.filter(batch=batch)

        total = patients.count()
        valid_count = patients.filter(is_valid=True).count()

        batch.total_rows = total
        batch.valid_rows = valid_count
        batch.invalid_rows = total - valid_count

        incomplete = (
            patients.filter(is_valid=True)
            .exclude(extractions__status=ExtractionStatus.COMPLETED)
            .exists()
        )

        # Si aparecieron válidos pendientes, el lote se reabre.
        if incomplete and batch.status in (
            BatchStatus.COMPLETED,
            BatchStatus.NO_VALID_ROWS,
        ):
            batch.status = BatchStatus.READY
            batch.finished_at = None

        batch.save(
            update_fields=[
                "total_rows",
                "valid_rows",
                "invalid_rows",
                "status",
                "finished_at",
                "updated_at",
            ]
        )

        return stats

    def _locked_reason(self, patient, diff):
        """
        Devuelve el motivo por el que NO se debe aplicar el cambio,
        o None si es seguro actualizar.
        """

        extraction = Extraction.objects.filter(batch_patient=patient).first()

        if extraction is None:
            return None

        delivery = Delivery.objects.filter(extraction=extraction).first()

        if delivery and delivery.status in (
            DeliveryStatus.SENT,
            DeliveryStatus.UNCERTAIN,
        ):
            return "Ya tiene un correo enviado o incierto: no se modifica."

        if extraction.attempts > 0 and any(
            field in diff for field in self.IDENTITY_FIELDS
        ):
            return "Cambió el paciente o el ingreso de una fila ya procesada."

        if (
            extraction.status == ExtractionStatus.COMPLETED
            and diff.get("is_valid", {}).get("new") is False
        ):
            return "La fila ya se descargó y quedaría inválida: revisar manualmente."

        return None

    @staticmethod
    def _log(batch, patient, row_number, kind, changes, file_hash, reason=""):
        BatchPatientChange.objects.create(
            batch=batch,
            batch_patient=patient,
            row_number=row_number,
            kind=kind,
            changes=changes,
            reason=reason,
            file_hash=file_hash,
        )

    @staticmethod
    def _log_conflict(batch, patient, row_number, diff, reason, file_hash):
        # Evita repetir el mismo conflicto en cada ejecución.
        last = (
            BatchPatientChange.objects.filter(batch=batch, row_number=row_number)
            .order_by("-id")
            .first()
        )

        if last and last.kind == ChangeKind.CONFLICT and last.changes == diff:
            return

        ExcelCleaner._log(
            batch,
            patient,
            row_number,
            ChangeKind.CONFLICT,
            diff,
            file_hash,
            reason,
        )
