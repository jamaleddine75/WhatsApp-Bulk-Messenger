"""Unit tests for unattended automated dispatch, pause/resume, and failure recovery."""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from src.logger_service import LoggerService
from src.message_engine import MessageEngine
from src.models import Contact, SendStatus
from src.providers.base import BaseMessageProvider, ProviderResult
from src.providers.cloud_api_provider import WhatsAppCloudApiProvider
from src.sender_controller import ControllerState, DispatchMode, SenderController


class MockCloudApiProvider(BaseMessageProvider):
    """Mock automated provider for controller testing."""

    def __init__(self, failure_on_phones=None):
        self.failure_on_phones = failure_on_phones or set()
        self.sent_calls = []

    @property
    def name(self) -> str:
        return "Mock Automated Provider"

    @property
    def is_automated(self) -> bool:
        return True

    def validate_configuration(self):
        return True, "Mock ready"

    def send(self, contact: Contact, message: str, **kwargs) -> ProviderResult:
        self.sent_calls.append(contact.clean_phone)
        if contact.clean_phone in self.failure_on_phones:
            return ProviderResult(
                success=False,
                status=SendStatus.FAILED,
                notes=f"Simulated API rejection for {contact.clean_phone}",
            )

        wamid = f"wamid.{contact.clean_phone}"
        return ProviderResult(
            success=True,
            status=SendStatus.API_SENT,
            message_id=wamid,
            notes=f"Dispatched via Mock API (ID: {wamid})",
        )


