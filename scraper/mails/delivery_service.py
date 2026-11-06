from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .config import MailConfig
from .graph_mailer import GraphMailer
from .pdf_protector import PdfProtector
from .renderer import MessageRenderer


class DeliveryService:

    def __init__(self, mailer: GraphMailer, renderer: MessageRenderer, protector: PdfProtector):
        self.mailer = mailer
        self.renderer = renderer
        self.protector = protector

    @classmethod
    def from_config(cls, config: MailConfig) -> "DeliveryService":
        return cls(
            mailer=GraphMailer.from_config(config),
            renderer=MessageRenderer(config),
            protector=PdfProtector(enabled=config.encrypt_pdfs),
        )

    @staticmethod
    def _password(document) -> str:
        """Pandas puede entregar 1017123456.0 si la columna se leyó como número."""
        value = str(document).strip()
        return value[:-2] if value.endswith(".0") else value

    def send_patients(self, patients: list, download_results: list) -> list:
        results = []

        for patient, download in zip(patients, download_results):
            started_at = datetime.now()

            result = {
                "index": download["index"],
                "status": "FAILED",
                "request_id": None,
                "attachments": 0,
                "error": None,
            }

            try:
                if download["status"] != "DOWNLOADED":
                    result["status"] = "SKIPPED"
                    result["error"] = "La descarga no se completó"
                    continue

                files = [Path(f) for f in download["file_path"]]
                missing = [f for f in files if not f.exists()]
                if not files or missing:
                    raise Exception(f"Faltan archivos en disco: {missing}")

                email = (patient.get("email") or "").strip()
                if not email:
                    raise Exception("El paciente no tiene correo")

                password = self._password(patient["document"])
                fecha = datetime.strptime(patient["date"], "%d/%m/%Y").date()
                subject, body = self.renderer.render(patient.get("name", ""), fecha)

                # Si falla el cifrado se lanza excepción: nunca se envía un PDF sin proteger.
                attachments = [
                    (f.name, self.protector.protect(f.read_bytes(), password))
                    for f in files
                ]

                send = self.mailer.send(email, subject, body, attachments)

                result["attachments"] = len(attachments)
                result["request_id"] = send.request_id
                result["error"] = send.error or None

                if send.ok:
                    result["status"] = "DRY_RUN" if send.dry_run else "SENT"
                elif send.uncertain:
                    result["status"] = "UNCERTAIN"
                else:
                    result["status"] = "FAILED"

            except Exception as error:
                result["status"] = "FAILED"
                result["error"] = str(error)
                logging.exception("Error enviando paciente %s", download["index"])

            finally:
                result["duration_seconds"] = (datetime.now() - started_at).total_seconds()
                results.append(result)

        return results