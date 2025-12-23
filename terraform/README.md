# Fortaleza Purchase Agent - Terraform Infrastructure

This directory contains Infrastructure as Code (IaC) for deploying the Fortaleza purchase agent to Google Cloud Platform using Terraform.

## What Gets Deployed

- **Cloud Run Service** - Containerized Python agent
- **Secret Manager Secrets** - 20 secrets for credentials (bnb_email, cc_number, etc.)
- **IAM Policies** - Service account permissions to access secrets
- **Public Access** - Allow webhook calls from your Pi

## Prerequisites

1. **Terraform** installed (v1.5+)
   ```bash
   brew install terraform
   ```

2. **Google Cloud SDK** (`gcloud`) configured
   ```bash
   gcloud auth application-default login
   gcloud config set project fortaleza-purchase-agent
   ```

3. **Required GCP APIs enabled** (one-time setup)
   
   **⚠️ Important:** These APIs must be enabled before running Terraform.
   
   ```bash
   # Required for Terraform to manage infrastructure
   gcloud services enable cloudresourcemanager.googleapis.com --project=fortaleza-purchase-agent
   gcloud services enable iam.googleapis.com --project=fortaleza-purchase-agent
   gcloud services enable secretmanager.googleapis.com --project=fortaleza-purchase-agent
   gcloud services enable run.googleapis.com --project=fortaleza-purchase-agent
   gcloud services enable artifactregistry.googleapis.com --project=fortaleza-purchase-agent
   gcloud services enable monitoring.googleapis.com --project=fortaleza-purchase-agent
   gcloud services enable logging.googleapis.com --project=fortaleza-purchase-agent
   ```
   
   **Why manual?** To enable APIs via Terraform would require `serviceusage.googleapis.com`
   already enabled (chicken-and-egg problem). See `terraform/apis.tf` for details.

4. **Container Image** built and pushed to Artifact Registry
   ```bash
   docker build -t us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:latest .
   docker push us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:latest
   ```

## Initial Setup

### 1. Configure Variables

Edit `terraform.tfvars` with your actual values:

```hcl
browser_worker_url        = "https://your-tunnel.trycloudflare.com"
browser_worker_auth_token = "your-secret-token"
webhook_base_url          = "https://fortaleza-agent-xxxxx.run.app"
```

**Security Note:** `terraform.tfvars` is gitignored - never commit it!

### 2. Initialize Terraform

Download provider plugins:

```bash
cd terraform
terraform init
```

This creates:
- `.terraform/` directory with Google Cloud provider
- `.terraform.lock.hcl` file (commit this to git)

### 3. Review the Plan

See what will be created:

```bash
terraform plan
```

Expected output:
```
Plan: 42 to add, 0 to change, 0 to destroy.
```

### 4. Apply Configuration

Create the infrastructure:

```bash
terraform apply
```

Type `yes` when prompted.

**First-time deployment:** This creates the Secret Manager secrets but NOT their values.

### 5. Add Secret Values

After applying, populate the secrets:

```bash
# Example for one secret
echo -n "your-email@example.com" | gcloud secrets versions add bnb_email --data-file=-

# Do this for all 20 secrets
```

Or use the helper script (if you have one):
```bash
./scripts/upload-secrets.sh
```

### 6. Verify Deployment

Check outputs:
```bash
terraform output
```

Should show:
- `service_url` - Your Cloud Run URL
- `service_account_email` - Service account being used

Test the service:
```bash
curl $(terraform output -raw service_url)/health
```

## Configuration

### Variables

All configurable values are in `variables.tf`:

| Variable | Description | Default |
|----------|-------------|---------|
| `project_id` | GCP project ID | `fortaleza-purchase-agent` |
| `region` | GCP region | `us-central1` |
| `service_name` | Cloud Run service name | `fortaleza-agent` |
| `container_image` | Docker image to deploy | `gcr.io/.../fortaleza-agent:latest` |
| `browser_worker_url` | Browser worker URL | *required* |
| `browser_worker_auth_token` | Auth token | *required* |
| `webhook_base_url` | Webhook callback URL | *required* |
| `approval_flow_timeout_seconds` | Timeout for approval flow | `900` (15 min) |
| `browser_launch_timeout` | Browser launch timeout (ms) | `300000` (5 min) |
| `browser_timeout` | Browser timeout (ms) | `60000` (1 min) |
| `navigation_timeout` | Navigation timeout (ms) | `120000` (2 min) |

### Overriding Defaults

In `terraform.tfvars`:

