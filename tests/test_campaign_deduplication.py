"""Regression tests for provider selection, campaign identity, deduplication, and resume behavior."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from src.database import DatabaseManager
from src.logger_service import LoggerService
from src.message_engine import MessageEngine
from src.models import Contact, SendStatus
from src.providers.base import BaseMessageProvider, ProviderResult
from src.providers.piwapp_provider import PiwappProvider
from src.providers.web_provider import WhatsAppWebManualProvider
from src.sender_controller import ControllerState, DispatchMode, SenderController
from src.ui.components.control_panel import ControlPanel


class MockTestProvider(BaseMessageProvider):
    """Mock provider recording dispatch calls for testing."""

    def __init__(self, name: str = "Mock Provider", automated: bool = True):
        self._name = name
        self._automated = automated
        self.sent_phones = []
        self.return_msg_id = "mock_msg_999"
        self.should_succeed = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_automated(self) -> bool:
        return self._automated

    def validate_configuration(self):
        return True, "Mock valid"

    def send(self, contact: Contact, message: str, **kwargs) -> ProviderResult:
        self.sent_phones.append(contact.clean_phone)
        if self.should_succeed:
            return ProviderResult(
                success=True,
                status=SendStatus.API_SENT if self._automated else SendStatus.OPENED,
                message_id=self.return_msg_id,
                notes=f"Server-acknowledged via {self._name} (ID: {self.return_msg_id})",
            )
        return ProviderResult(
            success=False,
            status=SendStatus.FAILED,
            notes=f"Transmission attempt failed via {self._name}",
        )


class TestCampaignDeduplicationAndSelection(unittest.TestCase):
    """Test suite ensuring reliable provider selection, campaign scoping, and deduplication."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_campaigns.db")
        self.log_path = os.path.join(self.temp_dir.name, "test_sent_log.csv")
        self.db_manager = DatabaseManager(self.db_path)
        self.logger_service = LoggerService(self.log_path)
        self.message_engine = MessageEngine()

    def tearDown(self):
        self.db_manager.close()
        self.temp_dir.cleanup()

    def _wait_for_controller(self, controller: SenderController, timeout_sec: float = 3.0) -> bool:
        import time
        start = time.time()
        while time.time() - start < timeout_sec:
            if controller.state in (ControllerState.FINISHED, ControllerState.STOPPED, ControllerState.AWAITING_CONFIRMATION):
                return True
            time.sleep(0.05)
        return False

    def test_provider_selection_resolves_correct_mode_and_provider(self):
        """Verify that provider selector resolves piwapp vs web manual accurately."""
        # 1. Controller resolves provider matching mode
        web_provider = WhatsAppWebManualProvider(self.message_engine)
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=web_provider,
            db_manager=self.db_manager,
        )

        # Even if controller.provider was set to web_provider, requesting PIWAPP_AUTOMATED must resolve PiwappProvider
        resolved = controller.get_or_create_provider(DispatchMode.PIWAPP_AUTOMATED)
        self.assertIsInstance(resolved, PiwappProvider)

        # Requesting WEB_MANUAL_REVIEW resolves WhatsAppWebManualProvider
        resolved_web = controller.get_or_create_provider(DispatchMode.WEB_MANUAL_REVIEW)
        self.assertIsInstance(resolved_web, WhatsAppWebManualProvider)

    def test_campaign_scoping_does_not_skip_contacts_in_new_campaign(self):
        """Starting a genuinely new campaign must NOT skip contacts sent in prior campaigns."""
        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "User One", is_valid=True),
            Contact(2, "0698765432", "212698765432", "+212 698-765432", "User Two", is_valid=True),
        ]

        provider_a = MockTestProvider("Provider A", automated=True)
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=provider_a,
            db_manager=self.db_manager,
        )

        # --- RUN 1: Campaign A ---
        camp_a_id = "camp_alpha_001"
        started = controller.start_batch(
            contacts=contacts,
            template="Hello {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=provider_a,
            skip_already_sent=True,
            campaign_id=camp_a_id,
            campaign_name="Campaign Alpha",
            is_new_campaign=True,
            global_deduplication=False,
        )
        self.assertTrue(started)
        self.assertTrue(self._wait_for_controller(controller))
        self.assertEqual(len(provider_a.sent_phones), 2)
        self.assertEqual(contacts[0].status, SendStatus.API_SENT)
        self.assertEqual(contacts[1].status, SendStatus.API_SENT)

        # In SQLite, both contacts are recorded as completed for Campaign Alpha
        completed_a = self.db_manager.get_completed_phones_for_campaign(camp_a_id)
        self.assertEqual(completed_a, {"212612345678", "212698765432"})

        # --- RUN 2: Resume Campaign A ---
        # Resuming Campaign A must skip both already-completed contacts
        provider_resume = MockTestProvider("Provider Resume", automated=True)
        started_resume = controller.start_batch(
            contacts=contacts,
            template="Hello {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=provider_resume,
            skip_already_sent=True,
            campaign_id=camp_a_id,
            campaign_name="Campaign Alpha Resume",
            is_new_campaign=False,  # Resuming existing campaign
            global_deduplication=False,
        )
        self.assertTrue(started_resume)
        self.assertTrue(self._wait_for_controller(controller))
        self.assertEqual(len(provider_resume.sent_phones), 0)  # Both skipped!
        self.assertEqual(contacts[0].status, SendStatus.ALREADY_PROCESSED)
        self.assertEqual(contacts[1].status, SendStatus.ALREADY_PROCESSED)

        # --- RUN 3: Genuinely New Campaign B ---
        # When user starts a NEW campaign with the same contacts:
        # Contacts must NOT be skipped, and should dispatch fresh!
        provider_b = MockTestProvider("Provider B", automated=True)
        camp_b_id = "camp_beta_002"
        started_b = controller.start_batch(
            contacts=contacts,
            template="Special Promo for {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=provider_b,
            skip_already_sent=True,
            campaign_id=camp_b_id,
            campaign_name="Campaign Beta",
            is_new_campaign=True,  # Genuinely new campaign
            global_deduplication=False,
        )
        self.assertTrue(started_b)
        self.assertTrue(self._wait_for_controller(controller))
        self.assertEqual(len(provider_b.sent_phones), 2)
        self.assertEqual(contacts[0].status, SendStatus.API_SENT)
        self.assertEqual(contacts[1].status, SendStatus.API_SENT)

    def test_global_deduplication_suppresses_historical_logs(self):
        """When global_deduplication is True, contacts in sent_log.csv are suppressed."""
        # Pre-seed sent_log.csv with phone 212612345678
        self.logger_service.log_attempt(
            phone="212612345678",
            name="Historic Client",
            status=SendStatus.MANUALLY_CONFIRMED,
            notes="Sent in past year",
        )

        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "Historic Client", is_valid=True),
            Contact(2, "0698765432", "212698765432", "+212 698-765432", "Fresh Client", is_valid=True),
        ]

        provider = MockTestProvider("Provider Test", automated=True)
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=provider,
            db_manager=self.db_manager,
        )

        # Case 1: Global deduplication ON -> Historic client is skipped
        camp_id = "camp_global_check"
        started = controller.start_batch(
            contacts=contacts,
            template="Test message {name}",
            mode=DispatchMode.CLOUD_API_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=provider,
            skip_already_sent=True,
            campaign_id=camp_id,
            is_new_campaign=True,
            global_deduplication=True,  # Explicitly suppress historical contacts
        )
        self.assertTrue(started)
        self.assertTrue(self._wait_for_controller(controller))

        # Only the Fresh Client was dispatched
        self.assertEqual(provider.sent_phones, ["212698765432"])
        self.assertEqual(contacts[0].status, SendStatus.ALREADY_PROCESSED)
        self.assertIn("global history", contacts[0].notes.lower())
        self.assertEqual(contacts[1].status, SendStatus.API_SENT)

    def test_manual_mode_opened_status_does_not_count_as_sent(self):
        """In manual mode, opening a chat in browser (OPENED) must not count as sent or prevent sending."""
        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "Manual Client", is_valid=True),
        ]

        mock_web = MockTestProvider("WhatsApp Web Manual", automated=False)
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=mock_web,
            db_manager=self.db_manager,
        )

        camp_id = "camp_manual_test"
        started = controller.start_batch(
            contacts=contacts,
            template="Review {name}",
            mode=DispatchMode.WEB_MANUAL_REVIEW,
            delay_seconds=0,
            has_consent=True,
            provider=mock_web,
            skip_already_sent=True,
            campaign_id=camp_id,
            is_new_campaign=True,
        )
        self.assertTrue(started)
        self.assertTrue(self._wait_for_controller(controller))

        # Controller enters AWAITING_CONFIRMATION, contact status is OPENED
        self.assertEqual(controller.state, ControllerState.AWAITING_CONFIRMATION)
        self.assertEqual(contacts[0].status, SendStatus.OPENED)

        # OPENED is NOT considered completed in database
        completed = self.db_manager.get_completed_phones_for_campaign(camp_id)
        self.assertNotIn("212612345678", completed)

        # If user stops while awaiting confirmation
        controller.stop()
        self.assertEqual(controller.state, ControllerState.STOPPED)

        # Now resume the session: contact 1 should NOT be skipped as ALREADY_PROCESSED!
        mock_web_resume = MockTestProvider("WhatsApp Web Manual Resume", automated=False)
        started_resume = controller.start_batch(
            contacts=contacts,
            template="Review {name}",
            mode=DispatchMode.WEB_MANUAL_REVIEW,
            delay_seconds=0,
            has_consent=True,
            provider=mock_web_resume,
            skip_already_sent=True,
            campaign_id=camp_id,
            is_new_campaign=False,
        )
        self.assertTrue(started_resume)
        self.assertTrue(self._wait_for_controller(controller))

        # The contact opened again for review
        self.assertEqual(controller.state, ControllerState.AWAITING_CONFIRMATION)
        self.assertEqual(contacts[0].status, SendStatus.OPENED)

        # Now operator explicitly confirms sent!
        controller.confirm_current_sent()
        import time
        time.sleep(0.1)

        # NOW contact is MANUALLY_CONFIRMED and recorded in DB
        self.assertEqual(contacts[0].status, SendStatus.MANUALLY_CONFIRMED)
        completed_after = self.db_manager.get_completed_phones_for_campaign(camp_id)
        self.assertIn("212612345678", completed_after)

    def test_piwapp_automated_dispatch_and_no_silent_fallback(self):
        """Verify Piwapp dispatches unattended without manual review and never silently falls back to web."""
        contacts = [
            Contact(1, "0612345678", "212612345678", "+212 612-345678", "Auto Client", is_valid=True),
        ]

        # Case 1: Unauthenticated Piwapp -> start_batch fails validation and returns False
        unauthenticated_piwapp = PiwappProvider(session_path="nonexistent_piwapp.json")
        controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=unauthenticated_piwapp,
            db_manager=self.db_manager,
        )

        started = controller.start_batch(
            contacts=contacts,
            template="Hello {name}",
            mode=DispatchMode.PIWAPP_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=unauthenticated_piwapp,
        )
        # MUST return False and NOT silently switch to web provider!
        self.assertFalse(started)
        self.assertEqual(controller.state, ControllerState.IDLE)

        # Case 2: Authenticated Piwapp -> dispatches fully automated without awaiting confirmation
        mock_piwapp = MockTestProvider("piwapp (Experimental Pure-Python Automation)", automated=True)
        controller_auth = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=mock_piwapp,
            db_manager=self.db_manager,
        )

        started_auth = controller_auth.start_batch(
            contacts=contacts,
            template="Hello {name}",
            mode=DispatchMode.PIWAPP_AUTOMATED,
            delay_seconds=0,
            has_consent=True,
            provider=mock_piwapp,
            campaign_id="camp_piwapp_test",
        )
        self.assertTrue(started_auth)
        self.assertTrue(self._wait_for_controller(controller_auth))

        # Verified: State reaches FINISHED automatically without manual confirmation
        self.assertEqual(controller_auth.state, ControllerState.FINISHED)
        self.assertEqual(contacts[0].status, SendStatus.API_SENT)
        self.assertEqual(mock_piwapp.sent_phones, ["212612345678"])

    def test_confirmation_dialog_text_and_piwapp_invocation(self):
        """Verify confirmation dialog displays actual selected provider name and invokes Piwapp."""
        from unittest.mock import patch
        from src.ui.app import WhatsAppBulkMessengerApp

        root = WhatsAppBulkMessengerApp()
        root.withdraw()
        try:
            # Add sample contact and template
            sample_contact = Contact(1, "0612345678", "212612345678", "+212 612-345678", "Test Client", is_valid=True)
            root.contact_manager.valid_contacts = [sample_contact]
            root.contact_manager.contacts = [sample_contact]
            root.message_editor.set_template_text("Hello {name}")
            root.control_panel.consent_var.set(True)

            # Ensure Piwapp is selected
            root.control_panel.set_selected_mode(DispatchMode.PIWAPP_AUTOMATED)
            self.assertEqual(root.control_panel.get_selected_mode(), DispatchMode.PIWAPP_AUTOMATED)

            # Mock piwapp validation so it is considered ready and connected
            root.piwapp_provider._is_connected = True
            root.piwapp_provider._paired_id = "212612345678:0@s.whatsapp.net"

            # Capture confirmation text shown to user
            captured_dialogs = []
            with patch("tkinter.messagebox.askyesno") as mock_ask:
                mock_ask.side_effect = lambda title, message: captured_dialogs.append((title, message)) or True
                with patch.object(root.controller, "start_batch", return_value=True) as mock_start:
                    root._handle_start()

                    self.assertTrue(len(captured_dialogs) > 0)
                    title, msg = captured_dialogs[0]
                    # Verify dynamic text contains Piwapp provider name and automated workflow
                    self.assertIn("piwapp (Experimental Pure-Python Automation)", msg)
                    self.assertIn("Automated Dispatch", msg)
                    self.assertNotIn("WhatsApp Web Click-to-Chat (Manual Review)", msg)

                    # Verify Piwapp provider was passed to controller
                    mock_start.assert_called_once()
                    _, kwargs = mock_start.call_args
                    self.assertEqual(kwargs.get("mode"), DispatchMode.PIWAPP_AUTOMATED)
                    self.assertEqual(kwargs.get("provider"), root.piwapp_provider)

            # Now switch to WhatsApp Web manual mode and verify confirmation dialog changes dynamically
            root.control_panel.set_selected_mode(DispatchMode.WEB_MANUAL_REVIEW)
            captured_dialogs.clear()
            with patch("tkinter.messagebox.askyesno") as mock_ask:
                mock_ask.side_effect = lambda title, message: captured_dialogs.append((title, message)) or True
                with patch.object(root.controller, "start_batch", return_value=True) as mock_start:
                    root._handle_start()

                    self.assertTrue(len(captured_dialogs) > 0)
                    title, msg = captured_dialogs[0]
                    self.assertIn("WhatsApp Web Click-to-Chat (Manual Review)", msg)
                    self.assertIn("Manual Review", msg)
                    self.assertEqual(mock_start.call_args.kwargs.get("mode"), DispatchMode.WEB_MANUAL_REVIEW)
                    self.assertEqual(mock_start.call_args.kwargs.get("provider"), root.web_provider)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()

