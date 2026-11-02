"""Unit tests for MessageEngine."""

import unittest
import urllib.parse
from src.message_engine import MessageEngine
from src.models import Contact


class TestMessageEngine(unittest.TestCase):
    """Test suite for message personalization and WhatsApp URL generation."""

    def setUp(self):
        self.engine = MessageEngine()
        self.sample_contact = Contact(
            index=1,
            raw_phone="0612345678",
            clean_phone="212612345678",
            formatted_phone="+212 612-345678",
            name="Mehdi Bennani",
            extra_fields={"city": "Casablanca", "order_id": "CMD-994"},
            is_valid=True,
        )

    def test_personalize_name_and_extras(self):
        template = "Salam {name}, commande {order_id} pour {city} est prête."
        result = self.engine.personalize_message(template, self.sample_contact)
        self.assertEqual(result, "Salam Mehdi Bennani, commande CMD-994 pour Casablanca est prête.")

    def test_empty_name_fallback(self):
        contact_no_name = Contact(
            index=2,
            raw_phone="0612345678",
            clean_phone="212612345678",
            formatted_phone="+212 612-345678",
            name="",
            is_valid=True,
        )
        template = "Bonjour {name}, votre compte est activé."
        result = self.engine.personalize_message(template, contact_no_name, default_name_fallback="Cher Client")
        self.assertEqual(result, "Bonjour Cher Client, votre compte est activé.")

    def test_arabic_script_and_darija(self):
        template = "السلام عليكم {name}، تبارك الله عليك!"
        result = self.engine.personalize_message(template, self.sample_contact)
        self.assertEqual(result, "السلام عليكم Mehdi Bennani، تبارك الله عليك!")

    def test_whatsapp_url_encoding(self):
        message = "Bonjour Mehdi!\nC'est validé à 100% 👍"
        url = self.engine.build_click_to_chat_url("212612345678", message)
        self.assertTrue(url.startswith("https://web.whatsapp.com/send?phone=212612345678&text="))
        # Ensure roundtrip decoding recovers the exact original text
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(params["phone"][0], "212612345678")
        self.assertEqual(params["text"][0], message)

    def test_extract_placeholders(self):
        template = "Hello {name}, your order {order_id} to {city} is confirmed on {date}."
        placeholders = self.engine.extract_placeholders(template)
        self.assertEqual(placeholders, ["city", "date", "name", "order_id"])

    def test_custom_variables_defaults_and_contact_overrides(self):
        template = "Bonjour {name}, offre pour {product} à {price} MAD à {city}."
        custom_vars = {"product": "Offre Standard", "price": "1000", "city": "Rabat"}

        # Case 1: Contact has city='Casablanca', but no product and no price
        result = self.engine.personalize_message(
            template, self.sample_contact, custom_variables=custom_vars
        )
        # city from contact overrides default 'Rabat'; product and price use defaults
        self.assertEqual(result, "Bonjour Mehdi Bennani, offre pour Offre Standard à 1000 MAD à Casablanca.")

        # Case 2: Contact has specific product and price in extra_fields
        contact_with_offer = Contact(
            index=3,
            raw_phone="0612345678",
            name="Sara",
            extra_fields={"product": "Formation Python", "price": "500", "city": "Tanger"},
        )
        result2 = self.engine.personalize_message(
            template, contact_with_offer, custom_variables=custom_vars
        )
        self.assertEqual(result2, "Bonjour Sara, offre pour Formation Python à 500 MAD à Tanger.")

    def test_missing_variables_detection(self):
        template = "Bonjour {name}, rendez-vous pour {appointment} avec le Dr. {doctor}."
        # Neither contact nor custom_variables provide appointment or doctor
        missing = self.engine.get_missing_variables(template, self.sample_contact)
        self.assertEqual(missing, ["appointment", "doctor"])

        # With default for appointment
        missing2 = self.engine.get_missing_variables(
            template, self.sample_contact, custom_variables={"appointment": "Consultation"}
        )
        self.assertEqual(missing2, ["doctor"])

    def test_multiline_and_emojis_rendering(self):
        template = "🎉 Félicitations {name}!\n\nVotre commande spéciale est prête 🚀.\nLivraison à {city} 📦."
        result = self.engine.personalize_message(template, self.sample_contact)
        self.assertIn("🎉 Félicitations Mehdi Bennani!", result)
        self.assertIn("Livraison à Casablanca 📦.", result)
        self.assertEqual(result.count("\n"), 3)


if __name__ == "__main__":
    unittest.main()

