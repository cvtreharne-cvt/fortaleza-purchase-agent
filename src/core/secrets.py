"""GCP Secret Manager integration for secure credential storage."""

from typing import Optional

from google.cloud import secretmanager

from .config import get_settings
from .errors import SecretNotFoundError
from .logging import get_logger

logger = get_logger(__name__)


class SecretManager:
    """Manager for GCP Secret Manager access."""
    
    def __init__(self):
        """Initialize Secret Manager client."""
        self.settings = get_settings()
        self.client: Optional[secretmanager.SecretManagerServiceClient] = None
        
        if self.settings.use_secret_manager and self.settings.gcp_project_id:
            try:
                self.client = secretmanager.SecretManagerServiceClient()
                logger.info("Secret Manager client initialized", project_id=self.settings.gcp_project_id)
            except Exception as e:
                logger.warning("Failed to initialize Secret Manager client", error=str(e))
                self.client = None
    
    def get_secret(self, secret_name: str) -> str:
        """
        Get a secret value from GCP Secret Manager or local environment.
        
        Args:
            secret_name: Name of the secret (e.g., "bnb_email")
            
        Returns:
            Secret value as string
            
        Raises:
            SecretNotFoundError: If secret is not found in either GCP or local env
        """
        # Try GCP Secret Manager first if configured
        if self.client and self.settings.gcp_project_id:
            try:
                name = f"projects/{self.settings.gcp_project_id}/secrets/{secret_name}/versions/latest"
                response = self.client.access_secret_version(request={"name": name})
                secret_value = response.payload.data.decode("UTF-8")
                logger.debug("Retrieved secret from GCP Secret Manager", secret_name=secret_name)
                return secret_value
            except Exception as e:
                logger.warning(
                    "Failed to retrieve secret from GCP, trying local fallback",
                    secret_name=secret_name,
                    error=str(e)
                )
        
        # Fallback to local environment variable
        local_value = getattr(self.settings, secret_name, None)
        if local_value:
            logger.debug("Retrieved secret from local environment", secret_name=secret_name)
            return local_value
        
        # Secret not found anywhere
        raise SecretNotFoundError(
            f"Secret '{secret_name}' not found in GCP Secret Manager or local environment"
        )
    
    def get_credentials(self) -> dict:
        """
        Get all required credentials for the agent.
        
        Returns:
            Dictionary with all credential values
        """
        credentials = {
            "bnb_email": self.get_secret("bnb_email"),
            "bnb_password": self.get_secret("bnb_password"),
            "cc_number": self.get_secret("cc_number"),
            "cc_exp_month": self.get_secret("cc_exp_month"),
            "cc_exp_year": self.get_secret("cc_exp_year"),
            "cc_cvv": self.get_secret("cc_cvv"),
            "billing_name": self.get_secret("billing_name"),
            "billing_address1": self.get_secret("billing_address1"),
            "billing_address2": self.get_secret("billing_address2") if self._secret_exists("billing_address2") else "",
            "billing_city": self.get_secret("billing_city"),
            "billing_state": self.get_secret("billing_state"),
            "billing_zip": self.get_secret("billing_zip"),
            "dob_month": self.get_secret("dob_month"),
            "dob_day": self.get_secret("dob_day"),
            "dob_year": self.get_secret("dob_year"),
        }
        
        logger.info("Successfully retrieved all credentials")
        return credentials
    
    def get_pushover_credentials(self) -> dict:
        """Get Pushover notification credentials."""
        return {
            "app_token": self.get_secret("pushover_app_token"),
            "user_key": self.get_secret("pushover_user_key"),
        }
    
    def get_webhook_secret(self) -> str:
        """Get webhook HMAC shared secret."""
        return self.get_secret("pi_webhook_shared_secret")
    
    def get_google_api_key(self) -> str:
        """Get Google Gemini API key for ADK."""
        return self.get_secret("google_api_key")
    
    def _secret_exists(self, secret_name: str) -> bool:
        """Check if a secret exists without raising an exception."""
        try:
            self.get_secret(secret_name)
            return True
        except SecretNotFoundError:
            return False


# Global instance
_secret_manager: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """Get or create the global SecretManager instance."""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager()
    return _secret_manager
