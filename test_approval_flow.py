"""
Integration test for the complete approval flow.

This script:
1. Starts the FastAPI webhook server
2. Creates a test approval request
3. Sends a Pushover notification to your phone
4. Waits for you to approve/reject
5. Shows the final result

Prerequisites:
- Pushover credentials configured in secrets
- Public URL for callbacks (use ngrok or similar if testing locally)
"""

import asyncio
import sys
import uuid
from datetime import datetime

# Add to path
sys.path.insert(0, '.')

from src.core.approval import create_approval_request, get_approval_status
from src.core.notify import get_pushover_client
from src.core.secrets import get_secret_manager


async def test_approval_flow():
    """Test the complete approval flow."""

    print("=" * 60)
    print("HUMAN APPROVAL FLOW - INTEGRATION TEST")
    print("=" * 60)
    print()

    # Generate unique run_id
    run_id = f"test-{uuid.uuid4()}"
    print(f"Run ID: {run_id}")
    print()

    # Create test order summary
    order_summary = {
        "product": "Test Product",
        "subtotal": "$36.50",
        "tax": "$3.61",
        "total": "$40.11",
        "pickup_location": "South San Francisco - 240 Grand Ave"
    }

    print("Order Summary:")
    for key, value in order_summary.items():
        print(f"  {key}: {value}")
    print()

    # Create approval request
    print("Creating approval request...")
    create_approval_request(
        run_id=run_id,
        order_summary=order_summary,
        timeout_minutes=10
    )
    print("✓ Approval request created")
    print()

    # Get base URL for callbacks
    print("For this test, you need a publicly accessible URL for callbacks.")
    print("Options:")
    print("  1. If deployed: Use your Cloud Run URL")
    print("  2. If local: Use ngrok (ngrok http 8080)")
    print()

    base_url = input("Enter your base URL (e.g., https://your-app.run.app or https://abc123.ngrok.io): ").strip()

    if not base_url:
        print("❌ No URL provided. Exiting.")
        return

    # Ensure no trailing slash
    base_url = base_url.rstrip('/')

    approve_url = f"{base_url}/approval/{run_id}/approve"
    reject_url = f"{base_url}/approval/{run_id}/reject"

    print()
    print("Callback URLs:")
    print(f"  Approve: {approve_url}")
    print(f"  Reject:  {reject_url}")
    print()

    # Send Pushover notification
    print("Sending Pushover notification...")

    try:
        pushover_client = get_pushover_client()
        success = pushover_client.send_approval_request(
            run_id=run_id,
            order_summary=order_summary,
            approve_url=approve_url,
            reject_url=reject_url
        )

        if success:
            print("✓ Pushover notification sent!")
            print()
            print("📱 Check your phone for the notification!")
            print()
        else:
            print("❌ Failed to send Pushover notification")
            return
    except Exception as e:
        print(f"❌ Error sending notification: {e}")
        return

    # Poll for decision
    print("Waiting for your decision...")
    print("(Will check every 2 seconds for up to 5 minutes)")
    print()

    max_polls = 150  # 5 minutes
    poll_count = 0

    while poll_count < max_polls:
        status = get_approval_status(run_id)

        if status and status["decision"] is not None:
            print()
            print("=" * 60)
            print("DECISION RECEIVED!")
            print("=" * 60)
            print()
            print(f"Decision: {status['decision'].upper()}")
            print(f"Status: {status['status']}")
            print(f"Decided at: {status['decided_at']}")
            print()

            if status["decision"] == "approved":
                print("✅ Purchase APPROVED")
                print("   → In production, the order would be submitted now")
            elif status["decision"] == "rejected":
                print("❌ Purchase REJECTED")
                print("   → In production, the order would be cancelled")
            elif status["decision"] == "timeout":
                print("⏱️  Request TIMED OUT")
                print("   → In production, the order would be cancelled")

            print()
            return

        # Progress indicator
        if poll_count % 10 == 0:
            elapsed = poll_count * 2
            print(f"  Still waiting... ({elapsed}s elapsed)")

        await asyncio.sleep(2)
        poll_count += 1

    print()
    print("⏱️  Timeout reached (5 minutes)")
    print("   No decision received")
    print()


async def test_notification_only():
    """Just test sending the notification without polling."""

    print("=" * 60)
    print("PUSHOVER NOTIFICATION TEST")
    print("=" * 60)
    print()

    run_id = f"test-notify-{uuid.uuid4()}"

    order_summary = {
        "product": "Test Product - Notification Only",
        "subtotal": "$36.50",
        "tax": "$3.61",
        "total": "$40.11",
        "pickup_location": "Test Location"
    }

    print("This will send a Pushover notification with dummy callback URLs.")
    print("You can click the buttons but they won't work (URLs are fake).")
    print()

    confirm = input("Send test notification? (y/n): ").strip().lower()

    if confirm != 'y':
        print("Cancelled")
        return

    print()
    print("Sending notification...")

    try:
        pushover_client = get_pushover_client()

        # Use dummy URLs for testing
        approve_url = f"https://example.com/approval/{run_id}/approve"
        reject_url = f"https://example.com/approval/{run_id}/reject"

        success = pushover_client.send_approval_request(
            run_id=run_id,
            order_summary=order_summary,
            approve_url=approve_url,
            reject_url=reject_url
        )

        if success:
            print("✓ Notification sent!")
            print()
            print("📱 Check your phone!")
            print()
            print("Note: The approve/reject buttons use dummy URLs")
            print("      (this is just to test the notification format)")
        else:
            print("❌ Failed to send notification")
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Main test menu."""

    print()
    print("Choose test mode:")
    print()
    print("1. Full approval flow (requires running webhook server)")
    print("2. Notification only (just test Pushover format)")
    print("3. Exit")
    print()

    choice = input("Enter choice (1-3): ").strip()

    if choice == "1":
        print()
        print("NOTE: Make sure your webhook server is running!")
        print("      Run: uvicorn src.app.main:app --reload")
        print()
        asyncio.run(test_approval_flow())
    elif choice == "2":
        asyncio.run(test_notification_only())
    else:
        print("Exiting")


if __name__ == "__main__":
    main()
