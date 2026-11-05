import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("MSGRAPH_CLIENT_ID")
TENANT_ID = os.getenv("MSGRAPH_TENANT_ID")

if not CLIENT_ID or not TENANT_ID:
    raise ValueError(
        "Faltan las variables de configuración de Microsoft Graph"
    )

SCOPES = [
    "User.Read",
    "Mail.Send",
]