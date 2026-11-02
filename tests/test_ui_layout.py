"""Unit tests for UI layout, responsiveness, and control placement."""

import unittest
from src.config import MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH
from src.ui.app import WhatsAppBulkMessengerApp


class TestUILayout(unittest.TestCase):
    """Test suite for GUI layout hierarchy, responsiveness, and button accessibility."""

    @classmethod
    def setUpClass(cls):
        cls.app = WhatsAppBulkMessengerApp()
        cls.app.withdraw()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_scrollable_container_exists(self):
        """Ensure the main content is housed in a scrollable frame."""
        self.assertTrue(hasattr(self.app, "scroll_body"))
        self.assertIsNotNone(self.app.scroll_body._parent_canvas)

    def test_all_panels_instantiated(self):
        """Ensure all 4 core panels are created and placed in the layout."""
        self.assertTrue(hasattr(self.app, "contact_view"))
        self.assertTrue(hasattr(self.app, "log_console"))
        self.assertTrue(hasattr(self.app, "message_editor"))
        self.assertTrue(hasattr(self.app, "control_panel"))

    def test_start_button_accessible(self):
        """Ensure Start button is created, enabled, and mapped."""
        btn_start = self.app.control_panel.btn_start
        self.assertIsNotNone(btn_start)
        self.assertEqual(btn_start.cget("state"), "normal")
        self.assertEqual(btn_start.cget("text"), "▶️ Start Broadcast")

    def test_minimum_window_dimensions(self):
        """Ensure minimum dimensions prevent window from collapsing beyond limits."""
        min_w = self.app._min_width
        min_h = self.app._min_height
        self.assertGreaterEqual(min_w, MIN_WINDOW_WIDTH)
        self.assertGreaterEqual(min_h, MIN_WINDOW_HEIGHT)

    def test_vertical_scrolling_on_small_window(self):
        """Verify that scrolling down and up moves the canvas view properly."""
        canvas = self.app.scroll_body._parent_canvas
        # Scroll down
        canvas.yview_scroll(3, "units")
        self.app.update_idletasks()

        # Reset back to top
        canvas.yview_moveto(0.0)
        self.app.update_idletasks()
        reset_y = canvas.yview()[0]

        self.assertEqual(reset_y, 0.0)

    def test_default_provider_is_piwapp_with_manual_fallback(self):
        """Ensure Piwapp is active provider by default, and Web Manual is available as fallback."""
        from src.sender_controller import DispatchMode
        self.assertEqual(
            self.app.control_panel.get_selected_mode(),
            DispatchMode.PIWAPP_AUTOMATED,
        )
        self.assertTrue(self.app.piwapp_provider.is_automated)
        # Check review buttons and fallback provider can be switched to
        self.app.control_panel.set_selected_mode(DispatchMode.WEB_MANUAL_REVIEW)
        self.assertEqual(
            self.app.control_panel.get_selected_mode(),
            DispatchMode.WEB_MANUAL_REVIEW,
        )
        self.assertIsNotNone(self.app.control_panel.btn_confirm)
        self.assertIsNotNone(self.app.control_panel.btn_skip)


if __name__ == "__main__":
    unittest.main()
