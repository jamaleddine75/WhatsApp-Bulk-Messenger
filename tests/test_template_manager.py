"""Unit tests for TemplateManager and MessageEditor advanced template workflows."""

import os
from pathlib import Path
import tempfile
import unittest

from src.message_engine import MessageEngine
from src.models import Contact
from src.template_manager import MessageTemplate, TemplateManager


class TestTemplateManager(unittest.TestCase):
    """Test suite for MessageTemplate persistence, loading, and corrupted file handling."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.temp_dir.name) / "templates"
        self.manager = TemplateManager(storage_dir=self.storage_dir)

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_seed_default_templates(self):
        templates = self.manager.list_templates()
        self.assertGreater(len(templates), 0)
        self.assertIn("French - Confirmation de Commande / RDV", templates)
        self.assertIn("Product Offer (with Custom Variables)", templates)

    def test_save_and_load_template_with_custom_variables(self):
        tpl = MessageTemplate(
            name="Holiday Special Offer",
            body="Bonjour {name},\nProfitez de {product} à {price} MAD!\nOffre limitée 🎁.",
            custom_variables={"product": "Formation IA", "price": "750"},
        )
        ok, msg = self.manager.save_template(tpl, overwrite=False)
        self.assertTrue(ok)

        loaded = self.manager.get_template("Holiday Special Offer")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "Holiday Special Offer")
        self.assertEqual(loaded.body, tpl.body)
        self.assertEqual(loaded.custom_variables, {"product": "Formation IA", "price": "750"})
        self.assertTrue(bool(loaded.created_at))
        self.assertTrue(bool(loaded.updated_at))

    def test_save_overwrite_protection(self):
        tpl = MessageTemplate(name="Unique Campaign", body="Text 1")
        ok, _ = self.manager.save_template(tpl, overwrite=False)
        self.assertTrue(ok)

        # Attempting save without overwrite flag must fail
        tpl_dup = MessageTemplate(name="Unique Campaign", body="Text 2")
        ok_dup, err = self.manager.save_template(tpl_dup, overwrite=False)
        self.assertFalse(ok_dup)
        self.assertIn("already exists", err.lower())

        # Overwrite with flag must succeed
        ok_overwrite, _ = self.manager.save_template(tpl_dup, overwrite=True)
        self.assertTrue(ok_overwrite)
        loaded = self.manager.get_template("Unique Campaign")
        self.assertEqual(loaded.body, "Text 2")

    def test_delete_template(self):
        tpl = MessageTemplate(name="Temporary Notice", body="Notice text")
        self.manager.save_template(tpl)
        self.assertIn("Temporary Notice", self.manager.list_templates())

        ok, _ = self.manager.delete_template("Temporary Notice")
        self.assertTrue(ok)
        self.assertNotIn("Temporary Notice", self.manager.list_templates())
        self.assertIsNone(self.manager.get_template("Temporary Notice"))

    def test_corrupted_json_resilience(self):
        # Create a completely corrupted JSON file in storage
        corrupted_path = self.storage_dir / "corrupted_template.json"
        corrupted_path.write_text("{ this is NOT valid json !!! }", encoding="utf-8")

        # Must not crash list_templates or get_template
        templates = self.manager.list_templates()
        self.assertIsInstance(templates, list)
        self.assertNotIn("corrupted_template", templates)

        # Querying non-existent or corrupted template returns None
        result = self.manager.get_template("NonExistent")
        self.assertIsNone(result)

    def test_empty_template_name_validation(self):
        tpl = MessageTemplate(name="   ", body="Body text")
        ok, msg = self.manager.save_template(tpl)
        self.assertFalse(ok)
        self.assertIn("cannot be empty", msg.lower())


class TestMessageEditorComponent(unittest.TestCase):
    """Test suite for MessageEditor GUI integration and variable insertion."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.temp_dir.name) / "templates"
        self.template_manager = TemplateManager(storage_dir=self.storage_dir)
        self.message_engine = MessageEngine()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_insert_variable_at_cursor_and_preview(self):
        import customtkinter as ctk
        from src.ui.components.message_editor import MessageEditor

        root = ctk.CTk()
        root.withdraw()
        try:
            editor = MessageEditor(
                root,
                message_engine=self.message_engine,
                template_manager=self.template_manager,
            )

            editor.set_template_text("Bonjour ")
            editor.insert_variable_at_cursor("{name}")
            self.assertEqual(editor.get_template_text(), "Bonjour {name}")

            # Insert custom variable
            editor.set_custom_variables({"product": "Abonnement VIP"})
            editor.insert_text_at_cursor(" pour ")
            editor.insert_variable_at_cursor("product")
            self.assertEqual(editor.get_template_text(), "Bonjour {name} pour {product}")

            # Verify custom variables retrieval
            vars_dict = editor.get_custom_variables()
            self.assertEqual(vars_dict, {"product": "Abonnement VIP"})

            # Preview verification for contact with extra field
            contact = Contact(
                index=1,
                raw_phone="0612345678",
                clean_phone="212612345678",
                name="Amine",
                extra_fields={"product": "Pass Festival"},
            )
            editor.update_preview(contact)
            preview_content = editor.preview_box.get("1.0", "end")
            self.assertIn("Bonjour Amine pour Pass Festival", preview_content)
        finally:
            root.destroy()

    def test_preview_missing_variable_warning(self):
        import customtkinter as ctk
        from src.ui.components.message_editor import MessageEditor

        root = ctk.CTk()
        root.withdraw()
        try:
            editor = MessageEditor(
                root,
                message_engine=self.message_engine,
                template_manager=self.template_manager,
            )

            # Template references {appointment_date} with no default and contact without it
            editor.set_template_text("RDV fixé au {appointment_date}.")
            contact = Contact(index=1, raw_phone="0612345678", name="Fatima")

            editor.update_preview(contact)
            preview_content = editor.preview_box.get("1.0", "end")
            self.assertIn("WARNING", preview_content)
            self.assertIn("{appointment_date}", preview_content)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
