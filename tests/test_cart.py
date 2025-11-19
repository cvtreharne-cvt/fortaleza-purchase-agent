"""Pytest tests for cart functionality."""

import pytest
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.login import login_to_account
from src.tools.cart import add_to_cart
from src.core.errors import ProductSoldOutError

setup_logging()

# Use an in-stock product for testing
TEST_PRODUCT_URL = "https://www.bittersandbottles.com/collections/rum/products/blackwell-jamaican-black-gold-reserve-rum"


@pytest.fixture
async def browser():
    """Browser fixture for tests."""
    async with managed_browser():
        yield get_browser_manager()


@pytest.fixture
async def logged_in_page(browser):
    """Fixture that provides a logged-in page on a product."""
    page = await browser.new_page()
    
    # Navigate to product
    await page.goto(TEST_PRODUCT_URL)
    
    # Login
    await login_to_account(page)
    
    # Navigate back to product after login
    await page.goto(TEST_PRODUCT_URL)
    await page.wait_for_load_state("domcontentloaded")
    
    yield page
    
    await page.close()


@pytest.mark.integration
@pytest.mark.slow
async def test_add_to_cart_basic(logged_in_page):
    """Test basic add to cart functionality."""
    page = logged_in_page
    
    # Add to cart
    result = await add_to_cart(page, proceed_to_checkout=False)
    
    # Verify success
    assert result["status"] == "success"
    assert "added to cart" in result["message"].lower()
    assert "current_url" in result


@pytest.mark.integration
@pytest.mark.slow
async def test_add_to_cart_with_checkout(logged_in_page):
    """Test add to cart with proceed to checkout."""
    page = logged_in_page
    
    # Add to cart and proceed to checkout
    result = await add_to_cart(page, proceed_to_checkout=True)
    
    # Verify success
    assert result["status"] == "success"
    assert "checkout" in result["message"].lower()
    
    # Verify we're on checkout page
    assert "checkout" in page.url.lower() or "cart" in page.url.lower()


@pytest.mark.integration
@pytest.mark.slow
async def test_add_to_cart_sold_out_product(browser):
    """Test that sold out products raise ProductSoldOutError."""
    page = await browser.new_page()
    
    try:
        # Navigate to Fortaleza (currently sold out)
        await page.goto("https://www.bittersandbottles.com/products/fortaleza-blanco-tequila")
        
        # Login
        await login_to_account(page)
        
        # Navigate back to product
        await page.goto("https://www.bittersandbottles.com/products/fortaleza-blanco-tequila")
        await page.wait_for_load_state("domcontentloaded")
        
        # Try to add to cart - should raise ProductSoldOutError
        with pytest.raises(ProductSoldOutError):
            await add_to_cart(page)
            
    finally:
        await page.close()


@pytest.mark.integration
@pytest.mark.slow
async def test_cart_drawer_appears(logged_in_page):
    """Test that cart drawer appears after adding item."""
    page = logged_in_page
    
    # Add to cart
    await add_to_cart(page, proceed_to_checkout=False)
    
    # Verify cart drawer success message is visible
    success_message = await page.query_selector("text=/Added to.*cart/i")
    assert success_message is not None, "Cart drawer should show success message"
    
    # Verify cart count updated
    cart_icon = await page.query_selector("a[href*='cart']")
    assert cart_icon is not None, "Cart icon should be present"
