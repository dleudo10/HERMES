from azure.identity import DeviceCodeCredential
from msgraph import GraphServiceClient
from .graph_config import CLIENT_ID, TENANT_ID, SCOPES

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
