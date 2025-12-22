# GitHub Actions Setup Guide

This guide helps you configure GitHub Actions for automated testing and deployment.

## Overview

The workflow automatically:
1. **On Pull Request:** Runs tests
2. **On Merge to Main:** Runs tests → Builds image → Deploys to Cloud Run → Runs smoke test

## Prerequisites

### Required Tools

1. **Terraform** (v1.5.0+)
   ```bash
   # macOS (Homebrew)
   brew tap hashicorp/tap
   brew install hashicorp/tap/terraform

   # Verify installation
   terraform version
   ```

2. **Google Cloud SDK** (`gcloud`)
   ```bash
   # macOS (Homebrew)
   brew install google-cloud-sdk

   # Authenticate
   gcloud auth login
   gcloud auth application-default login

   # Set project
   gcloud config set project fortaleza-purchase-agent
   ```

3. **GitHub CLI** (optional, for creating PRs)
   ```bash
   brew install gh
   gh auth login
   ```

### Required Access

- **GitHub Repository**: Admin access to configure secrets and workflows
- **GCP Project**: Owner or Editor role on `fortaleza-purchase-agent`
- **GCP APIs Enabled**:
  - Cloud Run API
  - Cloud Build API (for container builds)
  - Artifact Registry API
  - Secret Manager API
  - IAM API

### Verify Setup

```bash
# Check you can access GCP
gcloud projects describe fortaleza-purchase-agent

# Check GitHub access
gh repo view cvtreharne-cvt/fortaleza-purchase-agent

# Verify Terraform
cd terraform && terraform init
```

## Setup Steps

### 1. Set Up Workload Identity Federation (WIF)

**Why WIF?** More secure than JSON keys - no long-lived credentials to manage or rotate.

#### Step 1a: Create GCP Service Account

```bash
# Create service account for GitHub Actions
gcloud iam service-accounts create github-actions-fortaleza-agent \
  --display-name="GitHub Actions - Fortaleza Agent" \
  --project=fortaleza-purchase-agent

# Get the email
SA_EMAIL="github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"

# Grant deployment permissions
gcloud projects add-iam-policy-binding fortaleza-purchase-agent \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding fortaleza-purchase-agent \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding fortaleza-purchase-agent \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding fortaleza-purchase-agent \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/artifactregistry.writer"
```

#### Step 1b: Create Workload Identity Pool

```bash
# Create Workload Identity Pool
gcloud iam workload-identity-pools create "github-pool" \
  --project="fortaleza-purchase-agent" \
  --location="global" \
  --display-name="GH Actions Pool Fortaleza Agent"

# Get the pool ID
POOL_ID=$(gcloud iam workload-identity-pools describe github-pool \
  --project="fortaleza-purchase-agent" \
  --location="global" \
  --format="value(name)")

echo "Pool ID: $POOL_ID"
```

#### Step 1c: Create GitHub OIDC Provider

```bash
# Create GitHub OIDC provider
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="fortaleza-purchase-agent" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner=='cvtreharne-cvt'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

#### Step 1d: Bind Service Account to GitHub Repo

```bash
# Allow GitHub Actions from your repo to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  "github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com" \
  --project="fortaleza-purchase-agent" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/YOUR_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/cvtreharne-cvt/fortaleza-purchase-agent"

# Get your project number:
gcloud projects describe fortaleza-purchase-agent --format="value(projectNumber)"
# Replace YOUR_PROJECT_NUMBER above with the output
```

#### Step 1e: Get WIF Provider Name

```bash
# Get the full WIF provider name for GitHub secrets
gcloud iam workload-identity-pools providers describe github-provider \
  --project="fortaleza-purchase-agent" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --format="value(name)"
```

**Copy this output** - you'll add it as `WIF_PROVIDER` in GitHub secrets.

### 2. Add GitHub Secrets

Go to your repository on GitHub:
1. Click **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add these secrets:

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `WIF_PROVIDER` | Workload Identity Provider name | Output from step 1e above |
| `BROWSER_WORKER_URL` | Browser worker URL | Your Cloudflare tunnel URL |
| `BROWSER_WORKER_AUTH_TOKEN` | Worker auth token | Your auth token |
| `WEBHOOK_BASE_URL` | Cloud Run URL for webhooks | `https://fortaleza-agent-xxxxx.run.app` |

#### Adding Each Secret

For `WIF_PROVIDER`:
```
Name: WIF_PROVIDER
Value: [Paste the WIF provider name from step 1e]
```

For `BROWSER_WORKER_URL`:
```
Name: BROWSER_WORKER_URL
Value: https://your-tunnel.trycloudflare.com
```

For `BROWSER_WORKER_AUTH_TOKEN`:
```
Name: BROWSER_WORKER_AUTH_TOKEN
Value: your-secret-token-here
```

For `WEBHOOK_BASE_URL`:
```
Name: WEBHOOK_BASE_URL
Value: https://fortaleza-agent-xxxxx.run.app
```

### 3. Initial Deployment (Bootstrap)

The first time, you need to get the Cloud Run URL:

