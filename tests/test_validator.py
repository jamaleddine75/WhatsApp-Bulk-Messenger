"""Unit tests for phone number validator."""

import unittest
from src.validator import normalize_and_validate_phone


class TestPhoneValidator(unittest.TestCase):
    """Test suite for Moroccan and international phone validation."""

    def test_moroccan_domestic_06(self):
        valid, clean, formatted, err = normalize_and_validate_phone("0612345678")
        self.assertTrue(valid)
        self.assertEqual(clean, "212612345678")
        self.assertEqual(formatted, "+212 612-345678")
        self.assertEqual(err, "")

    def test_moroccan_domestic_07(self):
        valid, clean, formatted, err = normalize_and_validate_phone("07-98-76-54-32")
        self.assertTrue(valid)
        self.assertEqual(clean, "212798765432")
        self.assertEqual(formatted, "+212 798-765432")

    def test_moroccan_domestic_05(self):
        valid, clean, formatted, err = normalize_and_validate_phone("05 22 12 34 56")
        self.assertTrue(valid)
        self.assertEqual(clean, "212522123456")
        self.assertEqual(formatted, "+212 522-123456")

    def test_moroccan_with_plus_212(self):
        valid, clean, formatted, err = normalize_and_validate_phone("+212 661 112 233")
        self.assertTrue(valid)
        self.assertEqual(clean, "212661112233")
        self.assertEqual(formatted, "+212 661-112233")

    def test_moroccan_with_00212(self):
        valid, clean, formatted, err = normalize_and_validate_phone("00212661112233")
        self.assertTrue(valid)
        self.assertEqual(clean, "212661112233")

    def test_moroccan_raw_212(self):
        valid, clean, formatted, err = normalize_and_validate_phone("212661112233")
        self.assertTrue(valid)
        self.assertEqual(clean, "212661112233")

    def test_moroccan_missing_leading_zero(self):
        valid, clean, formatted, err = normalize_and_validate_phone("612345678")
        self.assertTrue(valid)
        self.assertEqual(clean, "212612345678")

    def test_invalid_moroccan_prefix(self):
        # 01 is not a valid Moroccan prefix
        valid, clean, formatted, err = normalize_and_validate_phone("0112345678")
        self.assertFalse(valid)
        self.assertIn("Invalid Moroccan prefix", err)

    def test_invalid_moroccan_length(self):
        # +212 with only 8 national digits
        valid, clean, formatted, err = normalize_and_validate_phone("+21261234567")
        self.assertFalse(valid)
        self.assertIn("Expected exactly 9", err)

    def test_international_e164_french(self):
        valid, clean, formatted, err = normalize_and_validate_phone("+33612345678")
        self.assertTrue(valid)
        self.assertEqual(clean, "33612345678")
        self.assertEqual(formatted, "+33612345678")

    def test_international_e164_us(self):
        valid, clean, formatted, err = normalize_and_validate_phone("+14155552671")
        self.assertTrue(valid)
        self.assertEqual(clean, "14155552671")
        self.assertEqual(formatted, "+14155552671")

    def test_reject_letters(self):
        valid, clean, formatted, err = normalize_and_validate_phone("061234ABCD")
        self.assertFalse(valid)
        self.assertIn("alphabetic", err)

    def test_reject_empty(self):
        valid, clean, formatted, err = normalize_and_validate_phone("")
        self.assertFalse(valid)
        self.assertIn("Empty", err)


if __name__ == "__main__":
    unittest.main()

