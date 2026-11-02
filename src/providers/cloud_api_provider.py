"""Official WhatsApp Business Cloud API automated sending provider."""

import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.request
import urllib.error

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from src.config import (
    DEFAULT_CLOUD_API_VERSION,
    ENV_WHATSAPP_PHONE_NUMBER_ID,
    ENV_WHATSAPP_TOKEN,
    WHATSAPP_CLOUD_API_BASE,
)
from src.diagnostics import get_logger
from src.models import Contact, SendStatus
from src.providers.base import BaseMessageProvider, ProviderResult

_logger = get_logger()


class WhatsAppCloudApiProvider(BaseMessageProvider):
    """Automated delivery provider using the official WhatsApp Business Cloud API.

    Uses documented REST endpoints under https://graph.facebook.com/.
    Requires explicit opt-in consent and securely supplied credentials.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: str = DEFAULT_CLOUD_API_VERSION,
        api_base: str = WHATSAPP_CLOUD_API_BASE,
        transport_fn: Optional[Callable[[urllib.request.Request], Tuple[int, bytes]]] = None,
        session: Optional[requests.Session] = None,
    ):
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self.api_version = api_version
        self.api_base = api_base
        self.transport_fn = transport_fn

        if session is not None:
            self._session = session
        else:
            self._session = self._create_resilient_session()

    @staticmethod
    def _create_resilient_session() -> requests.Session:
        """Create a requests session with exponential backoff retries for transient 429/5xx errors."""
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    @property
    def name(self) -> str:
        return "Official WhatsApp Business Cloud API (Automated)"

    @property
    def is_automated(self) -> bool:
        return True

    @property
    def access_token(self) -> str:
        """Fetch token from instance variable or environment."""
        if self._access_token:
            return self._access_token.strip()
        return os.environ.get(ENV_WHATSAPP_TOKEN, "").strip() or os.environ.get(
            "WHATSAPP_CLOUD_API_ACCESS_TOKEN", ""
        ).strip()

    @property
    def phone_number_id(self) -> str:
        """Fetch phone number ID from instance variable or environment."""
        if self._phone_number_id:
            return self._phone_number_id.strip()
        return os.environ.get(ENV_WHATSAPP_PHONE_NUMBER_ID, "").strip()

    def set_credentials(self, access_token: str, phone_number_id: str) -> None:
        """Update runtime credentials."""
        self._access_token = access_token.strip()
        self._phone_number_id = phone_number_id.strip()

    def validate_configuration(self) -> Tuple[bool, str]:
        """Verify that required API credentials exist."""
        token = self.access_token
        phone_id = self.phone_number_id

        if not token:
            return (
                False,
                f"Missing WhatsApp Cloud API access token. Set {ENV_WHATSAPP_TOKEN} in environment or settings.",
            )

        if not phone_id:
            return (
                False,
                f"Missing WhatsApp Phone Number ID. Set {ENV_WHATSAPP_PHONE_NUMBER_ID} in environment or settings.",
            )

        if len(token) < 15 or token.startswith("YOUR_"):
            return False, "Invalid or placeholder access token detected."

        if not phone_id.isdigit():
            return False, f"Phone Number ID should be numeric (got: '{phone_id}')."

        return True, "Cloud API configured and ready."

    def test_connection(self) -> Tuple[bool, str]:
        """Validate live API credentials by querying the Meta Graph API phone number node.

        GET https://graph.facebook.com/{api_version}/{phone_number_id}

        Returns:
            Tuple[bool, str]: (Success, Descriptive Message)
        """
        valid, err_msg = self.validate_configuration()
        if not valid:
            return False, err_msg

        endpoint = f"{self.api_base}/{self.api_version}/{self.phone_number_id}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "WhatsAppBulkMessenger/1.1",
        }

        try:
            resp = self._session.get(endpoint, headers=headers, timeout=(5.0, 15.0))
            data = resp.json()

            if resp.status_code == 200:
                verified_name = data.get("verified_name", "N/A")
                display_num = data.get("display_phone_number", self.phone_number_id)
                quality = data.get("quality_rating", "UNKNOWN")
                msg = f"Connected to {verified_name} ({display_num}) • Quality: {quality}"
                _logger.info("Cloud API test_connection succeeded: %s", msg)
                return True, msg
            else:
                err = data.get("error", {})
                error_msg = err.get("message", f"HTTP {resp.status_code}")
                code = err.get("code", resp.status_code)
                msg = f"Cloud API verification failed ({code}): {error_msg}"
                _logger.warning(msg)
                return False, msg

        except requests.exceptions.Timeout:
            msg = "Connection timed out connecting to Meta Graph API."
            _logger.error(msg)
            return False, msg
        except requests.exceptions.RequestException as e:
            msg = f"Network error during connection test: {e}"
            _logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Unexpected error during connection test: {e}"
            _logger.error(msg)
            return False, msg

    def build_payload(
        self,
        clean_phone: str,
        message: str,
        template_name: Optional[str] = None,
        language_code: str = "fr",
        template_parameters: Optional[List[str]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build compliant JSON payload for Cloud API.

        Supports both standard text messages and official approved template messages.
        """
        if template_name:
            if components:
                built_components = components
            elif template_parameters:
                built_components = [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(p)} for p in template_parameters
                        ],
                    }
                ]
            else:
                built_components = [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": message}],
                    }
                ]

            return {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                    "components": built_components,
                },
            }

        # Documented Standard Text Message Payload
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message,
            },
        }

    def send(
        self,
        contact: Contact,
        personalized_message: str,
        template_name: Optional[str] = None,
        language_code: str = "fr",
        template_parameters: Optional[List[str]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> ProviderResult:
        """Send automated message via WhatsApp Business Cloud API."""
        valid, err_msg = self.validate_configuration()
        if not valid:
            _logger.error("Cloud API configuration invalid: %s", err_msg)
            return ProviderResult(
                success=False,
                status=SendStatus.FAILED,
                notes=f"Configuration Error: {err_msg}",
            )

        endpoint = f"{self.api_base}/{self.api_version}/{self.phone_number_id}/messages"
        payload = self.build_payload(
            contact.clean_phone,
            personalized_message,
            template_name=template_name,
            language_code=language_code,
            template_parameters=template_parameters,
            components=components,
        )

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "WhatsAppBulkMessenger/1.1",
        }

        _logger.info(
            "Dispatching via WhatsApp Cloud API to %s (phone_id=%s)...",
            contact.clean_phone,
            self.phone_number_id,
        )

        # 1. Backwards-compatible legacy transport_fn support
        if self.transport_fn:
            payload_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url=endpoint,
                data=payload_bytes,
                headers=headers,
                method="POST",
            )
            try:
                status_code, resp_bytes = self.transport_fn(req)
                data = json.loads(resp_bytes.decode("utf-8"))
                return self._parse_api_response(status_code, data, contact)
            except urllib.error.HTTPError as he:
                try:
                    err_body = he.read().decode("utf-8")
                    err_json = json.loads(err_body)
                    err_data = err_json.get("error", {})
                    notes = f"Cloud API HTTP {he.code}: {err_data.get('message', he.reason)} (Code: {err_data.get('code', 'N/A')})"
                except Exception:
                    notes = f"Cloud API HTTP {he.code}: {he.reason}"
                _logger.error("Cloud API HTTP Error: %s", notes)
                return ProviderResult(success=False, status=SendStatus.FAILED, notes=notes)
            except Exception as ex:
                notes = f"Transport Error: {ex}"
                _logger.error(notes)
                return ProviderResult(success=False, status=SendStatus.FAILED, notes=notes)

        # 2. Modern requests.Session implementation with connection pooling & retries
        try:
            resp = self._session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=(5.0, 15.0),
            )
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}

            return self._parse_api_response(resp.status_code, data, contact)

        except requests.exceptions.Timeout:
            notes = "Network timeout: Meta Graph API did not respond within 15 seconds."
            _logger.error(notes)
            return ProviderResult(success=False, status=SendStatus.FAILED, notes=notes)
        except requests.exceptions.RequestException as re:
            notes = f"Network Connection Error: {re}"
            _logger.error(notes)
            return ProviderResult(success=False, status=SendStatus.FAILED, notes=notes)
        except Exception as ex:
            notes = f"Unexpected Dispatch Error: {ex}"
            _logger.error(notes)
            return ProviderResult(success=False, status=SendStatus.FAILED, notes=notes)

    def _parse_api_response(
        self, status_code: int, data: Dict[str, Any], contact: Contact
    ) -> ProviderResult:
        """Process API response dictionary and return appropriate ProviderResult."""
        if 200 <= status_code < 300:
            messages = data.get("messages", [])
            message_id = messages[0].get("id", "") if messages else ""
            contact.message_id = message_id
            _logger.info("Message sent successfully. wamid=%s", message_id)

            return ProviderResult(
                success=True,
                status=SendStatus.API_SENT,
                message_id=message_id,
                notes=f"Dispatched via Cloud API (ID: {message_id})",
                requires_manual_confirmation=False,
            )

        error_info = data.get("error", {})
        error_msg = error_info.get("message", "Unknown API error")
        error_code = error_info.get("code", status_code)
        notes = f"Cloud API Error {error_code}: {error_msg}"
        _logger.error(notes)
        return ProviderResult(
            success=False,
            status=SendStatus.FAILED,
            notes=notes,
        )
