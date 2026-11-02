"""Main application window and responsive layout for WhatsApp Bulk Messenger."""

import os
import time
from tkinter import filedialog, messagebox, ttk
from typing import Optional
import customtkinter as ctk

from src.config import (
    APP_NAME,
    APP_VERSION,
    CONSENT_CONFIRMATION_TEXT,
    DEFAULT_LOG_FILE,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    WINDOW_TITLE,
)
from src.contact_manager import ContactManager
from src.database import DEFAULT_DB_FILE, DatabaseManager
from src.diagnostics import attach_ui_log_callback, get_logger, log_startup_diagnostics
from src.logger_service import LoggerService
from src.message_engine import MessageEngine
from src.models import Contact
from src.providers.piwapp_provider import PiwappProvider
from src.providers.web_provider import WhatsAppWebManualProvider
from src.sender_controller import ControllerState, DispatchMode, SenderController
from src.ui.components import ContactView, ControlPanel, LogConsole, MessageEditor

_logger = get_logger()


class WhatsAppBulkMessengerApp(ctk.CTk):
    """Main application GUI window with responsive, scrollable 2-column layout."""

    def __init__(self, log_path: str = DEFAULT_LOG_FILE, db_path: str = DEFAULT_DB_FILE):
        super().__init__()

        # Appearance configuration
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title(WINDOW_TITLE)

        # Dynamic, screen-responsive window sizing
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = min(1120, max(860, int(screen_w * 0.88)))
        win_h = min(700, max(540, int(screen_h * 0.82)))

        self.geometry(f"{win_w}x{win_h}")
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        # Database and core services
        self.db_manager = DatabaseManager(db_path)
        self.contact_manager = ContactManager(db_manager=self.db_manager)
        self.message_engine = MessageEngine()
        self.logger_service = LoggerService(log_path)

        # Messaging Providers: WhatsApp Web Manual (Default) and piwapp (Experimental)
        self.web_provider = WhatsAppWebManualProvider(self.message_engine)
        self.piwapp_provider = PiwappProvider()

        # Controller initialized with thread-safe UI callbacks and SQLite DB manager
        self.controller = SenderController(
            message_engine=self.message_engine,
            logger_service=self.logger_service,
            provider=self.web_provider,
            db_manager=self.db_manager,
            on_progress_update=self._thread_safe_progress_update,
            on_state_change=self._thread_safe_state_change,
            on_log_message=self._thread_safe_log_message,
        )

        self._build_layout()

        # Connect diagnostics logger to UI console
        self._diag_handler = attach_ui_log_callback(self._thread_safe_log_message)

        # Log startup diagnostics
        scaling = ctk.ScalingTracker.get_widget_scaling(self)
        log_startup_diagnostics(screen_w, screen_h, win_w, win_h, scaling)

        # Set default provider: Piwapp is active by default
        self.control_panel.set_selected_mode(DispatchMode.PIWAPP_AUTOMATED)
        has_piwapp_auth = self.piwapp_provider.has_saved_session()
        saved_account = self.piwapp_provider.get_saved_account_id()

        if has_piwapp_auth:
            self.control_panel.update_piwapp_status(
                f"Saved Session ({saved_account or 'Ready'})", False, saved_account
            )
            _logger.info("Application initialized. Active provider: piwapp (Saved session: %s).", saved_account)
        else:
            self.control_panel.update_piwapp_status("Pairing Required", False)
            _logger.info("Application initialized. Active provider: piwapp (Pairing required).")

    def destroy(self) -> None:
        """Clean shutdown stopping background worker thread, piwapp client, and detaching handlers."""
        try:
            if hasattr(self, "_diag_handler"):
                _logger.removeHandler(self._diag_handler)
        except Exception:
            pass
        try:
            if hasattr(self, "controller"):
                self.controller.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "piwapp_provider"):
                self.piwapp_provider.disconnect()
        except Exception:
            pass
        try:
            if hasattr(self, "db_manager"):
                self.db_manager.close()
        except Exception:
            pass
        super().destroy()

    def _build_layout(self) -> None:
        # 1. Top Header (Fixed compact bar)
        header = ctk.CTkFrame(self, fg_color=("gray85", "gray15"), corner_radius=0, height=44)
        header.pack(fill="x", side="top")

        lbl_app = ctk.CTkLabel(
            header,
            text=f"💬 {APP_NAME}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=("#1976D2", "#42A5F5"),
        )
        lbl_app.pack(side="left", padx=12, pady=6)

        lbl_badge = ctk.CTkLabel(
            header,
            text="🛡️ Opt-in Authorized • WhatsApp Web Manual & piwapp Experimental",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        lbl_badge.pack(side="left", padx=6, pady=6)

        # Theme toggle switch
        self.theme_switch = ctk.CTkSwitch(
            header,
            text="Dark Theme",
            command=self._toggle_theme,
            font=ctk.CTkFont(size=11),
        )
        self.theme_switch.pack(side="right", padx=12, pady=6)
        if ctk.get_appearance_mode() == "Dark":
            self.theme_switch.select()

        # 2. Responsive Scrollable Body Frame
        self.scroll_body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_body.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        # 2-column balanced grid
        self.scroll_body.grid_columnconfigure(0, weight=1)  # Left column
        self.scroll_body.grid_columnconfigure(1, weight=1)  # Right column
        self.scroll_body.grid_rowconfigure(0, weight=1)

        # --- LEFT COLUMN (Contacts View + Log Console) ---
        left_col = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(4, 2), pady=0)
        left_col.grid_columnconfigure(0, weight=1)
        left_col.grid_rowconfigure(0, weight=3)  # ContactView
        left_col.grid_rowconfigure(1, weight=2)  # LogConsole

        # 1. Contact View
        self.contact_view = ContactView(
            left_col,
            on_import_clicked=self._handle_import_csv,
            on_contact_selected=self._handle_contact_selected,
            corner_radius=8,
        )
        self.contact_view.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 4))

        # 2. Log Console
        self.log_console = LogConsole(
            left_col,
            log_file_path=DEFAULT_LOG_FILE,
            corner_radius=8,
        )
        self.log_console.grid(row=1, column=0, sticky="nsew", padx=0, pady=(4, 0))

        # --- RIGHT COLUMN (Message Editor + Control Panel) ---
        right_col = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(2, 4), pady=0)
        right_col.grid_columnconfigure(0, weight=1)
        right_col.grid_rowconfigure(0, weight=3)  # MessageEditor
        right_col.grid_rowconfigure(1, weight=2)  # ControlPanel

        # 3. Message Editor
        self.message_editor = MessageEditor(
            right_col,
            message_engine=self.message_engine,
            corner_radius=8,
        )
        self.message_editor.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 4))

        # 4. Control Panel (WhatsApp Web Manual Mode by default, piwapp supported)
        self.control_panel = ControlPanel(
            right_col,
            on_start=self._handle_start,
            on_pause=self._handle_pause,
            on_resume=self._handle_resume,
            on_stop=self._handle_stop,
            on_confirm_sent=self._handle_confirm_sent,
            on_skip=self._handle_skip,
            on_view_history=self._open_campaign_history_dialog,
            on_piwapp_connect=self._open_piwapp_pairing_dialog,
            on_piwapp_disconnect=self._handle_piwapp_disconnect,
            on_provider_changed=self._handle_provider_changed,
            on_new_campaign=self._handle_new_campaign,
            corner_radius=8,
        )
        self.control_panel.grid(row=1, column=0, sticky="nsew", padx=0, pady=(4, 0))

    def _toggle_theme(self) -> None:
        if self.theme_switch.get() == 1:
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("Light")

    def _handle_provider_changed(self, choice: str) -> None:
        if "piwapp" in choice:
            self.log_console.append_log("Selected delivery provider: piwapp (Experimental Socket Automation)")
        else:
            self.log_console.append_log("Selected delivery provider: WhatsApp Web Click-to-Chat (Manual Review)")

    # --- piwapp Connection & QR Code Modal ---
    def _open_piwapp_pairing_dialog(self) -> None:
        """Modal dialog to display live QR code and status for linking device with piwapp."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Pair WhatsApp Device with piwapp")
        dialog.geometry("450x530")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="📱 Link WhatsApp with piwapp",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(padx=20, pady=(15, 4), anchor="w")

        info = (
            "1. Open WhatsApp on your mobile phone.\n"
            "2. Tap Menu (⋮) or Settings > Linked Devices > Link a Device.\n"
            "3. Point your camera at the QR code below:"
        )
        ctk.CTkLabel(dialog, text=info, font=ctk.CTkFont(size=11), justify="left").pack(
            padx=20, pady=(0, 10), anchor="w"
        )

        qr_card = ctk.CTkFrame(dialog, fg_color=("gray92", "gray18"), corner_radius=8, width=260, height=260)
        qr_card.pack(padx=20, pady=5)
        qr_card.pack_propagate(False)

        qr_label = ctk.CTkLabel(
            qr_card,
            text="Connecting to WhatsApp...\nRequesting pairing QR code...",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        qr_label.pack(expand=True)

        lbl_status = ctk.CTkLabel(
            dialog,
            text="Status: Initializing connection...",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#1E88E5",
        )
        lbl_status.pack(padx=20, pady=8)

        def on_qr_received(qr_str: str):
            if not dialog.winfo_exists():
                return
            try:
                import qrcode
                img = qrcode.make(qr_str).convert("RGB")
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(230, 230))
                dialog.after(0, lambda: self._apply_qr_to_label(qr_label, ctk_img))
            except Exception as e:
                _logger.error("Error creating QR image: %s", e)

        def on_status_update(msg: str):
            if dialog.winfo_exists():
                color = "#D32F2F" if any(err in msg.lower() for err in ["405", "error", "failed", "outdated"]) else "#1E88E5"
                dialog.after(0, lambda: lbl_status.configure(text=f"Status: {msg}", text_color=color))

        def on_connected_event(jid: str):
            if dialog.winfo_exists():
                dialog.after(0, lambda: self._handle_pairing_success(dialog, lbl_status, jid))

        def on_dialog_close():
            if not self.piwapp_provider.is_connected:
                self.piwapp_provider.disconnect()
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

        self.piwapp_provider.connect(
            on_qr=on_qr_received,
            on_status=on_status_update,
            on_connected=on_connected_event,
        )

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(10, 15))

        ctk.CTkButton(
            btn_row,
            text="Close Window",
            command=on_dialog_close,
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray90"),
            width=100,
        ).pack(side="right")

    def _apply_qr_to_label(self, label: ctk.CTkLabel, img: ctk.CTkImage) -> None:
        label.configure(image=img, text="")

    def _handle_pairing_success(self, dialog, lbl_status: ctk.CTkLabel, jid: str) -> None:
        lbl_status.configure(text=f"✅ Successfully linked: {jid}!", text_color="#2E7D32")
        self.control_panel.update_piwapp_status("Connected", True, jid)
        self.log_console.append_log(f"piwapp: Successfully authenticated and paired as {jid}.")

    def _handle_piwapp_disconnect(self) -> None:
        self.piwapp_provider.disconnect()
        self.control_panel.update_piwapp_status("Disconnected", False)
        self.log_console.append_log("piwapp: Disconnected session.")

    # --- Campaign History & Masked CSV Export Modal ---
    def _open_campaign_history_dialog(self) -> None:
        """Modal dialog displaying campaign records from SQLite with audit export."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Campaign History & Audit Log")
        dialog.geometry("680x420")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Broadcast History (SQLite Database)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=15, pady=(12, 4), anchor="w")

        table_frame = ctk.CTkFrame(dialog, fg_color=("gray95", "gray14"))
        table_frame.pack(fill="both", expand=True, padx=15, pady=6)

        cols = ("id", "name", "provider", "status", "sent", "failed", "skipped", "created_at")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=8)

        tree.heading("id", text="Campaign ID")
        tree.heading("name", text="Name")
        tree.heading("provider", text="Provider")
        tree.heading("status", text="Status")
        tree.heading("sent", text="Sent")
        tree.heading("failed", text="Failed")
        tree.heading("skipped", text="Skipped")
        tree.heading("created_at", text="Date")

        tree.column("id", width=90, anchor="w")
        tree.column("name", width=120, anchor="w")
        tree.column("provider", width=110, anchor="w")
        tree.column("status", width=70, anchor="center")
        tree.column("sent", width=45, anchor="center")
        tree.column("failed", width=45, anchor="center")
        tree.column("skipped", width=55, anchor="center")
        tree.column("created_at", width=110, anchor="center")

        tree.pack(side="left", fill="both", expand=True, padx=3, pady=3)
        sb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=3, pady=3)

        campaigns = self.db_manager.list_campaigns()
        for c in campaigns:
            tree.insert(
                "",
                "end",
                values=(
                    c.get("id", ""),
                    c.get("name", ""),
                    c.get("provider", "")[:24],
                    c.get("status", ""),
                    c.get("sent_count", 0),
                    c.get("failed_count", 0),
                    c.get("skipped_count", 0),
                    str(c.get("created_at", ""))[:16],
                ),
            )

        btn_bar = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_bar.pack(fill="x", padx=15, pady=(4, 12))

        def export_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Select Campaign", "Please select a campaign from the table to export.")
                return
            camp_id = tree.item(sel[0], "values")[0]
            out_file = filedialog.asksaveasfilename(
                title="Export Masked Campaign Audit CSV",
                defaultextension=".csv",
                initialfile=f"audit_{camp_id}.csv",
                filetypes=[("CSV Files", "*.csv")],
            )
            if out_file:
                try:
                    self.db_manager.export_campaign_csv(camp_id, out_file)
                    messagebox.showinfo(
                        "Export Complete",
                        f"Campaign audit log exported with masked phone numbers to:\n\n{out_file}",
                    )
                except Exception as e:
                    messagebox.showerror("Export Failed", f"Could not export CSV: {e}")

        ctk.CTkButton(
            btn_bar,
            text="📥 Export Masked CSV Audit",
            command=export_selected,
            fg_color="#00897B",
            hover_color="#00695C",
            width=180,
        ).pack(side="left")

        ctk.CTkButton(
            btn_bar,
            text="Close",
            command=dialog.destroy,
            width=80,
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray90"),
        ).pack(side="right")

    # --- File Import Handling ---
    def _handle_import_csv(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select Contacts CSV File",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        )
        if not file_path:
            return

        _logger.info("Importing CSV: %s", file_path)
        try:
            summary = self.contact_manager.load_from_csv(file_path, db_manager=self.db_manager)
            self.contact_view.set_contacts(self.contact_manager.contacts, summary)

            first_valid = next((c for c in self.contact_manager.contacts if c.is_valid), None)
            self.message_editor.update_preview(first_valid)

            self.control_panel.update_progress(0, summary.valid_count, None)
            self.log_console.append_log(
                f"Imported CSV '{os.path.basename(file_path)}': {summary.valid_count} valid, "
                f"{summary.invalid_count} invalid, {summary.duplicate_count} duplicates."
            )

            if summary.valid_count == 0:
                messagebox.showwarning(
                    "No Valid Contacts",
                    "No valid phone numbers were found in this CSV. Please check formatting.",
                )
            else:
                self.log_console.append_log(
                    f"Ready: {summary.valid_count} contacts loaded. Confirm consent and click 'Start Broadcast'."
                )
        except Exception as e:
            _logger.error("CSV Import Error: %s", e)
            messagebox.showerror("CSV Import Error", str(e))
            self.log_console.append_log(f"Error loading CSV: {e}")

    def _handle_contact_selected(self, contact: Contact) -> None:
        """When user clicks a contact row in the table, update the live message preview."""
        self.message_editor.update_preview(contact)

    # --- Broadcast Actions & Confirmation Dialog ---
    def _handle_start(self) -> None:
        _logger.info("Start broadcast requested.")

        if not self.contact_manager.valid_contacts:
            _logger.warning("Start blocked: No valid contacts imported.")
            self.log_console.append_log("Cannot start: Please import a CSV with valid contacts first.")
            messagebox.showwarning(
                "No Contacts", "Please import a CSV containing valid contacts first."
            )
            return

        if not self.control_panel.is_consent_given():
            _logger.warning("Start blocked: Recipient consent checkbox not checked.")
            self.control_panel.highlight_consent()
            self.log_console.append_log("Cannot start: Please certify recipient consent by checking the consent box.")
            messagebox.showwarning(
                "Consent Required",
                "You must check the consent confirmation box before broadcasting messages.\n\n"
                f"{CONSENT_CONFIRMATION_TEXT}",
            )
            return

        template = self.message_editor.get_template_text()
        if not template.strip():
            _logger.warning("Start blocked: Message template is empty.")
            self.log_console.append_log("Cannot start: Message template is empty.")
            messagebox.showwarning("Empty Message", "Please write or select a message template.")
            return

        mode = self.control_panel.get_selected_mode()
        delay_seconds = self.control_panel.get_selected_delay()
        skip_dups = self.control_panel.should_skip_already_sent()
        global_dedup = self.control_panel.should_global_dedup()
        campaign_name = self.control_panel.get_campaign_name() or f"Campaign {time.strftime('%Y-%m-%d %H:%M')}"
        valid_contacts = self.contact_manager.valid_contacts
        preview_sample = template[:90] + "..." if len(template) > 90 else template

        # Select active provider strictly based on selected mode
        if mode == DispatchMode.PIWAPP_AUTOMATED:
            provider = self.piwapp_provider
            valid_cfg, cfg_msg = provider.validate_configuration()
            if not valid_cfg:
                _logger.warning("piwapp configuration invalid: %s", cfg_msg)
                messagebox.showwarning(
                    "piwapp Setup Required",
                    f"{cfg_msg}\n\nPlease click '🔗 Connect / Pair QR' to link your WhatsApp account before starting.",
                )
                self._open_piwapp_pairing_dialog()
                return  # Never silently fall back to manual mode!
        elif mode == DispatchMode.CLOUD_API_AUTOMATED:
            provider = self.cloud_provider if hasattr(self, "cloud_provider") else self.controller.get_or_create_provider(mode)
        else:
            provider = self.web_provider

        # Dynamic confirmation dialog reflecting the actual provider and real workflow
        if provider.is_automated:
            account_info = getattr(provider, "paired_id", None) or getattr(provider, "phone_number_id", None) or "Active Session"
            workflow_desc = (
                "Automated Dispatch Workflow (Unattended - No Browser):\n"
                "1. Messages are transmitted directly via sockets/API without opening WhatsApp Web.\n"
                f"2. Cooldown pacing: {delay_seconds}s pause between contacts.\n"
                "3. Delivery receipts are verified from server transmission acknowledgements."
            )
            mode_desc = f"{provider.name} (Automated Dispatch)"
        else:
            account_info = "Local Web Browser Session"
            workflow_desc = (
                "Manual Review Workflow:\n"
                "1. Each contact's chat will open in WhatsApp Web in your browser.\n"
                "2. You inspect the prefilled message and click Send in WhatsApp Web.\n"
                "3. Click 'Confirm Sent & Next' in this app to advance to the next contact."
            )
            mode_desc = f"{provider.name} (Manual Review)"

        confirm_text = (
            f"Ready to launch campaign:\n\n"
            f"• Campaign Name: {campaign_name}\n"
            f"• Delivery Provider: {provider.name}\n"
            f"• Delivery Mode: {mode_desc}\n"
            f"• Connected Account: {account_info}\n"
            f"• Total Contacts: {len(valid_contacts)}\n"
            f"• Cooldown Delay: {delay_seconds}s between contacts\n"
            f"• Deduplication: {'Campaign Only (Safe Resume)' if not global_dedup else 'Global History Suppress'}\n"
            f"• Message Preview:\n\"{preview_sample}\"\n\n"
            f"{workflow_desc}\n\n"
            f"Start broadcast now?"
        )

        if not messagebox.askyesno("Confirm Broadcast Launch", confirm_text):
            _logger.info("Broadcast start cancelled by user in confirmation dialog.")
            return

        camp_id = f"camp_{int(time.time())}"
        try:
            custom_vars = self.message_editor.get_custom_variables() if hasattr(self.message_editor, "get_custom_variables") else {}
            started = self.controller.start_batch(
                contacts=valid_contacts,
                template=template,
                mode=mode,
                delay_seconds=delay_seconds,
                has_consent=True,
                provider=provider,
                skip_already_sent=skip_dups,
                campaign_id=camp_id,
                campaign_name=campaign_name,
                is_new_campaign=True,
                global_deduplication=global_dedup,
                custom_variables=custom_vars,
            )

            if not started:
                _logger.error("Controller could not start batch.")
                messagebox.showwarning(
                    "Unable to Start", "Broadcast could not be initiated. Check the log for details."
                )
            else:
                try:
                    if hasattr(self, "contact_view"):
                        self.contact_view.refresh_contacts(self.contact_manager.contacts)
                except Exception as ui_err:
                    _logger.warning("Non-fatal UI refresh error after starting batch: %s", ui_err)
        except Exception as e:
            _logger.error("Fatal exception starting batch: %s", e)
            try:
                self.controller.stop()
            except Exception:
                pass
            messagebox.showerror("Error", f"Failed to start broadcast: {e}")

    def _handle_new_campaign(self) -> None:
        """Explicitly reset state and configure a fresh campaign."""
        new_name = f"Campaign {time.strftime('%Y-%m-%d %H:%M')}"
        self.control_panel.set_campaign_name(new_name)
        self.contact_manager.reset_contacts_for_new_campaign()
        try:
            if hasattr(self, "contact_view"):
                self.contact_view.refresh_contacts(self.contact_manager.contacts)
        except Exception as ui_err:
            _logger.warning("Error refreshing contacts on new campaign: %s", ui_err)
        self.control_panel.update_progress(0, len(self.contact_manager.valid_contacts), None)
        self.log_console.append_log(
            f"✨ Initialized new campaign '{new_name}'. Contact queues reset to Pending."
        )

    def _handle_pause(self) -> None:
        _logger.info("Pause requested.")
        self.controller.pause()

    def _handle_resume(self) -> None:
        _logger.info("Resume requested.")
        self.controller.resume()

    def _handle_stop(self) -> None:
        _logger.info("Stop requested.")
        if messagebox.askyesno("Confirm Stop", "Are you sure you want to stop the broadcast?"):
            self.controller.stop()

    def _handle_confirm_sent(self) -> None:
        self.controller.confirm_current_sent()

    def _handle_skip(self) -> None:
        self.controller.skip_current_contact()

    # --- Thread-Safe Event Dispatchers ---
    def _thread_safe_progress_update(
        self, current: int, total: int, contact: Optional[Contact]
    ) -> None:
        try:
            if self.winfo_exists():
                self.after(0, lambda: self._apply_progress_update(current, total, contact))
        except Exception:
            pass

    def _apply_progress_update(
        self, current: int, total: int, contact: Optional[Contact]
    ) -> None:
        try:
            self.control_panel.update_progress(current, total, contact)
            if contact:
                self.contact_view.update_contact_status(contact)
                self.message_editor.update_preview(contact)
        except Exception as e:
            _logger.debug("Error applying progress update to UI: %s", e)

    def _thread_safe_state_change(self, state: ControllerState, note: str) -> None:
        try:
            if self.winfo_exists():
                self.after(0, lambda: self._apply_state_change(state, note))
        except Exception:
            pass

    def _apply_state_change(self, state: ControllerState, note: str) -> None:
        try:
            self.control_panel.set_controller_state(state, note)
            if self.controller.current_contact:
                self.contact_view.update_contact_status(self.controller.current_contact)
        except Exception as e:
            _logger.debug("Error applying state change to UI: %s", e)

    def _thread_safe_log_message(self, message: str) -> None:
        try:
            if self.winfo_exists():
                self.after(0, lambda: self._apply_log_message(message))
        except Exception:
            pass

    def _apply_log_message(self, message: str) -> None:
        try:
            self.log_console.append_log(message)
        except Exception:
            pass
