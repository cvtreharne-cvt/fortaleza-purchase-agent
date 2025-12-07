"""Human approval state management for purchase decisions."""

import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from .logging import get_logger

logger = get_logger(__name__)

# In-memory approval state storage
# In production, consider using Redis for multi-instance deployments
_pending_approvals: Dict[str, dict] = {}
_approvals_lock = threading.Lock()  # Thread safety for concurrent access


def create_approval_request(
    run_id: str,
    order_summary: dict,
    timeout_minutes: int = 10
) -> None:
    """
    Create a pending approval request.

    Args:
        run_id: Unique identifier for this agent run
        order_summary: Order details for human review
        timeout_minutes: How long to wait for approval
    """
    # Clean up old approvals before creating new one (prevents memory leak)
    cleanup_old_approvals()

    with _approvals_lock:
        now = datetime.now(timezone.utc)
        _pending_approvals[run_id] = {
            "status": "pending",
            "order_summary": order_summary,
            "created_at": now,
            "expires_at": now + timedelta(minutes=timeout_minutes),
            "decision": None,
            "decided_at": None
        }

    logger.info(
        "Approval request created",
        run_id=run_id,
        expires_in_minutes=timeout_minutes,
        total=order_summary.get("total", "unknown")
    )


def get_approval_status(run_id: str) -> Optional[dict]:
    """
    Get the current status of an approval request.

    Args:
        run_id: Unique identifier for the agent run

    Returns:
        Approval state dict or None if not found
    """
    with _approvals_lock:
        approval = _pending_approvals.get(run_id)

        if approval and datetime.now(timezone.utc) > approval["expires_at"]:
            # Mark as expired
            if approval["decision"] is None:
                approval["status"] = "expired"
                approval["decision"] = "timeout"
                logger.warning("Approval request expired", run_id=run_id)

        # Return a copy to prevent external mutation
        return approval.copy() if approval else None


def approve_request(run_id: str) -> bool:
    """
    Approve a pending purchase request.

    Args:
        run_id: Unique identifier for the agent run

    Returns:
        True if approval was recorded, False if request not found or expired
    """
    with _approvals_lock:
        approval = _pending_approvals.get(run_id)

        if not approval:
            logger.warning("Approval attempt for unknown run_id", run_id=run_id)
            return False

        if datetime.now(timezone.utc) > approval["expires_at"]:
            logger.warning("Approval attempt after expiration", run_id=run_id)
            return False

        if approval["decision"] is not None:
            logger.warning(
                "Approval attempt for already-decided request",
                run_id=run_id,
                existing_decision=approval["decision"]
            )
            return False

        approval["decision"] = "approved"
        approval["status"] = "approved"
        approval["decided_at"] = datetime.now(timezone.utc)

        logger.info("Purchase approved by human", run_id=run_id)
        return True


def reject_request(run_id: str) -> bool:
    """
    Reject a pending purchase request.

    Args:
        run_id: Unique identifier for the agent run

    Returns:
        True if rejection was recorded, False if request not found or expired
    """
    with _approvals_lock:
        approval = _pending_approvals.get(run_id)

        if not approval:
            logger.warning("Rejection attempt for unknown run_id", run_id=run_id)
            return False

        if datetime.now(timezone.utc) > approval["expires_at"]:
            logger.warning("Rejection attempt after expiration", run_id=run_id)
            return False

        if approval["decision"] is not None:
            logger.warning(
                "Rejection attempt for already-decided request",
                run_id=run_id,
                existing_decision=approval["decision"]
            )
            return False

        approval["decision"] = "rejected"
        approval["status"] = "rejected"
        approval["decided_at"] = datetime.now(timezone.utc)

        logger.info("Purchase rejected by human", run_id=run_id)
        return True


def cleanup_old_approvals(max_age_hours: int = 24) -> int:
    """
    Clean up approval requests older than specified age.

    Args:
        max_age_hours: Maximum age in hours

    Returns:
        Number of approvals cleaned up
    """
    with _approvals_lock:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        to_remove = [
            run_id for run_id, approval in _pending_approvals.items()
            if approval["created_at"] < cutoff
        ]

        for run_id in to_remove:
            del _pending_approvals[run_id]

        if to_remove:
            logger.info(
                "Cleaned up old approval requests",
                count=len(to_remove),
                max_age_hours=max_age_hours
            )

        return len(to_remove)


def get_pending_count() -> int:
    """Get count of pending approval requests."""
    with _approvals_lock:
        return sum(
            1 for approval in _pending_approvals.values()
            if approval["status"] == "pending"
        )
