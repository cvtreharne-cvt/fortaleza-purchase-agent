# Secret Manager Resources
# These define the secrets (but NOT their values)

# List of all secrets needed for the application
locals {
  secrets = [
    "bnb_email",
    "bnb_password",
    "cc_number",
    "cc_exp_month",
    "cc_exp_year",
    "cc_cvv",
    "cc_name",
    "billing_name",
    # Billing address secrets removed - not currently in Secret Manager
    # Add them to Secret Manager if needed, or provide via different method
    "dob_month",
    "dob_day",
    "dob_year",
    "pushover_app_token",
    "pushover_user_key",
    "pi_webhook_shared_secret",
    "google_api_key",
    "browser_worker_auth_token",
  ]
}

# Create a Secret Manager secret for each item
resource "google_secret_manager_secret" "secrets" {
  for_each = toset(local.secrets)

  secret_id = each.value  # The name of the secret

  replication {
    auto {}  # Automatically replicate across all regions
  }

  labels = {
    app = "fortaleza-agent"
  }
}

# Note: The actual secret VALUES are not managed by Terraform
# You add them manually via:
# echo -n "secret-value" | gcloud secrets versions add SECRET_NAME --data-file=-
#
# Or you can use terraform_data with a local-exec provisioner
# But that's less secure (values in state file)
