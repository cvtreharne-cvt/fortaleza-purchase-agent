# Webhook URL Configuration for Human Approval

## Overview

The human approval feature requires a publicly accessible webhook base URL to receive approval/rejection callbacks from Pushover notifications. This URL must be configured via the `WEBHOOK_BASE_URL` environment variable.

## Configuration

### Required Environment Variable

```bash
WEBHOOK_BASE_URL=https://your-app.run.app
```

**Important Notes:**
- Do NOT include a trailing slash
- Must be a full HTTPS URL
- Should point to your Cloud Run service URL
- Required when `submit_order=True` (production mode)

### Example Configurations

#### Cloud Run (Production)
```bash
WEBHOOK_BASE_URL=https://fortaleza-agent-xyz123.run.app
```

#### Local Development (with ngrok)
```bash
# Start ngrok tunnel
ngrok http 8080

# Use the ngrok URL
WEBHOOK_BASE_URL=https://abc123.ngrok.io
```

#### Local Development (test mode only)
```bash
# For testing without actual approval (dryrun/test mode)
# You can set a placeholder, but order submission will fail
WEBHOOK_BASE_URL=http://localhost:8080
```

| Gmail Fortaleza Monitor<br>(Mode) | Fortaleza Purchase Agent<br>(Mode) | Agent Action |
|:---:|:---:|:---:|
| PROD | PROD | Buy |
| TEST | PROD | Buy |
| DRYRUN | PROD | Do Not Buy |
| PROD | DRYRUN | Do Not Buy |
| TEST | DRYRUN | Do Not Buy |
| DRYRUN | DRYRUN | Do Not Buy |
| PROD | TEST | Buy |
| TEST | TEST | Buy |
| DRYRUN | TEST | Do Not Buy |

fortaleza-in-stock project root: 
    Add MODE=dryrun to allow test emails (e.g. emails sent by non Bitters & Bottles senders) to trigger a dryrun of the agent

You can test the complete pipeline with MODE=dryrun in fortaleza-in-stock, and use MODE=test when you want to validate the entire flow with a real (but cheap) purchase!

## How It Works

### Approval Flow

1. **Agent fills checkout form** and extracts order summary
2. **Creates approval request** with 10-minute timeout
3. **Sends Pushover notification** with interactive buttons:
   - APPROVE button: `{WEBHOOK_BASE_URL}/approval/{run_id}/approve`
   - Reject link: `{WEBHOOK_BASE_URL}/approval/{run_id}/reject`
4. **User clicks button** on phone/device
5. **Pushover calls webhook** (GET or POST request)
6. **Agent polls approval status** every 2 seconds
7. **Order submitted** on approval, or cancelled on rejection/timeout

### Webhook Endpoints

The following endpoints are automatically created:

- `POST/GET /approval/{run_id}/approve` - Approve the purchase
- `POST/GET /approval/{run_id}/reject` - Reject the purchase
- `GET /approval/{run_id}/status` - Query approval status

**Note:** Both GET and POST are supported for browser compatibility (clicking links in notifications).

## Security

### Rate Limiting
- 10 requests per minute per IP address
- Prevents brute-force attacks on run_id
- Returns 429 with `Retry-After` header

### Run ID Security
- UUIDs provide 122 bits of entropy
- 10-minute expiration window
- One-time use (cannot approve twice)
- Automatic cleanup after 24 hours

### HTTPS Required
Always use HTTPS URLs in production to prevent:
- Man-in-the-middle attacks
- Eavesdropping on approval decisions
- Tampering with webhook payloads

## Validation

The agent validates `WEBHOOK_BASE_URL` before sending approval requests:

```python
# In checkout.py
settings.validate_webhook_config()  # Raises ConfigurationError if not set
```

**Error Message:**
```
ConfigurationError: webhook_base_url must be configured when submitting orders with approval.
Set WEBHOOK_BASE_URL environment variable to your Cloud Run URL (e.g., https://your-app.run.app)
```

## Deployment

### Cloud Run Deployment

1. Set the environment variable in `app.yaml` or via `gcloud`:

```bash
gcloud run services update fortaleza-agent \
  --set-env-vars WEBHOOK_BASE_URL=https://fortaleza-agent-xyz123.run.app \
  --region us-central1
```

2. Or in `app.yaml`:

```yaml
env_variables:
  WEBHOOK_BASE_URL: "https://fortaleza-agent-xyz123.run.app"
```

3. Get your Cloud Run URL:

```bash
gcloud run services describe fortaleza-agent --region us-central1 --format='value(status.url)'
```

### Local Development

For local testing with actual Pushover callbacks:

1. **Install ngrok:**
   ```bash
   brew install ngrok  # macOS
   # or download from https://ngrok.com/
   ```

2. **Start your local server:**
   ```bash
   uvicorn src.app.main:app --reload --port 8080
   ```

3. **Start ngrok tunnel:**
   ```bash
   ngrok http 8080
   ```

4. **Copy the HTTPS URL** (e.g., `https://abc123.ngrok.io`)

5. **Set environment variable:**
   ```bash
   export WEBHOOK_BASE_URL=https://abc123.ngrok.io
   ```

6. **Test the approval flow**

## Testing

### Manual Testing

1. Create a test approval request:
   ```bash
   curl -X POST http://localhost:8080/test-approval
   ```

2. Check the Pushover notification on your device

3. Click APPROVE or the reject link

4. Verify the callback was received:
   ```bash
   curl http://localhost:8080/approval/{run_id}/status
   ```

### Unit Tests

Run the webhook integration tests:

```bash
pytest tests/test_webhook_approval.py -v
```

Tests include:
- Approval/rejection endpoints (GET and POST)
- Rate limiting enforcement
- Status queries
- Error cases (404, 400)

## Troubleshooting

### "webhook_base_url not configured" Error

**Cause:** `WEBHOOK_BASE_URL` environment variable not set

**Solution:**
```bash
export WEBHOOK_BASE_URL=https://your-app.run.app
```

### Pushover Notification Sent but No Callback

**Possible Causes:**
1. **URL not publicly accessible** - Check firewall/network settings
2. **Cloud Run requires authentication** - Ensure `--allow-unauthenticated`
3. **Wrong URL** - Verify `WEBHOOK_BASE_URL` matches actual service URL
4. **SSL certificate issues** - Use valid HTTPS certificate

**Debug Steps:**
```bash
# Test endpoint directly
curl https://your-app.run.app/approval/test-run-id/status

# Check Cloud Run logs
gcloud run services logs read fortaleza-agent --limit 50
```

### Rate Limiting Issues

**Symptom:** Getting 429 errors

**Solution:** Wait 60 seconds or check if you're being too aggressive with requests

**Note:** Rate limiting is per-IP and resets every minute

## Best Practices

1. **Always use HTTPS** in production
2. **Set webhook URL early** in deployment process
3. **Test with ngrok** before deploying to Cloud Run
4. **Monitor webhook logs** for failed callbacks
5. **Keep URLs consistent** - don't change mid-deployment
6. **Use environment variables** - never hardcode URLs

## Future Enhancements

Potential improvements for future versions:

- [ ] Add HMAC signature verification for callbacks
- [ ] Support multiple webhook URLs (failover)
- [ ] Add webhook retry logic with exponential backoff
- [ ] Implement webhook health checks
- [ ] Add metrics/monitoring for callback success rate
- [ ] Support custom approval timeout per request
