# Provider Configuration
# This tells Terraform to use the Google Cloud provider and which project/region to use

terraform {
  # Specify the minimum Terraform version required
  required_version = ">= 1.5.0"

  # Declare which providers we need
  required_providers {
    google = {
      source  = "hashicorp/google"  # Official Google Cloud provider
      version = "~> 5.0"             # Use version 5.x (allows minor updates)
    }
  }
}

# Configure the Google Cloud provider
provider "google" {
  project = "fortaleza-purchase-agent"  # Your GCP project ID
  region  = "us-central1"                # Default region for resources
}
