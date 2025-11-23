"""Test script to simulate Raspberry Pi webhook request to local server."""

import hmac
import hashlib
import json
import time
import httpx
from datetime import datetime


def compute_hmac_signature(payload: str, timestamp: str, secret: str) -> str:
    """
    Compute HMAC-SHA256 signature for webhook request.

    Args:
        payload: JSON payload as string
        timestamp: Unix timestamp as string
        secret: Shared secret

    Returns:
        HMAC signature as hex string
    """
    message = f"{timestamp}.{payload}"
    signature = hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature


async def test_webhook():
    """Test webhook endpoint with simulated Pi request."""

    # Load webhook secret from .env.local
    import os
    from dotenv import load_dotenv
    load_dotenv(".env.local")

    webhook_secret = os.getenv("PI_WEBHOOK_SHARED_SECRET")
    if not webhook_secret:
        print("❌ PI_WEBHOOK_SHARED_SECRET not found in .env.local")
        return

    # Webhook URL
    url = "http://localhost:8080/webhook/pi"

    # Create payload
    event_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    payload = {
        "event_id": event_id,
        "received_at": datetime.now().isoformat() + "Z",
        "subject": "Hamilton Grass Skirt Blend Rum - Back in Stock",
        "direct_link": "https://www.bittersandbottles.com/products/hamilton-the-grass-skirt-blend-rum",
        "product_hint": "Hamilton The Grass Skirt Blend Rum"
    }

    # Convert to JSON string (exactly as it will be sent)
    payload_json = json.dumps(payload, separators=(',', ':'))

    # Generate timestamp and signature
    timestamp = str(int(time.time()))
    signature = compute_hmac_signature(payload_json, timestamp, webhook_secret)

    print(f"🔐 Testing webhook endpoint")
    print(f"   URL: {url}")
    print(f"   Event ID: {event_id}")
    print(f"   Product: {payload['product_hint']}")
    print(f"   Timestamp: {timestamp}")
    print(f"   Signature: {signature[:20]}...")
    print()

    # Send request
    headers = {
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Signature": signature
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                content=payload_json,
                headers=headers
            )

            print(f"📡 Response Status: {response.status_code}")
            print(f"📝 Response Body:")
            print(json.dumps(response.json(), indent=2))

            if response.status_code == 200:
                print()
                print("✅ Webhook accepted! Agent should be running in background.")
                print("   Check server logs for agent execution details.")
            else:
                print()
                print(f"❌ Webhook failed with status {response.status_code}")

    except httpx.ConnectError:
        print("❌ Could not connect to http://localhost:8080")
        print("   Make sure the FastAPI server is running:")
        print("   python -m uvicorn src.app.main:app --reload --port 8080")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_webhook())
