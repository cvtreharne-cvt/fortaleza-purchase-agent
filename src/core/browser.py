"""Playwright browser harness for managing browser lifecycle."""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from .config import get_settings
from .logging import get_logger

logger = get_logger(__name__)


class BrowserManager:
    """Manages Playwright browser lifecycle."""

    def __init__(self):
        """Initialize browser manager."""
        self.settings = get_settings()
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._start_lock = asyncio.Lock()
        
    async def start(self) -> None:
        """Start Playwright and launch browser."""
        async with self._start_lock:
            if self.browser:
                logger.warning("Browser already started")
                return

            logger.info("Starting Playwright browser", headless=self.settings.headless)

            # Start Playwright
            self.playwright = await async_playwright().start()

            # Launch Chromium
            self.browser = await self.playwright.chromium.launch(
                headless=self.settings.headless,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                ]
            )

            # Create context with reasonable viewport and user agent
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                java_script_enabled=True,
                accept_downloads=False,
            )

            # Set default timeouts
            self.context.set_default_timeout(self.settings.browser_timeout)
            self.context.set_default_navigation_timeout(self.settings.navigation_timeout)

            logger.info("Browser started successfully")
    
    async def stop(self) -> None:
        """Stop browser and cleanup resources."""
        if not self.browser:
            logger.warning("Browser not running")
            return
        
        logger.info("Stopping browser")
        
        if self.context:
            await self.context.close()
            self.context = None
        
        if self.browser:
            await self.browser.close()
            self.browser = None
        
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        
        logger.info("Browser stopped")
    
    async def new_page(self) -> Page:
        """
        Create a new page in the browser context.
        
        Returns:
            New page instance
            
        Raises:
            RuntimeError: If browser not started
        """
        if not self.context:
            raise RuntimeError("Browser not started. Call start() first.")
        
        page = await self.context.new_page()
        logger.debug("Created new page")
        return page
    
    async def get_current_page(self) -> Optional[Page]:
        """
        Get the current active page.
        
        Returns:
            Current page or None if no pages exist
        """
        if not self.context:
            return None
        
        pages = self.context.pages
        return pages[0] if pages else None


# Global instance
_browser_manager: Optional[BrowserManager] = None


def get_browser_manager() -> BrowserManager:
    """Get or create the global BrowserManager instance."""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager


@asynccontextmanager
async def managed_browser():
    """
    Context manager for browser lifecycle.
    
    Usage:
        async with managed_browser():
            browser = get_browser_manager()
            page = await browser.new_page()
            # ... use page
    """
    browser = get_browser_manager()
    try:
        await browser.start()
        yield browser
    finally:
        await browser.stop()
