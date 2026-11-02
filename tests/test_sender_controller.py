"""Unit tests for SenderController state machine."""

import time
import unittest
from unittest.mock import MagicMock, patch
from src.logger_service import LoggerService
from src.message_engine import MessageEngine
from src.models import Contact, SendStatus
from src.sender_controller import ControllerState, DispatchMode, SenderController


class TestSenderController(unittest.TestCase):
    """Test suite for sender controller workflow."""

    def setUp(self):
        self.message_engine = MessageEngine()
        self.logger_service = MagicMock(spec=LoggerService)
        self.controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
        )
        self.sample_contacts = [
            Contact(
                index=1,
                raw_phone="0612345678",
                clean_phone="212612345678",
                formatted_phone="+212 612-345678",
                name="Contact 1",
                is_valid=True,
            ),
            Contact(
                index=2,
                raw_phone="0712345678",
                clean_phone="212712345678",
                formatted_phone="+212 712-345678",
                name="Contact 2",
                is_valid=True,
            ),
        ]

    def _wait_for_contact(self, contact_name: str, timeout: float = 2.0) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            if (
                self.controller.state == ControllerState.AWAITING_CONFIRMATION
                and self.controller.current_contact
                and self.controller.current_contact.name == contact_name
            ):
                return True
            time.sleep(0.02)
        return False

    def test_refuse_start_without_consent(self):
        started = self.controller.start_batch(
            contacts=self.sample_contacts,
            template="Hello {name}",
            has_consent=False,
        )
        self.assertFalse(started)
        self.assertEqual(self.controller.state, ControllerState.IDLE)

    def test_refuse_empty_contacts_or_template(self):
        started = self.controller.start_batch(
            contacts=[],
            template="Hello",
            has_consent=True,
        )
        self.assertFalse(started)

        started2 = self.controller.start_batch(
            contacts=self.sample_contacts,
            template="   ",
            has_consent=True,
        )
        self.assertFalse(started2)

    @patch("webbrowser.open")
    def test_step_by_step_workflow(self, mock_browser):
        mock_browser.return_value = True

        started = self.controller.start_batch(
            contacts=self.sample_contacts,
            template="Salam {name}",
            mode=DispatchMode.STEP_BY_STEP,
            delay_seconds=0,
            has_consent=True,
        )
        self.assertTrue(started)

        # Allow background thread to reach first contact and pause for confirmation
        self.assertTrue(self._wait_for_contact("Contact 1"))
        self.assertEqual(self.controller.current_contact.name, "Contact 1")

        # Confirm first contact
        self.controller.confirm_current_sent()

        # Should now reach second contact awaiting confirmation
        self.assertTrue(self._wait_for_contact("Contact 2"))
        self.assertEqual(self.controller.current_contact.name, "Contact 2")

        # Skip second contact
        self.controller.skip_current_contact()

        # Finished
        start_time = time.time()
        while time.time() - start_time < 2.0:
            if self.controller.state == ControllerState.FINISHED:
                break
            time.sleep(0.02)
        self.assertEqual(self.controller.state, ControllerState.FINISHED)
        self.assertTrue(mock_browser.called)


if __name__ == "__main__":
    unittest.main()
