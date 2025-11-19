"""Age verification modal handler."""

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ..core.logging import get_logger
from ..core.secrets import get_secret_manager

logger = get_logger(__name__)


async def verify_age(page: Page) -> dict:
    """
    Handle age verification modal if present.
    
    This function checks for age verification overlays/modals and
    fills in the required information to proceed.
    
    Args:
        page: Playwright page
        
    Returns:
        dict with status indicating if modal was found and handled
    """
    logger.info("Checking for age verification modal")
    
    try:
        # Check if age verification overlay is present
        # Common selectors for age verification modals
        overlay_selectors = [
            ".m-a-v-overlay",  # BittersAndBottles specific
            ".age-verification-overlay",
            ".age-gate",
            "[data-age-verification]",
            ".modal-age-verification",
        ]

        overlay = None
        matched_selector = None
        for selector in overlay_selectors:
            try:
                # Increase timeout - modal may take a moment to appear
                overlay = await page.wait_for_selector(selector, timeout=5000)
                if overlay:
                    matched_selector = selector
                    logger.info("Age verification overlay found", selector=selector)
                    break
            except PlaywrightTimeout:
                continue

        if not overlay:
            logger.info("No age verification modal found")
            return {"status": "not_found", "message": "No age verification required"}
        
        logger.info("Handling age verification")
        
        # First try the common simple confirmation buttons
        simple_button_selectors = [
            "button:has-text('Over 21')",
            "button:has-text('OVER 21')",
            "button:has-text('Yes')",
            "button:has-text('YES')",
            "a:has-text('Enter')",
            "button:has-text('Enter')",
            "button:has-text('I am 21')",
            ".age-verification-yes",
            "[data-age-yes]",
        ]
        
        simple_button = None
        for selector in simple_button_selectors:
            try:
                simple_button = await page.wait_for_selector(selector, timeout=2000)
                if simple_button:
                    logger.info("Found age confirmation button", selector=selector)
                    await simple_button.click()
                    logger.info("Clicked age confirmation button")

                    # Wait for modal to disappear - use the selector that matched
                    try:
                        await page.wait_for_selector(matched_selector, state="hidden", timeout=10000)
                        logger.info("Age verification modal closed")
                    except PlaywrightTimeout:
                        logger.error("Age verification modal did not close after clicking button")
                        return {
                            "status": "error",
                            "message": "Modal did not close after submission - may need manual intervention"
                        }

                    return {"status": "success", "message": "Age verification completed (button)"}
            except PlaywrightTimeout:
                continue
        
        # Fallback: date entry style gates
        logger.info("No simple confirmation button found, trying date entry form")
        
        # Get date of birth from secrets
        secret_manager = get_secret_manager()
        dob_month = secret_manager.get_secret("dob_month")
        dob_day = secret_manager.get_secret("dob_day")
        dob_year = secret_manager.get_secret("dob_year")
        
        logger.info("Filling age verification form")
        
        # Try to find and fill date fields
        # Different sites use different input patterns
        
        # Pattern 1: Separate dropdowns/inputs for month, day, year
        month_filled = await _fill_field(
            page,
            ["select[name='month']", "input[name='month']", "#age-month", "[placeholder*='Month' i]"],
            dob_month
        )
        
        day_filled = await _fill_field(
            page,
            ["select[name='day']", "input[name='day']", "#age-day", "[placeholder*='Day' i]"],
            dob_day
        )
        
        year_filled = await _fill_field(
            page,
            ["select[name='year']", "input[name='year']", "#age-year", "[placeholder*='Year' i]"],
            dob_year
        )
        
        if not (month_filled and day_filled and year_filled):
            logger.warning("Could not find all date fields")
            # Try alternative: single date input
            date_input = await page.query_selector("input[type='date']")
            if date_input:
                date_str = f"{dob_year}-{dob_month.zfill(2)}-{dob_day.zfill(2)}"
                await date_input.fill(date_str)
                logger.info("Filled single date input")
        
        # Look for submit button
        submit_selectors = [
            "button[type='submit']",
            "button:has-text('Enter')",
            "button:has-text('Confirm')",
            "button:has-text('Yes')",
            ".age-verification-submit",
            "[data-age-submit]",
        ]
        
        submit_button = None
        for selector in submit_selectors:
            try:
                submit_button = await page.wait_for_selector(selector, timeout=2000)
                if submit_button:
                    logger.debug("Found submit button", selector=selector)
                    break
            except PlaywrightTimeout:
                continue
        
        if not submit_button:
            logger.error("Could not find age verification submit button")
            return {"status": "error", "message": "Submit button not found"}
        
        # Click submit
        await submit_button.click()
        logger.info("Submitted age verification")

        # Wait for modal to disappear - use the selector that matched
        try:
            await page.wait_for_selector(matched_selector, state="hidden", timeout=10000)
            logger.info("Age verification modal closed")
        except PlaywrightTimeout:
            logger.error("Age verification modal did not close after date submission")
            return {
                "status": "error",
                "message": "Modal did not close after date submission - may need manual intervention"
            }
        
        return {
            "status": "success",
            "message": "Age verification completed"
        }
        
    except Exception as e:
        logger.error("Age verification failed", error=str(e))
        return {
            "status": "error",
            "message": f"Age verification failed: {str(e)}"
        }


async def _fill_field(page: Page, selectors: list[str], value: str) -> bool:
    """
    Try to find and fill a field using multiple selectors.
    
    Args:
        page: Playwright page
        selectors: List of CSS selectors to try
        value: Value to fill
        
    Returns:
        True if field was found and filled, False otherwise
    """
    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                # Check if it's a select or input
                tag_name = await element.evaluate("el => el.tagName")
                
                if tag_name.lower() == "select":
                    # For select, use selectOption
                    await element.select_option(value=value)
                else:
                    # For input, use fill
                    await element.fill(value)
                
                logger.debug("Filled field", selector=selector, tag=tag_name)
                return True
        except Exception as e:
            logger.debug("Could not fill field", selector=selector, error=str(e))
            continue
    
    return False
