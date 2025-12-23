# Required GCP APIs
#
# These APIs must be enabled for Terraform to manage the infrastructure.
# They are managed MANUALLY (not via Terraform) to avoid bootstrap issues.
#
# Manual enablement (one-time setup):
#   gcloud services enable cloudresourcemanager.googleapis.com --project=fortaleza-purchase-agent
#   gcloud services enable iam.googleapis.com --project=fortaleza-purchase-agent
#   gcloud services enable secretmanager.googleapis.com --project=fortaleza-purchase-agent
#   gcloud services enable run.googleapis.com --project=fortaleza-purchase-agent
#   gcloud services enable artifactregistry.googleapis.com --project=fortaleza-purchase-agent
#   gcloud services enable monitoring.googleapis.com --project=fortaleza-purchase-agent
#   gcloud services enable logging.googleapis.com --project=fortaleza-purchase-agent
#
# Why not managed by Terraform?
# - Chicken-and-egg: To enable APIs via Terraform, you need serviceusage.googleapis.com
#   already enabled, which itself would need to be enabled manually
# - GitHub Actions service account would need roles/serviceusage.serviceUsageAdmin
# - Simpler to enable once manually during initial project setup
#
# If you want to manage these in Terraform (advanced):
# 1. Uncomment the code below
# 2. Manually enable serviceusage.googleapis.com first:
#    gcloud services enable serviceusage.googleapis.com --project=fortaleza-purchase-agent
# 3. Grant GitHub Actions permission:
#    gcloud projects add-iam-policy-binding fortaleza-purchase-agent \
#      --member="serviceAccount:github-actions-fortaleza-agent@fortaleza-purchase-agent.iam.gserviceaccount.com" \
#      --role="roles/serviceusage.serviceUsageAdmin"

# Uncomment to manage APIs via Terraform:
# resource "google_project_service" "required_apis" {
#   for_each = toset([
#     "cloudresourcemanager.googleapis.com",  # Required for project-level IAM
#     "iam.googleapis.com",                   # Required for IAM management
#     "secretmanager.googleapis.com",         # Required for Secret Manager
#     "run.googleapis.com",                   # Required for Cloud Run
#     "artifactregistry.googleapis.com",      # Required for Docker images
#     "monitoring.googleapis.com",            # Required for alerts
#     "logging.googleapis.com",               # Required for log-based metrics
#   ])
# 
#   project = var.project_id
#   service = each.value
#   
#   # Don't disable APIs when running terraform destroy
#   # (could break other resources)
#   disable_on_destroy = false
# }
# 
# # Ensure APIs are enabled before creating resources
# # Uncomment these lines in other .tf files if using automated API enablement:
# #
# # In iam.tf:
# # depends_on = [google_project_service.required_apis]
# #
# # In cloudrun.tf:
# # depends_on = [google_project_service.required_apis]
# #
# # In secrets.tf:
# # depends_on = [google_project_service.required_apis]
