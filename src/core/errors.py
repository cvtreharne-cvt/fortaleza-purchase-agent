"""Custom exceptions for the Fortaleza Purchase Agent."""


class AgentError(Exception):
    """Base exception for agent errors."""
    pass


class NavigationError(AgentError):
    """Error navigating to a page."""
    pass


class ProtocolError(NavigationError):
    """Protocol error (e.g., trk.bittersandbottles.com redirect issue)."""
    pass


class PageNotFoundError(NavigationError):
    """Page not found (404)."""
    pass


class UnexpectedPageError(NavigationError):
    """Landed on unexpected page."""
    pass


class AuthenticationError(AgentError):
    """Error during login."""
    pass


class TwoFactorRequired(AuthenticationError):
    """Two-factor authentication required."""
    pass


class CaptchaRequired(AuthenticationError):
    """CAPTCHA challenge required."""
    pass


class ProductError(AgentError):
    """Error related to product."""
    pass


class ProductNotFoundError(ProductError):
    """Product not found via search."""
    pass


class ProductSoldOutError(ProductError):
    """Product is sold out."""
    pass


class CartError(AgentError):
    """Error adding to cart."""
    pass


class CheckoutError(AgentError):
    """Error during checkout."""
    pass


class PaymentError(CheckoutError):
    """Error during payment."""
    pass


class ThreeDSecureRequired(PaymentError):
    """3D Secure authentication required."""
    pass


class WebhookError(AgentError):
    """Error related to webhook."""
    pass


class InvalidSignatureError(WebhookError):
    """Invalid HMAC signature."""
    pass


class TimestampTooOldError(WebhookError):
    """Timestamp outside acceptable window."""
    pass


class DuplicateEventError(WebhookError):
    """Event already processed."""
    pass


class ConfigurationError(AgentError):
    """Configuration error."""
    pass


class SecretNotFoundError(AgentError):
    """Secret not found in Secret Manager."""
    pass
