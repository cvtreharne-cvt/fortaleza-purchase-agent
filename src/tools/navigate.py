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

# Timeout constants (in milliseconds)
TRACKING_REDIRECT_WAIT_MS = 5000  # Wait for trk.bittersandbottles.com redirects to complete
SEARCH_BUTTON_TIMEOUT = 2000  # Timeout for finding search button/icon
SEARCH_INPUT_TIMEOUT = 5000  # Timeout for search input field to appear
SEARCH_SUGGESTIONS_WAIT_MS = 1000  # Wait for search suggestions dropdown to populate
SEARCH_RESULTS_WAIT_MS = 2000  # Wait for search results page to load


async def navigate_to_product(
    direct_link: str,
    product_name: Optional[str] = None
) -> dict:
    """
    Navigate to product page using direct link with search fallback.

    Page Lifecycle:
    - Creates a new page via browser.new_page()
    - Returns page in result dict
    - Caller MUST manage page lifecycle (close old page before assigning new one)
    - On failure, page is closed automatically before raising NavigationError

    Args:
        direct_link: Direct URL to product page from email
        product_name: Product name for search fallback

    Returns:
        dict with status, current_url, and page object.
        Caller is responsible for managing the returned page's lifecycle.

    Raises:
        NavigationError: If navigation fails completely
    """
    settings = get_settings()
    browser = get_browser_manager()
    page = await browser.new_page()

    try:
        logger.info("Navigating to direct link", url=direct_link)

        # Navigate and wait for redirects to complete (tracking links may redirect multiple times)
        response = await page.goto(direct_link, wait_until="domcontentloaded")

        # Wait for any JavaScript redirects to complete
        await page.wait_for_timeout(TRACKING_REDIRECT_WAIT_MS)

        # Check if we're still on a tracking domain after redirects (shouldn't happen)
        # Note: Only check for tracking domain, not if URL changed - direct product URLs
        # won't redirect and should stay on the same URL
        if "trk." in page.url:
            logger.warning("Stuck on tracking domain", url=page.url)
            raise ProtocolError(f"Failed to redirect from tracking link: {page.url}")
        
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
            "current_url": page.url,
            "page": page
        }

    except (ProtocolError, PageNotFoundError, UnexpectedPageError, PlaywrightTimeout) as e:
        # Require product_name for search fallback - no default
        if not product_name:
            logger.error("Direct link failed and no product_name provided for search fallback")
            await page.close()
            raise NavigationError(
                f"Direct link failed and no product name specified for search fallback. "
                f"Direct link error: {str(e)}"
            )

        logger.warning(
            "Direct link failed, trying search fallback",
            error=str(e),
            product_name=product_name
        )

        # Fallback to homepage + search
        try:
            search_result = await _search_for_product(
                page,
                product_name
            )
            return search_result
        except Exception as search_error:
            logger.error("Search fallback also failed", error=str(search_error))
            # Close page on complete failure
            await page.close()
            raise NavigationError(
                f"Both direct link and search failed. "
                f"Direct: {str(e)}, Search: {str(search_error)}"
            )


async def _verify_product_page(page: Page) -> bool:
    """
    Verify that we're on a product page.

    Args:
        page: Playwright page

    Returns:
        True if on product page, False otherwise
    """
    try:
        # Simple check: URL contains '/products/' and we're not on a collection/search page
        url = page.url
        if '/products/' in url and '/search' not in url and '/collections' not in url:
            logger.debug("URL indicates product page", url=url)

            # Check for essential product page indicators
            has_price = await page.query_selector(".price, [data-price], .product-price") is not None
            has_add_to_cart = await page.query_selector("button[name='add'], .add-to-cart, [data-add-to-cart]") is not None

            # If we have price or add to cart button, it's a product page
            if has_price or has_add_to_cart:
                logger.debug("Product page verified", has_price=has_price, has_add_to_cart=has_add_to_cart)
                return True

        return False

    except Exception as e:
        logger.warning("Error verifying product page", error=str(e))
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
    age_verified = False
    if age_result["status"] == "success":
        logger.info("Age verification completed before search")
        age_verified = True
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
                search_button = await page.wait_for_selector(selector, timeout=SEARCH_BUTTON_TIMEOUT)
                if search_button:
                    logger.debug("Found search button", selector=selector)
                    break
            except PlaywrightTimeout:
                continue
        
        if not search_button:
            raise NavigationError("Could not find search button/icon")
        
        await search_button.click()
        
        # Check for age verification again after clicking (modal may appear now)
        # But skip if we already verified - no need to wait for a modal that won't appear
        if not age_verified:
            age_result = await verify_age(page)
            if age_result["status"] == "success":
                logger.info("Age verification completed after search click")
            elif age_result["status"] == "error":
                raise NavigationError(f"Age verification failed: {age_result['message']}")
        else:
            logger.debug("Skipping second age verification check (already verified)")
        
        # Wait for search input to appear
        search_input = await page.wait_for_selector(
            "input[type='search'], input[name='q'], .search__input, input[placeholder*='Search' i]",
            timeout=SEARCH_INPUT_TIMEOUT
        )
        
        # Type product name to show search suggestions
        await search_input.fill(product_name)

        # Wait for search suggestions dropdown to populate
        await page.wait_for_timeout(SEARCH_SUGGESTIONS_WAIT_MS)
        
        # Look for product in the suggestions dropdown (under "Products" section)
        # Note: Suggestions contain both search queries (/search?q=) and products (/products/)
        # We want the product link, not the search query link
        product_name_lower = product_name.lower().replace(' ', '-')
        suggestion_selectors = [
            f"a[href^='/products/'][href*='{product_name_lower}']",  # Product link (not search)
            f".predictive-search a[href^='/products/'][href*='{product_name_lower}']",
            f"a[href*='products/{product_name_lower}']",  # More specific product path
        ]
        
        product_link = None
        for selector in suggestion_selectors:
            product_link = await page.query_selector(selector)
            if product_link:
                logger.info("Found product in search suggestions", selector=selector)
                break
        
        if not product_link:
            # Fallback: press Enter and go to search results page
            logger.info("Product not in suggestions, trying full search results")
            await search_input.press("Enter")
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(SEARCH_RESULTS_WAIT_MS)
            
            # Try to find in search results
            # Be more flexible with matching - split product name into key words
            # For "Hamilton Grass Skirt Blend Rum", try matching on "hamilton" and "grass"
            name_parts = product_name_lower.split('-')

            result_selectors = [
                f"a[href*='{product_name_lower}'][href*='products']",  # Exact match
                f".productitem a[href*='{product_name_lower}']",       # Product item with exact
                f"a[href*='products'][href*='{name_parts[0]}']",       # First word (e.g., "hamilton")
                ".product-item a[href*='products']",                    # Any product link
                "a.product-link[href*='products']",                     # Product link class
            ]

            for selector in result_selectors:
                try:
                    product_link = await page.query_selector(selector)
                    if product_link:
                        href = await product_link.get_attribute('href')
                        logger.debug("Found product link in results", selector=selector, href=href)
                        break
                except Exception:
                    continue
        
        if not product_link:
            raise NavigationError(f"Product '{product_name}' not found in search suggestions or results")
        
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
            "current_url": page.url,
            "page": page
        }
        
    except PlaywrightTimeout as e:
        raise NavigationError(f"Search navigation timed out: {str(e)}")
    except Exception as e:
        raise NavigationError(f"Search navigation failed: {str(e)}")
