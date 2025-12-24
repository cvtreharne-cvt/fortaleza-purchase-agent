"""Webhook endpoint with HMAC signature validation."""

import hmac
import hashlib
import threading
import time
from typing import Dict, Set, Tuple

from fastapi import APIRouter, Header, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field

from agents.fortaleza_agent.agent import run_purchase_agent
from ..core.config import get_settings
from ..core.errors import InvalidSignatureError, TimestampTooOldError, DuplicateEventError
from ..core.logging import get_logger
from ..core.secrets import get_secret_manager

logger = get_logger(__name__)
router = APIRouter()

# In-memory store for processed event IDs (in production, use Redis or database)
_processed_events: Set[str] = set()

# Rate limiting for approval endpoints (IP address -> (request_count, window_start_time))
# Limit: 10 requests per minute per IP
_rate_limit_store: Dict[str, Tuple[int, float]] = {}
_rate_limit_lock = threading.Lock()
RATE_LIMIT_REQUESTS = 10  # Max requests per window
RATE_LIMIT_WINDOW = 60  # Window duration in seconds
RATE_LIMIT_CLEANUP_INTERVAL = 300  # Cleanup every 5 minutes
_last_rate_limit_cleanup = time.time()


class WebhookPayload(BaseModel):
    """Webhook payload from Raspberry Pi Gmail monitor."""
    event_id: str = Field(..., description="Unique event identifier for idempotency")
    received_at: str = Field(..., description="ISO 8601 timestamp when email was received")
    subject: str = Field(..., description="Email subject line")
    direct_link: str = Field(..., description="Direct link to product page")
    product_hint: str = Field(..., description="Product name hint from email")
    mode: str | None = Field(default=None, description="Optional mode override: dryrun, test, or prod")


def cleanup_rate_limit_store() -> None:
    """Clean up old entries from rate limit store to prevent memory leak."""
    global _last_rate_limit_cleanup
    current_time = time.time()

    # Only cleanup if enough time has passed
    if current_time - _last_rate_limit_cleanup < RATE_LIMIT_CLEANUP_INTERVAL:
        return

    with _rate_limit_lock:
        # Remove entries older than 2x the window duration
        cutoff_time = current_time - (2 * RATE_LIMIT_WINDOW)
        ips_to_remove = [
            ip for ip, (_, window_start) in _rate_limit_store.items()
            if window_start < cutoff_time
        ]

        for ip in ips_to_remove:
            del _rate_limit_store[ip]

        if ips_to_remove:
            logger.debug("Cleaned up rate limit store", removed_count=len(ips_to_remove))

        _last_rate_limit_cleanup = current_time


def check_rate_limit(client_ip: str) -> None:
    """
    Check if client has exceeded rate limit for approval endpoints.

    Args:
        client_ip: Client IP address

    Raises:
        HTTPException: If rate limit exceeded (429 Too Many Requests)
    """
    from ..core.config import get_settings, Mode

    # Skip rate limiting in test mode
    settings = get_settings()
    if settings.mode == Mode.TEST:
        return

    current_time = time.time()

    # Periodic cleanup to prevent memory leak
    cleanup_rate_limit_store()

    with _rate_limit_lock:
        # Get existing rate limit data or initialize new entry
        if client_ip not in _rate_limit_store:
            _rate_limit_store[client_ip] = (0, current_time)

        request_count, window_start = _rate_limit_store[client_ip]

        # Check if we're in a new window
        if current_time - window_start > RATE_LIMIT_WINDOW:
            # Reset counter for new window
            _rate_limit_store[client_ip] = (1, current_time)
            return

        # Check if limit exceeded
        if request_count >= RATE_LIMIT_REQUESTS:
            logger.warning(
                "Rate limit exceeded for approval endpoint",
                client_ip=client_ip,
                requests=request_count,
                window=RATE_LIMIT_WINDOW
            )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds.",
                headers={"Retry-After": str(int(RATE_LIMIT_WINDOW - (current_time - window_start)))}
            )

        # Increment counter
        _rate_limit_store[client_ip] = (request_count + 1, window_start)


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
        logger.warning(
            "Invalid timestamp - exceeds tolerance",
            timestamp=timestamp,
            age_seconds=age,
            tolerance_seconds=tolerance_seconds,
            security_event="invalid_timestamp",
            severity="WARNING"
        )
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
        logger.warning(
            "Duplicate event detected - possible replay attack",
            event_id=event_id,
            security_event="duplicate_event",
            severity="WARNING"
        )
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
    background_tasks: BackgroundTasks,
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
        
        # Get client IP for security logging
        client_ip = request.client.host if request.client else "unknown"

        # Verify HMAC signature
        if not verify_hmac_signature(body, x_timestamp, x_signature, webhook_secret):
            logger.error(
                "Invalid webhook signature",
                event_id=payload.event_id,
                timestamp=x_timestamp,
                client_ip=client_ip,
                security_event="failed_hmac",  # For GCP log-based metrics
                severity="WARNING"
            )
            raise InvalidSignatureError("Invalid HMAC signature")
        
        # Check idempotency
        check_idempotency(payload.event_id)
        
        logger.info(
            "Webhook received and validated",
            event_id=payload.event_id,
            product_hint=payload.product_hint,
            direct_link=payload.direct_link,
            mode_override=payload.mode
        )

        # Trigger agent execution in background
        background_tasks.add_task(
            run_purchase_agent,
            direct_link=payload.direct_link,
            product_name=payload.product_hint,
            event_id=payload.event_id,
            mode_override=payload.mode
        )

        logger.info(
            "Agent execution queued",
            event_id=payload.event_id
        )

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


