from playwright.async_api import async_playwright

class BrowserManager:
    def __init__(self, headless=False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
    async def start(self):
        self.playwright = await async_playwright().start()
        
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless
        )
        
        self.context = await self.browser.new_context(
            accept_downloads=True
        )

        self.page = await self.context.new_page()

        return self.page
    
    async def close(self):
        if self.context:
            await self.context.close()
            
        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()