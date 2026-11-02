"""Unit tests for DatabaseManager (idempotency, suppression, campaign recovery)."""

import os
import tempfile
import unittest
from src.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    """Test suite for SQLite campaign and suppression management."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        os.remove(self.temp_db.name)
        self.db = DatabaseManager(self.temp_db.name)

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_create_and_get_campaign(self):
        camp = self.db.create_campaign(
            campaign_id="camp_001",
            name="Summer Sale 2026",
            provider="WhatsAppCloudApiProvider",
            template_text="Hello {name}",
            total_contacts=50,
        )
        self.assertEqual(camp["id"], "camp_001")
        self.assertEqual(camp["name"], "Summer Sale 2026")
        self.assertEqual(camp["status"], "CREATED")

        fetched = self.db.get_campaign("camp_001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["total_contacts"], 50)

    def test_message_idempotency_and_duplicates(self):
        self.db.create_campaign("camp_002", "Idempotency Test", "Provider")

        # First record of message
        ok1 = self.db.record_message("camp_002", "212612345678", "Yassine", "API_SENT", "wamid.123", "Sent ok")
        self.assertTrue(ok1)

        # Query completed phones
        completed = self.db.get_completed_phones_for_campaign("camp_002")
        self.assertIn("212612345678", completed)

        # Update message with new status (UPSERT on conflict)
        ok2 = self.db.record_message("camp_002", "212612345678", "Yassine", "DELIVERED", "wamid.123", "Receipt confirmed")
        self.assertTrue(ok2)

        messages = self.db.get_campaign_messages("camp_002")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["status"], "DELIVERED")

    def test_opt_out_suppression(self):
        self.assertFalse(self.db.is_opted_out("212661998877"))

        self.db.add_opt_out("212661998877", "Customer requested stop")
        self.assertTrue(self.db.is_opted_out("212661998877"))
        self.assertTrue(self.db.is_opted_out("+212661998877"))

        opt_outs = self.db.get_all_opt_outs()
        self.assertIn("212661998877", opt_outs)

        self.db.remove_opt_out("212661998877")
        self.assertFalse(self.db.is_opted_out("212661998877"))

    def test_export_campaign_csv_masks_phone(self):
        self.db.create_campaign("camp_003", "Export Test", "Cloud API")
        self.db.record_message("camp_003", "212612345678", "Mehdi", "API_SENT", "wamid.456", "OK")

        export_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        export_file.close()

        try:
            self.db.export_campaign_csv("camp_003", export_file.name)
            with open(export_file.name, "r", encoding="utf-8-sig") as f:
                content = f.read()
            self.assertIn("21261****678", content)  # Masked phone
            self.assertNotIn("212612345678", content)  # Plain phone masked
            self.assertIn("wamid.456", content)
        finally:
            if os.path.exists(export_file.name):
                os.remove(export_file.name)


if __name__ == "__main__":
    unittest.main()

