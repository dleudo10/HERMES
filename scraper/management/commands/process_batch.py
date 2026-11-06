import asyncio
import os
from django.core.management.base import BaseCommand, CommandError
from ...main import main
from ...mails.config import MailConfig
from ...mails.delivery_service import DeliveryService


class Command(BaseCommand):
    help = "Procesa el lote de historias clínicas"
    
    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            type=str,
            help="Ruta del archivo Excel"
        )
    
    def handle(self, *args, **options):
        file = options["file"]

        # Validar que el archivo exista
        if not os.path.isfile(file):
            raise CommandError(
                f"No se encontró el archivo: {file}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Archivo encontrado: {file}"
            )
        )

        # Ejecutar el procesamiento
        asyncio.run(main(file))