"""Pytest tests for checkout functionality."""

import pytest
from src.tools.checkout import checkout_and_pay


@pytest.mark.integration
@pytest.mark.slow
async def test_checkout_complete_flow(checkout_page):
    """Test complete checkout flow: pickup selection, payment fields, order summary."""
    page = checkout_page
    
    # Complete checkout in dryrun mode
    result = await checkout_and_pay(page, submit_order=False)
    
    # Verify success and not submitted
    assert result["status"] == "success"
    assert "dryrun" in result["message"].lower() or "NOT submitted" in result["message"]
    assert "checkout" in page.url.lower(), "Should still be on checkout page"
    
    # Verify order summary was extracted
    assert "order_summary" in result
    summary = result["order_summary"]
    
    # Verify all order summary fields are populated
    assert summary["subtotal"] != "unknown", "Subtotal should be extracted"
    assert summary["tax"] != "unknown", "Tax should be extracted"
    assert summary["total"] != "unknown", "Total should be extracted"
    assert summary["pickup_location"] != "unknown", "Pickup location should be detected"
    assert "San Francisco" in summary["pickup_location"], f"Expected San Francisco location, got: {summary['pickup_location']}"


@pytest.mark.integration
@pytest.mark.slow
async def test_checkout_verifies_on_checkout_page(page):
    """Test that checkout fails if not on checkout page."""
    # Try to run checkout on homepage (should fail)
    await page.goto("https://www.bittersandbottles.com")
    
    with pytest.raises(Exception, match="Not on checkout page"):
        await checkout_and_pay(page, submit_order=False)


