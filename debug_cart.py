"""Debug script to test add to cart functionality."""

import asyncio
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.login import login_to_account
from src.tools.cart import add_to_cart

setup_logging()

# Use a product that's actually in stock for testing
TEST_PRODUCT_URL = "https://www.bittersandbottles.com/collections/rum/products/blackwell-jamaican-black-gold-reserve-rum"


async def debug_cart():
    """Debug cart functionality."""
    print("\n🛒 Testing Add to Cart Functionality")
    print("=" * 60)
    
    async with managed_browser():
        browser = get_browser_manager()
        page = await browser.new_page()
        
        try:
            print(f"\n1. Navigating to test product...")
            print(f"   URL: {TEST_PRODUCT_URL}")
            await page.goto(TEST_PRODUCT_URL)
            await page.wait_for_load_state("domcontentloaded")
            
            print("\n2. Logging in...")
            await login_to_account(page)
            
            # Navigate back to product after login
            print(f"\n3. Navigating back to product page...")
            await page.goto(TEST_PRODUCT_URL)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)
            
            print("\n4. Adding product to cart...")
            result = await add_to_cart(page, proceed_to_checkout=False)
            
            print(f"\n✅ Add to cart result: {result}")
            print(f"   Current URL: {page.url}")
            
            # Take a screenshot
            await page.screenshot(path="debug_cart_screenshot.png")
            print("\n📸 Screenshot saved to: debug_cart_screenshot.png")
            
            print("\n5. Waiting 10 seconds to inspect...")
            await page.wait_for_timeout(10000)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            await page.screenshot(path="debug_cart_error.png")
            print("📸 Error screenshot saved to: debug_cart_error.png")
            raise
        finally:
            await page.close()
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(debug_cart())
