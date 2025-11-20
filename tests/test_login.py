"""Pytest tests for login functionality."""

import pytest
from src.tools.login import login_to_account


@pytest.mark.integration
@pytest.mark.slow
async def test_login_success(page):
    """Test login flow with age verification and success validation."""
    # Start at homepage
    await page.goto("https://www.bittersandbottles.com")
    
    # Attempt login (handles age verification automatically)
    result = await login_to_account(page)
    
    # Verify success
    assert result["status"] == "success"
    assert "success" in result["message"].lower()
    
    # Verify we're on account page after login
    assert "/account" in page.url.lower(), f"Should be on account page, but at: {page.url}"
