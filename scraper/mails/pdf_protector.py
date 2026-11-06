from __future__ import annotations

import secrets
from io import BytesIO

from pypdf import PdfReader, PdfWriter


class PdfProtector:
    """Cifra PDFs en memoria. Los originales en disco no se modifican."""

    def __init__(self, enabled: bool = True, algorithm: str = "AES-256"):
        self.enabled = enabled
        self.algorithm = algorithm

    def protect(self, data: bytes, password: str) -> bytes:
        if not self.enabled:
            return data

        if not password:
            raise ValueError("Se requiere una contraseña para proteger el PDF")

        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("El PDF ya está cifrado")

        writer = PdfWriter(clone_from=reader)
        writer.encrypt(
            user_password=password,                     # la que usa el paciente
            owner_password=secrets.token_urlsafe(16),   # aleatoria: nadie edita permisos
            algorithm=self.algorithm,
        )

        output = BytesIO()
        writer.write(output)
        return output.getvalue()