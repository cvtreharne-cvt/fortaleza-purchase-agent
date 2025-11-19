"""Checkout and payment processing."""

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ..core.logging import get_logger
from ..core.secrets import get_secret_manager
from ..core.config import get_settings, Mode
from ..core.errors import ThreeDSecureRequired

logger = get_logger(__name__)


async def checkout_and_pay(page: Page, submit_order: bool = None) -> dict:
    """
    Complete checkout process with payment information.
    
    This function:
    - Verifies we're on checkout page
    - Selects "Pick up" as the Delivery method
    - Selects pickup location (South SF preferred, SF fallback)
    - Fills in credit card information
    - Fills in cardholder name
    - Optionally submits the order (based on mode)
    
    Args:
        page: Playwright page (should be on checkout page)
        submit_order: If True, submits order. If None, uses mode setting
                     (dryrun/test=False, prod=True)
        
    Returns:
        dict with status, message, and order details
        
    Raises:
        ThreeDSecureRequired: If 3D Secure verification is needed
        Exception: For other failures
    """
    settings = get_settings()
    
    # Determine if we should submit based on mode
    if submit_order is None:
        submit_order = settings.mode == Mode.PROD
    
    logger.info("Starting checkout process", submit_order=submit_order, mode=settings.mode.value)
    
    try:
        # Verify we're on checkout page
        if "checkout" not in page.url.lower():
            raise Exception(f"Not on checkout page. Current URL: {page.url}")
        
        # Wait for page to fully load
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)
        
        # Verify pick-up is selected (should be default)
        await _verify_pickup_selected(page)
        
        # Select pickup location
        await _select_pickup_location(page)
        
        # Fill in payment information
        await _fill_payment_info(page)
        
        # Get order summary before submitting
        order_summary = await _get_order_summary(page)
        logger.info("Order summary", **order_summary)
        
        if submit_order:
            # Submit the order
            logger.info("Submitting order for real")
            result = await _submit_order(page)
            
            return {
                "status": "success",
                "message": "Order submitted successfully",
                "order_summary": order_summary,
                **result
            }
        else:
            logger.info("Dryrun mode - NOT submitting order", order_summary=order_summary)
            return {
                "status": "success",
                "message": "Checkout completed (dryrun - order NOT submitted)",
                "order_summary": order_summary,
                "current_url": page.url
            }
        
    except ThreeDSecureRequired:
        raise
    except Exception as e:
        logger.error("Checkout failed", error=str(e))
        raise


async def _verify_pickup_selected(page: Page) -> None:
    """Verify that Pick-up delivery option is selected."""
    # Look for selected pickup radio button
    pickup_selectors = [
        "input[type='radio'][value*='pick']:checked",
        "input[type='radio'][id*='pickup']:checked",
        "input[type='radio']:checked + label:has-text('Pick')",
    ]
    
    pickup_selected = False
    for selector in pickup_selectors:
        element = await page.query_selector(selector)
        if element:
            logger.debug("Pick-up is selected", selector=selector)
            pickup_selected = True
            break
    
    if not pickup_selected:
        # Try to find and click pickup option
        logger.info("Pick-up not selected, attempting to select it")
        pickup_click_selectors = [
            "input[type='radio'][value*='pick']",
            "label:has-text('Pick-up')",
            "label:has-text('Pick up')",
        ]
        
        for selector in pickup_click_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=3000)
                if element:
                    await element.click()
                    logger.info("Selected pick-up option")
                    await page.wait_for_timeout(1000)
                    return
            except PlaywrightTimeout:
                continue
        
        logger.warning("Could not verify pick-up is selected")


async def _select_pickup_location(page: Page) -> None:
    """Select pickup location (South San Francisco preferred)."""
    logger.info("Selecting pickup location")
    
    # Wait for pickup location dropdown
    location_selectors = [
        "select[name*='pickup']",
        "select[name*='location']",
        "#pickup-location",
        "select",  # Generic select as fallback
    ]
    
    location_dropdown = None
    for selector in location_selectors:
        try:
            location_dropdown = await page.wait_for_selector(selector, timeout=5000)
            if location_dropdown:
                logger.debug("Found pickup location dropdown", selector=selector)
                break
        except PlaywrightTimeout:
            continue
    
    if not location_dropdown:
        logger.warning("Could not find pickup location dropdown")
        return
    
    # Try to select South San Francisco first, then San Francisco
    # Based on screenshot: "South San Francisco, 240 Grand Ave, South San Francisco CA, Usually ready in 1 hour - Free"
    preferred_locations = [
        "South San Francisco",
        "San Francisco",
    ]
    
    for location in preferred_locations:
        try:
            await location_dropdown.select_option(label=location)
            logger.info("Selected pickup location", location=location)
            await page.wait_for_timeout(1000)
            return
        except Exception as e:
            logger.debug("Could not select location", location=location, error=str(e))
            continue
    
    logger.warning("Could not select preferred pickup location, using default")


