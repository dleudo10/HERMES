from azure.identity import DeviceCodeCredential
from msgraph import GraphServiceClient
from .config import CLIENT_ID, TENANT_ID, SCOPES
from .config import MailConfig

class MicrosoftGraphService:
    def __init__(self):

        self.credential = DeviceCodeCredential(
            client_id=CLIENT_ID,
            tenant_id=TENANT_ID,
        )

        self.client = GraphServiceClient(
            credentials=self.credential,
            scopes=SCOPES,
        )
        
    async def get_authenticated_user(self):
        user = await self.client.me.get()
        return user
    
    def close(self):
        self.credential.close()
    
    @classmethod
    def from_config(cls, config: MailConfig) -> "GraphMailer":
        common = dict(max_retries=config.max_retries, timeout=config.timeout)

        if config.dry_run:
            return cls(config.sender or "dry-run@local", lambda: "", dry_run=True, **common)

        config.validate()

        import msal

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