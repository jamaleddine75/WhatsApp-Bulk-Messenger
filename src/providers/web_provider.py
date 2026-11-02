"""WhatsApp Web manual click-to-chat provider."""

import webbrowser
from typing import Optional, Tuple
from src.diagnostics import get_logger
from src.message_engine import MessageEngine
from src.models import Contact, SendStatus
from src.providers.base import BaseMessageProvider, ProviderResult

_logger = get_logger()


class WhatsAppWebManualProvider(BaseMessageProvider):
    """Opens chats in WhatsApp Web with prefilled message for operator manual review.

    Complies with WhatsApp terms: Does not simulate DOM clicks or bypass protections.
    Requires operator to review the message in browser and hit Send.
    """

    def __init__(self, message_engine: Optional[MessageEngine] = None):
        self.message_engine = message_engine or MessageEngine()

    @property
    def name(self) -> str:
        return "WhatsApp Web Click-to-Chat (Manual Review)"

    @property
    def is_automated(self) -> bool:
        return False

    def validate_configuration(self) -> Tuple[bool, str]:
        """Browser click-to-chat requires an active browser session with WhatsApp Web."""
        return True, "Ready to open chats in default browser."

    def send(self, contact: Contact, personalized_message: str, **kwargs) -> ProviderResult:
        """Construct click-to-chat URL and launch in user's browser."""
        url = self.message_engine.build_click_to_chat_url(
            contact.clean_phone, personalized_message
        )
        contact.chat_url = url

        _logger.info("Opening WhatsApp Web click-to-chat: %s", url)

        try:
            opened = webbrowser.open(url, new=2, autoraise=True)
            if not opened:
                _logger.warning("Browser open command returned false/non-zero.")
        except Exception as e:
            _logger.error("Browser launch error: %s", e)
            return ProviderResult(
                success=False,
                status=SendStatus.FAILED,
                notes=f"Browser launch error: {str(e)}",
                chat_url=url,
                requires_manual_confirmation=False,
            )

        return ProviderResult(
            success=True,
            status=SendStatus.OPENED,
            notes="Chat opened in WhatsApp Web for manual review",
            chat_url=url,
            requires_manual_confirmation=True,
        )

