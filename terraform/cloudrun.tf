# Cloud Run Service Configuration
# This is your main application deployment

resource "google_cloud_run_service" "fortaleza_agent" {
  name     = var.service_name
  location = var.region

  template {
    spec {
      # Container configuration
      containers {
        image = var.container_image

        # Resource limits
        # Why 512 MB RAM?
        # - Browser runs remotely on Pi (via browser_worker_url), not in Cloud Run
        # - Cloud Run only runs FastAPI app + webhook handling + ADK agent
        # - Typical memory usage: ~150-250 MB during purchase flow
        # - 512 MB provides comfortable headroom for:
        #   * FastAPI framework
        #   * Gemini ADK agent with tool execution
        #   * HTTP clients (requests library)
        #   * Concurrent requests during approval flow
        # - Could reduce to 256 MB for cost savings if needed
        resources {
          limits = {
            cpu    = "1000m"  # 1 CPU (standard for Python web apps)
            memory = "512Mi"  # 512 MB RAM (see comment above)
          }
        }

        # Environment variables (non-sensitive)
        env {
          name  = "MODE"
          value = "prod"
        }

        env {
          name  = "CONFIRM_PROD"
          value = "YES"
        }

        env {
          name  = "HEADLESS"
          value = "true"
        }

        env {
          name  = "BROWSER_WORKER_URL"
          value = var.browser_worker_url
        }

        env {
          name  = "WEBHOOK_BASE_URL"
          value = var.webhook_base_url
        }

        # BROWSER_WORKER_AUTH_TOKEN now comes from Secret Manager
        # (automatically mounted by dynamic block below)

        env {
          name  = "LOG_LEVEL"
          value = "INFO"
        }

        env {
          name  = "JSON_LOGS"
          value = "true"
        }

        # Timeout configurations
        env {
          name  = "BROWSER_LAUNCH_TIMEOUT"
          value = tostring(var.browser_launch_timeout)
        }

        env {
          name  = "BROWSER_TIMEOUT"
          value = tostring(var.browser_timeout)
        }

        env {
          name  = "NAVIGATION_TIMEOUT"
          value = tostring(var.navigation_timeout)
        }

        env {
          name  = "BROWSER_WORKER_TIMEOUT"
          value = tostring(var.approval_flow_timeout_seconds)
        }

        # Mount secrets as environment variables
        # This loops through all secrets and mounts them
        dynamic "env" {
          for_each = google_secret_manager_secret.secrets

          content {
            name = upper(env.key)  # Secret name in UPPERCASE

            value_from {
              secret_key_ref {
                name = env.value.secret_id
                key  = "latest"  # Use latest version
              }
            }
          }
        }
      }

      # Service account to run as
      service_account_name = data.google_compute_default_service_account.default.email

      # Timeout for requests (must accommodate approval flow)
      timeout_seconds = var.approval_flow_timeout_seconds
    }

    metadata {
      annotations = {
        # Autoscaling configuration
        "autoscaling.knative.dev/minScale" = "0"  # Scale to zero when idle
        "autoscaling.knative.dev/maxScale" = "1"  # Max 1 instance

        # Cloud Run execution environment
        "run.googleapis.com/execution-environment" = "gen2"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  # Prevent accidental deletion
  lifecycle {
    prevent_destroy = false  # Set to true in production!
  }
}

# Make the service publicly accessible (for webhooks)
resource "google_cloud_run_service_iam_member" "public_access" {
  service  = google_cloud_run_service.fortaleza_agent.name
  location = google_cloud_run_service.fortaleza_agent.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Output the service URL
output "service_url" {
  description = "URL of the deployed Cloud Run service"
  value       = google_cloud_run_service.fortaleza_agent.status[0].url
}
