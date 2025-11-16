# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Essential Development Commands

### Local Setup

```bash
# Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Running Locally

```bash
# Start FastAPI server (dryrun mode - no real purchase)
MODE=dryrun HEADLESS=false python -m uvicorn src.app.main:app --reload --port 8080

# Start in test mode (real purchase of test product)
MODE=test HEADLESS=false python -m uvicorn src.app.main:app --reload --port 8080

# Start in production mode (requires CONFIRM_PROD=YES)
MODE=prod CONFIRM_PROD=YES HEADLESS=true python -m uvicorn src.app.main:app --port 8080
```

### Testing Webhook Locally

```bash
# Trigger webhook endpoint (compute HMAC signature first)
curl -X POST http://localhost:8080/webhook/pi \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $(date +%s)" \
  -H "X-Signature: <compute_hmac>" \
  -d '{
    "event_id": "test-1",
    "received_at": "2025-11-16T00:00:00Z",
    "subject": "Fortaleza Back in Stock",
    "direct_link": "https://www.bittersandbottles.com/products/fortaleza-blanco",
    "product_hint": "Fortaleza"
  }'
```

### Debugging with Playwright

```bash
# Run with Playwright Inspector
PWDEBUG=1 HEADLESS=false python -m src.app.main

# Run with verbose logging
LOG_LEVEL=DEBUG JSON_LOGS=false MODE=dryrun python -m uvicorn src.app.main:app --reload
```

### GCP Deployment

```bash
# Build and push Docker image
docker build -t us-central1-docker.pkg.dev/fortaleza-agent-prod/agents/fortaleza:latest .
docker push us-central1-docker.pkg.dev/fortaleza-agent-prod/agents/fortaleza:latest

# Deploy to Cloud Run
gcloud run deploy fortaleza-agent \
  --image us-central1-docker.pkg.dev/fortaleza-agent-prod/agents/fortaleza:latest \
  --service-account fortaleza-agent-sa@fortaleza-agent-prod.iam.gserviceaccount.com \
  --region us-central1 \
  --platform managed \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --cpu 1 \
  --memory 1Gi \
  --timeout 540 \
  --set-env-vars MODE=prod,HEADLESS=true,GCP_PROJECT_ID=fortaleza-agent-prod
```

## Architecture Overview

### Core Components

1. **Google ADK Agent** (src/agent/)
   - Single agent with specialized tools
   - Orchestrates entire purchase workflow
   - Uses Google Gemini for decision-making

2. **Native Playwright Tools** (src/tools/)
   - `navigate_to_product`: Navigate using direct link with search fallback
   - `verify_age`: Handle age verification modals opportunistically
   - `login_to_account`: Authenticate with B&B account
   - `add_to_cart`: Add product to shopping cart
   - `checkout_and_pay`: Complete purchase with pickup option

3. **FastAPI Webhook Server** (src/app/)
   - Receives HMAC-signed webhooks from Raspberry Pi Gmail monitor
   - Validates timestamp and signature
   - Triggers agent execution

4. **GCP Secret Manager Integration** (src/core/secrets.py)
   - All credentials stored in Secret Manager
   - Runtime-only in-memory access
   - Automatic redaction in logs

5. **Pushover Notifications** (src/core/notify.py)
   - Real-time status updates
   - Success/failure alerts
   - Human assistance requests (2FA, CAPTCHA, 3DS)

### Agent Workflow

```
Gmail Alert → Pi Webhook → Cloud Run Agent →
  Navigate to direct_link → Verify Age (if modal appears) →
    Login (if needed) → Navigate back to product →
      Add to Cart → Checkout → Submit Order →
        Pushover Notification
```

**Fallback Flow:**
If direct link fails (protocol error, 404, wrong page):
```
Navigate to homepage → Login →
  Search for product → Select from results →
    Add to Cart → Checkout → Submit Order
