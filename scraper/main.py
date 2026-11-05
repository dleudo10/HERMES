from .browser.browser_manager import BrowserManager
from .services.download_service import DownloadService
from .services.batch_service import BatchImportService
from asgiref.sync import sync_to_async

async def main(file):
    # 1. Tratamiento de Datos - EXCEL
    batch = await sync_to_async(BatchImportService.execute, thread_sensitive=True)(file)

    print(f"ID LOTE: {batch.code}")
    print(f"ITEMS TOTAL: {batch.total_rows}")
    print(f"ITEMS VALIDOS: {batch.valid_rows}")
    print(f"ITEMS INVALIDOS: {batch.invalid_rows}")
    print(f"ESTADO {batch.status}")

    # 2. VERIFICAR SI HAY REGISTROS PARA PROCESAR
    if batch.status != "READY":
        print("El lote no tiene registros disponibles para procesar.")
        return []

    browser_manager = BrowserManager(headless=False)

    try:

        # 2. Creacion de HC
        page = await browser_manager.start()
        
        # 4. INICIALIZAR SERVICIO DE DESCARGA
        service = DownloadService(page)

        # 5. ABRIR HOSVITAL Y AUTENTICAR
        await service.extractor.open_system()

        await service.extractor.login(
            username='TIC',
            password='TIC432*',
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
                "error": result["error"],
            })

        return results
    finally:
        await browser_manager.close()