```bash
# Deploy manually once with Terraform
cd terraform
terraform init
terraform apply

# Get the URL
terraform output service_url
# Copy this URL

# Update the WEBHOOK_BASE_URL secret on GitHub
# with the actual URL from above
```

### 4. Test the Workflow

#### Method 1: Create a Test PR

```bash
# Make a small change
git checkout -b test-ci
echo "# Test" >> README.md
git add README.md
git commit -m "test: CI/CD workflow"
git push origin test-ci

# Open PR on GitHub
# Watch the "Tests" job run
```

#### Method 2: Manual Trigger

1. Go to **Actions** tab on GitHub
2. Click **Test and Deploy** workflow
3. Click **Run workflow**
4. Select branch `main`
5. Click **Run workflow**

### 5. Verify Deployment

After merging to main, check:

1. **Actions Tab:** All jobs should be green ✅
2. **Summary:** Shows deployment URL and status
3. **Cloud Run:** New revision deployed
4. **Health Check:** Visit `<service-url>/health`

## Workflow Behavior

### On Pull Request

```
Pull Request Opened/Updated
         │
         ▼
    Run Tests
         │
    ✅ Pass → Allow merge
    ❌ Fail → Block merge
```

### On Merge to Main

```
Merge to Main
     │
     ├──> Run Tests
     │         │
     │    ✅ Pass
     │         │
     ├──> Build Docker Image
     │         │
     │    Push to GCR
     │         │
     ├──> Terraform Plan & Apply
     │         │
     │    Deploy to Cloud Run
     │         │
     └──> Run Smoke Test
               │
          ✅ Success
```

## Viewing Logs

### GitHub Actions Logs

1. Go to **Actions** tab
2. Click on a workflow run
3. Click on a job (Test, Build, Deploy)
4. Expand steps to see logs

### Cloud Run Logs

```bash
# View recent logs
gcloud run services logs read fortaleza-agent \
  --region=us-central1 \
  --limit=50

# Follow logs in real-time
gcloud run services logs tail fortaleza-agent \
  --region=us-central1
```

## Troubleshooting

### "Error: Credentials not found"

**Cause:** GCP_SA_KEY secret not set or invalid

**Fix:**
1. Verify secret exists in GitHub Settings → Secrets
2. Regenerate service account key
3. Update secret with new key

### "Error: Permission denied"

**Cause:** Service account lacks permissions

**Fix:**
```bash
# Grant Cloud Run admin role
gcloud projects add-iam-policy-binding fortaleza-purchase-agent \
  --member="serviceAccount:github-actions@fortaleza-purchase-agent.iam.gserviceaccount.com" \
  --role="roles/run.admin"
```

### "Terraform apply failed"

**Cause:** Usually missing secrets or invalid configuration

**Fix:**
1. Check Terraform logs in GitHub Actions
2. Verify all secrets are set correctly
3. Test Terraform locally first:
   ```bash
   cd terraform
   terraform plan
   ```

### "Smoke test failed"

**Cause:** Service deployed but not responding

**Fix:**
1. Check Cloud Run logs for errors
2. Verify image built correctly
3. Check environment variables

## Advanced: Deployment Environments

Want separate dev/staging/prod environments? Here's how:

### 1. Create GitHub Environments

**Settings** → **Environments** → **New environment**

Create:
- `staging` - Auto-deploys on merge to main
- `production` - Requires approval before deploy

### 2. Update Workflow

```yaml
deploy-staging:
  environment: staging
  # ... deploy to staging Cloud Run service

deploy-production:
  environment: production  # Requires approval!
  needs: deploy-staging
  # ... deploy to production Cloud Run service
```

### 3. Add Protection Rules

For `production` environment:
- ✅ Required reviewers: Your team members
- ✅ Wait timer: 5 minutes
- ✅ Deployment branches: Only `main`

## Monitoring Deployments

### Slack Notifications

Add this step to get Slack notifications:

```yaml
- name: Notify Slack
  if: always()  # Run even if previous steps failed
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    payload: |
      {
        "text": "Deployment ${{ job.status }}: ${{ github.sha }}"
      }
```

### Deployment History

View all deployments:
```bash
# Cloud Run revisions
gcloud run revisions list \
  --service=fortaleza-agent \
  --region=us-central1

# GitHub deployment history
# Go to: Deployments tab on GitHub
```

## Best Practices

1. **Always test locally first**
   ```bash
   pytest tests/
   docker build -t test .
   ```

2. **Use PRs for all changes**
   - Never push directly to main
   - Let CI run tests first

3. **Review Terraform plans**
   - Check GitHub Actions logs
   - Verify changes before merge

4. **Monitor after deployment**
   - Check Cloud Run logs
   - Run manual smoke tests
   - Monitor error rates

5. **Keep secrets updated**
   - Rotate credentials regularly
   - Update GitHub secrets when changed

## Next Steps

- [ ] Set up Slack notifications
- [ ] Create staging environment
- [ ] Add deployment approval for production
- [ ] Set up error monitoring (Sentry)
- [ ] Add performance monitoring
- [ ] Configure automatic rollbacks

## Getting Help

If deployment fails:
1. Check GitHub Actions logs
2. Check Cloud Run logs
3. Test Terraform locally
4. Verify all secrets are set correctly
