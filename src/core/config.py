"""Configuration management using Pydantic Settings."""

import os
from enum import Enum
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .errors import ConfigurationError


# Timeout constants (in milliseconds)
NAVIGATION_TIMEOUT_DEFAULT = 30000  # 30 seconds for local development
NAVIGATION_TIMEOUT_CLOUD_RUN = 120000  # 2 minutes for slow Cloud Run cold starts


class Mode(str, Enum):
    """Operating mode for the agent."""
    DRYRUN = "dryrun"
    TEST = "test"
    PROD = "prod"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Operating Mode
    mode: Mode = Field(default=Mode.DRYRUN, description="Operating mode")
    confirm_prod: str = Field(default="NO", description="Confirmation for production mode")
    
    # Product Configuration
    product_name: str = Field(default="Fortaleza", description="Product to purchase")
    product_url: Optional[str] = Field(default=None, description="Optional direct product URL")
    
    # Browser Configuration
    headless: bool = Field(default=True, description="Run browser in headless mode")
    browser_launch_timeout: int = Field(default=300000, description="Browser launch timeout in milliseconds (5 minutes for Cloud Run cold starts)")
    browser_timeout: int = Field(default=60000, description="Browser timeout in milliseconds")
    navigation_timeout: int = Field(default=NAVIGATION_TIMEOUT_DEFAULT, description="Navigation timeout in milliseconds (30s default, set to 120000 for Cloud Run)")
    
    # Retry Configuration
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: int = Field(default=2, description="Base retry delay in seconds")
    
    # GCP Configuration
    gcp_project_id: Optional[str] = Field(default=None, description="GCP project ID")
    gcp_region: str = Field(default="us-central1", description="GCP region")
    use_secret_manager: bool = Field(default=True, description="Use GCP Secret Manager")
    
    # Local Secrets (development only - never use in production)
    bnb_email: Optional[str] = Field(default=None, description="B&B account email (local dev only)")
    bnb_password: Optional[str] = Field(default=None, description="B&B password (local dev only)")
    cc_number: Optional[str] = Field(default=None, description="Credit card number (local dev only)")
    cc_exp_month: Optional[str] = Field(default=None, description="CC expiry month (local dev only)")
    cc_exp_year: Optional[str] = Field(default=None, description="CC expiry year (local dev only)")
    cc_cvv: Optional[str] = Field(default=None, description="CC CVV (local dev only)")
    billing_name: Optional[str] = Field(default=None, description="Billing name (local dev only)")
    billing_address1: Optional[str] = Field(default=None, description="Billing address 1 (local dev only)")
    billing_address2: Optional[str] = Field(default="", description="Billing address 2 (local dev only)")
    billing_city: Optional[str] = Field(default=None, description="Billing city (local dev only)")
    billing_state: Optional[str] = Field(default=None, description="Billing state (local dev only)")
    billing_zip: Optional[str] = Field(default=None, description="Billing ZIP (local dev only)")
    dob_month: Optional[str] = Field(default=None, description="Date of birth month (local dev only)")
    dob_day: Optional[str] = Field(default=None, description="Date of birth day (local dev only)")
    dob_year: Optional[str] = Field(default=None, description="Date of birth year (local dev only)")
    pushover_app_token: Optional[str] = Field(default=None, description="Pushover app token (local dev only)")
    pushover_user_key: Optional[str] = Field(default=None, description="Pushover user key (local dev only)")
    pi_webhook_shared_secret: Optional[str] = Field(default=None, description="Webhook HMAC secret (local dev only)")
    
    # Google Gemini API Key (for ADK)
    google_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    agent_model: str = Field(default="gemini-2.5-flash-lite", description="Google Gemini model for agent")

    # Webhook Configuration
    webhook_timestamp_tolerance: int = Field(default=300, description="Webhook timestamp tolerance in seconds")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    json_logs: bool = Field(default=True, description="Use JSON logging format")
    
    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v):
        """Validate and normalize mode."""
        if isinstance(v, str):
            return v.lower()
        return v
    
    @field_validator("confirm_prod", mode="before")
    @classmethod
    def validate_confirm_prod(cls, v):
        """Validate production confirmation."""
        if isinstance(v, str):
            return v.upper()
        return v
    
    def validate_production_mode(self):
        """Validate that production mode has proper confirmation."""
        if self.mode == Mode.PROD and self.confirm_prod != "YES":
            raise ConfigurationError(
                "Production mode requires CONFIRM_PROD=YES. "
                "This is a safety measure to prevent accidental purchases."
            )
    
    def is_cloud_environment(self) -> bool:
        """Check if running in cloud environment."""
        return os.getenv("K_SERVICE") is not None  # Cloud Run sets this
    
    def __repr__(self):
        """Redact sensitive fields in repr."""
        safe_dict = {}
        for key, value in self.model_dump().items():
            if any(sensitive in key.lower() for sensitive in ["password", "secret", "key", "token", "cc_", "cvv"]):
                safe_dict[key] = "***REDACTED***"
            else:
                safe_dict[key] = value
        return f"Settings({safe_dict})"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.validate_production_mode()
    return _settings


def reload_settings() -> Settings:
    """Reload settings (useful for testing)."""
    global _settings
    _settings = None
    return get_settings()
