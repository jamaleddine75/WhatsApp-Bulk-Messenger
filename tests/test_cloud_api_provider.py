"""Unit tests for WhatsAppCloudApiProvider."""

import json
import urllib.error
import urllib.request
from typing import Tuple
import unittest
from unittest.mock import MagicMock

from src.models import Contact, SendStatus
from src.providers.cloud_api_provider import WhatsAppCloudApiProvider


class TestWhatsAppCloudApiProvider(unittest.TestCase):
    """Test suite for WhatsApp Business Cloud API provider."""

    def setUp(self):
        self.sample_contact = Contact(
            index=1,
            raw_phone="0612345678",
            clean_phone="212612345678",
            formatted_phone="+212 612-345678",
            name="Yassine",
            is_valid=True,
        )

    def test_configuration_validation_missing_credentials(self):
        provider = WhatsAppCloudApiProvider(access_token="", phone_number_id="")
        valid, msg = provider.validate_configuration()
        self.assertFalse(valid)
        self.assertIn("Missing WhatsApp Cloud API access token", msg)

        provider_with_token = WhatsAppCloudApiProvider(access_token="VALID_TOKEN_1234567890", phone_number_id="")
        valid2, msg2 = provider_with_token.validate_configuration()
        self.assertFalse(valid2)
        self.assertIn("Missing WhatsApp Phone Number ID", msg2)

    def test_configuration_validation_valid(self):
        provider = WhatsAppCloudApiProvider(
            access_token="EAA1234567890abcdefghijklmnopqrstuvwxyz",
            phone_number_id="109876543210987",
        )
        valid, msg = provider.validate_configuration()
        self.assertTrue(valid)
        self.assertIn("ready", msg.lower())

    def test_build_payload_text(self):
        provider = WhatsAppCloudApiProvider()
        payload = provider.build_payload("212612345678", "Bonjour Yassine")
        self.assertEqual(payload["messaging_product"], "whatsapp")
        self.assertEqual(payload["to"], "212612345678")
        self.assertEqual(payload["type"], "text")
        self.assertEqual(payload["text"]["body"], "Bonjour Yassine")

    def test_build_payload_template(self):
        provider = WhatsAppCloudApiProvider()
        payload = provider.build_payload(
            "212612345678",
            "Order #1234",
            template_name="order_confirmation",
            language_code="ar",
        )
        self.assertEqual(payload["type"], "template")
        self.assertEqual(payload["template"]["name"], "order_confirmation")
        self.assertEqual(payload["template"]["language"]["code"], "ar")

    def test_send_success_automated(self):
        """Verify successful response sets status to API_SENT with message_id."""
        def mock_transport(req: urllib.request.Request) -> Tuple[int, bytes]:
            self.assertEqual(req.get_method(), "POST")
            self.assertTrue(req.full_url.endswith("/messages"))
            self.assertIn("Bearer valid_token", req.headers.get("Authorization"))

            resp_data = {
                "messaging_product": "whatsapp",
                "contacts": [{"input": "212612345678", "wa_id": "212612345678"}],
                "messages": [{"id": "wamid.HBgLMjEyNjEyMzQ1Njc4FQIAERgSRjQ2OTc2Q..."}],
            }
            return 200, json.dumps(resp_data).encode("utf-8")

        provider = WhatsAppCloudApiProvider(
            access_token="valid_token_1234567890",
            phone_number_id="1029384756",
            transport_fn=mock_transport,
        )

        result = provider.send(self.sample_contact, "Test message")
        self.assertTrue(result.success)
        self.assertEqual(result.status, SendStatus.API_SENT)
        self.assertTrue(result.message_id.startswith("wamid."))
        self.assertFalse(result.requires_manual_confirmation)
        self.assertEqual(self.sample_contact.message_id, result.message_id)

    def test_send_api_failure_handled_correctly(self):
        """Verify API errors return FAILED status and do not claim success."""
        def mock_error_transport(req: urllib.request.Request):
            err_body = json.dumps({
                "error": {
                    "message": "(#131030) Recipient phone number not in allowed list.",
                    "type": "OAuthException",
                    "code": 131030,
                    "error_subcode": 2655007,
                }
            }).encode("utf-8")
            fp = MagicMock()
            fp.read.return_value = err_body
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, fp)

        provider = WhatsAppCloudApiProvider(
            access_token="valid_token_1234567890",
            phone_number_id="1029384756",
            transport_fn=mock_error_transport,
        )

        result = provider.send(self.sample_contact, "Test message")
        self.assertFalse(result.success)
        self.assertEqual(result.status, SendStatus.FAILED)
        self.assertIn("131030", result.notes)
        self.assertIn("not in allowed list", result.notes)

    def test_requests_session_send_success(self):
        """Test sending via requests.Session with mock response."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.REQTEST123456"}],
        }
        mock_session.post.return_value = mock_response

        provider = WhatsAppCloudApiProvider(
            access_token="valid_token_1234567890",
            phone_number_id="1029384756",
            session=mock_session,
        )

        result = provider.send(self.sample_contact, "Bonjour requests!")
        self.assertTrue(result.success)
        self.assertEqual(result.status, SendStatus.API_SENT)
        self.assertEqual(result.message_id, "wamid.REQTEST123456")
        mock_session.post.assert_called_once()

    def test_test_connection_success(self):
        """Test test_connection returns True with verified business info."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "1029384756",
            "display_phone_number": "+212 612-345678",
            "verified_name": "Acme Corp Morocco",
            "quality_rating": "GREEN",
        }
        mock_session.get.return_value = mock_response

        provider = WhatsAppCloudApiProvider(
            access_token="valid_token_1234567890",
            phone_number_id="1029384756",
            session=mock_session,
        )

        ok, msg = provider.test_connection()
        self.assertTrue(ok)
        self.assertIn("Acme Corp Morocco", msg)
        self.assertIn("GREEN", msg)

    def test_test_connection_invalid_token(self):
        """Test test_connection returns False with Graph API error description."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": {
                "message": "Invalid OAuth access token.",
                "type": "OAuthException",
                "code": 190,
            }
        }
        mock_session.get.return_value = mock_response

        provider = WhatsAppCloudApiProvider(
            access_token="invalid_token_1234567890",
            phone_number_id="1029384756",
            session=mock_session,
        )

        ok, msg = provider.test_connection()
        self.assertFalse(ok)
        self.assertIn("190", msg)
        self.assertIn("Invalid OAuth", msg)


if __name__ == "__main__":
    unittest.main()

