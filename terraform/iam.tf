# IAM Configuration
# Grants permissions for the Cloud Run service to access secrets

# Get the default Compute Engine service account
# Cloud Run uses this by default
data "google_compute_default_service_account" "default" {}

# Grant the service account access to read all secrets
resource "google_secret_manager_secret_iam_member" "secret_access" {
  for_each = google_secret_manager_secret.secrets

  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}

# Grant GitHub Actions service account permissions for CI/CD
#
# Note: The Terraform state bucket (fortaleza-purchase-agent-tfstate) and
# GitHub Actions' access to it are managed OUTSIDE of Terraform to avoid
# circular dependencies (the bucket stores Terraform's own state).
#
# Bootstrap resources were created manually:
#   gcloud storage buckets create gs://fortaleza-purchase-agent-tfstate \
#     --location=us-central1 --uniform-bucket-level-access
#
#   gcloud storage buckets add-iam-policy-binding \
#     gs://fortaleza-purchase-agent-tfstate \
#     --member="serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com" \
#     --role="roles/storage.objectAdmin"
#
# This is a best practice: state storage infrastructure should be managed
# separately from the infrastructure it tracks.

# 1. Permission to push images to Artifact Registry
resource "google_artifact_registry_repository_iam_member" "github_actions_writer" {
  project    = var.project_id
  location   = "us-central1"
  repository = "agents"
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"
}

# 2. Permission to read Compute Engine resources (needed by Terraform data sources)
resource "google_project_iam_member" "github_actions_compute_viewer" {
  project = var.project_id
  role    = "roles/compute.viewer"
  member  = "serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"
}

# 3. Permission to manage Secret Manager secrets (needed by Terraform)
resource "google_project_iam_member" "github_actions_secret_admin" {
  project = var.project_id
  role    = "roles/secretmanager.admin"
  member  = "serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"
}

# 4. Permission to manage Cloud Run services (needed by Terraform)
resource "google_project_iam_member" "github_actions_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"
}

# 5. Permission to manage Monitoring resources (needed by Terraform)
resource "google_project_iam_member" "github_actions_monitoring_admin" {
  project = var.project_id
  role    = "roles/monitoring.admin"
  member  = "serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"
}

# 6. Permission to manage IAM policies (needed by Terraform to create IAM bindings)
resource "google_project_iam_member" "github_actions_iam_admin" {
  project = var.project_id
  role    = "roles/iam.securityAdmin"
  member  = "serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"
}

# 7. Permission to act as service accounts (needed for Cloud Run deployment)
resource "google_project_iam_member" "github_actions_service_account_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"
}

# Output the service account email for reference
output "service_account_email" {
  description = "Service account used by Cloud Run"
  value       = data.google_compute_default_service_account.default.email
}
