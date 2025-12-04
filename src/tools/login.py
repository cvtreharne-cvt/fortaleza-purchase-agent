"""Login to Bitters & Bottles account."""

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ..core import browser_service
from ..core.logging import get_logger
from ..core.notify import send_notification
from ..core.secrets import get_secret_manager
from ..core.errors import TwoFactorRequired, CaptchaRequired
from .verify_age import verify_age

logger = get_logger(__name__)

BASE_URL = "https://www.bittersandbottles.com"

# Timeout constants (in milliseconds)
SELECTOR_WAIT_TIMEOUT = 3000  # Standard timeout for element selectors
TWO_FACTOR_CHECK_TIMEOUT = 1000  # Quick timeout for 2FA indicators
ERROR_CHECK_TIMEOUT = 1000  # Quick timeout for error messages
CAPTCHA_CHECK_TIMEOUT = 1000  # Quick timeout for CAPTCHA detection


async def login_to_account(page: Page) -> dict:
    """
    Login to B&B account.
    
    This function handles the login flow, including:
    - Navigating to login page (if not already there)
    - Filling in email and password
    - Submitting the form
    - Detecting if already logged in
    - Detecting 2FA requirements
    
    Args:
        page: Playwright page
        
    Returns:
        dict with status and message
        
    Raises:
        TwoFactorRequired: If 2FA is required
        Exception: For other login failures
    """
    logger.info("Starting login process")

    # Browser worker path (Node Playwright)
    if browser_service.is_enabled():
        secret_manager = get_secret_manager()
        dob = {
            "dob_month": secret_manager.get_secret("dob_month"),
            "dob_day": secret_manager.get_secret("dob_day"),
            "dob_year": secret_manager.get_secret("dob_year"),
        }
        email = secret_manager.get_secret("bnb_email")
        password = secret_manager.get_secret("bnb_password")
        return await browser_service.login(email, password, dob)
    
    try:
        # Check if already logged in
        if await _is_logged_in(page):
            logger.info("Already logged in")
            return {"status": "success", "message": "Already logged in"}
        
        # Navigate to account/login page
        # Try multiple patterns for login URL
        login_url_paths = [
            "/account/login",
            "/account",
            "/login",
        ]
        
        current_url = page.url
        if not any(path in current_url for path in login_url_paths):
            logger.info("Navigating to login page")
            await page.goto(f"{BASE_URL}/account/login", wait_until="domcontentloaded")
        
        # Handle age verification if present
        age_result = await verify_age(page)
        if age_result["status"] == "success":
            logger.info("Age verification completed before login")
        elif age_result["status"] == "error":
            raise Exception(f"Age verification failed: {age_result['message']}")

        # Get credentials from secrets
        secret_manager = get_secret_manager()
        email = secret_manager.get_secret("bnb_email")
        password = secret_manager.get_secret("bnb_password")

        logger.info("Filling login form", email=email[:3] + "***")

        # Check for CAPTCHA before attempting to find login fields
        # CAPTCHA can appear on login page and overlay/replace the form
        if await _check_for_captcha(page):
            logger.warning("CAPTCHA detected on login page - human intervention needed")
            raise CaptchaRequired("CAPTCHA challenge detected - manual intervention needed")

        # Find and fill email field
        email_selectors = [
            "input[name='customer[email]']",
            "input[type='email']",
            "input[id*='email' i]",
            "input[placeholder*='email' i]",
        ]
        
        email_input = None
        for selector in email_selectors:
            try:
                email_input = await page.wait_for_selector(selector, timeout=SELECTOR_WAIT_TIMEOUT)
                if email_input:
                    logger.debug("Found email input", selector=selector)
                    break
            except PlaywrightTimeout:
                continue
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        await email_input.fill(email)
        
        # Find and fill password field
        password_selectors = [
            "input[name='customer[password]']",
            "input[type='password']",
            "input[id*='password' i]",
            "input[placeholder*='password' i]",
        ]
        
        password_input = None
        for selector in password_selectors:
            try:
                password_input = await page.wait_for_selector(selector, timeout=SELECTOR_WAIT_TIMEOUT)
                if password_input:
                    logger.debug("Found password input", selector=selector)
                    break
            except PlaywrightTimeout:
                continue
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        await password_input.fill(password)
        
        # Find and click submit button
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Sign In')",
            "button:has-text('Log In')",
            "button:has-text('Login')",
            ".login-button",
            "[data-action='login']",
        ]
        
        submit_button = None
        for selector in submit_selectors:
            try:
                submit_button = await page.wait_for_selector(selector, timeout=SELECTOR_WAIT_TIMEOUT)
                if submit_button:
                    logger.debug("Found submit button", selector=selector)
                    break
            except PlaywrightTimeout:
                continue
        
        if not submit_button:
            raise Exception("Could not find submit button")
        
        logger.info("Submitting login form")
        await submit_button.click()

        # Wait for navigation to complete
        # Note: B&B website takes ~14s to process login server-side
        await page.wait_for_load_state("domcontentloaded")

        # Check for 2FA
        if await _check_for_2fa(page):
            logger.warning("2FA required - human intervention needed")
            raise TwoFactorRequired("Two-factor authentication required - manual intervention needed")

        # Check for login errors
        error = await _check_for_login_error(page)
        if error:
            raise Exception(f"Login failed: {error}")

        # Verify login was successful by checking URL
        # The logout link is hidden in hamburger menu, so URL is more reliable
        if "/account" in page.url.lower():
            logger.info("Login successful", current_url=page.url)
            return {"status": "success", "message": "Login successful"}

        # Fallback: still on login page means login failed
        if "/login" in page.url.lower():
            raise Exception("Login failed - still on login page")

        # If we're somewhere else, assume success
        logger.info("Login appears successful", current_url=page.url)
        return {"status": "success", "message": "Login successful"}

    except CaptchaRequired as e:
        # Send emergency notification immediately
        logger.error("CAPTCHA required - sending emergency notification")
        send_notification(
            "🚨 CAPTCHA Required",
            "CAPTCHA challenge detected on login page. Please solve manually and the agent will resume.",
            priority=2  # Emergency - requires acknowledgment
        )
        raise
    except TwoFactorRequired as e:
        # Send emergency notification immediately
        logger.error("2FA required - sending emergency notification")
        send_notification(
            "🚨 2FA Required",
            "Two-factor authentication is required to login. Please complete manually.",
            priority=2  # Emergency - requires acknowledgment
        )
        raise
    except Exception as e:
        logger.error("Login failed", error=str(e))
        raise


