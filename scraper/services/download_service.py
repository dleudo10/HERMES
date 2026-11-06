from pathlib import Path
import re
from datetime import datetime
import logging

from asgiref.sync import sync_to_async

from ..browser.clinical_extractor import ClinicalExtractor, PatientNotFoundError
from ..models import DocumentStatus, ExtractionStatus
from .batch_processing_service import BatchProcessingService
from .extraction import ExtractionService

logger = logging.getLogger(__name__)


class DownloadService:
    DOWNLOAD_ROOT = Path("data/downloads")

    def __init__(self, page):

        self.extractor = ClinicalExtractor(page)

        self.download_dir = self.DOWNLOAD_ROOT
        self.download_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # --------------------------------------------------
    # PROCESAR UN LOTE
    # --------------------------------------------------
    async def process_batch(self, batch_code: str):
        """
        Reserva el lote, procesa sus pacientes pendientes y lo finaliza.
        Estructura de salida: data/downloads/<LOTE>/<DOCUMENTO>/archivos.pdf
        """
        # 1. Consultar y reservar el lote.
        batch_data = await sync_to_async(
            BatchProcessingService.prepare_batch,
            thread_sensitive=True,
        )(batch_code)

        batch_id = batch_data["batch_id"]
        patients_data = batch_data["patients"]

        if not patients_data:
            print(
                f"\nEl lote {batch_code} no tiene pacientes pendientes "
                "(todos completados o con los intentos agotados)."
            )
            return []

        print(f"\nINICIANDO LOTE: {batch_code}")
        print(f"PACIENTES A PROCESAR: {batch_data['total']}")

        # 2. Transformar los registros al formato de Playwright.
        patients = []

        for patient in patients_data:

            patients.append({
                "batch_patient_id": patient["id"],
                "extraction_id": patient["extraction_id"],
                "row_number": patient["row_number"],
                "document": patient["identificacion"].strip(),
                "date": self.format_date(patient["fecha_cita"]),
                "numero_ingreso": self.clean_number(patient["ingreso"]),
                "type_document": patient["tdoc"].strip(),
                "numero_folio": self.clean_number(patient["cit_folio"]),
            })

        # 3. Crear carpeta exclusiva para el lote.
        output_dir = self.download_dir / batch_code
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:

            # 4. Procesar pacientes.
            results = await self.process_patients(
                patients=patients,
                output_dir=output_dir,
            )

            has_errors = any(
                result["status"] != "DOWNLOADED"
                for result in results
            )

            # 5. Finalizar lote.
            await sync_to_async(
                BatchProcessingService.finish_batch,
                thread_sensitive=True,
            )(
                batch_id=batch_id,
                has_errors=has_errors,
            )

            print(f"\nLOTE FINALIZADO: {batch_code}")

            return results

        except Exception:

            logger.exception(
                "Error general procesando el lote %s",
                batch_code,
            )

            await sync_to_async(
                BatchProcessingService.fail_batch,
                thread_sensitive=True,
            )(batch_id)

            raise

    # --------------------------------------------------
    # PROCESAR PACIENTES
    # --------------------------------------------------
    async def process_patients(self, patients: list, output_dir: Path = None):

        results = []
        output_dir = output_dir or self.download_dir

        for index, patient in enumerate(patients, start=1):

            document = patient["document"]
            extraction_id = patient["extraction_id"]

            print(f"Procesando paciente {index}/{len(patients)}")

            started_at = datetime.now()

            result = {
                "batch_patient_id": patient.get("batch_patient_id"),
                "extraction_id": extraction_id,
                "row_number": patient.get("row_number"),
                "document": document,
                "status": "FAILED",
                "started_at": started_at,
                "finished_at": None,
                "file_path": [],
                "documents": [],
                "error": None,
            }

            patient_dir = None

            try:

                # 1. Registrar el intento (suma attempts y valida el máximo).
                await sync_to_async(
                    ExtractionService.start,
                    thread_sensitive=True,
                )(extraction_id)

                # 2. Carpeta del paciente: <LOTE>/<DOCUMENTO>/
                patient_dir = self.get_patient_directory(output_dir, document)

                # 3. Descargar los documentos en el navegador.
                try:
                    doc_results = await self.extractor.search_patient(
                        document=document,
                        date=patient["date"],
                        numero_ingreso=patient["numero_ingreso"],
                        type_document=patient["type_document"],
                        numero_folio=patient["numero_folio"],
                        output_dir=patient_dir,
                    )

                except PatientNotFoundError as error:

                    extraction = await sync_to_async(
                        ExtractionService.fail,
                        thread_sensitive=True,
                    )(extraction_id, "PATIENT_NOT_FOUND", str(error))

                except Exception as error:

                    logger.exception(
                        "Error procesando paciente %s, fila %s",
                        document,
                        patient.get("row_number"),
                    )

                    extraction = await sync_to_async(
                        ExtractionService.fail,
                        thread_sensitive=True,
                    )(
                        extraction_id,
                        "UNEXPECTED_ERROR",
                        f"{type(error).__name__}: {error}",
                    )

                else:

                    # 4. Guardar Documents y decidir el estado final.
                    extraction = await sync_to_async(
                        ExtractionService.finish,
                        thread_sensitive=True,
                    )(extraction_id, doc_results)

                    result["documents"] = [
                        {
                            "type": r.type_document,
                            "status": str(r.status),
                            "files": [str(f) for f in r.files],
                            "message": r.message,
                        }
                        for r in doc_results
                    ]

                    result["file_path"] = [
                        str(file)
                        for r in doc_results
                        if r.status == DocumentStatus.DOWNLOADED
                        for file in r.files
                    ]

                if extraction.status == ExtractionStatus.COMPLETED:
                    result["status"] = "DOWNLOADED"

                result["error"] = extraction.error_message

            except Exception as error:

                # Falló algo fuera del navegador (p. ej. no se pudo iniciar
                # el intento o se agotaron los intentos).
                result["status"] = "FAILED"
                result["error"] = str(error)

                logger.exception(
                    "Error gestionando la extracción del paciente %s, fila %s",
                    document,
                    patient.get("row_number"),
                )

            finally:

                # No dejar carpetas vacías de pacientes sin documentos.
                if patient_dir is not None:
                    try:
                        patient_dir.rmdir()
                    except OSError:
                        pass

                result["finished_at"] = datetime.now()

                result["duration_seconds"] = (
                    result["finished_at"] - started_at
                ).total_seconds()

                results.append(result)

        return results

    # --------------------------------------------------
    # UTILIDADES
    # --------------------------------------------------
    @staticmethod
    def get_patient_directory(output_dir: Path, document: str) -> Path:
        """
        Carpeta del paciente dentro del lote: <output_dir>/<documento>/
        """
        safe_document = re.sub(r"[^a-zA-Z0-9_-]", "", str(document))

        if not safe_document:
            raise ValueError(f"Documento no válido para crear carpeta: {document!r}")

        patient_dir = Path(output_dir) / safe_document
        patient_dir.mkdir(parents=True, exist_ok=True)

        return patient_dir

    @staticmethod
    def clean_number(value) -> str:
        """
        Convierte valores como '12345.0' en '12345'.
        """
        value = str(value).strip()

        if re.fullmatch(r"\d+\.0+", value):
            value = value.split(".")[0]

        return value

    @staticmethod
    def format_date(value: str) -> str:

        value = str(value).strip()

        formats = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.strftime("%d/%m/%Y")
            except ValueError:
                continue

        raise ValueError(f"Formato de fecha no válido: {value}")