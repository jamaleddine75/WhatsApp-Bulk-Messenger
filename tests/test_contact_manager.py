"""Unit tests for ContactManager."""

import os
import tempfile
import unittest
from src.contact_manager import ContactManager
from src.models import SendStatus


class TestContactManager(unittest.TestCase):
    """Test suite for CSV loading, deduplication, and validation."""

    def setUp(self):
        self.manager = ContactManager()

    def test_load_valid_csv(self):
        csv_data = (
            "phone,name,city\n"
            "0612345678,Yassine Bennani,Casablanca\n"
            "0798765432,Salma Idrissi,Rabat\n"
            "+212661223344,Mehdi Alami,Marrakech\n"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
            f.write(csv_data)
            tmp_path = f.name

        try:
            summary = self.manager.load_from_csv(tmp_path)
            self.assertEqual(summary.total_rows, 3)
            self.assertEqual(summary.valid_count, 3)
            self.assertEqual(summary.invalid_count, 0)
            self.assertEqual(summary.duplicate_count, 0)

            # Check first contact
            c0 = self.manager.valid_contacts[0]
            self.assertEqual(c0.name, "Yassine Bennani")
            self.assertEqual(c0.clean_phone, "212612345678")
            self.assertEqual(c0.extra_fields.get("city"), "Casablanca")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_duplicate_detection(self):
        csv_data = (
            "phone,name\n"
            "0612345678,Karim First\n"
            "+212612345678,Karim Duplicate Same Number\n"
            "0699887766,Amina Valid\n"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
            f.write(csv_data)
            tmp_path = f.name

        try:
            summary = self.manager.load_from_csv(tmp_path)
            self.assertEqual(summary.total_rows, 3)
            self.assertEqual(summary.valid_count, 2)
            self.assertEqual(summary.duplicate_count, 1)
            self.assertEqual(len(self.manager.duplicate_contacts), 1)
            self.assertIn("Duplicate", self.manager.duplicate_contacts[0].validation_error)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_invalid_entries_skipped(self):
        csv_data = (
            "phone,name\n"
            "0612345678,Good Contact\n"
            "NOT_A_PHONE,Bad Contact\n"
            "0112345678,Bad Prefix\n"
            "0612345,Too Short\n"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
            f.write(csv_data)
            tmp_path = f.name

        try:
            summary = self.manager.load_from_csv(tmp_path)
            self.assertEqual(summary.total_rows, 4)
            self.assertEqual(summary.valid_count, 1)
            self.assertEqual(summary.invalid_count, 3)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_semicolon_and_arabic_utf8(self):
        csv_data = (
            "telephone;nom;ville\n"
            "0661123456;محمد التازي;طنجة\n"
            "0712345678;فاطمة الزهراء;فاس\n"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
            f.write(csv_data)
            tmp_path = f.name

        try:
            summary = self.manager.load_from_csv(tmp_path)
            self.assertEqual(summary.valid_count, 2)
            self.assertEqual(self.manager.valid_contacts[0].name, "محمد التازي")
            self.assertEqual(self.manager.valid_contacts[0].extra_fields.get("ville"), "طنجة")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_opt_in_consent_parsing(self):
        csv_data = (
            "phone,name,opted_in\n"
            "0612345678,Consented Person,yes\n"
            "0712345678,Unconsented Person,no\n"
            "0522123456,Another Consented,1\n"
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
            f.write(csv_data)
            tmp_path = f.name

        try:
            summary = self.manager.load_from_csv(tmp_path)
            self.assertEqual(summary.valid_count, 3)
            self.assertEqual(summary.eligible_count, 2)
            self.assertEqual(summary.no_consent_count, 1)

            # Check unconsented status
            c_unconsented = [c for c in self.manager.valid_contacts if c.name == "Unconsented Person"][0]
            self.assertFalse(c_unconsented.opted_in)
            self.assertFalse(c_unconsented.is_eligible)
            self.assertEqual(c_unconsented.status, SendStatus.SKIPPED_NO_CONSENT)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_suppression_list_cross_check(self):
        from src.database import DatabaseManager
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        db_file.close()
        try:
            db = DatabaseManager(db_file.name)
            db.add_opt_out("212612345678", "User requested DND")

            csv_data = (
                "phone,name\n"
                "0612345678,Suppressed Contact\n"
                "0712345678,Allowed Contact\n"
            )
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".csv") as f:
                f.write(csv_data)
                csv_path = f.name

            try:
                summary = self.manager.load_from_csv(csv_path, db_manager=db)
                self.assertEqual(summary.suppressed_count, 1)
                self.assertEqual(summary.eligible_count, 1)

                suppressed = [c for c in self.manager.valid_contacts if c.clean_phone == "212612345678"][0]
                self.assertTrue(suppressed.is_suppressed)
                self.assertFalse(suppressed.is_eligible)
                self.assertEqual(suppressed.status, SendStatus.SKIPPED_OPT_OUT)
            finally:
                if os.path.exists(csv_path):
                    os.remove(csv_path)
        finally:
            if os.path.exists(db_file.name):
                os.remove(db_file.name)


if __name__ == "__main__":
    unittest.main()