@router.api_route("/approval/{run_id}/approve", methods=["GET", "POST"])
async def approve_purchase(run_id: str, request: Request):
    """
    Handle purchase approval callback from Pushover.

    Args:
        run_id: Unique identifier for the agent run
        request: FastAPI request object (for rate limiting)

    Returns:
        Approval status and details
    """
    # Rate limiting (prevent brute force attacks on run_id)
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    from ..core.approval import approve_request, get_approval_status

    success = approve_request(run_id)

    if not success:
        approval = get_approval_status(run_id)
        if not approval:
            logger.warning("Approval attempt for unknown run_id", run_id=run_id)
            raise HTTPException(status_code=404, detail=f"Approval request {run_id} not found")
        else:
            logger.warning("Approval attempt failed", run_id=run_id, reason="expired or already decided")
            raise HTTPException(status_code=400, detail="Approval request expired or already decided")

    logger.info("Purchase approved via callback", run_id=run_id)

    return {
        "status": "approved",
        "run_id": run_id,
        "message": "Purchase approved successfully"
    }


@router.api_route("/approval/{run_id}/reject", methods=["GET", "POST"])
async def reject_purchase(run_id: str, request: Request):
    """
    Handle purchase rejection callback from Pushover.

    Args:
        run_id: Unique identifier for the agent run
        request: FastAPI request object (for rate limiting)

    Returns:
        Rejection status and details
    """
    # Rate limiting (prevent brute force attacks on run_id)
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    from ..core.approval import reject_request, get_approval_status

    success = reject_request(run_id)

    if not success:
        approval = get_approval_status(run_id)
        if not approval:
            logger.warning("Rejection attempt for unknown run_id", run_id=run_id)
            raise HTTPException(status_code=404, detail=f"Approval request {run_id} not found")
        else:
            logger.warning("Rejection attempt failed", run_id=run_id, reason="expired or already decided")
            raise HTTPException(status_code=400, detail="Approval request expired or already decided")

    logger.info("Purchase rejected via callback", run_id=run_id)

    return {
        "status": "rejected",
        "run_id": run_id,
        "message": "Purchase rejected successfully"
    }


@router.get("/approval/{run_id}/status")
async def get_approval_status_endpoint(run_id: str, request: Request):
    """
    Get current status of an approval request.

    Args:
        run_id: Unique identifier for the agent run
        request: FastAPI request object (for rate limiting)

    Returns:
        Current approval status
    """
    # Rate limiting (prevent brute force attacks on run_id)
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    from ..core.approval import get_approval_status

    approval = get_approval_status(run_id)

    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval request {run_id} not found")

    return {
        "run_id": run_id,
        "status": approval["status"],
        "decision": approval["decision"],
        "created_at": approval["created_at"].isoformat(),
        "expires_at": approval["expires_at"].isoformat(),
        "decided_at": approval["decided_at"].isoformat() if approval["decided_at"] else None
    }
