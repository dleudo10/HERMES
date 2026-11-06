import asyncio
import os
from django.core.management.base import BaseCommand, CommandError
from ...main import main


class Command(BaseCommand):
    help = "Procesa el lote de historias clínicas: descarga los documentos y envía los correos"

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            type=str,
            help="Ruta del archivo Excel"
        )
        parser.add_argument(
            "--no-mail",
            action="store_true",
            help="Solo descarga los documentos, sin enviar correos",
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
        asyncio.run(main(file, send_mail=not options["no_mail"]))