async def _fill_payment_info(page: Page) -> None:
    """Fill in credit card payment information."""
    logger.info("Filling payment information")
    
    # Scroll to payment section to ensure fields are loaded
    payment_section = await page.query_selector("text=/Payment/i")
    if payment_section:
        await payment_section.scroll_into_view_if_needed()
        await page.wait_for_timeout(1000)
        logger.debug("Scrolled to payment section")
    
    # Get payment info from secrets
    secret_manager = get_secret_manager()
    cc_number = secret_manager.get_secret("cc_number")
    cc_exp_month = secret_manager.get_secret("cc_exp_month")
    cc_exp_year = secret_manager.get_secret("cc_exp_year")
    cc_cvv = secret_manager.get_secret("cc_cvv")
    billing_name = secret_manager.get_secret("billing_name")
    
    # Payment fields are in iframes (Shopify PCI-compliant checkout)
    # We need to find the iframes and fill them
    # Important: The iframe title="Field container for: Card number" etc.
    
    # Fill card number (in iframe)
    logger.debug("Looking for card number iframe")
    try:
        # Look for iframe with title containing "Card number"
        card_number_iframe = await page.wait_for_selector(
            "iframe[title*='Field container for: Card number' i], iframe[name*='number' i]",
            timeout=5000
        )
        if card_number_iframe:
            card_frame = await card_number_iframe.content_frame()
            card_input = await card_frame.wait_for_selector("input", timeout=5000)
            await card_input.click(force=True)
            await page.wait_for_timeout(200)
            await card_input.type(cc_number, delay=30)
            logger.info("Filled card number", last_4=cc_number[-4:])
            # Press Tab to move to expiration field
            await card_input.press("Tab")
            await page.wait_for_timeout(500)
        else:
            raise Exception("Could not find card number iframe")
    except Exception as e:
        logger.error("Failed to fill card number", error=str(e))
        raise
    
    # Fill expiration date (focus should already be here after Tab)
    logger.debug("Filling expiration date")
    try:
        exp_value = f"{cc_exp_month.zfill(2)}{cc_exp_year[-2:]}"
        await page.keyboard.type(exp_value, delay=30)
        logger.info("Filled expiration date", value=f"{cc_exp_month}/{cc_exp_year[-2:]}")
        # Tab to CVV field
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)
    except Exception as e:
        logger.warning("Could not fill expiration date", error=str(e))
    
    # Fill security code (CVV, focus should already be here after Tab)
    logger.debug("Filling CVV")
    try:
        await page.keyboard.type(cc_cvv, delay=30)
        logger.info("Filled CVV")
        # Tab to name on card field
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)
    except Exception as e:
        logger.warning("Could not fill CVV", error=str(e))
    
    # Fill name on card (focus should already be here after Tab)
    logger.debug("Filling name on card")
    try:
        await page.keyboard.type(billing_name, delay=30)
        logger.info("Filled name on card")
    except Exception as e:
        logger.warning("Could not fill name on card", error=str(e))
    
    logger.info("Payment information filled successfully")


async def _get_order_summary(page: Page) -> dict:
    """Extract order summary information from checkout page."""
    summary = {
        "subtotal": "unknown",
        "tax": "unknown",
        "total": "unknown",
        "pickup_location": "unknown",
    }
    
    # Try to get total
    total_selectors = [
        ".total",
        "[data-total]",
        "text=/^Total/",
    ]
    
    for selector in total_selectors:
        element = await page.query_selector(selector)
        if element:
            text = await element.inner_text()
            summary["total"] = text
            break
    
    # Try to get pickup location
    location_element = await page.query_selector("select[name*='pickup'], select[name*='location']")
    if location_element:
        selected_option = await location_element.evaluate("el => el.options[el.selectedIndex].text")
        summary["pickup_location"] = selected_option
    
    return summary


async def _submit_order(page: Page) -> dict:
    """Submit the order."""
    logger.info("Looking for 'Pay now' button")
    
    # Based on screenshot: blue button with "Pay now"
    submit_selectors = [
        "button:has-text('Pay now')",
        "button[type='submit']:has-text('Pay')",
        "button:has-text('Complete order')",
        "button:has-text('Place order')",
        "button[type='submit']",
        "#submit-button",
    ]
    
    submit_button = None
    for selector in submit_selectors:
        try:
            submit_button = await page.wait_for_selector(selector, timeout=3000)
            if submit_button:
                logger.debug("Found submit button", selector=selector)
                break
        except PlaywrightTimeout:
            continue
    
    if not submit_button:
        raise Exception("Could not find 'Pay now' button")
    
    logger.info("Clicking 'Pay now' button")
    await submit_button.click()
    
    # Wait for navigation or processing
    await page.wait_for_timeout(5000)
    
    # Check for 3D Secure
    if await _check_for_3d_secure(page):
        logger.warning("3D Secure verification required - human intervention needed")
        raise ThreeDSecureRequired("3D Secure verification required - manual intervention needed")
    
    # Check for errors
    error = await _check_for_payment_error(page)
    if error:
        raise Exception(f"Payment failed: {error}")
    
    # Verify order was placed
    if "thank" in page.url.lower() or "confirmation" in page.url.lower() or "order" in page.url.lower():
        logger.info("Order submitted successfully", confirmation_url=page.url)
        return {
            "confirmation_url": page.url,
            "order_placed": True
        }
    else:
        logger.warning("Order submission unclear", current_url=page.url)
        return {
            "current_url": page.url,
            "order_placed": False
        }


async def _check_for_3d_secure(page: Page) -> bool:
    """Check if 3D Secure verification is required."""
    secure_selectors = [
        "iframe[name*='3d']",
        "iframe[name*='secure']",
        "text=/3d secure/i",
        "text=/verify/i",
        "#challenge-iframe",
    ]
    
    for selector in secure_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=2000)
            if element:
                logger.debug("Found 3D Secure indicator", selector=selector)
                return True
        except PlaywrightTimeout:
            continue
    
    return False


async def _check_for_payment_error(page: Page) -> str | None:
    """Check for payment error messages."""
    error_selectors = [
        ".error-message",
        ".payment-error",
        "[role='alert']",
        "text=/payment.*failed/i",
        "text=/card.*declined/i",
        "text=/error/i",
    ]
    
    for selector in error_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=2000)
            if element:
                error_text = await element.inner_text()
                logger.debug("Found error message", selector=selector, error=error_text)
                return error_text
        except PlaywrightTimeout:
            continue
    
    return None
