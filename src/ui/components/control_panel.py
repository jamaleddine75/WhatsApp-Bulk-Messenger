"""Control panel component for managing WhatsApp Web and piwapp dispatch sessions."""

from typing import Callable, Optional
import customtkinter as ctk
from src.config import DEFAULT_DELAY_SECONDS, MAX_DELAY_SECONDS, MIN_DELAY_SECONDS
from src.diagnostics import get_logger
from src.models import Contact
from src.sender_controller import ControllerState, DispatchMode

_logger = get_logger()


class ControlPanel(ctk.CTkFrame):
    """Panel containing progress indicators, pacing controls, provider selection, and execution buttons."""

    def __init__(
        self,
        master,
        on_start: Callable[[], None],
        on_pause: Callable[[], None],
        on_resume: Callable[[], None],
        on_stop: Callable[[], None],
        on_confirm_sent: Callable[[], None],
        on_skip: Callable[[], None],
        on_configure_api: Optional[Callable[[], None]] = None,
        on_test_connection: Optional[Callable[[], None]] = None,
        on_view_history: Optional[Callable[[], None]] = None,
        on_piwapp_connect: Optional[Callable[[], None]] = None,
        on_piwapp_disconnect: Optional[Callable[[], None]] = None,
        on_provider_changed: Optional[Callable[[str], None]] = None,
        on_new_campaign: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_stop = on_stop
        self.on_confirm_sent = on_confirm_sent
        self.on_skip = on_skip
        self.on_configure_api = on_configure_api
        self.on_test_connection = on_test_connection
        self.on_view_history = on_view_history
        self.on_piwapp_connect = on_piwapp_connect
        self.on_piwapp_disconnect = on_piwapp_disconnect
        self.on_provider_changed = on_provider_changed
        self.on_new_campaign = on_new_campaign

        self.mode_var = ctk.StringVar(value="piwapp (Experimental Automation - Default)")
        self.skip_duplicates_var = ctk.BooleanVar(value=True)
        self.global_dedup_var = ctk.BooleanVar(value=False)

        self._build_ui()

    def _build_ui(self) -> None:
        # Title and History Button
        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", padx=8, pady=(8, 4))

        title_lbl = ctk.CTkLabel(
            top_row,
            text="3. Broadcast & Pacing Controls",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        title_lbl.pack(side="left")

        if self.on_view_history:
            btn_history = ctk.CTkButton(
                top_row,
                text="📊 History & Audit",
                command=self.on_view_history,
                width=115,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="#37474F",
                hover_color="#263238",
            )
            btn_history.pack(side="right")

        # Progress Information Card
        prog_card = ctk.CTkFrame(self, fg_color=("gray90", "gray17"), corner_radius=6)
        prog_card.pack(fill="x", padx=8, pady=3)

        # Status badge and current contact info
        status_row = ctk.CTkFrame(prog_card, fg_color="transparent")
        status_row.pack(fill="x", padx=8, pady=(6, 3))

        self.lbl_status = ctk.CTkLabel(
            status_row,
            text="STATUS: READY",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="white",
            fg_color="#455A64",
            corner_radius=5,
            width=140,
            height=24,
        )
        self.lbl_status.pack(side="left")

        self.lbl_current_contact = ctk.CTkLabel(
            status_row,
            text="Current: None",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        )
        self.lbl_current_contact.pack(side="left", padx=(8, 0), fill="x", expand=True)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(prog_card, height=8)
        self.progress_bar.pack(fill="x", padx=8, pady=3)
        self.progress_bar.set(0.0)

        # Progress percentage label
        self.lbl_progress_text = ctk.CTkLabel(
            prog_card,
            text="Progress: 0 / 0 (0%) • 0 Remaining",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.lbl_progress_text.pack(anchor="w", padx=8, pady=(1, 5))

        # --- PRIMARY ACTION BUTTONS (Start, Pause, Resume, Stop) ---
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=8, pady=(3, 4))

        self.btn_start = ctk.CTkButton(
            btn_bar,
            text="▶️ Start Broadcast",
            command=self._on_start_clicked,
            fg_color="#1E88E5",
            hover_color="#1565C0",
            width=130,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.btn_start.pack(side="left", padx=(0, 4))

        self.btn_pause = ctk.CTkButton(
            btn_bar,
            text="⏸️ Pause",
            command=self.on_pause,
            fg_color="#757575",
            hover_color="#616161",
            width=75,
            height=30,
            font=ctk.CTkFont(size=11),
            state="disabled",
        )
        self.btn_pause.pack(side="left", padx=2)

        self.btn_resume = ctk.CTkButton(
            btn_bar,
            text="⏯️ Resume",
            command=self.on_resume,
            fg_color="#00897B",
            hover_color="#00695C",
            width=80,
            height=30,
            font=ctk.CTkFont(size=11),
            state="disabled",
        )
        self.btn_resume.pack(side="left", padx=2)

        self.btn_stop = ctk.CTkButton(
            btn_bar,
            text="⏹️ Stop",
            command=self.on_stop,
            fg_color="#D32F2F",
            hover_color="#B71C1C",
            width=75,
            height=30,
            font=ctk.CTkFont(size=11),
            state="disabled",
        )
        self.btn_stop.pack(side="left", padx=2)

        # Provider Selector Frame
        provider_frame = ctk.CTkFrame(self, fg_color="transparent")
        provider_frame.pack(fill="x", padx=8, pady=(2, 2))

        lbl_provider = ctk.CTkLabel(
            provider_frame,
            text="Delivery Provider:",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        lbl_provider.pack(side="left", padx=(0, 6))

        self.combo_provider = ctk.CTkComboBox(
            provider_frame,
            values=[
                "piwapp (Experimental Automation - Default)",
                "WhatsApp Web (Manual Review Fallback)",
            ],
            variable=self.mode_var,
            width=290,
            height=26,
            font=ctk.CTkFont(size=11),
            state="readonly",
            command=self._on_provider_selection_changed,
        )
        self.combo_provider.pack(side="left", fill="x", expand=True)

        # piwapp Connection Controls Frame (Visible by default for piwapp)
        self.piwapp_frame = ctk.CTkFrame(self, fg_color=("#E8F5E9", "#1B2E24"), corner_radius=6)
        self.piwapp_frame.pack(fill="x", padx=8, pady=3)

        piwapp_top = ctk.CTkFrame(self.piwapp_frame, fg_color="transparent")
        piwapp_top.pack(fill="x", padx=8, pady=(6, 2))

        self.lbl_piwapp_status = ctk.CTkLabel(
            piwapp_top,
            text="piwapp: Disconnected",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#C62828",
        )
        self.lbl_piwapp_status.pack(side="left")

        self.btn_piwapp_connect = ctk.CTkButton(
            piwapp_top,
            text="🔗 Connect / Pair QR",
            command=self._on_piwapp_connect_clicked,
            width=135,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color="#2E7D32",
            hover_color="#1B5E20",
        )
        self.btn_piwapp_connect.pack(side="right", padx=(4, 0))

        self.btn_piwapp_disconnect = ctk.CTkButton(
            piwapp_top,
            text="Disconnect",
            command=self._on_piwapp_disconnect_clicked,
            width=80,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color="#757575",
            hover_color="#616161",
            state="disabled",
        )
        self.btn_piwapp_disconnect.pack(side="right")

        lbl_piwapp_hint = ctk.CTkLabel(
            self.piwapp_frame,
            text="⚠️ Pure-Python automation: Pairs directly via QR scan. Use responsibly with opted-in contacts.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        )
        lbl_piwapp_hint.pack(anchor="w", padx=8, pady=(0, 4))

        # Campaign Metadata Frame (Campaign Name & New Campaign Trigger)
        meta_frame = ctk.CTkFrame(self, fg_color="transparent")
        meta_frame.pack(fill="x", padx=8, pady=(2, 2))

        self.entry_camp_name = ctk.CTkEntry(
            meta_frame,
            placeholder_text="Campaign Name (optional, e.g. Customer Update)",
            height=26,
            font=ctk.CTkFont(size=11),
        )
        self.entry_camp_name.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_new_campaign = ctk.CTkButton(
            meta_frame,
            text="✨ New Campaign",
            command=self._on_new_campaign_clicked,
            width=115,
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#00695C",
            hover_color="#004D40",
        )
        self.btn_new_campaign.pack(side="right")

        # Pacing Slider Frame & Deduplication Controls
        slider_frame = ctk.CTkFrame(self, fg_color="transparent")
        slider_frame.pack(fill="x", padx=8, pady=(2, 2))

        lbl_delay = ctk.CTkLabel(slider_frame, text="Delay Cooldown:", font=ctk.CTkFont(size=11))
        lbl_delay.pack(side="left", padx=(0, 4))

        self.delay_slider = ctk.CTkSlider(
            slider_frame,
            from_=MIN_DELAY_SECONDS,
            to=MAX_DELAY_SECONDS,
            number_of_steps=MAX_DELAY_SECONDS - MIN_DELAY_SECONDS,
            width=110,
            command=self._on_slider_moved,
        )
        self.delay_slider.set(DEFAULT_DELAY_SECONDS)
        self.delay_slider.pack(side="left")

        self.lbl_slider_val = ctk.CTkLabel(
            slider_frame,
            text=f"{DEFAULT_DELAY_SECONDS}s",
            width=28,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.lbl_slider_val.pack(side="left", padx=2)

        # Global deduplication checkbox
        self.chk_global_dedup = ctk.CTkCheckBox(
            slider_frame,
            text="Global history suppress",
            variable=self.global_dedup_var,
            font=ctk.CTkFont(size=10),
            checkbox_height=16,
            checkbox_width=16,
        )
        self.chk_global_dedup.pack(side="right", padx=(4, 0))

        # Resume / Campaign-scoped deduplication checkbox
        self.chk_skip_dups = ctk.CTkCheckBox(
            slider_frame,
            text="Deduplicate campaign",
            variable=self.skip_duplicates_var,
            font=ctk.CTkFont(size=10),
            checkbox_height=16,
            checkbox_width=16,
        )
        self.chk_skip_dups.pack(side="right")

        # Human-in-the-Loop Confirmation Bar (WhatsApp Web Review, hidden when piwapp is active)
        self.review_frame = ctk.CTkFrame(self, fg_color=("#E3F2FD", "#1A2E3D"), corner_radius=6)
        # Not packed by default (packed when WhatsApp Web is chosen)

        self.review_title = ctk.CTkLabel(
            self.review_frame,
            text="👉 Review each chat in WhatsApp Web. Click 'Confirm Sent & Next' after sending, or 'Skip Contact'.",
            font=ctk.CTkFont(size=11),
            text_color=("#0D47A1", "#90CAF9"),
            wraplength=480,
            justify="left",
        )
        self.review_title.pack(anchor="w", padx=8, pady=(4, 2))

        review_btns = ctk.CTkFrame(self.review_frame, fg_color="transparent")
        review_btns.pack(fill="x", padx=8, pady=(1, 5))

        self.btn_confirm = ctk.CTkButton(
            review_btns,
            text="✅ Confirm Sent & Next",
            command=self.on_confirm_sent,
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
        )
        self.btn_confirm.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_skip = ctk.CTkButton(
            review_btns,
            text="⏭️ Skip Contact",
            command=self.on_skip,
            fg_color="#F57C00",
            hover_color="#E65100",
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
        )
        self.btn_skip.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Consent Checkbox
        self.consent_var = ctk.BooleanVar(value=False)
        self.chk_consent = ctk.CTkCheckBox(
            self,
            text="I certify that all recipients gave explicit consent to receive these messages.",
            variable=self.consent_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#1B5E20", "#81C784"),
            checkbox_height=18,
            checkbox_width=18,
        )
        self.chk_consent.pack(anchor="w", padx=8, pady=(4, 6))

    def _on_provider_selection_changed(self, choice: str) -> None:
        self.mode_var.set(choice)
        if "piwapp" in choice.lower():
            self.piwapp_frame.pack(fill="x", padx=8, pady=3, after=self.combo_provider.master)
            self.review_frame.pack_forget()
        else:
            self.piwapp_frame.pack_forget()
            self.review_frame.pack(fill="x", padx=8, pady=3, after=self.chk_skip_dups.master)

        if self.on_provider_changed:
            self.on_provider_changed(choice)

    def _on_new_campaign_clicked(self) -> None:
        _logger.info("ControlPanel: New Campaign button clicked.")
        if self.on_new_campaign:
            self.on_new_campaign()

    def _on_piwapp_connect_clicked(self) -> None:
        if self.on_piwapp_connect:
            self.on_piwapp_connect()

    def _on_piwapp_disconnect_clicked(self) -> None:
        if self.on_piwapp_disconnect:
            self.on_piwapp_disconnect()

    def update_piwapp_status(
        self, status_text: str, is_connected: bool, paired_id: Optional[str] = None
    ) -> None:
        """Update piwapp badge and button enable states."""
        if is_connected:
            disp_id = paired_id or "Active Session"
            self.lbl_piwapp_status.configure(
                text=f"piwapp: Connected ({disp_id})", text_color="#2E7D32"
            )
            self.btn_piwapp_connect.configure(state="disabled")
            self.btn_piwapp_disconnect.configure(state="normal")
        else:
            self.lbl_piwapp_status.configure(
                text=f"piwapp: {status_text}", text_color="#C62828"
            )
            self.btn_piwapp_connect.configure(state="normal")
            self.btn_piwapp_disconnect.configure(state="disabled")

    def _on_start_clicked(self) -> None:
        _logger.info("ControlPanel: Start button clicked by user.")
        self.on_start()

    def highlight_consent(self) -> None:
        """Visual pulse or indicator if consent is missing."""
        self.chk_consent.configure(text_color="#D32F2F")
        self.after(1500, lambda: self.chk_consent.configure(text_color=("#1B5E20", "#81C784")))

    def _on_slider_moved(self, val: float) -> None:
        seconds = int(val)
        self.lbl_slider_val.configure(text=f"{seconds}s")

    def get_selected_delay(self) -> int:
        return int(self.delay_slider.get())

    def should_skip_already_sent(self) -> bool:
        return self.skip_duplicates_var.get()

    def should_global_dedup(self) -> bool:
        return bool(self.global_dedup_var.get())

    def get_selected_mode(self) -> DispatchMode:
        val = ""
        if hasattr(self, "combo_provider") and self.combo_provider:
            val = self.combo_provider.get() or ""
        if not val and hasattr(self, "mode_var"):
            val = self.mode_var.get() or ""
        if "piwapp" in val.lower():
            return DispatchMode.PIWAPP_AUTOMATED
        return DispatchMode.WEB_MANUAL_REVIEW

    def set_selected_mode(self, mode: DispatchMode) -> None:
        choice = (
            "piwapp (Experimental Automation - Default)"
            if mode == DispatchMode.PIWAPP_AUTOMATED
            else "WhatsApp Web (Manual Review Fallback)"
        )
        self.mode_var.set(choice)
        if hasattr(self, "combo_provider") and self.combo_provider:
            self.combo_provider.set(choice)
        self._on_provider_selection_changed(choice)

    def get_campaign_name(self) -> str:
        return self.entry_camp_name.get().strip()

    def set_campaign_name(self, name: str) -> None:
        self.entry_camp_name.delete(0, "end")
        self.entry_camp_name.insert(0, name)

    def get_template_name(self) -> str:
        return ""

    def is_consent_given(self) -> bool:
        return self.consent_var.get()

    def update_progress(self, current: int, total: int, contact: Optional[Contact]) -> None:
        """Update progress bar, counts, and contact label."""
        if total <= 0:
            pct = 0.0
            remaining = 0
        else:
            pct = current / total
            remaining = max(0, total - current)

        self.progress_bar.set(pct)
        pct_display = int(pct * 100)
        self.lbl_progress_text.configure(
            text=f"Progress: {current} / {total} ({pct_display}%) • {remaining} Remaining"
        )

        if contact:
            self.lbl_current_contact.configure(
                text=f"[{current}/{total}] {contact.display_name} ({contact.formatted_phone or contact.raw_phone})"
            )
        elif current == total and total > 0:
            self.lbl_current_contact.configure(text="Batch Complete! All contacts processed.")
        elif total > 0 and current == 0:
            self.lbl_current_contact.configure(text=f"Ready to start ({total} contacts in queue)")
        else:
            self.lbl_current_contact.configure(text="Current: None")

    def set_controller_state(self, state: ControllerState, note: str = "") -> None:
        """Update button enable states and color badges based on state machine."""
        is_manual = self.get_selected_mode() == DispatchMode.WEB_MANUAL_REVIEW

        if state == ControllerState.IDLE:
            self.lbl_status.configure(text="STATUS: READY", fg_color="#455A64")
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled")
            self.btn_resume.configure(state="disabled")
            self.btn_stop.configure(state="disabled")
            self.btn_confirm.configure(state="disabled")
            self.btn_skip.configure(state="disabled")

        elif state == ControllerState.RUNNING:
            self.lbl_status.configure(text="STATUS: RUNNING", fg_color="#1976D2")
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="normal")
            self.btn_resume.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self.btn_confirm.configure(state="disabled")
            self.btn_skip.configure(state="disabled")

        elif state == ControllerState.AWAITING_CONFIRMATION:
            self.lbl_status.configure(text="STATUS: REVIEW CHAT", fg_color="#F57C00")
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="disabled")
            self.btn_resume.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            if is_manual:
                self.btn_confirm.configure(state="normal")
                self.btn_skip.configure(state="normal")

        elif state == ControllerState.PAUSED:
            self.lbl_status.configure(text="STATUS: PAUSED", fg_color="#757575")
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="disabled")
            self.btn_resume.configure(state="normal")
            self.btn_stop.configure(state="normal")
            self.btn_confirm.configure(state="disabled")
            self.btn_skip.configure(state="disabled")

        elif state in (ControllerState.STOPPED, ControllerState.FINISHED):
            color = "#2E7D32" if state == ControllerState.FINISHED else "#D32F2F"
            self.lbl_status.configure(text=f"STATUS: {state.value}", fg_color=color)
            self.btn_start.configure(state="normal")
            self.btn_pause.configure(state="disabled")
            self.btn_resume.configure(state="disabled")
            self.btn_stop.configure(state="disabled")
            self.btn_confirm.configure(state="disabled")
            self.btn_skip.configure(state="disabled")
