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
        import traceback
        err_msg = traceback.format_exc()
        print(f"Fatal error launching application:\n{err_msg}")
        try:
            from src.config import get_user_data_dir
            crash_file = get_user_data_dir() / "crash.log"
            crash_file.write_text(err_msg, encoding="utf-8")
        except Exception:
            pass
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                f"{APP_NAME} - Launch Error",
                f"A fatal error occurred while starting {APP_NAME} v{APP_VERSION}:\n\n"
                f"{e}\n\n"
                f"Detailed log written to:\n"
                f"%LOCALAPPDATA%\\WhatsAppBulkMessenger\\crash.log"
            )
            root.destroy()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()

