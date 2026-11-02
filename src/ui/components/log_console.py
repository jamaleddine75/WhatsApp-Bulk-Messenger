"""Live activity console and audit log viewer component."""

import os
import subprocess
import sys
from datetime import datetime
from typing import Optional
import customtkinter as ctk
from src.config import DEFAULT_LOG_FILE, DELIVERY_DISCLAIMER
from src.diagnostics import get_logger

_logger = get_logger()


class LogConsole(ctk.CTkFrame):
    """Component for displaying real-time events and opening sent_log.csv."""

    def __init__(self, master, log_file_path: str = DEFAULT_LOG_FILE, **kwargs):
        super().__init__(master, **kwargs)
        self.log_file_path = log_file_path
        self._build_ui()

    def _build_ui(self) -> None:
        # Top Bar
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(8, 3))

        lbl_title = ctk.CTkLabel(
            top_bar,
            text="4. Live Activity Log & Audit Trail",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        lbl_title.pack(side="left")

        # Action Buttons
        btn_open_csv = ctk.CTkButton(
            top_bar,
            text="📊 Open sent_log.csv",
            command=self._open_log_file,
            width=130,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#37474F",
            hover_color="#263238",
        )
        btn_open_csv.pack(side="right", padx=(4, 0))

        btn_clear = ctk.CTkButton(
            top_bar,
            text="🧹 Clear Log",
            command=self.clear_log,
            width=75,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray90"),
            hover_color=("gray65", "gray40"),
        )
        btn_clear.pack(side="right")

        # Console Textbox (Compact height, expands with window)
        self.textbox = ctk.CTkTextbox(
            self,
            height=90,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=("gray95", "gray10"),
            wrap="word",
        )
        self.textbox.pack(fill="both", expand=True, padx=8, pady=(2, 4))

        # Disclaimer Footer
        disclaimer_lbl = ctk.CTkLabel(
            self,
            text=f"⚠️ {DELIVERY_DISCLAIMER}",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color=("#E65100", "#FFB74D"),
            anchor="w",
            wraplength=520,
        )
        disclaimer_lbl.pack(fill="x", padx=8, pady=(0, 6))

        # Initial message
        self.append_log("System initialized. Ready to load contacts.")

    def append_log(self, text: str) -> None:
        """Append a timestamped message to the console."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {text}\n"

        try:
            self.textbox.configure(state="normal")
            self.textbox.insert("end", entry)
            self.textbox.see("end")
            self.textbox.configure(state="disabled")
        except Exception as e:
            _logger.error("Failed to append to UI log console: %s", e)

    def clear_log(self) -> None:
        """Clear the console screen."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.append_log("Console cleared.")

    def _open_log_file(self) -> None:
        """Open sent_log.csv using the host OS default application."""
        if not os.path.exists(self.log_file_path):
            self.append_log(f"Notice: Log file '{self.log_file_path}' does not exist yet.")
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(self.log_file_path)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", self.log_file_path])
            else:
                subprocess.Popen(["xdg-open", self.log_file_path])
            self.append_log(f"Opened log file: {self.log_file_path}")
            _logger.info("Opened log file externally: %s", self.log_file_path)
        except Exception as e:
            self.append_log(f"Could not open file automatically: {e}")
            _logger.error("Could not open log file: %s", e)
