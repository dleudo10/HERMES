
from ..data_structure.excel_cleaner import ExcelCleaner
from pathlib import Path
from ..models import Batch


class BatchImportService:

    @staticmethod
    def execute(file):
        existing_batch = (
            BatchImportService.get_existing_batch(file)
        )

        if existing_batch:
            return existing_batch
        

        cleaner = ExcelCleaner(
            file=file,

            estados=[
                "ATENDIDA",
                "FACTURADA",
            ],

            especialidades=[
                "ANESTESIOLOGIA Y REANIMACION",
                "CIRUGIA GENERAL",
                "CIRUGIA MAXILOFACIAL",
                "CIRUGIA PLASTICA Y ESTETICA",
                "CIRUGIA VASCULAR Y ANGIOLOGIA",
                "GINECOLOGIA Y OBSTETRICIA",
                "NEUROCIRUGIA",
                "ORTOPEDIA Y TRAUMATOLOGIA",
                "UROLOGIA",
            ],

            skip_if_bad_email=True,
        )

        return cleaner.execute()
    
    @staticmethod
    def get_existing_batch(file) -> Batch | None:
        filename = Path(getattr(file, "name", file)).name
        
        return Batch.objects.filter(
            original_filename=filename
        ).first()
