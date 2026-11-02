"""Base abstraction for WhatsApp message delivery providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
from src.models import Contact, SendStatus


@dataclass
class ProviderResult:
    """Outcome of a provider dispatch attempt."""
    success: bool
    status: SendStatus
    notes: str = ""
    message_id: str = ""
    chat_url: str = ""
    requires_manual_confirmation: bool = False


class BaseMessageProvider(ABC):
    """Abstract base class for WhatsApp delivery providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Display name of the provider."""
        pass

    @property
    @abstractmethod
    def is_automated(self) -> bool:
        """True if messages are sent automatically without human-in-the-loop."""
        pass

    @abstractmethod
    def validate_configuration(self) -> Tuple[bool, str]:
        """Verify that provider settings/credentials are configured and valid.

        Returns:
            Tuple of (is_valid, error_or_status_message).
        """
        pass

    @abstractmethod
    def send(self, contact: Contact, personalized_message: str, **kwargs) -> ProviderResult:
        """Dispatch or prepare message for the recipient.

        Args:
            contact: Validated recipient contact.
            personalized_message: Formatted text with placeholders substituted.

        Returns:
            ProviderResult containing status, notes, and metadata.
        """
        pass

