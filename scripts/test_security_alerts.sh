#!/bin/bash

# Test script for security monitoring alerts
# This script triggers security events to verify monitoring alerts are working

set -e

# Get webhook URL from terraform or use default
if [ -d "terraform" ] && command -v terraform &> /dev/null; then
    cd terraform
    WEBHOOK_URL=$(terraform output -raw service_url 2>/dev/null)/webhook/pi || WEBHOOK_URL="https://fortaleza-agent-aqxpcn45ma-uc.a.run.app/webhook/pi"
    cd ..
else
    WEBHOOK_URL="https://fortaleza-agent-aqxpcn45ma-uc.a.run.app/webhook/pi"
fi

echo "=================================================="
echo "Security Alerts Testing"
echo "=================================================="
echo "Webhook URL: $WEBHOOK_URL"
echo ""
echo "This will trigger 3 security alerts:"
echo "  1. Failed HMAC Authentication (>5 in 5 min)"
echo "  2. Invalid Timestamp (>5 in 5 min)"
echo "  3. Duplicate Event/Replay Attack (>0)"
echo ""
echo "Expected: Email alerts within 2-5 minutes"
echo "=================================================="
echo ""

# Test 1: Failed HMAC Authentication
echo "Test 1: Failed HMAC Authentication"
echo "--------------------------------------------------"
echo "Sending 6 requests with invalid HMAC signatures..."
echo ""

for i in {1..6}; do
  echo "  Request $i/6..."
  curl -s -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -H "X-Signature: invalid-signature-$i" \
    -H "X-Timestamp: $(date +%s)" \
    -d '{"event_id":"test-hmac-'$i'","received_at":"2025-11-17T00:00:00Z","subject":"Test","direct_link":"https://example.com","product_hint":"Test"}' \
    > /dev/null
  sleep 1
done

echo "✅ Sent 6 requests with invalid signatures"
echo ""

# Test 2: Invalid Timestamp
echo "Test 2: Invalid Timestamp"
echo "--------------------------------------------------"
echo "Sending 6 requests with old timestamps (>5 minutes)..."
echo ""

OLD_TIMESTAMP=$(($(date +%s) - 400))  # 6 minutes 40 seconds ago

for i in {1..6}; do
  echo "  Request $i/6..."
  curl -s -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -H "X-Signature: any-signature" \
    -H "X-Timestamp: $OLD_TIMESTAMP" \
    -d '{"event_id":"test-timestamp-'$i'","received_at":"2025-11-17T00:00:00Z","subject":"Test","direct_link":"https://example.com","product_hint":"Test"}' \
    > /dev/null
  sleep 1
done

echo "✅ Sent 6 requests with old timestamps"
echo ""

# Test 3: Duplicate Event (Replay Attack)
echo "Test 3: Duplicate Event (Replay Attack)"
echo "--------------------------------------------------"
echo "Sending same event_id 6 times..."
echo ""

EVENT_ID="test-duplicate-$(date +%s)"
TIMESTAMP=$(date +%s)

for i in {1..6}; do
  echo "  Request $i/6..."
  curl -s -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -H "X-Signature: test-signature" \
    -H "X-Timestamp: $TIMESTAMP" \
    -d '{"event_id":"'$EVENT_ID'","received_at":"2025-11-17T00:00:00Z","subject":"Test","direct_link":"https://example.com","product_hint":"Test"}' \
    > /dev/null
  sleep 1
done

echo "✅ Sent 6 requests with duplicate event_id"
echo ""

# Summary
echo "=================================================="
echo "✅ All security tests completed"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Check email for alert notifications (2-5 min)"
echo "  2. View logs with:"
echo "     gcloud logging read 'jsonPayload.security_event!=\"\"' --limit=20"
echo "  3. View incidents at:"
echo "     https://console.cloud.google.com/monitoring/alerting/incidents?project=fortaleza-purchase-agent"
echo ""
echo "Expected alerts:"
echo "  - Failed HMAC Authentication (6 events)"
echo "  - Invalid Timestamp Attempts (6 events)"
echo "  - Duplicate Event Detected (5 duplicates after first)"
echo ""
