"""Pytest tests for cart functionality."""

import pytest
from src.tools.cart import add_to_cart
from src.core.errors import ProductSoldOutError

# Use an in-stock product for testing
TEST_PRODUCT_URL = "https://www.bittersandbottles.com/collections/rum/products/blackwell-jamaican-black-gold-reserve-rum"


@pytest.fixture
async def product_page(authenticated_page):
    """Page on a product, ready to add to cart."""
    page = authenticated_page
    await page.goto(TEST_PRODUCT_URL)
    await page.wait_for_load_state("domcontentloaded")
    return page


@pytest.mark.integration
@pytest.mark.slow
async def test_add_to_cart_and_checkout(product_page):
    """Test add to cart with checkout flow and cart drawer verification."""
    page = product_page
    
    # Add to cart and proceed to checkout
    result = await add_to_cart(page, proceed_to_checkout=True)
    
    # Verify success
    assert result["status"] == "success"
    assert "checkout" in result["message"].lower()
    
    # Verify we're on checkout page
    assert "checkout" in page.url.lower() or "cart" in page.url.lower()


@pytest.mark.integration
@pytest.mark.slow
async def test_add_to_cart_sold_out_product(authenticated_page):
    """Test that sold out products raise ProductSoldOutError."""
    page = authenticated_page
    
    # Navigate to Fortaleza (currently sold out)
    await page.goto("https://www.bittersandbottles.com/products/fortaleza-blanco-tequila")
    await page.wait_for_load_state("domcontentloaded")
    
    # Try to add to cart - should raise ProductSoldOutError
    with pytest.raises(ProductSoldOutError):
        await add_to_cart(page)