```hcl
# Use a longer timeout for slow networks
approval_flow_timeout_seconds = 1200  # 20 minutes

# Deploy to a different region
region = "us-west1"
```

## Common Tasks

### Update Container Image

After building a new image:

```bash
# 1. Push new image
docker build -t us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:v1.2.3 .
docker push us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:v1.2.3

# 2. Update terraform.tfvars
container_image = "us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:v1.2.3"

# 3. Apply changes
terraform apply
```

### Update Environment Variables

```bash
# Edit variables.tf or terraform.tfvars
# Then:
terraform apply
```

Terraform will only update the changed parts.

### View Current State

```bash
# List all resources
terraform state list

# Show details of a resource
terraform state show google_cloud_run_service.fortaleza_agent
```

### Destroy Everything

⚠️ **Careful!** This deletes all infrastructure:

```bash
terraform destroy
```

Type `yes` to confirm.

**Note:** Secret Manager secrets have a recovery period. Truly deleting them requires:
```bash
gcloud secrets delete SECRET_NAME --project=fortaleza-purchase-agent
```

## Workflow

### Typical Development Cycle

```bash
# 1. Make changes to .tf files
vim cloudrun.tf

# 2. Format code
terraform fmt

# 3. Validate syntax
terraform validate

# 4. Preview changes
terraform plan

# 5. Apply changes
terraform apply

# 6. Commit to git
git add terraform/
git commit -m "Update Cloud Run memory to 1GB"
```

## Terraform State

### What is State?

Terraform tracks your infrastructure in `terraform.tfstate`:
- Maps configuration to real resources
- Stores resource IDs, metadata, dependencies
- **Contains sensitive data!** (gitignored)

### Remote State Backend (GCS)

**This project uses remote state storage** in Google Cloud Storage for:
- ✅ Shared state between local development and GitHub Actions CI/CD
- ✅ Automatic state locking to prevent conflicts
- ✅ State versioning and backup
- ✅ Team collaboration support

### First-Time Remote State Setup

**⚠️ One-time manual setup** (already completed for this project):

