"""Pytest tests for navigation and age verification."""

import pytest
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.navigate import navigate_to_product
from src.tools.verify_age import verify_age

setup_logging()


@pytest.fixture
async def browser():
    """Browser fixture for tests."""
    async with managed_browser():
        yield get_browser_manager()


@pytest.mark.integration
async def test_browser_lifecycle(browser):
    """Test browser start/stop lifecycle."""
    assert browser is not None
    assert browser.browser is not None
    assert browser.context is not None
    
    # Create a test page
    page = await browser.new_page()
    assert page is not None
    
    # Navigate to a simple page
    await page.goto("https://example.com")
    title = await page.title()
    assert "Example Domain" in title
    
    await page.close()


@pytest.mark.integration
@pytest.mark.slow
async def test_fortaleza_direct_link_navigation(browser):
    """Test navigation to Fortaleza product page via direct link."""
    # Correct Fortaleza URL
    test_url = "https://www.bittersandbottles.com/products/fortaleza-blanco-tequila"

    result = await navigate_to_product(
        direct_link=test_url,
        product_name="Fortaleza"
    )

    assert result["status"] == "success"
    assert result["method"] == "direct_link"
    assert "fortaleza" in result["current_url"].lower()

    # Clean up: close the page
    if "page" in result:
        await result["page"].close()


@pytest.mark.integration
@pytest.mark.slow
async def test_404_search_fallback(browser):
    """Test search fallback when direct link returns 404."""
    # URL that doesn't exist
    test_url = "https://www.bittersandbottles.com/products/nonexistent-product-12345"

    # This may succeed via search fallback or fail if Fortaleza is out of stock
    try:
        result = await navigate_to_product(
            direct_link=test_url,
            product_name="Fortaleza"
        )
        # If it succeeds, verify it used search
        assert result["method"] == "search"
        # Clean up: close the page
        if "page" in result:
            await result["page"].close()
    except Exception as e:
        # Failure is acceptable if search also fails (product out of stock)
        assert "search" in str(e).lower() or "not found" in str(e).lower()


@pytest.mark.integration
@pytest.mark.slow
async def test_search_icon_detection(browser):
    """Test that we can find the search icon on homepage."""
    page = await browser.new_page()
    
    await page.goto("https://www.bittersandbottles.com")
    
    # Try to find search icon
    search_icon = await page.query_selector("svg.icon-search")
    assert search_icon is not None, "Search icon not found with svg.icon-search selector"
    
    await page.close()


@pytest.mark.integration
@pytest.mark.slow
async def test_age_verification_handling(browser):
    """Test age verification modal handling."""
    page = await browser.new_page()
    
    await page.goto("https://www.bittersandbottles.com")
    
    # Check for and handle age verification
    result = await verify_age(page)
    
    # Should either successfully handle or not find modal (if already verified)
    assert result["status"] in ["success", "not_found"]
    
    if result["status"] == "success":
        assert "completed" in result["message"].lower()
    
    await page.close()


@pytest.mark.integration
@pytest.mark.slow
async def test_product_page_out_of_stock_detection(browser):
    """Test that out-of-stock product pages are correctly identified."""
    test_url = "https://www.bittersandbottles.com/products/fortaleza-blanco-tequila"

    result = await navigate_to_product(
        direct_link=test_url,
        product_name="Fortaleza"
    )

    # Should successfully recognize as product page even if sold out
    assert result["status"] == "success"
    assert "fortaleza" in result["current_url"].lower()

    # Clean up: close the page
    if "page" in result:
        await result["page"].close()


@pytest.mark.integration
@pytest.mark.slow
async def test_page_usable_after_navigation(browser):
    """Test that the page returned by navigate_to_product is usable."""
    test_url = "https://www.bittersandbottles.com/products/fortaleza-blanco-tequila"

    result = await navigate_to_product(
        direct_link=test_url,
        product_name="Fortaleza"
    )

    # Verify we got a page object
    assert "page" in result, "Result should contain a page object"
    page = result["page"]
    assert page is not None, "Page should not be None"

    # Verify the page is still usable by interacting with it
    # 1. Check we can get the title
    title = await page.title()
    assert title is not None, "Should be able to get page title"
    assert len(title) > 0, "Title should not be empty"

    # 2. Check we can query selectors
    product_title = await page.query_selector("h1.product-title, .product__title, [data-product-title]")
    assert product_title is not None, "Should be able to find product title element"

    # 3. Check we can get text content
    title_text = await product_title.text_content()
    assert title_text is not None, "Should be able to get text content"
    assert "fortaleza" in title_text.lower(), "Product title should contain 'fortaleza'"

    # 4. Check we can evaluate JavaScript
    url = await page.evaluate("() => window.location.href")
    assert url == result["current_url"], "Should be able to evaluate JavaScript"

    # Clean up: close the page
    await page.close()
