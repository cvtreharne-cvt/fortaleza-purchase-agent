# Variables Definition
# These let you parameterize your infrastructure

variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "fortaleza-purchase-agent"
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Name of the Cloud Run service"
  type        = string
  default     = "fortaleza-agent"
}

variable "container_image" {
  description = "Container image to deploy"
  type        = string
  # You'll need to update this when you build new images
  default     = "us-central1-docker.pkg.dev/fortaleza-purchase-agent/agents/fortaleza:latest"
}

variable "browser_worker_url" {
  description = "Browser worker URL (your Pi)"
  type        = string
  sensitive   = true  # Won't show in logs
}

# browser_worker_auth_token removed - now in Secret Manager
# (mounted automatically via dynamic block in cloudrun.tf)

variable "webhook_base_url" {
  description = "Base URL for approval webhooks"
  type        = string
}

# Timeout configurations
variable "browser_launch_timeout" {
  description = "Browser launch timeout in milliseconds"
  type        = number
  default     = 300000  # 5 minutes for Cloud Run cold starts
}

variable "browser_timeout" {
  description = "Browser timeout in milliseconds"
  type        = number
  default     = 60000  # 1 minute
}

variable "navigation_timeout" {
  description = "Navigation timeout in milliseconds"
  type        = number
  default     = 120000  # 2 minutes for Cloud Run (vs 30s for local)
}

variable "approval_flow_timeout_seconds" {
  description = "Timeout in seconds for the entire approval flow (used for both Cloud Run service timeout and browser worker HTTP timeout)"
  type        = number
  default     = 900  # 15 minutes for human approval
}
