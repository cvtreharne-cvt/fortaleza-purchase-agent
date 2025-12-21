"""Integration tests for webhook approval endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.app.main import app
from src.core.approval import (
    create_approval_request,
    get_approval_status,
    _pending_approvals,
    _approvals_lock
)


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_approvals():
    """Clean up approval state before and after each test."""
    with _approvals_lock:
        _pending_approvals.clear()
    yield
    with _approvals_lock:
        _pending_approvals.clear()


class TestApprovalEndpoints:
    """Tests for approval webhook endpoints."""

    def test_approve_endpoint_success(self, client):
        """Test successful approval via POST endpoint."""
        # Create an approval request
        create_approval_request("test-run-1", {"total": "$40"})

        # Call approve endpoint
        response = client.post("/approval/test-run-1/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["run_id"] == "test-run-1"

        # Verify approval was recorded
        status = get_approval_status("test-run-1")
        assert status["decision"] == "approved"

    def test_approve_endpoint_get_method(self, client):
        """Test approval via GET endpoint (browser compatibility)."""
        create_approval_request("test-run-2", {"total": "$40"})

        # Call approve endpoint with GET
        response = client.get("/approval/test-run-2/approve")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"

    def test_reject_endpoint_success(self, client):
        """Test successful rejection via POST endpoint."""
        create_approval_request("test-run-3", {"total": "$40"})

        # Call reject endpoint
        response = client.post("/approval/test-run-3/reject")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert data["run_id"] == "test-run-3"

        # Verify rejection was recorded
        status = get_approval_status("test-run-3")
        assert status["decision"] == "rejected"

    def test_reject_endpoint_get_method(self, client):
        """Test rejection via GET endpoint (browser compatibility)."""
        create_approval_request("test-run-4", {"total": "$40"})

        # Call reject endpoint with GET
        response = client.get("/approval/test-run-4/reject")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

    def test_approve_nonexistent_request(self, client):
        """Test approving a non-existent request returns 404."""
        response = client.post("/approval/nonexistent-id/approve")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_reject_nonexistent_request(self, client):
        """Test rejecting a non-existent request returns 404."""
        response = client.post("/approval/nonexistent-id/reject")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_double_approval_fails(self, client):
        """Test that approving twice returns 400."""
        create_approval_request("test-run-5", {"total": "$40"})

        # First approval
        response1 = client.post("/approval/test-run-5/approve")
        assert response1.status_code == 200

        # Second approval should fail
        response2 = client.post("/approval/test-run-5/approve")
        assert response2.status_code == 400
        assert "expired or already decided" in response2.json()["detail"].lower()

    def test_status_endpoint_success(self, client):
        """Test status endpoint returns approval state."""
        create_approval_request("test-run-6", {"total": "$40"})

        response = client.get("/approval/test-run-6/status")

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "test-run-6"
        assert data["status"] == "pending"
        assert data["decision"] is None

    def test_status_endpoint_after_approval(self, client):
        """Test status endpoint after approval."""
        create_approval_request("test-run-7", {"total": "$40"})
        client.post("/approval/test-run-7/approve")

        response = client.get("/approval/test-run-7/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["decision"] == "approved"
        assert data["decided_at"] is not None

    def test_status_endpoint_nonexistent(self, client):
        """Test status endpoint for non-existent request."""
        response = client.get("/approval/nonexistent-id/status")

        assert response.status_code == 404


@pytest.mark.rate_limit
class TestRateLimiting:
    """Tests for rate limiting on approval endpoints."""

    def test_rate_limit_enforcement(self, client):
        """Test that rate limiting blocks excessive requests."""
        create_approval_request("test-rate-limit", {"total": "$40"})

        # Make 10 requests (should all succeed)
        for i in range(10):
            response = client.get("/approval/test-rate-limit/status")
            assert response.status_code in (200, 404)  # 404 if already approved

        # 11th request should be rate limited
        response = client.get("/approval/test-rate-limit/status")
        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()
        assert "Retry-After" in response.headers

    def test_rate_limit_per_ip(self, client):
        """Test that rate limiting is per IP address."""
        create_approval_request("test-rate-limit-1", {"total": "$40"})
        create_approval_request("test-rate-limit-2", {"total": "$50"})

        # Make 5 requests to each endpoint (total 10 from same IP)
        for i in range(5):
            client.get("/approval/test-rate-limit-1/status")
            client.get("/approval/test-rate-limit-2/status")

        # 11th request from same IP should be rate limited
        response = client.get("/approval/test-rate-limit-1/status")
        assert response.status_code == 429
