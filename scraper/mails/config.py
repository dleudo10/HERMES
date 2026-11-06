from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MailConfig:
    sender: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    dry_run: bool = True
    encrypt_pdfs: bool = True
    max_retries: int = 4
    timeout: float = 60
    delay_seconds: float = 2.0      # pausa entre correos (Exchange Online ~30 correos/min por buzón)
    test_recipient: str = ""       # si se define, TODO se envía a este correo y no se guarda como enviado
    subject: str = "Historia clínica - {fecha}"
    body_html: str = (
        '<meta name="color-scheme" content="light dark">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;">Sus documentos clínicos están adjuntos a este correo.</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#e9eef3" style="background-color:#e9eef3;">'
        '<tr><td align="center" style="padding:24px 12px;">'
            '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff" style="width:100%;max-width:600px;background-color:#ffffff;border-radius:12px;">'
            '<tr>'
                '<td style="padding:28px 28px 8px 28px;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
                    '<td align="left" valign="middle"><img src="cid:logo" alt="Clínica Antioquia" height="52" style="display:block;height:52px;width:auto;border:0;"></td>'
                    '<td align="right" valign="middle"><img src="cid:icon" alt="" height="40" style="display:block;height:40px;width:auto;border:0;"></td>'
                '</tr></table>'
                '</td>'
            '</tr>'
            '<tr>'
                '<td style="padding:20px 28px 0 28px;font-family:Arial,Helvetica,sans-serif;">'
                '<h1 style="margin:0 0 14px 0;font-size:26px;line-height:32px;font-weight:bold;color:#003085;">Tus documentos clínicos están disponibles</h1>'
                '<p style="margin:0 0 12px 0;font-size:15px;line-height:24px;color:#1d2b38;">Cordial saludo, {nombre}.</p>'
                '<p style="margin:0 0 12px 0;font-size:15px;line-height:24px;color:#1d2b38;">Adjuntamos los documentos clínicos de su atención del <b>{fecha}</b>.</p>'
                '</td>'
            '</tr>'
            '<tr>'
                '<td style="padding:8px 28px 8px 28px;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f1f7fc" style="background-color:#f1f7fc;border:1px solid #d6e1ec;border-radius:10px;">'
                    '<tr><td style="padding:16px 18px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:22px;color:#003085;">'
                    '<b>Archivos protegidos con contraseña.</b><br>'
                    '<span style="color:#1d2b38;">Use su <b>número de documento de identidad</b> (sin puntos ni espacios) para abrirlos.</span>'
                    '</td></tr>'
                '</table>'
                '</td>'
            '</tr>'
            '<tr>'
                '<td style="padding:16px 28px 8px 28px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:22px;color:#1d2b38;">'
                'En Clínica Antioquia S.A. estamos comprometidos con el medio ambiente, por eso recuerda imprimir solo lo necesario para ayudar a cuidar nuestro planeta.'
                '</td>'
            '</tr>'
            '<tr>'
                '<td style="padding:20px 28px 0 28px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td height="1" bgcolor="#d6e1ec" style="height:1px;line-height:1px;font-size:1px;background-color:#d6e1ec;">&nbsp;</td></tr></table></td>'
            '</tr>'
            '<tr>'
                '<td align="center" style="padding:20px 28px 28px 28px;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;color:#4d6372;">'
                '<p style="margin:0 0 6px 0;font-size:13px;font-weight:bold;color:#003085;">Este mensaje se generó automáticamente; por favor no responda a este correo.</p>'
                '<p style="margin:0;"><i style="color:#45a1e6;font-weight:bold;">Juntos construimos tu bienestar</i><br>Clínica Antioquia S.A.</p>'
                '</td>'
            '</tr>'
            '</table>'
        '</td></tr>'
        '</table>'
    )

    @classmethod
    def from_env(cls) -> "MailConfig":
        return cls(
            sender=os.environ.get("HERMES_MAIL_SENDER", ""),
            tenant_id=os.environ.get("GRAPH_TENANT_ID", ""),
            client_id=os.environ.get("GRAPH_CLIENT_ID", ""),
            client_secret=os.environ.get("GRAPH_CLIENT_SECRET", ""),
            dry_run=os.environ.get("HERMES_MAIL_DRY_RUN", "1") == "1",
            encrypt_pdfs=os.environ.get("HERMES_ENCRYPT_PDFS", "1") == "1",
            delay_seconds=float(os.environ.get("HERMES_MAIL_DELAY", "2")),
            test_recipient=os.environ.get("HERMES_MAIL_TEST_TO", "").strip(),
        )

    def validate(self) -> None:
        """Solo se exige en modo real."""
        missing = [
            name for name, value in {
                "HERMES_MAIL_SENDER": self.sender,
                "GRAPH_TENANT_ID": self.tenant_id,
                "GRAPH_CLIENT_ID": self.client_id,
                "GRAPH_CLIENT_SECRET": self.client_secret,
            }.items() if not value
        ]
        if missing:
            raise RuntimeError(f"Faltan variables de entorno: {', '.join(missing)}")