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

# Grant GitHub Actions service account permission to push images to Artifact Registry
resource "google_artifact_registry_repository_iam_member" "github_actions_writer" {
  project    = var.project_id
  location   = "us-central1"
  repository = "agents"
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com"
}

# Output the service account email for reference
output "service_account_email" {
  description = "Service account used by Cloud Run"
  value       = data.google_compute_default_service_account.default.email
}
