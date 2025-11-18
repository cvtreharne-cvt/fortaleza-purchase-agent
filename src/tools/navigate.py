"""Navigate to product page tool with fallback to search."""

from typing import Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ..core.browser import get_browser_manager
from ..core.config import get_settings
from ..core.errors import NavigationError, ProtocolError, PageNotFoundError, UnexpectedPageError
from ..core.logging import get_logger
from .verify_age import verify_age

logger = get_logger(__name__)

BASE_URL = "https://www.bittersandbottles.com"


async def navigate_to_product(
    direct_link: str,
    product_name: Optional[str] = None
) -> dict:
    """
    Navigate to product page using direct link with search fallback.
    
    Args:
        direct_link: Direct URL to product page from email
        product_name: Product name for search fallback
        
    Returns:
        dict with status and current_url
        
    Raises:
        NavigationError: If navigation fails completely
    """
    settings = get_settings()
    browser = get_browser_manager()
    page = await browser.new_page()
    
    # Ensure page is closed even if errors occur
    try:
        logger.info("Navigating to direct link", url=direct_link)
        
        response = await page.goto(direct_link, wait_until="domcontentloaded")
        
        # Check for protocol errors (e.g., trk.bittersandbottles.com)
        if "trk." in page.url:
            logger.warning("Protocol error: redirect domain detected", url=page.url)
            raise ProtocolError(f"Protocol error: redirected to {page.url}")
        
        # Check for 404
        if response and response.status == 404:
            logger.warning("Direct link returned 404", url=direct_link)
            raise PageNotFoundError(f"Page not found: {direct_link}")
        
        # Verify we're on a product page
        is_product_page = await _verify_product_page(page)
        if not is_product_page:
            logger.warning("Direct link did not lead to product page", url=page.url)
            raise UnexpectedPageError(f"Not a product page: {page.url}")
        
        logger.info("Successfully navigated to product page", url=page.url)
        return {
            "status": "success",
            "method": "direct_link",
            "current_url": page.url
        }
        
    except (ProtocolError, PageNotFoundError, UnexpectedPageError, PlaywrightTimeout) as e:
        logger.warning(
            "Direct link failed, trying search fallback",
            error=str(e),
            product_name=product_name or settings.product_name
        )
        
        # Fallback to homepage + search
        try:
            search_result = await _search_for_product(
                page,
                product_name or settings.product_name
            )
            return search_result
        except Exception as search_error:
            logger.error("Search fallback also failed", error=str(search_error))
            raise NavigationError(
                f"Both direct link and search failed. "
                f"Direct: {str(e)}, Search: {str(search_error)}"
            )
    finally:
        # Always close the page to prevent resource leaks
        await page.close()


async def _verify_product_page(page: Page) -> bool:
    """
    Verify that we're on a product page.
    
    Args:
        page: Playwright page
        
    Returns:
        True if on product page, False otherwise
    """
    try:
        # Check for product page indicators
        # Must have: Product title
        # Must have at least one: Add to cart button, Notify button, Sold Out text, or Price
        
        # First verify title exists
        title = await page.wait_for_selector(
            "h1.product-title, .product__title, [data-product-title]",
            timeout=5000
        )
        
        if not title:
            return False
        
        # Check for at least one product indicator
        add_to_cart = await page.query_selector(
            "button[name='add'], .product-form__submit, [data-add-to-cart]"
        )
        notify_me = await page.query_selector("text=/notify me when available/i")
        sold_out = await page.query_selector("text=/sold out/i")
        price = await page.query_selector(".price, .product-price, [data-product-price]")
        
        # Require title AND at least one other indicator
        has_indicator = (add_to_cart is not None) or (notify_me is not None) or (sold_out is not None) or (price is not None)
        
        return has_indicator
        
    except PlaywrightTimeout:
        return False


async def _search_for_product(page: Page, product_name: str) -> dict:
    """
    Navigate to homepage and search for product.
    
    Args:
        page: Playwright page
        product_name: Name of product to search for
        
    Returns:
        dict with status and current_url
        
    Raises:
        NavigationError: If search fails
    """
    logger.info("Navigating to homepage for search", product_name=product_name)
    
    # Navigate to homepage
    await page.goto(BASE_URL, wait_until="domcontentloaded")
    
    # Handle age verification if present
    age_result = await verify_age(page)
    if age_result["status"] == "success":
        logger.info("Age verification completed before search")
    elif age_result["status"] == "error":
        raise NavigationError(f"Age verification failed: {age_result['message']}")
    
    # Find and click search icon/button
    try:
        # Try multiple selector strategies for search icon (magnifying glass)
        # 1. SVG icon with search-related class
        # 2. Button/link with search icon
        # 3. Data attributes
        # 4. Role-based selectors
        search_selectors = [
            "svg.icon-search",  # SVG with search class
            ".icon-search",  # Any element with search class
            "[data-search-toggle]",  # Data attribute
            "button:has(svg[class*='search'])",  # Button containing search SVG
            "a:has(svg[class*='search'])",  # Link containing search SVG  
            ".header__search",  # Header search element
            "[aria-label='Search']",  # Accessible label
            "button[aria-label='Search']",
        ]
        
        search_button = None
        for selector in search_selectors:
            try:
                search_button = await page.wait_for_selector(selector, timeout=2000)
                if search_button:
                    logger.debug("Found search button", selector=selector)
                    break
            except PlaywrightTimeout:
                continue
        
        if not search_button:
            raise NavigationError("Could not find search button/icon")
        
        await search_button.click()
        
        # Wait for search input to appear
        search_input = await page.wait_for_selector(
            "input[type='search'], input[name='q'], .search__input, input[placeholder*='Search' i]",
            timeout=5000
        )
        
        # Type product name and submit
        await search_input.fill(product_name)
        await search_input.press("Enter")
        
        # Wait for search results
        await page.wait_for_load_state("networkidle", timeout=10000)
        
        # Look for product in results - try case-insensitive partial match
        # Use text selector with case-insensitive flag
        product_selectors = [
            f"a[href*='products']:has-text('{product_name}')",
            f"a[href*='products'] >> text=/{product_name}/i",  # Case-insensitive regex
            f".product-item:has-text('{product_name}') a[href*='products']",
        ]
        
        product_link = None
        for selector in product_selectors:
            try:
                product_link = await page.wait_for_selector(selector, timeout=3000)
                if product_link:
                    logger.debug("Found product link", selector=selector)
                    break
            except PlaywrightTimeout:
                continue
        
        if not product_link:
            raise NavigationError(f"Product '{product_name}' not found in search results")
        
        # Click on product
        await product_link.click()
        await page.wait_for_load_state("domcontentloaded")
        
        # Verify we're on product page
        is_product_page = await _verify_product_page(page)
        if not is_product_page:
            raise NavigationError(f"Search result did not lead to product page")
        
        logger.info("Successfully navigated via search", url=page.url)
        return {
            "status": "success",
            "method": "search",
            "current_url": page.url
        }
        
    except PlaywrightTimeout as e:
        raise NavigationError(f"Search navigation timed out: {str(e)}")
    except Exception as e:
        raise NavigationError(f"Search navigation failed: {str(e)}")
