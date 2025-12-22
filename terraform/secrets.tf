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
    # Note: Billing address fields (address1, city, state, zip) are NOT needed
    # because B&B auto-fills them after login. Only billing_name is required.
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

# IMPORTANT: Terraform creates secret CONTAINERS, not the secret VALUES
# You MUST populate secret values manually after terraform apply
#
# To populate a secret:
# echo -n "your-secret-value" | gcloud secrets versions add SECRET_NAME --data-file=-
#
# Required secrets to populate (see terraform/README.md for full guide):
# - bnb_email, bnb_password (B&B account credentials)
# - cc_number, cc_exp_month, cc_exp_year, cc_cvv, cc_name (Credit card)
# - dob_month, dob_day, dob_year (Date of birth for age verification)
# - billing_name (Billing name - address auto-filled by B&B)
# - pushover_app_token, pushover_user_key (For push notifications)
# - pi_webhook_shared_secret (HMAC authentication for Pi webhooks)
# - browser_worker_auth_token (Bearer token for Pi browser worker)
# - google_api_key (For Gemini ADK agent)
#
# VALIDATION: The Cloud Run service will fail at runtime if secrets are empty!
# Test your deployment after populating secrets to ensure everything works.
#
# SECURITY: Never commit secret VALUES to git or store in terraform.tfvars
# Always use Secret Manager for sensitive data.
