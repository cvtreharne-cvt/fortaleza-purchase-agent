#!/bin/bash
# Import existing secrets into Terraform state

PROJECT_ID="fortaleza-purchase-agent"

echo "Importing existing secrets into Terraform state..."

secrets=(
  "bnb_email"
  "bnb_password"
  "cc_number"
  "cc_exp_month"
  "cc_exp_year"
  "cc_cvv"
  "cc_name"
  "billing_name"
  "dob_month"
  "dob_day"
  "dob_year"
  "pushover_app_token"
  "pushover_user_key"
  "pi_webhook_shared_secret"
  "google_api_key"
  "browser_worker_auth_token"
)

for secret in "${secrets[@]}"; do
  echo "Importing: $secret"
  terraform import "google_secret_manager_secret.secrets[\"$secret\"]" "projects/$PROJECT_ID/secrets/$secret"
done

echo ""
echo "✅ Import complete!"
echo "Now run: terraform plan"
