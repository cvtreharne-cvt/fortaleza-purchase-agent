"""Debug script to inspect search results."""

import asyncio
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.verify_age import verify_age

setup_logging()


async def debug_search():
    """Debug search functionality."""
    async with managed_browser():
        browser = get_browser_manager()
        page = await browser.new_page()
        
        print("1. Navigating to homepage...")
        await page.goto('https://www.bittersandbottles.com')
        
        print("2. Handling age verification...")
        await verify_age(page)
        
        print("3. Clicking search icon...")
        search = await page.wait_for_selector('svg.icon-search')
        await search.click()
        await page.wait_for_timeout(1000)  # Wait for animation
        
        print("4. Typing 'Fortaleza' in search...")
        search_input = await page.wait_for_selector('input[type=search], input[name=q]', state='visible')
        await page.wait_for_timeout(500)  # Ensure input is ready
        await search_input.click()  # Focus the input
        await search_input.type('Fortaleza', delay=100)  # Type with delay
        
        print("\n5. Waiting for search suggestions...")
        await page.wait_for_timeout(2000)
        
        print("6. Looking for suggestions dropdown...")
        # Check various suggestion containers
        suggestions_container = await page.query_selector('.predictive-search, [role="listbox"], .search-suggestions')
        if suggestions_container:
            print("   ✓ Found suggestions container")
            all_links = await suggestions_container.query_selector_all('a')
            print(f"   Found {len(all_links)} links in suggestions\n")
            
            for i, link in enumerate(all_links[:5]):
                href = await link.get_attribute('href')
                text = await link.inner_text()
                print(f"   {i+1}. {text[:50]}")
                print(f"      href: {href}")
            
            # Try to click the product link directly
            print("\n7. Trying to click product link from suggestions...")
            product_link = await suggestions_container.query_selector("a[href^='/products/'][href*='fortaleza']")
            if product_link:
                print("   ✓ Found product link, clicking...")
                await product_link.click()
                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                print(f"   ✓ Clicked! Current URL: {page.url}")
                # Check if we're on the product page
                if '/products/' in page.url:
                    print("   ✓ Successfully navigated to product page!")
                    print("\n✓ SUCCESS! Search suggestion click worked!")
                    return
            else:
                print("   ✗ Product link not found, pressing Enter instead")
                await search_input.press('Enter')
        else:
            print("   ✗ No suggestions container found")
            print("   Checking for any visible links...")
            all_links = await page.query_selector_all('a[href*="fortaleza"]')
            print(f"   Found {len(all_links)} links with 'fortaleza' in href")
            print("\n7. Pressing Enter to see full results...")
            await search_input.press('Enter')
        
        print("6. Waiting for search results...")
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(2000)
        
        print(f"\n✓ Current URL: {page.url}")
        
        # Try to find product links
        print("\n7. Looking for product links...")
        
        all_links = await page.query_selector_all('a[href*="products"]')
        print(f"   Found {len(all_links)} total product links\n")
        
        # Now try to find Fortaleza specifically
        print("8. Looking specifically for Fortaleza links...")
        
        # Try our current selectors
        selector1 = await page.query_selector('a[href*="products"]:has-text("Fortaleza")')
        selector2 = await page.query_selector('.productitem a[href*="fortaleza"]')
        selector3 = await page.query_selector('a[href*="fortaleza-blanco-tequila"]')
        
        print(f"   Selector 'a:has-text(Fortaleza)': {'FOUND' if selector1 else 'NOT FOUND'}")
        print(f"   Selector '.productitem a[href*=fortaleza]': {'FOUND' if selector2 else 'NOT FOUND'}")
        print(f"   Selector 'a[href*=fortaleza-blanco-tequila]': {'FOUND' if selector3 else 'NOT FOUND'}")
        
        if selector3:
            text = await selector3.inner_text()
            href = await selector3.get_attribute('href')
            print(f"\n   ✓ Found Fortaleza link!")
            print(f"     Text: {text}")
            print(f"     Href: {href}")
        
        print("\n9. Showing product grid items:")
        product_items = await page.query_selector_all('.productgrid--item, .productitem, [class*="product"]')
        print(f"   Found {len(product_items)} product items")
        
        if len(product_items) > 0:
            print("\n   First 3 product items:")
            for i, item in enumerate(product_items[:3]):
                links = await item.query_selector_all('a')
                text = (await item.inner_text()).strip()[:100]
                print(f"   {i+1}. Links in item: {len(links)}")
                print(f"      Text: {text}")
        
        print("\n10. Done! Check output above.")
        print("    Press Ctrl+C to exit")
        await page.wait_for_timeout(300000)  # Wait 5 minutes


if __name__ == "__main__":
    asyncio.run(debug_search())
