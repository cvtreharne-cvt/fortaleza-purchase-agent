"""Unit tests for approval module."""
import pytest
from datetime import datetime, timezone, timedelta

from src.core.approval import (
    create_approval_request,
    approve_request,
    reject_request,
    get_approval_status,
    cleanup_old_approvals,
    _pending_approvals,
    _approvals_lock
)


class TestApprovalCreation:
    """Tests for creating approval requests."""

    def test_create_approval_request(self):
        """Test basic approval request creation."""
        create_approval_request("test-create-1", {"total": "$40"}, timeout_minutes=10)

        status = get_approval_status("test-create-1")

        assert status is not None
        assert status["status"] == "pending"
        assert status["decision"] is None
        assert status["order_summary"]["total"] == "$40"
        assert status["created_at"].tzinfo is not None  # Timezone-aware
        assert status["expires_at"].tzinfo is not None  # Timezone-aware

    def test_create_multiple_approvals(self):
        """Test creating multiple approval requests."""
        create_approval_request("test-multi-1", {"total": "$50"})
        create_approval_request("test-multi-2", {"total": "$60"})

        status1 = get_approval_status("test-multi-1")
        status2 = get_approval_status("test-multi-2")

        assert status1 is not None
        assert status2 is not None
        assert status1["order_summary"]["total"] == "$50"
        assert status2["order_summary"]["total"] == "$60"


class TestApprovalDecisions:
    """Tests for approval and rejection."""

    def test_approve_request(self):
        """Test approving a request."""
        create_approval_request("test-approve-1", {"total": "$40"})

        result = approve_request("test-approve-1")

        assert result == True

        status = get_approval_status("test-approve-1")
        assert status["decision"] == "approved"
        assert status["status"] == "approved"
        assert status["decided_at"] is not None
        assert status["decided_at"].tzinfo is not None  # Timezone-aware

    def test_reject_request(self):
        """Test rejecting a request."""
        create_approval_request("test-reject-1", {"total": "$40"})

        result = reject_request("test-reject-1")

        assert result == True

        status = get_approval_status("test-reject-1")
        assert status["decision"] == "rejected"
        assert status["status"] == "rejected"
        assert status["decided_at"] is not None

    def test_double_approval_prevention(self):
        """Test that approving twice fails."""
        create_approval_request("test-double-1", {"total": "$40"})

        # First approval should succeed
        result1 = approve_request("test-double-1")
        assert result1 == True

        # Second approval should fail
        result2 = approve_request("test-double-1")
        assert result2 == False

    def test_approve_after_reject_fails(self):
        """Test that approving after rejection fails."""
        create_approval_request("test-reject-then-approve", {"total": "$40"})

        reject_request("test-reject-then-approve")
        result = approve_request("test-reject-then-approve")

        assert result == False

    def test_approve_unknown_request(self):
        """Test approving non-existent request."""
        result = approve_request("nonexistent-id")
        assert result == False

    def test_reject_unknown_request(self):
        """Test rejecting non-existent request."""
        result = reject_request("nonexistent-id")
        assert result == False


class TestApprovalExpiration:
    """Tests for approval expiration."""

    def test_expired_approval_marked_as_timeout(self):
        """Test that expired approvals are marked as timeout."""
        # Create approval with very short timeout
        create_approval_request("test-expire-1", {"total": "$40"}, timeout_minutes=0)

        # Directly modify the expires_at to be in the past
        with _approvals_lock:
            approval = _pending_approvals.get("test-expire-1")
            approval["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Get status should mark it as expired
        status = get_approval_status("test-expire-1")

        assert status["status"] == "expired"
        assert status["decision"] == "timeout"

    def test_approve_expired_request_fails(self):
        """Test that approving an expired request fails."""
        create_approval_request("test-expire-approve", {"total": "$40"}, timeout_minutes=0)

        # Make it expired
        with _approvals_lock:
            approval = _pending_approvals.get("test-expire-approve")
            approval["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

        result = approve_request("test-expire-approve")
        assert result == False


class TestCleanup:
    """Tests for cleanup functionality."""

    def test_cleanup_old_approvals(self):
        """Test cleanup removes old approvals."""
        # Create an old approval by manipulating created_at
        create_approval_request("test-cleanup-old", {"total": "$40"})

        with _approvals_lock:
            approval = _pending_approvals.get("test-cleanup-old")
            approval["created_at"] = datetime.now(timezone.utc) - timedelta(hours=25)

        # Cleanup should remove it
        cleaned_count = cleanup_old_approvals(max_age_hours=24)

        assert cleaned_count >= 1

        # Verify it's gone
        status = get_approval_status("test-cleanup-old")
        assert status is None

    def test_cleanup_keeps_recent_approvals(self):
        """Test cleanup keeps recent approvals."""
        create_approval_request("test-cleanup-recent", {"total": "$40"})

        # Cleanup with 24 hour window shouldn't remove it
        cleanup_old_approvals(max_age_hours=24)

        status = get_approval_status("test-cleanup-recent")
        assert status is not None


class TestThreadSafety:
    """Tests for thread safety."""

    def test_lock_exists(self):
        """Test that the threading lock exists."""
        assert _approvals_lock is not None

    def test_get_approval_status_returns_copy(self):
        """Test that get_approval_status returns a copy to prevent external mutation."""
        create_approval_request("test-copy", {"total": "$40"})

        status1 = get_approval_status("test-copy")
        status2 = get_approval_status("test-copy")

        # Should be different objects (copies)
        assert status1 is not status2

        # But with same data
        assert status1["status"] == status2["status"]


class TestTimezoneAwareness:
    """Tests for timezone-aware datetimes."""

    def test_all_datetimes_are_timezone_aware(self):
        """Test that all datetime fields are timezone-aware."""
        create_approval_request("test-tz", {"total": "$40"})

        with _approvals_lock:
            approval = _pending_approvals.get("test-tz")

            assert approval["created_at"].tzinfo is not None
            assert approval["expires_at"].tzinfo is not None

        # Approve it and check decided_at
        approve_request("test-tz")

        with _approvals_lock:
            approval = _pending_approvals.get("test-tz")
            assert approval["decided_at"].tzinfo is not None