The state bucket must be created **before** Terraform initialization to avoid
circular dependencies (the bucket can't store its own creation state).

```bash
# 1. Create the state bucket
gcloud storage buckets create gs://fortaleza-purchase-agent-tfstate \
  --location=us-central1 \
  --uniform-bucket-level-access

# 2. Enable versioning for state backup/recovery
gcloud storage buckets update gs://fortaleza-purchase-agent-tfstate \
  --versioning

# 3. Enable public access prevention (security best practice)
gcloud storage buckets update gs://fortaleza-purchase-agent-tfstate \
  --public-access-prevention

# 4. Grant GitHub Actions access to the bucket
gcloud storage buckets add-iam-policy-binding \
  gs://fortaleza-purchase-agent-tfstate \
  --member="serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# 5. Initialize Terraform with remote backend (migrate local state)
cd terraform
terraform init -migrate-state
```

**Why manual?** The state bucket is "meta-infrastructure" - if managed by
Terraform, deleting it would also delete the state file tracking it. This
is a best practice for bootstrap resources.

### State Management

```bash
# View current state location
terraform state list

# The state is stored at:
# gs://fortaleza-purchase-agent-tfstate/terraform/state/default.tfstate

# Access state directly (rarely needed)
gcloud storage cat gs://fortaleza-purchase-agent-tfstate/terraform/state/default.tfstate
```

### State Recovery

If state becomes corrupted:

```bash
# List state versions in GCS
gcloud storage ls -l gs://fortaleza-purchase-agent-tfstate/terraform/state/

# Download a previous version
gcloud storage cp gs://fortaleza-purchase-agent-tfstate/terraform/state/default.tfstate#<generation> \
  ./terraform.tfstate.backup
```

## Troubleshooting

### Remote State Issues

#### "Error: Failed to get state lock"

**Cause:** Another Terraform process is running or crashed without releasing the lock.

**Symptoms:**
```
Error: Error acquiring the state lock
Lock Info:
  ID:        1234567890-abcd-1234-5678-0123456789ab
  Path:      gs://fortaleza-purchase-agent-tfstate/terraform/state/default.tflock
```

**Solution:**
```bash
# 1. Verify no other Terraform processes are running
ps aux | grep terraform

# 2. If safe, force unlock (use ID from error message)
terraform force-unlock 1234567890-abcd-1234-5678-0123456789ab

# 3. If force-unlock fails, manually delete lock file
gcloud storage rm gs://fortaleza-purchase-agent-tfstate/terraform/state/default.tflock
```

**Prevention:** Always let `terraform apply` complete or use `Ctrl+C` gracefully.

#### "Backend initialization failed" / "Failed to get existing workspaces"

**Cause:** Missing IAM permissions to access state bucket.

**Symptoms:**
```
Error: Failed to get existing workspaces: storage: bucket doesn't exist
Error: Error inspecting states in backend: querying Cloud Storage failed: storage: bucket doesn't exist
```

**Solution:**
```bash
# 1. Verify bucket exists
gcloud storage ls gs://fortaleza-purchase-agent-tfstate

# 2. Check your permissions
gcloud storage buckets get-iam-policy gs://fortaleza-purchase-agent-tfstate

# 3. Grant yourself access (for local development)
gcloud storage buckets add-iam-policy-binding \
  gs://fortaleza-purchase-agent-tfstate \
  --member="user:$(gcloud config get-value account)" \
  --role="roles/storage.objectAdmin"

# 4. For GitHub Actions, ensure service account has access
gcloud storage buckets add-iam-policy-binding \
  gs://fortaleza-purchase-agent-tfstate \
  --member="serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

#### "State file corrupt" / "Failed to read state"

**Cause:** State file corrupted due to interrupted write or manual editing.

**Symptoms:**
```
Error: Failed to read state: <parse errors>
Error: state snapshot was created by Terraform vX.Y, which is newer than current vA.B
```

**Solution - Restore from version history:**
```bash
# 1. List available state versions
gcloud storage ls -l gs://fortaleza-purchase-agent-tfstate/terraform/state/

# Output shows versions with generation numbers:
#   12345678  2024-01-15  default.tfstate#1705334400000000
#   12345679  2024-01-16  default.tfstate#1705420800000000 (latest)

# 2. Download a working previous version (use generation number)
gcloud storage cp \
  'gs://fortaleza-purchase-agent-tfstate/terraform/state/default.tfstate#1705334400000000' \
  ./terraform.tfstate

# 3. Push it back as the current state
gcloud storage cp ./terraform.tfstate \
  gs://fortaleza-purchase-agent-tfstate/terraform/state/default.tfstate

# 4. Verify recovery
terraform state list
```

**Prevention:** Never manually edit `terraform.tfstate`. Always use `terraform state` commands.

#### "Cannot access Terraform state bucket" (CI/CD)

**Cause:** GitHub Actions service account lacks permissions.

**Symptoms:** GitHub Actions workflow fails at "Validate Terraform State Access" step.

**Solution:**
```bash
# Grant storage access to GitHub Actions service account
gcloud storage buckets add-iam-policy-binding \
  gs://fortaleza-purchase-agent-tfstate \
  --member="serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Verify permission granted
gcloud storage buckets get-iam-policy gs://fortaleza-purchase-agent-tfstate \
  --flatten="bindings[].members" \
  --filter="bindings.members:github-actions-fortaleza-agent"
```

### General Issues

#### "Error 403: Permission denied"

**Solution:** Ensure you're authenticated:
```bash
gcloud auth application-default login
```

#### "Secret already exists"

**Cause:** Secret exists from previous deployment but not in Terraform state.

**Solution 1:** Import existing secret:
```bash
terraform import google_secret_manager_secret.secrets[\"bnb_email\"] projects/fortaleza-purchase-agent/secrets/bnb_email
```

**Solution 2:** Delete and recreate:
```bash
gcloud secrets delete bnb_email
terraform apply
```

#### "Container image not found"

**Cause:** Image hasn't been pushed to Artifact Registry.

**Solution:** Build and push:
```bash
docker build -t us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:latest .
docker push us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:latest
```

#### "API not enabled"

**Cause:** Required GCP API not enabled in project.

**Solution:** Enable the API mentioned in error:
```bash
# Example for Cloud Resource Manager API
gcloud services enable cloudresourcemanager.googleapis.com

# See Prerequisites section for full list of required APIs
```

#### Changes Not Applying

**Check the plan:**
```bash
terraform plan -out=tfplan
```

**Force recreation:**
```bash
terraform taint google_cloud_run_service.fortaleza_agent
terraform apply
```

## Architecture

```
┌─────────────────────────────────────────────┐
│ Terraform Configuration                     │
├─────────────────────────────────────────────┤
│                                             │
│  provider.tf    - GCP connection            │
│  variables.tf   - Input variables           │
│  secrets.tf     - Secret Manager resources  │
│  iam.tf         - IAM permissions           │
│  cloudrun.tf    - Cloud Run service         │
│                                             │
└─────────────────────────────────────────────┘
                    │
                    │ terraform apply
                    ▼
┌─────────────────────────────────────────────┐
│ Google Cloud Platform                       │
├─────────────────────────────────────────────┤
│                                             │
│  ┌───────────────────────────────────┐     │
│  │ Cloud Run Service                 │     │
│  │  - Container: fortaleza-agent     │     │
│  │  - Timeout: 900s                  │     │
│  │  - Memory: 512Mi                  │     │
│  └───────────────────────────────────┘     │
│                    │                        │
│                    │ reads secrets          │
│                    ▼                        │
│  ┌───────────────────────────────────┐     │
│  │ Secret Manager                    │     │
│  │  - bnb_email                      │     │
│  │  - cc_number                      │     │
│  │  - ... (20 secrets)               │     │
│  └───────────────────────────────────┘     │
│                                             │
└─────────────────────────────────────────────┘
```

## Best Practices

1. **Always run `terraform plan` before `apply`**
   - Review what will change
   - Catch mistakes before they affect production

2. **Use version control**
   - Commit `.tf` files to git
   - Never commit `terraform.tfvars` or `*.tfstate`

3. **Use variables for everything that changes**
   - Container images
   - Timeouts
   - Feature flags

4. **Document changes in commit messages**
   - "Increase approval timeout to 20 minutes"
   - "Update to container v1.2.3"

5. **Test in a separate environment first**
   - Use workspaces or separate projects
   - Apply to staging before production

## Next Steps

- [ ] Set up remote state backend (GCS bucket)
- [ ] Add Terraform Cloud for team collaboration
- [ ] Create separate environments (dev/staging/prod)
- [ ] Add automated testing (terraform validate in CI/CD)
- [ ] Document secret rotation procedure

## Emergency Procedures

### Rollback to Previous Version

If a deployment causes issues, you can quickly rollback:

**Option 1: Rollback via Cloud Run Console (Fastest)**
```bash
# List recent revisions
gcloud run revisions list --service=fortaleza-agent --region=us-central1

# Rollback to previous revision
gcloud run services update-traffic fortaleza-agent \
  --region=us-central1 \
  --to-revisions=fortaleza-agent-00027-xyz=100
```

**Option 2: Rollback via Terraform**
```bash
# Revert to previous image
terraform apply -var="container_image=us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:PREVIOUS_SHA"

# Or revert Terraform files to previous commit
git checkout HEAD~1 -- terraform/
terraform apply
```

**Option 3: Emergency Disable**
```bash
# Scale to zero instances (stops serving traffic)
gcloud run services update fortaleza-agent \
  --region=us-central1 \
  --min-instances=0 \
  --max-instances=0

# Re-enable when fixed
gcloud run services update fortaleza-agent \
  --region=us-central1 \
  --min-instances=0 \
  --max-instances=1
```

### Secrets Rotation

Rotate secrets periodically or when compromised:

**1. Rotate HMAC Webhook Secret (PI_WEBHOOK_SHARED_SECRET)**

```bash
# Generate new secret
NEW_SECRET=$(openssl rand -hex 32)

# Update in GCP Secret Manager
echo -n "$NEW_SECRET" | gcloud secrets versions add pi_webhook_shared_secret --data-file=-

# Update on Raspberry Pi
ssh pi@bnb-worker.treharne.com
# Edit .env file with new secret
# Restart Pi webhook service

# Cloud Run picks up new version automatically (within ~1 hour)
# Or force immediate refresh:
gcloud run services update fortaleza-agent --region=us-central1
```

**2. Rotate Browser Worker Auth Token**

```bash
# Generate new token
NEW_TOKEN=$(openssl rand -base64 32)

# Update in GCP Secret Manager
echo -n "$NEW_TOKEN" | gcloud secrets versions add browser_worker_auth_token --data-file=-

# Update on Raspberry Pi
ssh pi@bnb-worker.treharne.com
# Update BROWSER_WORKER_AUTH_TOKEN in Pi's .env
# Restart browser worker service

# Force Cloud Run to pick up new version
gcloud run services update fortaleza-agent --region=us-central1
```

**3. Rotate B&B Account Credentials**

```bash
# Change password on B&B website first
# Then update in Secret Manager:
echo -n "NEW_PASSWORD" | gcloud secrets versions add bnb_password --data-file=-

# Force Cloud Run refresh
gcloud run services update fortaleza-agent --region=us-central1
```

**4. Rotate Pushover Credentials**

```bash
# Get new token from Pushover dashboard
# Update in Secret Manager:
echo -n "NEW_TOKEN" | gcloud secrets versions add pushover_app_token --data-file=-
echo -n "NEW_USER_KEY" | gcloud secrets versions add pushover_user_key --data-file=-
```

**Best Practices:**
- Test new secrets in a curl/postman request before rotating
- Keep old secret version for 24 hours in case of issues
- Document rotation in a changelog
- Set calendar reminders for quarterly rotation

**Secret Version Management:**
```bash
# List all versions of a secret
gcloud secrets versions list SECRET_NAME

# Access specific version
gcloud secrets versions access VERSION_NUMBER --secret=SECRET_NAME

# Disable old version (after confirming new one works)
gcloud secrets versions disable VERSION_NUMBER --secret=SECRET_NAME

# Destroy old version permanently (after 30 days)
gcloud secrets versions destroy VERSION_NUMBER --secret=SECRET_NAME
```

## Testing Security Alerts

After deploying the monitoring infrastructure, you can manually test the security alerts to verify they're working correctly.

### Test 1: Failed HMAC Authentication

Trigger the failed HMAC alert by sending requests with invalid signatures:

```bash
# Get your webhook URL from terraform output
WEBHOOK_URL=$(terraform output -raw service_url)/webhook/pi

# Send 6 requests with invalid HMAC signatures (threshold is >5 in 5 minutes)
for i in {1..6}; do
  curl -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -H "X-Signature: invalid-signature-$i" \
    -H "X-Timestamp: $(date +%s)" \
    -d '{"event_id":"test-'$i'","event_type":"purchase_requested","product_name":"Test","product_url":"https://example.com"}'
  sleep 1
done
```

**Expected:** Alert fires within 2-5 minutes, email sent to configured address.

### Test 2: Invalid Timestamp

Trigger the invalid timestamp alert by sending requests with old timestamps:

```bash
# Send requests with timestamp 6+ minutes old (tolerance is ±5 minutes)
OLD_TIMESTAMP=$(($(date +%s) - 400))  # 6 minutes 40 seconds ago

for i in {1..6}; do
  curl -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -H "X-Signature: any-signature" \
    -H "X-Timestamp: $OLD_TIMESTAMP" \
    -d '{"event_id":"test-old-'$i'","event_type":"purchase_requested","product_name":"Test","product_url":"https://example.com"}'
  sleep 1
done
```

**Expected:** Alert fires within 2-5 minutes, email sent to configured address.

### Test 3: Duplicate Event (Replay Attack)

Trigger the duplicate event alert by sending the same event_id multiple times:

```bash
# Send same event_id 6 times (threshold is >0)
EVENT_ID="test-duplicate-$(date +%s)"
TIMESTAMP=$(date +%s)

for i in {1..6}; do
  curl -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -H "X-Signature: test-signature" \
    -H "X-Timestamp: $TIMESTAMP" \
    -d '{"event_id":"'$EVENT_ID'","event_type":"purchase_requested","product_name":"Test","product_url":"https://example.com"}'
  sleep 1
done
```

**Expected:** Alert fires within 1-3 minutes, email sent to configured address.

### Verify Security Events

After running tests, check the logs:

```bash
# View security events in Cloud Logging
gcloud logging read \
  'resource.type="cloud_run_revision"
   resource.labels.service_name="fortaleza-agent"
   jsonPayload.security_event!=""
   timestamp>="'$(date -u -d '5 minutes ago' '+%Y-%m-%dT%H:%M:%SZ')'"' \
  --limit=50 \
  --project=fortaleza-purchase-agent
```

Or view in GCP Console:
- **Logs**: https://console.cloud.google.com/logs/query?project=fortaleza-purchase-agent
- **Incidents**: https://console.cloud.google.com/monitoring/alerting/incidents?project=fortaleza-purchase-agent

**Alert Timeline:**
- Event logged: Immediate
- Metric updated: 1-2 minutes
- Alert evaluates: Every 60 seconds
- Email sent: 1-2 minutes after alert fires
- **Total latency: 2-5 minutes**

## Resources

- [Terraform Google Provider Docs](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Cloud Run Terraform Reference](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_service)
- [Terraform Best Practices](https://www.terraform-best-practices.com/)
- [GCP Secret Manager Best Practices](https://cloud.google.com/secret-manager/docs/best-practices)
