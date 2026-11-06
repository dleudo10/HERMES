"""Envío por Microsoft Graph (client credentials). Un correo por ingreso, PDFs adjuntos uno a uno."""
from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from .config import MailConfig

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024  # límite de adjuntos en línea de sendMail (suma de todos)

# Imágenes que usa la plantilla con <img src="cid:...">: cid -> nombre de archivo.
ASSETS_DIR = Path(__file__).parent / "assets"
INLINE_IMAGES = {"logo": "logo.png", "icon": "icon.png"}


@dataclass
class SendResult:
    ok: bool
    uncertain: bool = False        # puede haberse enviado: NO reintentar automáticamente
    status_code: int | None = None
    request_id: str | None = None
    error: str = ""
    dry_run: bool = False


def load_inline_images() -> list[tuple[str, str, bytes]]:
    """Devuelve [(content_id, nombre_archivo, bytes)] de las imágenes que existan."""
    images = []
    for cid, filename in INLINE_IMAGES.items():
        path = ASSETS_DIR / filename
        if path.is_file():
            images.append((cid, filename, path.read_bytes()))
        else:
            logger.warning("No se encontró la imagen %s: el correo saldrá sin ella", path)
    return images


class GraphMailer:
    def __init__(self, sender: str, token_provider: Callable[[], str], session: requests.Session | None = None,
                 dry_run: bool = True, max_retries: int = 4, timeout: float = 60, sleep=time.sleep,
                 inline_images: list[tuple[str, str, bytes]] | None = None):
        self.sender = sender
        self.token_provider = token_provider
        self.session = session or requests.Session()
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.timeout = timeout
        self._sleep = sleep
        self.inline_images = inline_images or []

    def send(self, to: str, subject: str, html_body: str, attachments: list[tuple[str, bytes]]) -> SendResult:
        total = sum(len(data) for _, data in attachments) + sum(len(d) for _, _, d in self.inline_images)
        if total > MAX_ATTACHMENT_BYTES:
            return SendResult(False, error=f"adjuntos_superan_3MB:{total}")
        if self.dry_run:
            return SendResult(True, dry_run=True)

        file_attachments = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": name,
                "contentType": "application/pdf",
                "contentBytes": base64.b64encode(data).decode("ascii"),
            }
            for name, data in attachments
        ]
        # Imágenes incrustadas: se referencian en el HTML como <img src="cid:logo">.
        file_attachments += [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": "image/png",
                "contentBytes": base64.b64encode(data).decode("ascii"),
                "isInline": True,
                "contentId": cid,
            }
            for cid, filename, data in self.inline_images
        ]

        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": html_body},
                "toRecipients": [{"emailAddress": {"address": to}}],
                "attachments": file_attachments,
            },
            "saveToSentItems": True,
        }
        url = f"{GRAPH}/users/{self.sender}/sendMail"
        refreshed = False
        attempt = 0
        while True:
            try:
                headers = {"Authorization": f"Bearer {self.token_provider()}"}
                resp = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
            except requests.exceptions.ConnectTimeout as e:
                # No llegó a conectar: la petición no fue procesada, es seguro reintentar.
                if attempt >= self.max_retries:
                    return SendResult(False, error=f"sin_conexion:{type(e).__name__}")
                attempt += 1
                self._sleep(min(60, 2 ** attempt * 2))
                continue
            except requests.exceptions.RequestException as e:
                return SendResult(False, uncertain=True, error=f"red_incierta:{type(e).__name__}")

            rid = resp.headers.get("request-id") or resp.headers.get("client-request-id")
            code = resp.status_code
            if code == 202:
                return SendResult(True, status_code=code, request_id=rid)
            if code == 401 and not refreshed:
                refreshed = True
                continue
            if code in (429, 503):
                if attempt >= self.max_retries:
                    return SendResult(False, status_code=code, request_id=rid, error=f"limitado:{code}")
                wait = _retry_after(resp) or min(120, 2 ** attempt * 5)
                attempt += 1
                self._sleep(wait)
                continue
            if code >= 500:
                return SendResult(False, uncertain=True, status_code=code, request_id=rid,
                                  error=f"servidor_incierto:{code}")
            return SendResult(False, status_code=code, request_id=rid, error=_graph_error(resp))

    @classmethod
    def from_config(cls, config: MailConfig) -> "GraphMailer":
        common = dict(max_retries=config.max_retries, timeout=config.timeout,
                      inline_images=load_inline_images())

        if config.dry_run:
            return cls(config.sender or "dry-run@local", lambda: "", dry_run=True, **common)

        config.validate()

        import msal  # import diferido: solo se necesita en modo real

        app = msal.ConfidentialClientApplication(
            config.client_id,
            authority=f"https://login.microsoftonline.com/{config.tenant_id}",
            client_credential=config.client_secret,
        )

        def provider() -> str:
            r = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            if "access_token" not in r:
                raise RuntimeError(f"No se obtuvo token de Graph: {r.get('error')}: {r.get('error_description')}")
            return r["access_token"]

        return cls(config.sender, provider, dry_run=False, **common)


def _retry_after(resp: requests.Response) -> float | None:
    v = resp.headers.get("Retry-After")
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _graph_error(resp: requests.Response) -> str:
    try:
        err = resp.json().get("error", {})
        return f"{resp.status_code}:{err.get('code', '')}:{err.get('message', '')}"[:500]
    except Exception:  # noqa: BLE001
        return f"{resp.status_code}:{resp.text[:200]}"