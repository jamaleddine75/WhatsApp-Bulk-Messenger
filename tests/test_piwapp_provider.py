"""Unit tests for the experimental PiwappProvider."""

import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from src.models import Contact, SendStatus
from src.providers.piwapp_provider import PiwappProvider


class TestPiwappProvider(unittest.TestCase):
    """Test suite for PiwappProvider connection management and message dispatch."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.session_path = os.path.join(self.temp_dir.name, "test_session.json")
        self.keys_path = os.path.join(self.temp_dir.name, "test_session.keys")

        self.contact = Contact(
            index=1,
            raw_phone="0612345678",
            clean_phone="212612345678",
            formatted_phone="+212 612-345678",
            name="Yassine",
            is_valid=True,
            opted_in=True,
        )

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_provider_metadata(self):
        provider = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)
        self.assertIn("piwapp", provider.name.lower())
        self.assertTrue(provider.is_automated)
        self.assertFalse(provider.is_connected)

    def test_validate_configuration_disconnected(self):
        provider = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)
        ok, msg = provider.validate_configuration()
        self.assertFalse(ok)
        self.assertIn("not currently connected", msg.lower())

    def test_send_fails_when_disconnected(self):
        provider = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)
        result = provider.send(self.contact, "Bonjour Yassine")
        self.assertFalse(result.success)
        self.assertEqual(result.status, SendStatus.FAILED)
        self.assertIn("not ready", result.notes.lower())

    def test_send_success_with_mock_client(self):
        """Verify successful socket message dispatch returns API_SENT with message_id."""
        provider = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)

        # Mock an active event loop and client
        loop = asyncio.new_event_loop()
        provider._loop = loop
        mock_client = MagicMock()
        mock_client.is_open = True
        mock_client.send_text = AsyncMock(return_value="3EB0TEST987654321")

        provider._client = mock_client
        provider._is_connected = True
        provider._paired_id = "212612345678@s.whatsapp.net"

        # Run loop in background thread for the duration of the test
        import threading
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()

        try:
            result = provider.send(self.contact, "Bonjour Yassine via piwapp!")
            self.assertTrue(result.success)
            self.assertEqual(result.status, SendStatus.API_SENT)
            self.assertEqual(result.message_id, "3EB0TEST987654321")
            self.assertEqual(self.contact.message_id, "3EB0TEST987654321")
            self.assertIn("piwapp socket", result.notes)
            mock_client.send_text.assert_called_once_with("212612345678@s.whatsapp.net", "Bonjour Yassine via piwapp!")
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=2.0)
            loop.close()

    def test_send_failure_on_exception(self):
        """Verify errors during socket transmission return FAILED status."""
        provider = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)

        loop = asyncio.new_event_loop()
        provider._loop = loop
        mock_client = MagicMock()
        mock_client.is_open = True
        mock_client.send_text = AsyncMock(side_effect=RuntimeError("Connection reset by peer"))

        provider._client = mock_client
        provider._is_connected = True

        import threading
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()

        try:
            result = provider.send(self.contact, "Test message")
            self.assertFalse(result.success)
            self.assertEqual(result.status, SendStatus.FAILED)
            self.assertIn("Connection reset by peer", result.notes)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=2.0)
            loop.close()

    def test_logout_removes_session_files(self):
        with open(self.session_path, "w") as f:
            f.write("{}")
        with open(self.keys_path, "w") as f:
            f.write("{}")

        provider = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)
        self.assertTrue(os.path.exists(self.session_path))
        self.assertTrue(os.path.exists(self.keys_path))

        provider.logout()
        self.assertFalse(os.path.exists(self.session_path))
        self.assertFalse(os.path.exists(self.keys_path))

    def test_has_saved_session_and_account_id(self):
        """Verify session authentication detection distinguishes paired vs unpaired sessions."""
        provider = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)
        self.assertFalse(provider.has_saved_session())
        self.assertIsNone(provider.get_saved_account_id())

        # Save an initial (unpaired) creds json
        from piwapp import AuthenticationCreds
        creds = AuthenticationCreds.initial()
        with open(self.session_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        self.assertFalse(provider.has_saved_session())
        self.assertIsNone(provider.get_saved_account_id())

        # Update creds with me (paired account)
        from piwapp.auth.creds import Me
        creds.me = Me(id="212612345678:1@s.whatsapp.net", name="Test Operator")
        with open(self.session_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        provider_with_auth = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)
        self.assertTrue(provider_with_auth.has_saved_session())
        self.assertEqual(provider_with_auth.get_saved_account_id(), "212612345678:1@s.whatsapp.net")
        self.assertEqual(provider_with_auth.paired_id, "212612345678:1@s.whatsapp.net")

    def test_send_timeout_marks_failed_with_unconfirmed_note(self):
        """Verify socket transmission timeouts return FAILED with unconfirmed note."""
        provider = PiwappProvider(session_path=self.session_path, keys_path=self.keys_path)

        loop = asyncio.new_event_loop()
        provider._loop = loop
        mock_client = MagicMock()
        mock_client.is_open = True

        async def slow_send(*args, **kwargs):
            await asyncio.sleep(0.5)
            return "msg_never_reached"

        mock_client.send_text = slow_send
        provider._client = mock_client
        provider._is_connected = True

        # Use mock future that raises TimeoutError
        from unittest.mock import patch
        with patch("asyncio.run_coroutine_threadsafe") as mock_run:
            mock_future = MagicMock()
            mock_future.result.side_effect = TimeoutError("Timed out")
            mock_run.return_value = mock_future

            result = provider.send(self.contact, "Hello")
            self.assertFalse(result.success)
            self.assertEqual(result.status, SendStatus.FAILED)
            self.assertIn("Transmission unconfirmed", result.notes)
            loop.close()

    def test_resolve_wa_web_version_caching_and_invalidation(self):
        """Verify protocol version is cached to disk and invalidated on demand."""
        cache_file = os.path.join(self.temp_dir.name, "test_wa_version.json")
        provider = PiwappProvider(
            session_path=self.session_path,
            keys_path=self.keys_path,
            version_cache_path=cache_file,
        )

        # First call creates cache
        ver = provider.get_resolved_wa_version()
        self.assertIsInstance(ver, tuple)
        self.assertEqual(len(ver), 3)
        self.assertTrue(os.path.exists(cache_file))

        # Manually alter cache file to verify reading from cache
        import json
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"version": [2, 3000, 999999999], "timestamp": 9999999999}, f)

        cached_ver = provider.get_resolved_wa_version()
        self.assertEqual(cached_ver, (2, 3000, 999999999))

        # Invalidate cache
        provider.invalidate_version_cache()
        self.assertFalse(os.path.exists(cache_file))

    def test_contact_view_refresh_contacts_method_exists_and_runs(self):
        """Verify ContactView implements refresh_contacts and does not raise AttributeError."""
        import customtkinter as ctk
        from src.ui.components.contact_view import ContactView

        root = ctk.CTk()
        root.withdraw()
        try:
            view = ContactView(root, on_import_clicked=lambda: None)
            contacts = [self.contact]
            # Should run cleanly without raising AttributeError
            view.refresh_contacts(contacts)
            self.assertEqual(len(view._all_contacts), 1)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()

