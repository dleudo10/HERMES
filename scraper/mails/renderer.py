from __future__ import annotations

import html
from datetime import date

from .config import MailConfig


class MessageRenderer:

    def __init__(self, config: MailConfig):
        self.config = config

    def render(self, nombre: str, fecha: date) -> tuple[str, str]:
        fecha_str = fecha.strftime("%d/%m/%Y")

        subject = self.config.subject.format(fecha=fecha_str)
        body = self.config.body_html.format(
            nombre=html.escape(nombre.title() if nombre else "paciente"),
            fecha=fecha_str,
        )
        return subject, body