```

### Operating Modes

- **dryrun**: Full navigation and form filling, stops before final purchase
- **test**: Real purchase of cheap in-stock product for end-to-end validation
- **prod**: Real Fortaleza purchase (requires `CONFIRM_PROD=YES` safety check)

## Key Technical Decisions

### Why Native Playwright (Not MCP)?

This project uses native Python Playwright instead of MCP (Model Context Protocol) browser tools:

✅ **Advantages:**
- Simpler deployment (single container)
- Lower latency (no network overhead between agent and browser)
- Better debugging (local headed mode with Playwright Inspector)
- Full Playwright API control
- Easier state management
- Lower cost (one service instead of two)

❌ **MCP would add:**
- Extra complexity (separate MCP server)
- Network latency between agent and browser
- Additional infrastructure to manage
- More failure points

For this focused, automated purchase use case, native Playwright provides the best balance.

### Webhook Security

- **HMAC-SHA256** signed requests using shared secret
- **Timestamp validation** with 5-minute tolerance window (configurable via `WEBHOOK_TIMESTAMP_TOLERANCE`)
- **Constant-time signature comparison** to prevent timing attacks
- **Idempotency** via `event_id` tracking to prevent duplicate processing

### Error Handling Strategy

- **Typed exceptions** for each failure category (see src/core/errors.py):
  - Navigation: `ProtocolError`, `PageNotFoundError`, `UnexpectedPageError`
  - Authentication: `TwoFactorRequired`, `CaptchaRequired`
  - Product: `ProductNotFoundError`, `ProductSoldOutError`
  - Payment: `ThreeDSecureRequired`
  - Webhook: `InvalidSignatureError`, `TimestampTooOldError`, `DuplicateEventError`

- **Automatic fallbacks:**
  - Direct link fails → Homepage + login + search
  - Protocol error (trk.bittersandbottles.com) → Search fallback
  - Cart drawer missing → Direct cart page navigation

- **Manual intervention required:**
  - 2FA, CAPTCHA, 3D Secure verification
  - Out of stock (no automatic retry until new email event)

## Important Configuration

### Environment Variables

**Required in Production:**
- `MODE`: Operating mode (`dryrun`, `test`, `prod`)
- `CONFIRM_PROD`: Must be `YES` for prod mode
- `GCP_PROJECT_ID`: GCP project for Secret Manager
- `HEADLESS`: Browser visibility (`true` for cloud, `false` for local debugging)

**Browser Configuration:**
- `BROWSER_TIMEOUT`: Default 30000ms
- `NAVIGATION_TIMEOUT`: Default 60000ms

**Retry Configuration:**
- `MAX_RETRIES`: Default 3
- `RETRY_DELAY`: Default 2 seconds

**Product Configuration:**
- `PRODUCT_NAME`: Product to purchase (default: "Fortaleza")
- `PRODUCT_URL`: Optional direct product URL

**Webhook Security:**
- `PI_WEBHOOK_SHARED_SECRET`: HMAC signing secret
- `WEBHOOK_TIMESTAMP_TOLERANCE`: Default 300 seconds

### Local Development Secrets

For local development, create `.env.local` with:
```
MODE=dryrun
HEADLESS=false
BNB_EMAIL=your@email.com
BNB_PASSWORD=your_password
# ... other local secrets
```

**IMPORTANT**: Never commit `.env.local` or use local secret env vars in production. Always use GCP Secret Manager for cloud deployments.

### Configuration Loading

- Uses `pydantic-settings` with automatic `.env.local` loading
- All config keys are case-insensitive
- Environment variables override `.env.local` values
- Settings singleton: `from src.core.config import get_settings`

## Project Structure

```
src/
├── core/          # Core infrastructure
│   ├── config.py       # Pydantic settings (modes, timeouts, env vars)
│   ├── errors.py       # Typed exception hierarchy
│   ├── secrets.py      # GCP Secret Manager integration
│   ├── logging.py      # Structured logging (JSON in cloud)
│   ├── notify.py       # Pushover notification client
│   ├── browser.py      # Playwright browser harness
│   └── utils.py        # Shared utilities
├── agent/         # Google ADK agent
│   └── orchestrator.py # Main agent logic and tool coordination
├── tools/         # Playwright-based ADK tools
│   ├── navigate.py     # Navigate to product (with search fallback)
│   ├── verify_age.py   # Age verification modal handler
│   ├── login.py        # B&B account authentication
│   ├── cart.py         # Add to cart functionality
│   └── checkout.py     # Checkout and payment
└── app/           # FastAPI application
    ├── main.py         # FastAPI app definition
    └── webhook.py      # Webhook endpoint and HMAC validation
```

## Monitoring & Observability

### Cloud Logging Queries

```
# All agent runs
resource.type="cloud_run_revision"
resource.labels.service_name="fortaleza-agent"

# Specific run
jsonPayload.run_id="abc-123"

# Failures only
jsonPayload.level="ERROR"
```

### Pushover Notification Types

- **START**: Agent begins processing
- **SUCCESS**: Purchase completed
- **FAILURE**: Error occurred (includes details)
- **HUMAN-ASSIST-NEEDED**: Manual intervention required (2FA, CAPTCHA, 3DS)
