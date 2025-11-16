"""Webhook endpoint with HMAC signature validation."""

import hmac
import hashlib
import time
from typing import Set

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..core.errors import InvalidSignatureError, TimestampTooOldError, DuplicateEventError
from ..core.logging import get_logger
from ..core.secrets import get_secret_manager

logger = get_logger(__name__)
router = APIRouter()

# In-memory store for processed event IDs (in production, use Redis or database)
_processed_events: Set[str] = set()


class WebhookPayload(BaseModel):
    """Webhook payload from Raspberry Pi Gmail monitor."""
    event_id: str = Field(..., description="Unique event identifier for idempotency")
    received_at: str = Field(..., description="ISO 8601 timestamp when email was received")
    subject: str = Field(..., description="Email subject line")
    direct_link: str = Field(..., description="Direct link to product page")
    product_hint: str = Field(..., description="Product name hint from email")


def verify_hmac_signature(
    payload: bytes,
    timestamp: str,
    signature: str,
    secret: str
) -> bool:
    """
    Verify HMAC-SHA256 signature of webhook request.
    
    Args:
        payload: Raw request body bytes
        timestamp: Request timestamp from X-Timestamp header
        signature: HMAC signature from X-Signature header
        secret: Shared secret for HMAC computation
        
    Returns:
        True if signature is valid, False otherwise
    """
    # Construct message: timestamp + payload
    message = f"{timestamp}.{payload.decode('utf-8')}"
    
    # Compute expected signature
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(signature, expected_signature)


def verify_timestamp(timestamp: str, tolerance_seconds: int = 300) -> None:
    """
    Verify that timestamp is within acceptable window.
    
    Args:
        timestamp: Unix timestamp as string
        tolerance_seconds: Maximum age of request in seconds
        
    Raises:
        TimestampTooOldError: If timestamp is outside tolerance window
    """
    try:
        request_time = int(timestamp)
    except ValueError:
        raise TimestampTooOldError(f"Invalid timestamp format: {timestamp}")
    
    current_time = int(time.time())
    age = abs(current_time - request_time)
    
    if age > tolerance_seconds:
        raise TimestampTooOldError(
            f"Request timestamp is {age}s old, exceeds tolerance of {tolerance_seconds}s"
        )


def check_idempotency(event_id: str) -> None:
    """
    Check if event has already been processed.
    
    Args:
        event_id: Unique event identifier
        
    Raises:
        DuplicateEventError: If event has already been processed
    """
    if event_id in _processed_events:
        raise DuplicateEventError(f"Event {event_id} has already been processed")
    
    # Mark as processed
    _processed_events.add(event_id)
    
    # Limit memory usage (keep last 1000 events)
    if len(_processed_events) > 1000:
        # Remove oldest entries (simple approach; in production use LRU cache or TTL)
        oldest = list(_processed_events)[:100]
        _processed_events.difference_update(oldest)


@router.post("/webhook/pi")
async def handle_webhook(
    request: Request,
    payload: WebhookPayload,
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    """
    Handle webhook from Raspberry Pi Gmail monitor.
    
    Expected headers:
    - X-Timestamp: Unix timestamp of request
    - X-Signature: HMAC-SHA256 signature
    
    Request body: WebhookPayload JSON
    """
    settings = get_settings()
    
    # Get raw request body
    body = await request.body()
    
    try:
        # Verify timestamp
        verify_timestamp(x_timestamp, settings.webhook_timestamp_tolerance)
        
        # Get webhook secret
        secret_manager = get_secret_manager()
        webhook_secret = secret_manager.get_webhook_secret()
        
        # Verify HMAC signature
        if not verify_hmac_signature(body, x_timestamp, x_signature, webhook_secret):
            logger.error(
                "Invalid webhook signature",
                event_id=payload.event_id,
                timestamp=x_timestamp
            )
            raise InvalidSignatureError("Invalid HMAC signature")
        
        # Check idempotency
        check_idempotency(payload.event_id)
        
        logger.info(
            "Webhook received and validated",
            event_id=payload.event_id,
            product_hint=payload.product_hint,
            direct_link=payload.direct_link
        )
        
        # TODO: Trigger agent execution here
        # For now, just return success
        return {
            "status": "accepted",
            "event_id": payload.event_id,
            "message": "Webhook received and agent execution queued"
        }
        
    except (InvalidSignatureError, TimestampTooOldError, DuplicateEventError) as e:
        logger.warning(
            "Webhook validation failed",
            error=str(e),
            event_id=payload.event_id
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            "Unexpected error processing webhook",
            error=str(e),
            event_id=payload.event_id
        )
        raise HTTPException(status_code=500, detail="Internal server error")