class TestAutomatedDispatch(unittest.TestCase):
    """Test suite for automated unattended sending workflow."""

    def setUp(self):
        self.temp_log = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        self.temp_log.close()
        os.remove(self.temp_log.name)
        self.logger_service = LoggerService(self.temp_log.name)
        self.message_engine = MessageEngine()

    def tearDown(self):
        if os.path.exists(self.temp_log.name):
            os.remove(self.temp_log.name)

    def _wait_for_state(self, controller: SenderController, target_state: ControllerState, timeout: float = 2.0) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if controller.state == target_state:
                return True
            time.sleep(0.02)
        return False

    def test_unattended_automated_batch(self):
        """Verify automated mode dispatches all contacts without manual confirmations."""
        mock_provider = MockCloudApiProvider()
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=mock_provider,
        )

        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "Contact 1", is_valid=True),
            Contact(2, "0712345678", "212712345678", "+212 712-345678", "Contact 2", is_valid=True),
            Contact(3, "0522123456", "212522123456", "+212 522-123456", "Contact 3", is_valid=True),
        ]

        started = controller.start_batch(
            contacts=contacts,
            template="Bonjour {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=mock_provider,
        )
        self.assertTrue(started)

        # Wait for completion
        self.assertTrue(self._wait_for_state(controller, ControllerState.FINISHED))
        self.assertEqual(len(mock_provider.sent_calls), 3)

        # Verify all contacts were marked API_SENT with message_id
        for c in contacts:
            self.assertEqual(c.status, SendStatus.API_SENT)
            self.assertTrue(c.message_id.startswith("wamid."))

    def test_failure_recovery_does_not_mark_as_sent(self):
        """Verify failed messages are tracked as FAILED and do not claim delivery."""
        mock_provider = MockCloudApiProvider(failure_on_phones={"212712345678"})
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=mock_provider,
        )

        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "Good Contact 1", is_valid=True),
            Contact(2, "0712345678", "212712345678", "+212 712-345678", "Failing Contact 2", is_valid=True),
            Contact(3, "0522123456", "212522123456", "+212 522-123456", "Good Contact 3", is_valid=True),
        ]

        controller.start_batch(
            contacts=contacts,
            template="Hello {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=mock_provider,
        )

        self.assertTrue(self._wait_for_state(controller, ControllerState.FINISHED))

        self.assertEqual(contacts[0].status, SendStatus.API_SENT)
        self.assertEqual(contacts[1].status, SendStatus.FAILED)
        self.assertIn("Simulated API rejection", contacts[1].notes)
        self.assertEqual(contacts[2].status, SendStatus.API_SENT)

    def test_deduplication_on_resume_skips_already_sent(self):
        """Verify resume/re-run skips contacts already successfully dispatched."""
        # Pre-populate log with contact 1 as API_SENT
        self.logger_service.log_attempt(
            phone="212612345678",
            name="Contact 1",
            status=SendStatus.API_SENT,
            notes="Prior dispatch",
            message_id="wamid.prior123",
        )

        mock_provider = MockCloudApiProvider()
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=mock_provider,
        )

        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "Contact 1", is_valid=True),
            Contact(2, "0712345678", "212712345678", "+212 712-345678", "Contact 2", is_valid=True),
        ]

        controller.start_batch(
            contacts=contacts,
            template="Hello {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=mock_provider,
            skip_already_sent=True,
        )

        self.assertTrue(self._wait_for_state(controller, ControllerState.FINISHED))

        # Contact 1 was skipped as ALREADY_PROCESSED
        self.assertEqual(contacts[0].status, SendStatus.ALREADY_PROCESSED)
        self.assertIn("already sent", contacts[0].notes.lower())

        # Contact 2 was processed
        self.assertEqual(contacts[1].status, SendStatus.API_SENT)
        self.assertEqual(mock_provider.sent_calls, ["212712345678"])

    def test_pause_and_resume_automated(self):
        """Verify pause/resume works cleanly during automated sending."""
        mock_provider = MockCloudApiProvider()
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=mock_provider,
        )

        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "Contact 1", is_valid=True),
            Contact(2, "0712345678", "212712345678", "+212 712-345678", "Contact 2", is_valid=True),
        ]

        controller.start_batch(
            contacts=contacts,
            template="Hello {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=1,
            has_consent=True,
            provider=mock_provider,
        )

        # Pause immediately
        controller.pause()
        self.assertEqual(controller.state, ControllerState.PAUSED)

        # Resume
        controller.resume()
        self.assertEqual(controller.state, ControllerState.RUNNING)

        # Wait for completion
        self.assertTrue(self._wait_for_state(controller, ControllerState.FINISHED, timeout=3.0))
        self.assertEqual(len(mock_provider.sent_calls), 2)

    def test_consent_enforcement_skips_unconsented_and_suppressed(self):
        """Verify automated dispatch strictly skips contacts without opt-in or on suppression list."""
        mock_provider = MockCloudApiProvider()
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=mock_provider,
        )

        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "Consented", is_valid=True, opted_in=True),
            Contact(2, "0712345678", "212712345678", "+212 712-345678", "No Consent", is_valid=True, opted_in=False),
            Contact(3, "0522123456", "212522123456", "+212 522-123456", "Opted Out", is_valid=True, opted_in=True, is_suppressed=True),
        ]

        controller.start_batch(
            contacts=contacts,
            template="Hello {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=mock_provider,
        )

        self.assertTrue(self._wait_for_state(controller, ControllerState.FINISHED))

        # Only contact 1 should be sent
        self.assertEqual(contacts[0].status, SendStatus.API_SENT)
        self.assertEqual(contacts[1].status, SendStatus.SKIPPED_NO_CONSENT)
        self.assertEqual(contacts[2].status, SendStatus.SKIPPED_OPT_OUT)
        self.assertEqual(mock_provider.sent_calls, ["212612345678"])

    def test_database_campaign_persistence(self):
        """Verify SenderController records campaign, messages, and counts into SQLite DatabaseManager."""
        from src.database import DatabaseManager
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        db_file.close()

        try:
            db = DatabaseManager(db_file.name)
            mock_provider = MockCloudApiProvider()
            controller = SenderController(
                message_engine=self.message_engine,
                logger_service=self.logger_service,
                provider=mock_provider,
                db_manager=db,
            )

            contacts = [
                Contact(1, "0612345678", "212612345678", "+212 612-345678", "Contact 1", is_valid=True),
            ]

            camp_id = "test_camp_999"
            controller.start_batch(
                contacts=contacts,
                template="Hello {name}",
                mode=DispatchMode.CLOUD_API_AUTOMATED,
                delay_seconds=0,
                has_consent=True,
                provider=mock_provider,
                campaign_id=camp_id,
                campaign_name="Test SQLite Campaign",
            )

            self.assertTrue(self._wait_for_state(controller, ControllerState.FINISHED))

            # Query DB
            camp = db.get_campaign(camp_id)
            self.assertIsNotNone(camp)
            self.assertEqual(camp["name"], "Test SQLite Campaign")
            self.assertEqual(camp["sent_count"], 1)
            self.assertEqual(camp["status"], "COMPLETED")

            messages = db.get_campaign_messages(camp_id)
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["phone"], "212612345678")
            self.assertEqual(messages[0]["status"], SendStatus.API_SENT.value)
        finally:
            if os.path.exists(db_file.name):
                os.remove(db_file.name)


if __name__ == "__main__":
    unittest.main()

