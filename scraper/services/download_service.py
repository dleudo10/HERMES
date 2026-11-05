from pathlib import Path
import re
from datetime import datetime
import logging

from asgiref.sync import sync_to_async

from ..browser.clinical_extractor import ClinicalExtractor
from .batch_processing_service import BatchProcessingService

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
        Consulta un lote, obtiene sus pacientes válidos
        y ejecuta las descargas con Playwright.
        """
        # 1. Consultar y reservar el lote.
        batch_data = await sync_to_async(
            BatchProcessingService.prepare_batch,
            thread_sensitive=True,
        )(batch_code)
        
        batch_id = batch_data["batch_id"]
        patients_data = batch_data["patients"]

        print(f"\nINICIANDO LOTE: {batch_code}")
        print(f"PACIENTES VÁLIDOS: {batch_data['total']}")
        
        # 2. Transformar los registros al formato de Playwright.
        patients = []

        for patient in patients_data:

            patients.append({
                "batch_patient_id": patient["id"],
                "row_number": patient["row_number"],
                "document": patient["identificacion"].strip(),
                "date": self.format_date(patient["fecha_cita"]),
                "numero_ingreso": patient["ingreso"].strip(),
                "type_document": patient["tdoc"].strip(),
                "numero_folio": patient["cit_folio"].strip(),
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
            

    async def process_patients(self, patients: list, output_dir: Path = None,):

        results = []
        output_dir = output_dir or self.download_dir

        for index, patient in enumerate(patients, start=1):

            document = patient["document"]
            date = patient["date"]
            numero_ingreso = patient["numero_ingreso"]
            type_document = patient["type_document"]
            numero_folio = patient["numero_folio"]

            print(f"Procesando paciente {index}/{len(patients)}")

            started_at = datetime.now()

            result = {
                "batch_patient_id": patient.get("batch_patient_id"),
                "row_number": patient.get("row_number"),
                "document": document,
                "status": "FAILED",
                "started_at": started_at,
                "finished_at": None,
                "file_path": [],
                "error": None,
            }

            try:

                files = await self.extractor.search_patient(
                    document=document,
                    date=date,
                    numero_ingreso=numero_ingreso,
                    type_document=type_document,
                    numero_folio=numero_folio,
                    output_dir=output_dir,
                )

                missing = [f for f in files if not f.exists()]

                if not files or missing:
                    raise Exception(
                        f"Archivos no encontrados tras la descarga: {missing}"
                    )

                result["status"] = "DOWNLOADED"
                result["file_path"] = [str(f) for f in files]

            except Exception as error:

                result["status"] = "FAILED"
                result["error"] = str(error)

                logger.exception(
                    "Error procesando paciente %s, fila %s",
                    document,
                    patient.get("row_number"),
                )

            finally:

                result["finished_at"] = datetime.now()

                result["duration_seconds"] = (
                    result["finished_at"] - started_at
                ).total_seconds()

                results.append(result)

        return results

    @staticmethod
    def format_date(value: str) -> str:
        from datetime import datetime

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
    
    @staticmethod
    def get_patient_directory(self, batch_code: str, document: str) -> Path:
        safe_document = re.sub(r"[^a-zA-Z0-9_-]", "", document)

        patient_dir = (
            self.DOWNLOAD_ROOT
            / batch_code
            / safe_document
        )

        patient_dir.mkdir(parents=True, exist_ok=True)

        return patient_dir
