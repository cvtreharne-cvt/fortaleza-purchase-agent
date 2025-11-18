"""Test script for Phase 2 - Browser and Navigation."""

import asyncio
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging, get_logger
from src.tools.navigate import navigate_to_product

setup_logging()
logger = get_logger(__name__)


async def test_browser_lifecycle():
    """Test browser start/stop."""
    print("=" * 60)
    print("Test 1: Browser Lifecycle")
    print("=" * 60)
    
    async with managed_browser():
        browser = get_browser_manager()
        print("✓ Browser started")
        
        # Create a test page
        page = await browser.new_page()
        print(f"✓ Page created")
        
        # Navigate to a simple page
        await page.goto("https://example.com")
        print(f"✓ Navigated to example.com")
        print(f"  Page title: {await page.title()}")
    
    print("✓ Browser stopped")
    print()


async def test_direct_link_navigation():
    """Test navigation with direct link."""
    print("=" * 60)
    print("Test 2: Direct Link Navigation")
    print("=" * 60)
    
    # Test with a real Fortaleza product URL
    # This will likely work if the product exists and is in stock
    test_url = "https://www.bittersandbottles.com/products/fortaleza-blanco-tequila"
    
    async with managed_browser():
        try:
            result = await navigate_to_product(
                direct_link=test_url,
                product_name="Fortaleza"
            )
            print(f"✓ Navigation successful")
            print(f"  Method: {result['method']}")
            print(f"  URL: {result['current_url']}")
        except Exception as e:
            print(f"✗ Navigation failed: {e}")
            print(f"  This is expected if product doesn't exist or URL changed")
    
    print()


async def test_404_fallback():
    """Test fallback when direct link returns 404."""
    print("=" * 60)
    print("Test 3: 404 Error Fallback")
    print("=" * 60)
    
    # URL that doesn't exist
    test_url = "https://www.bittersandbottles.com/products/nonexistent-product-12345"
    
    async with managed_browser():
        try:
            result = await navigate_to_product(
                direct_link=test_url,
                product_name="Fortaleza"
            )
            print(f"✓ Fallback successful")
            print(f"  Method: {result['method']}")
            print(f"  URL: {result['current_url']}")
        except Exception as e:
            print(f"✗ Fallback failed: {e}")
            print(f"  Note: This is expected if search also fails")
    
    print()


async def test_search_icon_detection():
    """Test that we can find the search icon on the homepage."""
    print("=" * 60)
    print("Test 4: Search Icon Detection")
    print("=" * 60)
    
    async with managed_browser():
        browser = get_browser_manager()
        page = await browser.new_page()
        
        await page.goto("https://www.bittersandbottles.com")
        print("✓ Navigated to homepage")
        
        # Try to find search icon using our selectors
        search_selectors = [
            "svg.icon-search",
            ".icon-search",
            "[data-search-toggle]",
            "button:has(svg[class*='search'])",
            "a:has(svg[class*='search'])",
            ".header__search",
            "[aria-label='Search']",
        ]
        
        found = False
        for selector in search_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    print(f"✓ Found search icon with selector: {selector}")
                    # Get the element's HTML for debugging
                    html = await element.evaluate("el => el.outerHTML")
                    print(f"  HTML: {html[:100]}...")
                    found = True
                    break
            except Exception:
                continue
        
        if not found:
            print("✗ Could not find search icon with any selector")
            print("  Taking screenshot for debugging...")
            await page.screenshot(path="/tmp/bittersandbottles-homepage.png")
            print("  Screenshot saved to /tmp/bittersandbottles-homepage.png")
            
            # Try to find any SVG in the header for debugging
            svgs = await page.query_selector_all("header svg, .header svg")
            print(f"  Found {len(svgs)} SVG elements in header")
            for i, svg in enumerate(svgs[:3]):  # Show first 3
                svg_html = await svg.evaluate("el => el.outerHTML")
                print(f"  SVG {i+1}: {svg_html[:150]}...")
    
    print()


async def main():
    """Run all tests."""
    print("\n🧪 Phase 2 Navigation Tests\n")
    
    try:
        # Test 1: Basic browser lifecycle
        await test_browser_lifecycle()
        
        # Test 2: Direct link (should work if product exists)
        await test_direct_link_navigation()
        
        # Test 3: 404 fallback (tests search fallback)
        await test_404_fallback()
        
        # Test 4: Search icon detection (debugging)
        await test_search_icon_detection()
        
        print("=" * 60)
        print("✅ Phase 2 Navigation Tests Complete")
        print("=" * 60)
        print("\nNote: Some tests may fail if:")
        print("- Fortaleza is out of stock")
        print("- Website structure has changed")
        print("- Network issues")
        print("\nCheck the logs above for details.")
        
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
