"""HTTP client for the external browser worker (Node Playwright service)."""

from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from .config import get_settings, Mode
from .errors import (
    NavigationError,
    TwoFactorRequired,
    CaptchaRequired,
    ProductSoldOutError,
    ThreeDSecureRequired,
    ConfigurationError,
)
from .logging import get_logger

logger = get_logger(__name__)


def _redact_sensitive(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive fields from payload for logging."""
    if not isinstance(data, dict):
        return data

    redacted = {}
    for key, value in data.items():
        if key == "payment" and isinstance(value, dict):
            # Redact all payment fields
            redacted[key] = {k: "***REDACTED***" for k in value.keys()}
        elif any(s in key.lower() for s in ["password", "cc_", "cvv", "secret", "token", "key"]):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = _redact_sensitive(value)
        else:
            redacted[key] = value
    return redacted


def is_enabled() -> bool:
    """Return True if browser worker URL is configured."""
    settings = get_settings()
    return bool(settings.browser_worker_url)


def _base_url() -> str:
    settings = get_settings()
    url = settings.browser_worker_url.rstrip("/")  # type: ignore[union-attr]

    # Enforce HTTPS in production mode to protect sensitive data in transit
    # Local development (dryrun/test) can use http://localhost
    if settings.mode == Mode.PROD and not url.startswith("https://"):
        raise ConfigurationError(
            "BROWSER_WORKER_URL must use HTTPS in production mode. "
            f"Got: {url}. Use https://your-worker-url for production."
        )

    return url


async def _post_json(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Send POST to browser worker and return JSON."""
    settings = get_settings()
    url = urljoin(_base_url() + "/", endpoint.lstrip("/"))

    # Log request with sensitive data redacted
    safe_payload = _redact_sensitive(payload)
    logger.debug(f"Browser worker request: {endpoint}", payload=safe_payload)

    async with httpx.AsyncClient(timeout=settings.browser_worker_timeout) as client:
        resp = await client.post(url, json=payload)
        data = resp.json()
        if resp.status_code >= 400:
            message = data.get("message", f"Browser worker error {resp.status_code}")
            error_type = data.get("error_type")
            _raise_for_error(message, error_type)
        return data


def _raise_for_error(message: str, error_type: Optional[str]) -> None:
    """Map worker error types to Python exceptions."""
    if error_type == "TwoFactorRequired":
        raise TwoFactorRequired(message)
    if error_type == "CaptchaRequired":
        raise CaptchaRequired(message)
    if error_type == "ProductSoldOut":
        raise ProductSoldOutError(message)
    if error_type == "ThreeDSecureRequired":
        raise ThreeDSecureRequired(message)
    raise NavigationError(message)


async def navigate(direct_link: Optional[str], product_name: Optional[str], dob: Optional[Dict[str, str]]):
    """Navigate to a product page (direct link with search fallback)."""
    payload = {"direct_link": direct_link, "product_name": product_name, "dob": dob}
    return await _post_json("/navigate", payload)


async def verify_age(dob: Optional[Dict[str, str]]):
    """Verify age gate if present."""
    return await _post_json("/verify-age", dob or {})


async def login(email: str, password: str, dob: Optional[Dict[str, str]]):
    """Login to account via worker."""
    return await _post_json("/login", {"email": email, "password": password, "dob": dob})


async def add_to_cart(proceed_to_checkout: bool = False):
    """Add current product to cart."""
    return await _post_json("/add-to-cart", {"proceed_to_checkout": proceed_to_checkout})


async def checkout(submit_order: bool, payment: Dict[str, str], pickup_preference: Optional[str] = None):
    """Complete checkout."""
    return await _post_json(
        "/checkout",
        {"submit_order": submit_order, "payment": payment, "pickup_preference": pickup_preference},
    )


async def reset():
    """Reset browser worker state."""
    return await _post_json("/reset", {})
