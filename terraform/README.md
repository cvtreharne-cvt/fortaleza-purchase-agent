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

3. **Container Image** built and pushed to GCR
   ```bash
   docker build -t gcr.io/fortaleza-purchase-agent/fortaleza-agent:latest .
   docker push gcr.io/fortaleza-purchase-agent/fortaleza-agent:latest
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
docker build -t gcr.io/fortaleza-purchase-agent/fortaleza-agent:v1.2.3 .
docker push gcr.io/fortaleza-purchase-agent/fortaleza-agent:v1.2.3

# 2. Update terraform.tfvars
container_image = "gcr.io/fortaleza-purchase-agent/fortaleza-agent:v1.2.3"

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

### State File Location

**Current:** Local file (`terraform.tfstate`)
- ✅ Simple for single developer
- ❌ Can't share with team
- ❌ No locking (risk of conflicts)

**Production:** Remote backend (e.g., GCS bucket)
- ✅ Shared across team
- ✅ Locking prevents conflicts
- ✅ Versioned and backed up

### Upgrading to Remote State

```hcl
# Add to provider.tf
terraform {
  backend "gcs" {
    bucket = "fortaleza-terraform-state"
    prefix = "prod"
  }
}
```

Then:
```bash
terraform init -migrate-state
```

## Troubleshooting

### "Error 403: Permission denied"

**Solution:** Ensure you're authenticated:
```bash
gcloud auth application-default login
```

### "Secret already exists"

**Cause:** Secret exists from previous deployment

**Solution 1:** Import existing secret:
```bash
terraform import google_secret_manager_secret.secrets[\"bnb_email\"] projects/fortaleza-purchase-agent/secrets/bnb_email
```

**Solution 2:** Delete and recreate:
```bash
gcloud secrets delete bnb_email
terraform apply
```

### "Container image not found"

**Cause:** Image hasn't been pushed to GCR

**Solution:** Build and push:
```bash
docker build -t gcr.io/fortaleza-purchase-agent/fortaleza-agent:latest .
docker push gcr.io/fortaleza-purchase-agent/fortaleza-agent:latest
```

### Changes Not Applying

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

## Resources

- [Terraform Google Provider Docs](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Cloud Run Terraform Reference](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_service)
- [Terraform Best Practices](https://www.terraform-best-practices.com/)
