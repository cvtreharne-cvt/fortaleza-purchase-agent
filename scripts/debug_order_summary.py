"""
Debug script to inspect order summary elements on checkout page.

Usage: Run this script to examine the DOM structure of order summary elements.
       This is extremely helpful when the order summary extraction logic breaks
       due to website changes.

When to use:
- Debugging order summary extraction failures
- Investigating "unknown" values in subtotal, tax, or total
- Finding new selectors after B&B website updates
- Understanding the DOM structure of checkout page

Requirements:
- .env.local with valid credentials and payment info
- HEADLESS=false REQUIRED to see the output
- TEST_PRODUCT_URL should point to an in-stock product

Output: This script prints detailed information about DOM structure including:
        - All text containing price ($) symbols
        - Parent/grandparent hierarchy for tax/subtotal/total labels
        - Potential selector strategies

Note: This is a diagnostic tool, not a functional test. Use it to gather
      information for updating _get_order_summary() in checkout.py.
"""

import asyncio
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.login import login_to_account
from src.tools.cart import add_to_cart

setup_logging()

# Use an in-stock product for testing
TEST_PRODUCT_URL = "https://www.bittersandbottles.com/collections/rum/products/blackwell-jamaican-black-gold-reserve-rum"


async def debug_order_summary():
    """Debug order summary extraction."""
    print("\n🔍 Inspecting Order Summary Elements")
    print("=" * 60)

    async with managed_browser():
        browser = get_browser_manager()
        page = await browser.new_page()

        try:
            print("\n1. Logging in...")
            await page.goto("https://www.bittersandbottles.com")
            await login_to_account(page)

            print(f"\n2. Navigating to test product...")
            await page.goto(TEST_PRODUCT_URL)
            await page.wait_for_timeout(1000)

            print("\n3. Adding to cart and proceeding to checkout...")
            await add_to_cart(page, proceed_to_checkout=True)

            print(f"\n4. Current URL: {page.url}")

            # Wait for checkout page to load
            await page.wait_for_timeout(3000)

            # Select Pickup delivery method (like the real checkout flow does)
            print("\n5. Selecting Pick up delivery method...")
            pickup_radio = await page.query_selector("text=/Pick up/i")
            if pickup_radio:
                await pickup_radio.click()
                print("   ✅ Clicked Pick up option")
                await page.wait_for_timeout(2000)  # Wait for pickup options to load
            else:
                print("   ❌ Could not find Pick up option")

            print("\n6. Searching for order summary elements...")

            # Try to find any text containing price info
            all_text = await page.evaluate("""() => {
                return document.body.innerText;
            }""")

            # Look for lines containing prices
            price_lines = [line for line in all_text.split('\n') if '$' in line]
            print("\n📝 Lines containing prices:")
            for line in price_lines[:20]:  # Show first 20
                print(f"   {line.strip()}")

            # Try specific selectors
            print("\n\n🔎 Testing specific selectors:")

            # First, let's understand the relationship between tax label and value
            print("\n🔍 Finding tax value relative to tax label:")
            tax_label = await page.query_selector("text=/^Estimated taxes$/i")
            if tax_label:
                # Try to find the value in the same container or nearby
                tax_container_text = await tax_label.evaluate("""el => {
                    // Try different parent levels
                    let p1 = el.parentElement;
                    let p2 = p1?.parentElement;
                    let p3 = p2?.parentElement;
                    let p4 = p3?.parentElement;
                    let p5 = p4?.parentElement;

                    return {
                        p1: p1?.innerText?.substring(0, 150),
                        p2: p2?.innerText?.substring(0, 150),
                        p3: p3?.innerText?.substring(0, 150),
                        p4: p4?.innerText?.substring(0, 150),
                        p5: p5?.innerText,  // Full text to see all lines
                    };
                }""")
                for level in range(1, 6):
                    text = tax_container_text.get(f'p{level}', 'None')
                    has_dollar = '$' in str(text)
                    print(f"   Parent level {level}: {text} {'💰' if has_dollar else ''}")

            test_selectors = [
                ("text=/Subtotal/i", "Subtotal label"),
                ("text=/Estimated taxes/i", "Tax label"),
                ("text=/^Total$/i", "Total label"),
                ("text=/\\$3\\.61/", "Exact tax value $3.61"),
                (".payment-due__price", "Payment due price class"),
                ("[data-checkout-payment-due-target]", "Payment due data attribute"),
                ("text=/South San Francisco/i", "Pickup location"),
            ]

            for selector, desc in test_selectors:
                elem = await page.query_selector(selector)
                if elem:
                    text = await elem.inner_text()
                    print(f"   ✅ {desc}: found - '{text[:100]}'")

                    # Try getting parent and its full text
                    parent = await elem.evaluate_handle("el => el.parentElement")
                    parent_text = await parent.inner_text()
                    print(f"      Parent inner_text: '{parent_text[:150]}'")

                    # Try getting all text in parent's parent
                    grandparent = await elem.evaluate_handle("el => el.parentElement.parentElement")
                    grandparent_text = await grandparent.inner_text()
                    print(f"      Grandparent inner_text: '{grandparent_text[:150]}'")

                    # Try finding sibling with price
                    price_sibling = await elem.evaluate("""el => {
                        let sibling = el.nextSibling;
                        while (sibling) {
                            if (sibling.textContent && sibling.textContent.includes('$')) {
                                return sibling.textContent;
                            }
                            sibling = sibling.nextSibling;
                        }
                        return null;
                    }""")
                    if price_sibling:
                        print(f"      Next sibling with $: '{price_sibling.strip()}'")

                    # For tax label, explore the row structure more
                    if "Tax label" in desc:
                        print(f"\n      Exploring tax row DOM structure:")
                        row_info = await elem.evaluate("""el => {
                            let row = el.closest('tr, div[class*="line"], div[class*="row"]');
                            if (!row) row = el.parentElement.parentElement;
                            return {
                                rowHTML: row.outerHTML.substring(0, 500),
                                rowText: row.innerText,
                                children: Array.from(row.children).map(child => ({
                                    tag: child.tagName,
                                    text: child.innerText,
                                    class: child.className
                                }))
                            };
                        }""")
                        print(f"         Row text: {row_info['rowText'][:150]}")
                        print(f"         Children: {row_info['children']}")
                else:
                    print(f"   ❌ {desc}: NOT found")

            # Take a screenshot
            await page.screenshot(path="debug_order_summary.png")
            print("\n📸 Screenshot saved to: debug_order_summary.png")

            print("\n7. Waiting 10 seconds to inspect...")
            await page.wait_for_timeout(10000)

        except Exception as e:
            print(f"\n❌ Error: {e}")
            await page.screenshot(path="debug_order_summary_error.png")
            print("📸 Error screenshot saved to: debug_order_summary_error.png")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await page.close()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(debug_order_summary())
