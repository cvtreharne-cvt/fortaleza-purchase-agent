"""Shared pytest fixtures for all tests."""

import pytest
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.login import login_to_account
from src.tools.cart import add_to_cart

setup_logging()

# Use an in-stock product for testing
TEST_PRODUCT_URL = "https://www.bittersandbottles.com/collections/rum/products/blackwell-jamaican-black-gold-reserve-rum"


@pytest.fixture
async def browser():
    """Browser fixture for tests."""
    async with managed_browser():
        yield get_browser_manager()


@pytest.fixture
async def page(browser):
    """Create a new page for each test."""
    page = await browser.new_page()
    yield page
    await page.close()


@pytest.fixture
async def authenticated_page(browser):
    """Page with user already logged in (age verified automatically)."""
    page = await browser.new_page()
    
    # Login (handles age verification)
    await page.goto("https://www.bittersandbottles.com")
    await login_to_account(page)
    
    yield page
    await page.close()


@pytest.fixture
async def checkout_page(authenticated_page):
    """Page at the checkout step with product in cart."""
    page = authenticated_page
    
    # Navigate to product and add to cart
    await page.goto(TEST_PRODUCT_URL)
    await page.wait_for_timeout(1000)
    
    # Add to cart and proceed to checkout
    await add_to_cart(page, proceed_to_checkout=True)
    
    # Verify we're on checkout page
    assert "checkout" in page.url.lower()
    
    return page
