"""Pushover notification client for real-time status updates."""

from enum import Enum
from typing import Optional

import httpx

from .logging import get_logger
from .secrets import get_secret_manager

logger = get_logger(__name__)


class NotificationPriority(int, Enum):
    """Pushover notification priority levels."""
    LOWEST = -2
    LOW = -1
    NORMAL = 0
    HIGH = 1
    EMERGENCY = 2


class NotificationType(str, Enum):
    """Types of notifications sent during agent execution."""
    START = "start"
    SUCCESS = "success"
    FAILURE = "failure"
    HUMAN_ASSIST = "human_assist"
    INFO = "info"


class PushoverClient:
    """Client for sending Pushover notifications."""
    
    PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"
    
    def __init__(self):
        """Initialize Pushover client with credentials from Secret Manager."""
        secret_manager = get_secret_manager()
        try:
            creds = secret_manager.get_pushover_credentials()
            self.app_token = creds["app_token"]
            self.user_key = creds["user_key"]
            self.enabled = True
            logger.info("Pushover client initialized")
        except Exception as e:
            logger.warning("Failed to initialize Pushover client, notifications disabled", error=str(e))
            self.enabled = False
            self.app_token = None
            self.user_key = None
    
    def send(
        self,
        message: str,
        title: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        url: Optional[str] = None,
        url_title: Optional[str] = None,
    ) -> bool:
        """
        Send a notification via Pushover.
        
        Args:
            message: The notification message
            title: Optional title for the notification
            priority: Notification priority level
            url: Optional URL to include
            url_title: Optional title for the URL
            
        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Pushover notifications disabled, skipping", message=message)
            return False
        
        payload = {
            "token": self.app_token,
            "user": self.user_key,
            "message": message,
            "priority": priority.value,
        }
        
        if title:
            payload["title"] = title
        if url:
            payload["url"] = url
        if url_title:
            payload["url_title"] = url_title
        
        try:
            response = httpx.post(self.PUSHOVER_API_URL, data=payload, timeout=10.0)
            response.raise_for_status()
            logger.info("Pushover notification sent", title=title, priority=priority.value)
            return True
        except Exception as e:
            logger.error("Failed to send Pushover notification", error=str(e), title=title)
            return False
    
    def notify_start(self, run_id: str, product_name: str) -> bool:
        """Notify that agent execution has started."""
        return self.send(
            message=f"Agent run {run_id} started for product: {product_name}",
            title="🚀 Fortaleza Agent Started",
            priority=NotificationPriority.NORMAL,
        )
    
    def notify_success(self, run_id: str, product_name: str, order_number: Optional[str] = None) -> bool:
        """Notify successful purchase."""
        message = f"Successfully purchased {product_name}!"
        if order_number:
            message += f"\nOrder: {order_number}"
        
        return self.send(
            message=message,
            title="✅ Purchase Successful",
            priority=NotificationPriority.HIGH,
        )
    
    def notify_failure(self, run_id: str, error: str, details: Optional[str] = None) -> bool:
        """Notify purchase failure."""
        message = f"Run {run_id} failed: {error}"
        if details:
            message += f"\n\nDetails: {details}"
        
        return self.send(
            message=message,
            title="❌ Purchase Failed",
            priority=NotificationPriority.HIGH,
        )
    
    def notify_human_assist_needed(
        self,
        run_id: str,
        reason: str,
        details: Optional[str] = None
    ) -> bool:
        """Notify that human intervention is required."""
        message = f"Run {run_id} requires human assistance: {reason}"
        if details:
            message += f"\n\n{details}"
        
        return self.send(
            message=message,
            title="🚨 Human Assistance Needed",
            priority=NotificationPriority.HIGH,
        )
    
    def notify_sold_out(self, run_id: str, product_name: str) -> bool:
        """Notify that product is sold out."""
        return self.send(
            message=f"Product {product_name} is sold out. Agent will wait for next email notification.",
            title="⏸️ Product Sold Out",
            priority=NotificationPriority.NORMAL,
        )


# Global instance
_pushover_client: Optional[PushoverClient] = None


def get_pushover_client() -> PushoverClient:
    """Get or create the global PushoverClient instance."""
    global _pushover_client
    if _pushover_client is None:
        _pushover_client = PushoverClient()
    return _pushover_client
