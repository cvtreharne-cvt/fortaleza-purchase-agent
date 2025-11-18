"""Quick test for age verification."""

import asyncio
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging, get_logger
from src.tools.verify_age import verify_age

setup_logging()
logger = get_logger(__name__)


async def test_age_verification():
    """Test age verification on homepage."""
    print("\n🧪 Testing Age Verification\n")
    print("=" * 60)
    
    async with managed_browser():
        browser = get_browser_manager()
        page = await browser.new_page()
        
        # Navigate to homepage
        print("Navigating to bittersandbottles.com...")
        await page.goto("https://www.bittersandbottles.com")
        print("✓ Loaded homepage")
        
        # Check for and handle age verification
        print("\nChecking for age verification modal...")
        result = await verify_age(page)
        
        print(f"\nResult: {result['status']}")
        print(f"Message: {result['message']}")
        
        if result["status"] == "success":
            print("\n✅ Age verification completed successfully!")
            print("\nWaiting 2 seconds to verify modal is gone...")
            await asyncio.sleep(2)
            
            # Take a screenshot
            await page.screenshot(path="/tmp/after-age-verification.png")
            print("Screenshot saved to /tmp/after-age-verification.png")
            
        elif result["status"] == "not_found":
            print("\n✓ No age verification modal found (may have been remembered)")
            
        else:
            print("\n❌ Age verification failed")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_age_verification())
