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


@pytest.mark.integration
@pytest.mark.slow
async def test_scoring_selects_best_match(browser):
    """Test that scoring algorithm selects highest-match product from search results.

    This test verifies the product scoring algorithm correctly identifies the best
    matching product when multiple similar products exist. It searches for a specific
    Hamilton rum variant and ensures the scoring algorithm selects the correct one
    instead of a different variant.
    """
    # Use a non-existent URL to force search fallback
    test_url = "https://www.bittersandbottles.com/products/nonexistent-hamilton-product"

    # Search for a specific Hamilton product
    # Expected: Should find "Hamilton Pot Still Blonde" (score: 4/4 words)
    # Should NOT find "Hamilton Breezeway Blend" (score: 1/4 words - only "hamilton")
    result = await navigate_to_product(
        direct_link=test_url,
        product_name="Hamilton Pot Still Blonde"
    )

    # Should use search fallback
    assert result["method"] == "search", "Should use search fallback for non-existent URL"

    # Verify correct product was selected
    url_lower = result["current_url"].lower()
    assert "hamilton" in url_lower, "URL should contain 'hamilton'"
    assert "pot" in url_lower or "still" in url_lower or "blonde" in url_lower, \
        "URL should contain at least one of: pot, still, or blonde"

    # Verify we didn't select a different Hamilton variant
    assert "breezeway" not in url_lower, "Should not select Hamilton Breezeway Blend"

    # Clean up
    if "page" in result:
        await result["page"].close()


@pytest.mark.integration
@pytest.mark.slow
async def test_single_word_product_scoring(browser):
    """Test that scoring works correctly for single-word product names.

    This test verifies the dynamic threshold adjustment for single-word products.
    With MIN_WORD_MATCH_THRESHOLD = 2, single-word products would never match
    unless the threshold is adjusted to min(2, len(name_parts)).
    """
    # Use a non-existent URL to force search fallback
    test_url = "https://www.bittersandbottles.com/products/nonexistent-fortaleza"

    # Search for single-word product name
    result = await navigate_to_product(
        direct_link=test_url,
        product_name="Fortaleza"
    )

    # Should successfully find the product via search
    assert result["method"] == "search", "Should use search fallback"
    assert result["status"] == "success", "Should successfully find product"
    assert "fortaleza" in result["current_url"].lower(), "URL should contain 'fortaleza'"

    # Clean up
    if "page" in result:
        await result["page"].close()


@pytest.mark.integration
@pytest.mark.slow
async def test_multi_word_product_scoring_threshold(browser):
    """Test that multi-word products require minimum threshold of matching words.

    This test verifies that products with multiple words require at least
    MIN_WORD_MATCH_THRESHOLD (2) matching words to be selected, preventing
    false positives from single-word matches.
    """
    # Use a non-existent URL to force search fallback
    test_url = "https://www.bittersandbottles.com/products/nonexistent-product"

    # Search for a multi-word product
    # This should require at least 2 matching words in the URL
    try:
        result = await navigate_to_product(
            direct_link=test_url,
            product_name="Hamilton Pot Still Blonde Rum"
        )

        # If successful, verify it found a good match
        assert result["method"] == "search"
        url_lower = result["current_url"].lower()

        # Count how many words from the search term appear in URL
        search_words = ["hamilton", "pot", "still", "blonde", "rum"]
        matches = sum(1 for word in search_words if word in url_lower)

        # Should have at least 2 matching words
        assert matches >= 2, f"URL should contain at least 2 matching words, found {matches}"

        # Clean up
        if "page" in result:
            await result["page"].close()

    except Exception as e:
        # Acceptable if no product meets the threshold
        assert "not found" in str(e).lower(), f"Should fail with 'not found' error, got: {e}"