async def _is_logged_in(page: Page) -> bool:
    """
    Check if user is already logged in.
    
    Args:
        page: Playwright page
        
    Returns:
        True if logged in, False otherwise
    """
    # First check URL - most reliable indicator
    if "/account" in page.url.lower() and "/login" not in page.url.lower():
        logger.debug("Detected logged in via URL", url=page.url)
        return True
    
    # Logout link is hidden in hamburger menu, so we'd need to click it first
    # Just rely on URL check
    return False


async def _check_for_2fa(page: Page) -> bool:
    """
    Check if 2FA is required.
    
    Args:
        page: Playwright page
        
    Returns:
        True if 2FA is required, False otherwise
    """
    # Look for 2FA indicators
    twofa_selectors = [
        "input[name*='code' i]",
        "input[placeholder*='code' i]",
        "text=/verification code/i",
        "text=/authenticator/i",
        "text=/two.factor/i",
        ".two-factor-form",
        "[data-2fa]",
    ]
    
    for selector in twofa_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=TWO_FACTOR_CHECK_TIMEOUT)
            if element:
                logger.debug("Found 2FA indicator", selector=selector)
                return True
        except PlaywrightTimeout:
            continue

    return False


async def _check_for_login_error(page: Page) -> str | None:
    """
    Check for login error messages.

    Args:
        page: Playwright page

    Returns:
        Error message if found, None otherwise
    """
    # Look for error messages
    error_selectors = [
        ".error-message",
        ".alert-error",
        ".form-error",
        "[role='alert']",
        "text=/incorrect password/i",
        "text=/invalid email/i",
        "text=/login failed/i",
    ]

    for selector in error_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=ERROR_CHECK_TIMEOUT)
            if element:
                error_text = await element.inner_text()
                logger.debug("Found error message", selector=selector, error=error_text)
                return error_text
        except PlaywrightTimeout:
            continue

    return None


async def _check_for_captcha(page: Page) -> bool:
    """
    Check if CAPTCHA is present on the page.

    Args:
        page: Playwright page

    Returns:
        True if CAPTCHA is detected, False otherwise
    """
    # Look for common CAPTCHA indicators
    # Covers reCAPTCHA, hCaptcha, and generic CAPTCHA implementations
    captcha_selectors = [
        # Google reCAPTCHA v2 (checkbox and image challenge)
        "iframe[src*='recaptcha']",
        ".g-recaptcha",
        "#g-recaptcha",
        "[data-sitekey]",  # reCAPTCHA site key attribute

        # hCaptcha
        "iframe[src*='hcaptcha']",
        ".h-captcha",
        "#h-captcha",

        # Generic CAPTCHA
        ".captcha",
        "#captcha",
        "img[alt*='captcha' i]",
        "img[src*='captcha' i]",
        "[class*='captcha' i]",
        "[id*='captcha' i]",

        # Text indicators
        "text=/verify you are human/i",
        "text=/captcha/i",
        "text=/prove you're not a robot/i",
    ]

    for selector in captcha_selectors:
        try:
            # Use shorter timeout for CAPTCHA check
            element = await page.wait_for_selector(selector, timeout=CAPTCHA_CHECK_TIMEOUT)
            if element:
                # Additional check: ensure element is visible
                if await element.is_visible():
                    logger.debug("Found CAPTCHA indicator", selector=selector)
                    return True
        except PlaywrightTimeout:
            continue

    return False
