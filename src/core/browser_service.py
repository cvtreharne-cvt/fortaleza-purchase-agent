"""HTTP client for the external browser worker (Node Playwright service)."""

from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from .config import get_settings
from .errors import (
    NavigationError,
    TwoFactorRequired,
    CaptchaRequired,
    ProductSoldOutError,
    ThreeDSecureRequired,
)
from .logging import get_logger

logger = get_logger(__name__)


def is_enabled() -> bool:
    """Return True if browser worker URL is configured."""
    settings = get_settings()
    return bool(settings.browser_worker_url)


def _base_url() -> str:
    settings = get_settings()
    return settings.browser_worker_url.rstrip("/")  # type: ignore[union-attr]


async def _post_json(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Send POST to browser worker and return JSON."""
    settings = get_settings()
    url = urljoin(_base_url() + "/", endpoint.lstrip("/"))
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
