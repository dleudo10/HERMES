from .browser.browser_manager import BrowserManager
from .services.download_service import DownloadService
from .services.batch_service import BatchImportService
from .services.batch_processing_service import BatchProcessingService
from asgiref.sync import sync_to_async
import os
from dotenv import load_dotenv

load_dotenv()


async def main(file):
    # 1. Tratamiento de Datos - EXCEL
    batch = await sync_to_async(BatchImportService.execute, thread_sensitive=True)(file)

    print(f"ID LOTE: {batch.code}")
    print(f"ITEMS TOTAL: {batch.total_rows}")
    print(f"ITEMS VALIDOS: {batch.valid_rows}")
    print(f"ITEMS INVALIDOS: {batch.invalid_rows}")
    print(f"ESTADO {batch.status}")

    # 2. VERIFICAR SI HAY REGISTROS PARA PROCESAR
    if batch.status not in BatchProcessingService.PROCESSABLE_STATUSES:
        print(
            f"El lote no se puede procesar. Estado actual: {batch.status}"
        )
        return []

    username = os.getenv("HOSVITAL_USER")
    password = os.getenv("HOSVITAL_PASSWORD")

    if not username or not password:
        raise ValueError(
            "Faltan HOSVITAL_USER y HOSVITAL_PASSWORD en el archivo .env"
        )

    browser_manager = BrowserManager(headless=False)

    try:

        # 2. Creacion de HC
        page = await browser_manager.start()

        # 4. INICIALIZAR SERVICIO DE DESCARGA
        service = DownloadService(page)

        # 5. ABRIR HOSVITAL Y AUTENTICAR
        await service.extractor.open_system()

        await service.extractor.login(
            username=username,
            password=password,
        )

        # 6. PROCESAR LOTE
        results = await service.process_batch(batch.code)

        # 7. MOSTRAR RESULTADOS
        print("\nRESULTADOS DEL PROCESAMIENTO")

        for result in results:

            print({
                "fila": result["row_number"],
                "documento": result["document"],
                "estado": result["status"],
                "archivos": result["file_path"],
                "documentos": [
                    (d["type"], d["status"], d["message"])
                    for d in result.get("documents", [])
                ],
                "error": result["error"],
            })

        return results
    finally:
        await browser_manager.close()