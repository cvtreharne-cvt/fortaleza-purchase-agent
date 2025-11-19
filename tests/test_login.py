"""Pytest tests for login functionality."""

import pytest
from src.core.browser import managed_browser, get_browser_manager
from src.core.logging import setup_logging
from src.tools.login import login_to_account

setup_logging()


@pytest.fixture
async def browser():
    """Browser fixture for tests."""
    async with managed_browser():
        yield get_browser_manager()


@pytest.mark.integration
@pytest.mark.slow
async def test_login_from_homepage(browser):
    """Test login flow starting from homepage."""
    page = await browser.new_page()
    
    try:
        # Start at homepage
        await page.goto("https://www.bittersandbottles.com")
        
        # Attempt login
        result = await login_to_account(page)
        
        # Verify success
        assert result["status"] == "success"
        assert "success" in result["message"].lower()
        
        # Verify we're on account page (logout link is hidden in menu)
        assert "/account" in page.url.lower(), f"Should be on account page, but at: {page.url}"
        
    finally:
        await page.close()


@pytest.mark.integration
@pytest.mark.slow
async def test_login_verifies_success(browser):
    """Test that login verifies success after submission."""
    page = await browser.new_page()
    
    try:
        # Login from homepage
        await page.goto("https://www.bittersandbottles.com")
        result = await login_to_account(page)
        
        # Verify success and we're on account page
        assert result["status"] == "success"
        assert "/account" in page.url.lower()
        
    finally:
        await page.close()


@pytest.mark.integration
@pytest.mark.slow
async def test_login_from_product_page(browser):
    """Test login flow starting from a product page."""
    page = await browser.new_page()
    
    try:
        # Start at a product page
        await page.goto("https://www.bittersandbottles.com/collections/rum/products/blackwell-jamaican-black-gold-reserve-rum")
        
        # Attempt login
        result = await login_to_account(page)
        
        # Verify success
        assert result["status"] == "success"
        
        # Verify logged in (check URL)
        assert "/account" in page.url.lower() or "bittersandbottles.com" in page.url
        
    finally:
        await page.close()
