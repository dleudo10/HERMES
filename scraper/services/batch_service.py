from pathlib import Path

from ..data_structure.excel_cleaner import ExcelCleaner
from ..models import Batch


class BatchImportService:

    ESTADOS = [
        "ATENDIDA",
        "FACTURADA",
    ]

    ESPECIALIDADES = [
        "ANESTESIOLOGIA Y REANIMACION",
        "CIRUGIA GENERAL",
        "CIRUGIA MAXILOFACIAL",
        "CIRUGIA PLASTICA Y ESTETICA",
        "CIRUGIA VASCULAR Y ANGIOLOGIA",
        "GINECOLOGIA Y OBSTETRICIA",
        "NEUROCIRUGIA",
        "ORTOPEDIA Y TRAUMATOLOGIA",
        "UROLOGIA",
    ]

    @staticmethod
    def build_cleaner(file) -> ExcelCleaner:
        return ExcelCleaner(
            file=file,
            estados=BatchImportService.ESTADOS,
            especialidades=BatchImportService.ESPECIALIDADES,
            skip_if_bad_email=True,
        )

    @staticmethod
    def execute(file, resync: bool = True):
        existing_batch = BatchImportService.get_existing_batch(file)
        cleaner = BatchImportService.build_cleaner(file)

        # Archivo nuevo: importación normal.
        if existing_batch is None:
            return cleaner.execute()

        # Archivo ya importado: se vuelve a leer y a validar todo.
        if resync:
            existing_batch.sync_stats = cleaner.sync(existing_batch)

        return existing_batch

    @staticmethod
    def get_existing_batch(file) -> Batch | None:
        filename = Path(getattr(file, "name", file)).name

        return Batch.objects.filter(original_filename=filename).first()