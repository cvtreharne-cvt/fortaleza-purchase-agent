# Cloud Monitoring Configuration
# Log-based metrics and alert policies for security monitoring

# Log-based metric for failed HMAC attempts
resource "google_logging_metric" "failed_hmac_attempts" {
  name   = "security/failed_hmac_attempts"
  filter = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="fortaleza-agent"
    jsonPayload.security_event="failed_hmac"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
    display_name = "Failed HMAC Authentication Attempts"

    labels {
      key         = "client_ip"
      value_type  = "STRING"
      description = "Client IP address"
    }
  }

  label_extractors = {
    "client_ip" = "EXTRACT(jsonPayload.client_ip)"
  }

  bucket_options {
    linear_buckets {
      num_finite_buckets = 10
      width             = 1
      offset            = 0
    }
  }
}

# Log-based metric for invalid timestamp attempts
resource "google_logging_metric" "invalid_timestamp_attempts" {
  name   = "security/invalid_timestamp_attempts"
  filter = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="fortaleza-agent"
    jsonPayload.security_event="invalid_timestamp"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
    display_name = "Invalid Timestamp Attempts"

    labels {
      key         = "age_seconds"
      value_type  = "INT64"
      description = "How old/future the timestamp was"
    }
  }

  label_extractors = {
    "age_seconds" = "EXTRACT(jsonPayload.age_seconds)"
  }
}

# Log-based metric for duplicate events (replay attacks)
resource "google_logging_metric" "duplicate_events" {
  name   = "security/duplicate_events"
  filter = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="fortaleza-agent"
    jsonPayload.security_event="duplicate_event"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
    display_name = "Duplicate Event Attempts (Replay Attacks)"

    labels {
      key         = "event_id"
      value_type  = "STRING"
      description = "Duplicate event ID"
    }
  }

  label_extractors = {
    "event_id" = "EXTRACT(jsonPayload.event_id)"
  }
}

# Notification channel for email alerts (optional - can add Pushover webhook later)
resource "google_monitoring_notification_channel" "email_alerts" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "Security Alert Email"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }
}

# Alert policy for failed HMAC attempts
resource "google_monitoring_alert_policy" "failed_hmac_alert" {
  display_name = "Security: Multiple Failed HMAC Attempts"
  combiner     = "OR"

  conditions {
    display_name = "Failed HMAC attempts > 5 in 5 minutes"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.failed_hmac_attempts.name}\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5

      aggregations {
        alignment_period   = "300s"  # 5 minutes
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_alerts[0].id] : []

  alert_strategy {
    auto_close = "86400s"  # Auto-close after 24 hours
  }

  documentation {
    content = <<-EOT
      ## Security Alert: Multiple Failed HMAC Attempts

      This alert indicates **multiple failed HMAC authentication attempts** on your Fortaleza purchase agent webhook endpoint.

      **What happened:**
      - 5 or more failed HMAC signature verifications in the last 5 minutes
      - This could indicate:
        - Someone trying to forge webhook requests
        - Misconfigured client with wrong secret
        - Potential attack attempt

      **What to do:**
      1. Check Cloud Logging for details: https://console.cloud.google.com/logs
      2. Filter by: `jsonPayload.security_event="failed_hmac"`
      3. Review the client IPs involved
      4. If from unknown IP: potential attack (monitor)
      5. If from your Pi's IP: check Pi webhook configuration

      **Note:** Your service is protected - invalid requests are rejected.
    EOT
  }
}

# Alert policy for duplicate events (replay attacks)
resource "google_monitoring_alert_policy" "duplicate_event_alert" {
  display_name = "Security: Duplicate Event Detected (Possible Replay Attack)"
  combiner     = "OR"

  conditions {
    display_name = "Duplicate event detected"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.duplicate_events.name}\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0  # Alert on ANY duplicate

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = var.alert_email != "" ? [google_monitoring_notification_channel.email_alerts[0].id] : []

  alert_strategy {
    auto_close = "3600s"  # Auto-close after 1 hour
  }

  documentation {
    content = <<-EOT
      ## Security Alert: Duplicate Event (Possible Replay Attack)

      This alert indicates a **duplicate webhook event** was received.

      **What happened:**
      - Same event ID received multiple times
      - Could indicate:
        - Replay attack (attacker replaying captured request)
        - Pi retrying a webhook (normal if first failed)

      **What to do:**
      1. Check if this event was already processed successfully
      2. Review timing - if minutes apart, likely replay attack
      3. If from Pi during outage/retry: normal
      4. If from unknown source: investigate

      **Note:** Duplicate events are automatically rejected - no action needed.
    EOT
  }
}

# Outputs
output "security_metrics" {
  description = "Log-based metrics for security monitoring"
  value = {
    failed_hmac         = google_logging_metric.failed_hmac_attempts.id
    invalid_timestamp   = google_logging_metric.invalid_timestamp_attempts.id
    duplicate_events    = google_logging_metric.duplicate_events.id
  }
}
