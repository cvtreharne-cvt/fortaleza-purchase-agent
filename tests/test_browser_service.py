"""Unit tests for browser_service HTTP client."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.core import browser_service
from src.core.errors import (
    NavigationError,
    TwoFactorRequired,
    CaptchaRequired,
    ProductSoldOutError,
    ThreeDSecureRequired,
)


@pytest.fixture
def mock_settings():
    """Mock settings with browser worker URL."""
    with patch("src.core.browser_service.get_settings") as mock:
        settings = MagicMock()
        settings.browser_worker_url = "http://localhost:3001"
        settings.browser_worker_timeout = 30.0
        mock.return_value = settings
        yield mock


@pytest.fixture
def mock_settings_disabled():
    """Mock settings with no browser worker URL."""
    with patch("src.core.browser_service.get_settings") as mock:
        settings = MagicMock()
        settings.browser_worker_url = None
        mock.return_value = settings
        yield mock


def test_is_enabled_returns_true_when_url_configured(mock_settings):
    """Test is_enabled returns True when worker URL is configured."""
    assert browser_service.is_enabled() is True


def test_is_enabled_returns_false_when_url_not_configured(mock_settings_disabled):
    """Test is_enabled returns False when worker URL is not configured."""
    assert browser_service.is_enabled() is False


@pytest.mark.asyncio
async def test_navigate_success(mock_settings):
    """Test successful navigation request."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "current_url": "https://example.com/product",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        result = await browser_service.navigate(
            direct_link="https://example.com/product",
            product_name=None,
            dob=None,
        )

        assert result["status"] == "success"
        assert result["current_url"] == "https://example.com/product"


@pytest.mark.asyncio
async def test_navigate_two_factor_error(mock_settings):
    """Test navigation raises TwoFactorRequired on worker error."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "status": "error",
        "message": "Two-factor authentication required",
        "error_type": "TwoFactorRequired",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(TwoFactorRequired) as exc_info:
            await browser_service.navigate(
                direct_link="https://example.com/product",
                product_name=None,
                dob=None,
            )

        assert "Two-factor authentication required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_login_captcha_error(mock_settings):
    """Test login raises CaptchaRequired on worker error."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "status": "error",
        "message": "CAPTCHA detected",
        "error_type": "CaptchaRequired",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(CaptchaRequired) as exc_info:
            await browser_service.login(
                email="test@example.com", password="password", dob=None
            )

        assert "CAPTCHA detected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_add_to_cart_sold_out_error(mock_settings):
    """Test add_to_cart raises ProductSoldOutError on worker error."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "status": "error",
        "message": "Product sold out",
        "error_type": "ProductSoldOut",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ProductSoldOutError) as exc_info:
            await browser_service.add_to_cart(proceed_to_checkout=False)

        assert "Product sold out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_checkout_3ds_error(mock_settings):
    """Test checkout raises ThreeDSecureRequired on worker error."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "status": "error",
        "message": "3D Secure verification required",
        "error_type": "ThreeDSecureRequired",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(ThreeDSecureRequired) as exc_info:
            await browser_service.checkout(
                submit_order=True,
                payment={"cc_number": "1234"},
                pickup_preference=None,
            )

        assert "3D Secure verification required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_checkout_generic_error(mock_settings):
    """Test checkout raises NavigationError for unknown error types."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json.return_value = {
        "status": "error",
        "message": "Internal server error",
        "error_type": "UnknownError",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(NavigationError) as exc_info:
            await browser_service.checkout(
                submit_order=True,
                payment={"cc_number": "1234"},
                pickup_preference=None,
            )

        assert "Internal server error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_checkout_missing_error_type(mock_settings):
    """Test checkout raises NavigationError when error_type is missing."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "status": "error",
        "message": "Something went wrong",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(NavigationError) as exc_info:
            await browser_service.checkout(
                submit_order=True,
                payment={"cc_number": "1234"},
                pickup_preference=None,
            )

        assert "Something went wrong" in str(exc_info.value)


@pytest.mark.asyncio
async def test_verify_age_success(mock_settings):
    """Test successful age verification."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "message": "Age verification completed",
    }

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        result = await browser_service.verify_age(
            dob={"dob_month": "1", "dob_day": "1", "dob_year": "1990"}
        )

        assert result["status"] == "success"


@pytest.mark.asyncio
async def test_reset_success(mock_settings):
    """Test successful browser reset."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "reset"}

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        result = await browser_service.reset()

        assert result["status"] == "reset"


@pytest.mark.asyncio
async def test_http_timeout_handling(mock_settings):
    """Test that HTTP timeout is properly configured."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success"}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        await browser_service.navigate(
            direct_link="https://example.com", product_name=None, dob=None
        )

        # Verify that AsyncClient was initialized with correct timeout
        mock_client_class.assert_called_once_with(timeout=30.0)


@pytest.mark.asyncio
async def test_network_error_propagation(mock_settings):
    """Test that network errors are properly propagated."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection failed")
        )

        with pytest.raises(httpx.ConnectError):
            await browser_service.navigate(
                direct_link="https://example.com", product_name=None, dob=None
            )
