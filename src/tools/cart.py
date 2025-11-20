"""Add products to shopping cart."""

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ..core.logging import get_logger
from ..core.errors import ProductSoldOutError

logger = get_logger(__name__)

# Timeout constants (in milliseconds)
SELECTOR_WAIT_TIMEOUT = 3000  # Standard timeout for element selectors
SOLD_OUT_CHECK_TIMEOUT = 1000  # Quick timeout for sold out indicators
CART_DRAWER_TIMEOUT = 5000  # Timeout for cart drawer to appear
SUCCESS_INDICATOR_TIMEOUT = 2000  # Timeout for success indicators


async def add_to_cart(page: Page, proceed_to_checkout: bool = False) -> dict:
    """
    Add product to shopping cart.
    
    This function:
    - Checks if product is in stock
    - Clicks "Add to Cart" button
    - Waits for cart drawer to appear
    - Verifies product was added
    - Optionally clicks "CHECKOUT" in the drawer
    
    Args:
        page: Playwright page (should be on product page)
        proceed_to_checkout: If True, clicks CHECKOUT button in drawer
        
    Returns:
        dict with status and message
        
    Raises:
        ProductSoldOutError: If product is sold out
        Exception: For other failures
    """
    logger.info("Adding product to cart", proceed_to_checkout=proceed_to_checkout)
    
    try:
        # First check if product is sold out
        if await _is_sold_out(page):
            raise ProductSoldOutError("Product is sold out - cannot add to cart")
        
        # Find and click "Add to Cart" button
        add_to_cart_selectors = [
            "button:has-text('ADD TO CART')",
            "button:has-text('Add to Cart')",
            "button[name='add']",
            "button[data-add-to-cart]",
            ".product-form__submit",
            "[data-action='add-to-cart']",
            "input[type='submit'][value*='Add']",
        ]
        
        add_button = None
        for selector in add_to_cart_selectors:
            try:
                add_button = await page.wait_for_selector(selector, timeout=SELECTOR_WAIT_TIMEOUT)
                if add_button:
                    # Check if button is disabled
                    is_disabled = await add_button.is_disabled()
                    if not is_disabled:
                        logger.debug("Found add to cart button", selector=selector)
                        break
                    else:
                        logger.debug("Button found but disabled", selector=selector)
                        add_button = None
            except PlaywrightTimeout:
                continue
        
        if not add_button:
            raise Exception("Could not find enabled 'Add to Cart' button")
        
        logger.info("Clicking 'Add to Cart' button")
        await add_button.click()
        
        # Wait for cart drawer to appear from top
        # Based on screenshot: drawer has "Added to your cart:" text
        try:
            await page.wait_for_selector("text=/Added to.*cart/i", timeout=CART_DRAWER_TIMEOUT)
            logger.info("Cart drawer appeared with success message")
        except PlaywrightTimeout:
            logger.warning("Cart drawer success message not found, but continuing")

        # Verify item was added by checking for cart indicators
        item_added = await _verify_item_added(page)
        
        if not item_added:
            raise Exception("Could not verify that product was added to cart")
        
        logger.info("Product successfully added to cart")
        
        # Optionally proceed to checkout
        if proceed_to_checkout:
            logger.info("Proceeding to checkout from cart drawer")
            
            # Look for CHECKOUT button in the drawer
            checkout_selectors = [
                "button:has-text('CHECKOUT')",
                "a:has-text('CHECKOUT')",
                "[data-checkout]",
                ".cart-drawer__checkout",
                "button[name='checkout']",
            ]
            
            checkout_button = None
            for selector in checkout_selectors:
                try:
                    checkout_button = await page.wait_for_selector(selector, timeout=SELECTOR_WAIT_TIMEOUT)
                    if checkout_button:
                        logger.debug("Found checkout button", selector=selector)
                        break
                except PlaywrightTimeout:
                    continue
            
            if not checkout_button:
                raise Exception("Could not find CHECKOUT button in cart drawer")
            
            await checkout_button.click()
            await page.wait_for_load_state("domcontentloaded")
            
            logger.info("Clicked CHECKOUT button", current_url=page.url)
            return {
                "status": "success",
                "message": "Product added to cart and proceeded to checkout",
                "current_url": page.url
            }
        
        return {
            "status": "success",
            "message": "Product added to cart",
            "current_url": page.url
        }
        
    except ProductSoldOutError:
        raise
    except Exception as e:
        logger.error("Failed to add product to cart", error=str(e))
        raise


async def _is_sold_out(page: Page) -> bool:
    """
    Check if product is sold out.
    
    Args:
        page: Playwright page
        
    Returns:
        True if sold out, False otherwise
    """
    sold_out_selectors = [
        "text=/sold out/i",
        "text=/out of stock/i",
        "text=/notify me when available/i",
        ".sold-out",
        "[data-sold-out='true']",
        "button:has-text('NOTIFY ME')",
    ]
    
    for selector in sold_out_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=SOLD_OUT_CHECK_TIMEOUT)
            if element:
                logger.debug("Found sold out indicator", selector=selector)
                return True
        except PlaywrightTimeout:
            continue

    return False


async def _verify_item_added(page: Page) -> bool:
    """
    Verify that item was successfully added to cart.
    
    Args:
        page: Playwright page
        
    Returns:
        True if item was added, False otherwise
    """
    # Look for cart drawer success indicators
    success_indicators = [
        "text=/Added to.*cart/i",
        "text=/item.*added/i",
        ".cart-item",
        "[data-cart-item]",
    ]
    
    for selector in success_indicators:
        try:
            element = await page.wait_for_selector(selector, timeout=SUCCESS_INDICATOR_TIMEOUT)
            if element:
                logger.debug("Found cart success indicator", selector=selector)
                return True
        except PlaywrightTimeout:
            continue

    # Check cart count as fallback
    cart_count = await _get_cart_count(page)
    if cart_count > 0:
        logger.info("Verified item added via cart count", count=cart_count)
        return True

    return False


async def _get_cart_count(page: Page) -> int:
    """
    Get current cart item count from header icon.
    
    Args:
        page: Playwright page
        
    Returns:
        Number of items in cart, or 0 if can't determine
    """
    # Based on screenshot: cart icon in header shows count
    cart_count_selectors = [
        ".cart-count",
        "[data-cart-count]",
        ".cart__item-count",
        "#cart-count",
        "a[href*='cart'] span",  # Generic: link to cart with span
    ]
    
    for selector in cart_count_selectors:
        element = await page.query_selector(selector)
        if element:
            try:
                count_text = await element.inner_text()
                # Remove any non-numeric characters
                count_str = ''.join(filter(str.isdigit, count_text))
                if count_str:
                    count = int(count_str)
                    logger.debug("Found cart count", selector=selector, count=count)
                    return count
            except (ValueError, AttributeError):
                continue
    
    return 0
