"""Debug script to test login functionality."""

import asyncio
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.login import login_to_account

setup_logging()


async def debug_login():
    """Debug login functionality."""
    print("\n🔐 Testing Login Functionality")
    print("=" * 60)
    
    async with managed_browser():
        browser = get_browser_manager()
        page = await browser.new_page()
        
        try:
            print("\n1. Navigating to homepage...")
            await page.goto("https://www.bittersandbottles.com")
            
            print("\n2. Attempting login...")
            result = await login_to_account(page)
            
            print(f"\n✅ Login result: {result}")
            print(f"   Current URL: {page.url}")
            
            # Take a screenshot for verification
            await page.screenshot(path="debug_login_screenshot.png")
            print("\n📸 Screenshot saved to: debug_login_screenshot.png")
            
            print("\n3. Waiting 10 seconds to inspect...")
            await page.wait_for_timeout(10000)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            await page.screenshot(path="debug_login_error.png")
            print("📸 Error screenshot saved to: debug_login_error.png")
            raise
        finally:
            await page.close()
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(debug_login())
