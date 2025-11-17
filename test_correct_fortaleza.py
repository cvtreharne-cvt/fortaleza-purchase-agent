"""Test with correct Fortaleza URL."""

import asyncio
from src.core.browser import managed_browser
from src.core.logging import setup_logging, get_logger
from src.tools.navigate import navigate_to_product

setup_logging()
logger = get_logger(__name__)


async def test_correct_fortaleza_url():
    """Test navigation to correct Fortaleza product page."""
    print("\n🧪 Testing Correct Fortaleza URL\n")
    print("=" * 60)
    
    # Correct URL per your info
    correct_url = "https://www.bittersandbottles.com/products/fortaleza-blanco-tequila"
    
    async with managed_browser():
        try:
            print(f"Navigating to: {correct_url}")
            result = await navigate_to_product(
                direct_link=correct_url,
                product_name="Fortaleza"
            )
            print(f"\n✅ Navigation successful!")
            print(f"  Method: {result['method']}")
            print(f"  URL: {result['current_url']}")
            
            # Check if it's the sold out page
            if "fortaleza" in result['current_url'].lower():
                print(f"\n  ✓ On Fortaleza product page")
                print(f"  Note: Product may be out of stock (has 'NOTIFY ME' button)")
            
        except Exception as e:
            print(f"\n❌ Navigation failed: {e}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_correct_fortaleza_url())
