from .browser.browser_manager import BrowserManager
from .services.download_service import DownloadService
from .services.batch_service import BatchImportService
from .services.batch_processing_service import BatchProcessingService
from .mails.config import MailConfig
from .mails.delivery_service import DeliveryService
from asgiref.sync import sync_to_async
import os
from dotenv import load_dotenv

load_dotenv()


async def main(file, send_mail: bool = True):
    # 1. Tratamiento de Datos - EXCEL
    batch = await sync_to_async(BatchImportService.execute, thread_sensitive=True)(file)

    print(f"ID LOTE: {batch.code}")
    print(f"ITEMS TOTAL: {batch.total_rows}")
    print(f"ITEMS VALIDOS: {batch.valid_rows}")
    print(f"ITEMS INVALIDOS: {batch.invalid_rows}")
    print(f"ESTADO {batch.status}")

    # 2. DESCARGA DE DOCUMENTOS (solo si el lote tiene algo por descargar)
    results = []

    if batch.status in BatchProcessingService.PROCESSABLE_STATUSES:
        results = await download_batch(batch)
    else:
        print(f"El lote no requiere descarga. Estado actual: {batch.status}")

    # 3. ENVÍO DE CORREOS (con el navegador ya cerrado)
    if send_mail:
        await sync_to_async(send_batch_mail, thread_sensitive=True)(batch.code)

    return results


async def download_batch(batch):
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


def send_batch_mail(batch_code: str) -> list:
    """
    Envía los correos del lote. Es síncrona (ORM + requests), por eso se
    invoca desde main() con sync_to_async.
    """
    config = MailConfig.from_env()

    if config.dry_run:
        print("\nCORREOS: MODO PRUEBA (HERMES_MAIL_DRY_RUN=1). No se envía nada.")
    elif config.test_recipient:
        print(f"\nCORREOS: MODO PRUEBA. Todo se envía a {config.test_recipient}")
    else:
        print("\nCORREOS: MODO REAL. Se envía a los correos de los pacientes.")

    service = DeliveryService.from_config(config)
    results = service.send_batch(batch_code)

    print(f"\nRESULTADOS DEL ENVÍO ({len(results)} correos)")

    for result in results:
        print({
            "fila": result["row_number"],
            "documento": result["document"],
            "correo": result["email"],
            "estado": result["status"],
            "adjuntos": result["attachments"],
            "error": result["error"],
        })

    return results