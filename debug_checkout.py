"""Debug script to test checkout functionality."""

import asyncio
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.login import login_to_account
from src.tools.cart import add_to_cart
from src.tools.checkout import checkout_and_pay

setup_logging()

# Use an in-stock product for testing
TEST_PRODUCT_URL = "https://www.bittersandbottles.com/collections/rum/products/blackwell-jamaican-black-gold-reserve-rum"


async def debug_checkout():
    """Debug checkout functionality."""
    print("\n💳 Testing Checkout Functionality (DRYRUN)")
    print("=" * 60)
    
    async with managed_browser():
        browser = get_browser_manager()
        page = await browser.new_page()
        
        try:
            print("\n1. Logging in (will handle age verification)...")
            await page.goto("https://www.bittersandbottles.com")
            await login_to_account(page)
            
            print(f"\n2. Navigating to test product...")
            await page.goto(TEST_PRODUCT_URL)
            await page.wait_for_timeout(1000)
            
            print("\n3. Adding to cart and proceeding to checkout...")
            await add_to_cart(page, proceed_to_checkout=True)
            
            print(f"\n4. Current URL: {page.url}")
            
            print("\n5. Filling checkout form (DRYRUN - will NOT submit)...")
            result = await checkout_and_pay(page, submit_order=False)
            
            print(f"\n✅ Checkout result: {result}")
            print(f"   Order summary: {result.get('order_summary', {})}")
            print(f"   Current URL: {page.url}")
            
            # Take a screenshot
            await page.screenshot(path="debug_checkout_screenshot.png")
            print("\n📸 Screenshot saved to: debug_checkout_screenshot.png")
            
            print("\n6. Waiting 10 seconds to inspect...")
            await page.wait_for_timeout(10000)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            await page.screenshot(path="debug_checkout_error.png")
            print("📸 Error screenshot saved to: debug_checkout_error.png")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await page.close()
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(debug_checkout())
