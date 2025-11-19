#!/bin/bash

# Test script for FastAPI server and webhook endpoint

echo "🚀 Starting FastAPI server..."

# Start server in background
source venv/bin/activate
MODE=dryrun python -m uvicorn src.app.main:app --port 8080 > /tmp/fortaleza-server.log 2>&1 &
SERVER_PID=$!

echo "   Server PID: $SERVER_PID"
echo "   Waiting for server to start..."
sleep 3

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping server..."
    kill $SERVER_PID 2>/dev/null
    wait $SERVER_PID 2>/dev/null
    echo "   Server stopped"
}

trap cleanup EXIT

# Test 1: Health endpoint
echo ""
echo "============================================================"
echo "Test 1: Health Endpoint"
echo "============================================================"
HEALTH_RESPONSE=$(curl -s http://localhost:8080/health)
echo "Response: $HEALTH_RESPONSE"

if echo "$HEALTH_RESPONSE" | grep -q '"status":"healthy"'; then
    echo "✅ Health check passed"
else
    echo "❌ Health check failed"
    exit 1
fi

# Test 2: Root endpoint
echo ""
echo "============================================================"
echo "Test 2: Root Endpoint"
echo "============================================================"
ROOT_RESPONSE=$(curl -s http://localhost:8080/)
echo "Response: $ROOT_RESPONSE"

if echo "$ROOT_RESPONSE" | grep -q 'Fortaleza Purchase Agent'; then
    echo "✅ Root endpoint passed"
else
    echo "❌ Root endpoint failed"
    exit 1
fi

# Test 3: Valid webhook request
echo ""
echo "============================================================"
echo "Test 3: Webhook with Valid Signature"
echo "============================================================"

TIMESTAMP=$(date +%s)
PAYLOAD='{"event_id": "test-valid-123", "received_at": "2025-11-17T00:00:00Z", "subject": "Fortaleza Back in Stock", "direct_link": "https://www.bittersandbottles.com/products/fortaleza-blanco", "product_hint": "Fortaleza"}'

# Generate HMAC signature (Python one-liner)
SIGNATURE=$(python3 -c "
import hmac, hashlib
secret = 'test-webhook-secret-123'
timestamp = '$TIMESTAMP'
payload = '$PAYLOAD'
message = f'{timestamp}.{payload}'
print(hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest())
")

echo "Timestamp: $TIMESTAMP"
echo "Signature: $SIGNATURE"

WEBHOOK_RESPONSE=$(curl -s -X POST http://localhost:8080/webhook/pi \
  -H 'Content-Type: application/json' \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD")

echo "Response: $WEBHOOK_RESPONSE"

if echo "$WEBHOOK_RESPONSE" | grep -q '"status":"accepted"'; then
    echo "✅ Valid webhook request passed"
else
    echo "❌ Valid webhook request failed"
    exit 1
fi

# Test 4: Invalid signature
echo ""
echo "============================================================"
echo "Test 4: Webhook with Invalid Signature (should fail)"
echo "============================================================"

INVALID_RESPONSE=$(curl -s -X POST http://localhost:8080/webhook/pi \
  -H 'Content-Type: application/json' \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Signature: invalid-signature-123" \
  -d "$PAYLOAD")

echo "Response: $INVALID_RESPONSE"

if echo "$INVALID_RESPONSE" | grep -q 'Invalid HMAC signature'; then
    echo "✅ Invalid signature correctly rejected"
else
    echo "❌ Invalid signature test failed (should have been rejected)"
    exit 1
fi

# Test 5: Duplicate event (idempotency)
echo ""
echo "============================================================"
echo "Test 5: Duplicate Event ID (should fail)"
echo "============================================================"

# Regenerate signature with same event_id
SIGNATURE=$(python3 -c "
import hmac, hashlib
secret = 'test-webhook-secret-123'
timestamp = '$TIMESTAMP'
payload = '$PAYLOAD'
message = f'{timestamp}.{payload}'
print(hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest())
")

DUPLICATE_RESPONSE=$(curl -s -X POST http://localhost:8080/webhook/pi \
  -H 'Content-Type: application/json' \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Signature: $SIGNATURE" \
  -d "$PAYLOAD")

echo "Response: $DUPLICATE_RESPONSE"

if echo "$DUPLICATE_RESPONSE" | grep -q 'already been processed'; then
    echo "✅ Duplicate event correctly rejected"
else
    echo "❌ Duplicate event test failed (should have been rejected)"
    exit 1
fi

# Test 6: Check server logs
echo ""
echo "============================================================"
echo "Test 6: Server Logs (last 20 lines)"
echo "============================================================"
tail -20 /tmp/fortaleza-server.log

echo ""
echo "============================================================"
echo "✅ All server tests passed!"
echo "============================================================"
echo ""
echo "Server is still running. Press Ctrl+C to stop it."
echo "Or run: kill $SERVER_PID"
echo ""

# Keep script running so server stays up
read -p "Press Enter to stop the server and exit..."
