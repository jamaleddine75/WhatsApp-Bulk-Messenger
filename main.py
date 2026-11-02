#!/usr/bin/env python3
"""Main entry point for WhatsApp Bulk Messenger application."""

import sys
import os

# Ensure project root directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.config import APP_NAME, APP_VERSION
from src.ui.app import WhatsAppBulkMessengerApp


def check_python_version() -> None:
    """Verify that Python version meets the minimum requirement."""
    if sys.version_info < (3, 10):
        print(
            f"ERROR: {APP_NAME} requires Python 3.10 or newer. "
            f"Detected version: {sys.version.split()[0]}"
        )
        sys.exit(1)


def main() -> None:
    """Initialize and launch the GUI application."""
    check_python_version()

    try:
        app = WhatsAppBulkMessengerApp()
        app.mainloop()
    except KeyboardInterrupt:
        print("\nApplication closed by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error launching application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

