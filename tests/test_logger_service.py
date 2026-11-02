"""Unit tests for LoggerService."""

import csv
import os
import tempfile
import unittest
from src.logger_service import LoggerService, LOG_HEADERS
from src.models import SendStatus


class TestLoggerService(unittest.TestCase):
    """Test suite for CSV audit logging."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        self.temp_file.close()
        os.remove(self.temp_file.name)  # ensure file doesn't exist yet
        self.logger = LoggerService(self.temp_file.name)

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_file_creation_with_headers(self):
        self.assertTrue(os.path.exists(self.temp_file.name))
        with open(self.temp_file.name, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header, LOG_HEADERS)

    def test_log_multiple_statuses(self):
        self.logger.log_attempt(
            phone="212612345678",
            name="Yassine",
            status=SendStatus.OPENED,
            notes="Opened in browser for review",
            chat_url="https://web.whatsapp.com/send?phone=212612345678",
        )
        self.logger.log_attempt(
            phone="212612345678",
            name="Yassine",
            status=SendStatus.MANUALLY_CONFIRMED,
            notes="User confirmed sent in WhatsApp Web",
        )
        self.logger.log_attempt(
            phone="212798765432",
            name="فاطمة الزهراء",
            status=SendStatus.SKIPPED,
            notes="Skipped by operator",
        )

        entries = self.logger.get_recent_entries()
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].status, SendStatus.OPENED.value)
        self.assertEqual(entries[1].status, SendStatus.MANUALLY_CONFIRMED.value)
        self.assertEqual(entries[2].status, SendStatus.SKIPPED.value)
        self.assertEqual(entries[2].name, "فاطمة الزهراء")


if __name__ == "__main__":
    unittest.main()

