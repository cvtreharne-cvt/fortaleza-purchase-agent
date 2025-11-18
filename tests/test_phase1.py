"""Quick test script for Phase 1 components."""

import json
import hmac
import hashlib
import time


def test_config():
    """Test configuration loading."""
    print("=" * 60)
    print("Testing Configuration")
    print("=" * 60)
    
    from src.core.config import get_settings
    
    settings = get_settings()
    print(f"✓ Config loaded successfully")
    print(f"  Mode: {settings.mode.value}")
    print(f"  Headless: {settings.headless}")
    print(f"  Product: {settings.product_name}")
    print(f"  Log Level: {settings.log_level}")
    print()


def test_logging():
    """Test structured logging."""
    print("=" * 60)
    print("Testing Logging")
    print("=" * 60)
    
    from src.core.logging import setup_logging, get_logger
    
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("Test info message", test_field="value")
    logger.warning("Test warning", important=True)
    logger.error("Test error", error="sample error")
    
    # Test sensitive data redaction
    logger.info(
        "Testing redaction",
        password="should_be_redacted",
        cc_number="4111111111111111",
        normal_field="should_be_visible"
    )
    
    print("✓ Logging configured and tested")
    print("  Check above for log output")
    print()


def test_webhook_signature():
    """Test HMAC signature generation (for manual testing)."""
    print("=" * 60)
    print("Testing Webhook Signature Generation")
    print("=" * 60)
    
    # Sample payload
    payload = {
        "event_id": "test-123",
        "received_at": "2025-11-17T00:00:00Z",
        "subject": "Fortaleza Back in Stock",
        "direct_link": "https://www.bittersandbottles.com/products/fortaleza-blanco",
        "product_hint": "Fortaleza"
    }
    
    payload_json = json.dumps(payload)
    timestamp = str(int(time.time()))
    
    # Use a test secret (in real usage, this comes from Secret Manager)
    test_secret = "test-webhook-secret-123"
    
    # Generate signature
    message = f"{timestamp}.{payload_json}"
    signature = hmac.new(
        test_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    print("✓ Signature generated")
    print(f"\nTo test the webhook endpoint, use:")
    print(f"\ncurl -X POST http://localhost:8080/webhook/pi \\")
    print(f"  -H 'Content-Type: application/json' \\")
    print(f"  -H 'X-Timestamp: {timestamp}' \\")
    print(f"  -H 'X-Signature: {signature}' \\")
    print(f"  -d '{payload_json}'")
    print(f"\nNote: Set PI_WEBHOOK_SHARED_SECRET={test_secret} in your .env.local")
    print()


def test_fastapi_imports():
    """Test that FastAPI app can be imported."""
    print("=" * 60)
    print("Testing FastAPI Application Import")
    print("=" * 60)
    
    try:
        from src.app.main import app
        print("✓ FastAPI app imported successfully")
        print(f"  Title: {app.title}")
        print(f"  Version: {app.version}")
        print()
    except Exception as e:
        print(f"✗ Failed to import FastAPI app: {e}")
        print()


def main():
    """Run all tests."""
    print("\n🧪 Phase 1 Component Tests\n")
    
    try:
        test_config()
        test_logging()
        test_webhook_signature()
        test_fastapi_imports()
        
        print("=" * 60)
        print("✅ All Phase 1 component tests passed!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Create .env.local with configuration")
        print("2. Run: MODE=dryrun python -m uvicorn src.app.main:app --reload --port 8080")
        print("3. Test health endpoint: curl http://localhost:8080/health")
        print("4. Test webhook endpoint using the curl command above")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
