from django.core.management.base import BaseCommand, CommandError

from ...models import Batch
from ...main import send_batch_mail


class Command(BaseCommand):
    help = "Envía (o reintenta) los correos de un lote ya descargado, sin abrir el navegador"

    def add_arguments(self, parser):
        parser.add_argument(
            "batch_code",
            type=str,
            help="Código del lote, por ejemplo HER-0123456789AB",
        )

    def handle(self, *args, **options):
        batch_code = options["batch_code"]

        if not Batch.objects.filter(code=batch_code).exists():
            raise CommandError(f"No existe el lote: {batch_code}")

        send_batch_mail(batch_code)