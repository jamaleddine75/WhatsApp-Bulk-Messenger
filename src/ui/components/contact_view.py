"""Contact list and summary view component."""

from tkinter import ttk
from typing import Callable, List, Optional
import customtkinter as ctk
from src.models import Contact, ImportSummary


class ContactView(ctk.CTkFrame):
    """Component for loading, summarizing, and viewing contacts with consent/suppression statuses."""

    def __init__(
        self,
        master,
        on_import_clicked: Callable[[], None],
        on_contact_selected: Optional[Callable[[Contact], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.on_import_clicked = on_import_clicked
        self.on_contact_selected = on_contact_selected
        self._all_contacts: List[Contact] = []
        self._filtered_contacts: List[Contact] = []

        self._build_ui()

    def _build_ui(self) -> None:
        # Header & Import Button
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(8, 4))

        title_label = ctk.CTkLabel(
            top_bar,
            text="1. Contacts Manager",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        title_label.pack(side="left")

        import_btn = ctk.CTkButton(
            top_bar,
            text="📂 Import CSV",
            command=self.on_import_clicked,
            width=110,
            height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1F6AA5",
            hover_color="#144870",
        )
        import_btn.pack(side="right")

        # Summary Badges Frame (Compact 2-row grid)
        self.stats_frame = ctk.CTkFrame(self, fg_color=("gray90", "gray17"), corner_radius=6)
        self.stats_frame.pack(fill="x", padx=8, pady=3)

        self.lbl_total = self._create_badge(self.stats_frame, "Total: 0", "#607D8B", row=0, col=0)
        self.lbl_valid = self._create_badge(self.stats_frame, "Valid: 0", "#37474F", row=0, col=1)
        self.lbl_eligible = self._create_badge(self.stats_frame, "Eligible: 0", "#2E7D32", row=0, col=2)

        self.lbl_no_consent = self._create_badge(self.stats_frame, "No Consent: 0", "#EF6C00", row=1, col=0)
        self.lbl_suppressed = self._create_badge(self.stats_frame, "Suppressed: 0", "#D84315", row=1, col=1)
        self.lbl_invalid = self._create_badge(self.stats_frame, "Invalid/Dup: 0", "#C62828", row=1, col=2)

        # Filter Tabs
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(fill="x", padx=8, pady=3)

        self.filter_var = ctk.StringVar(value="All")
        filter_seg = ctk.CTkSegmentedButton(
            filter_frame,
            values=["All", "Eligible", "No Consent", "Suppressed", "Invalid"],
            variable=self.filter_var,
            command=self._apply_filter,
            height=26,
            font=ctk.CTkFont(size=11),
        )
        filter_seg.pack(side="left", fill="x", expand=True)

        # Contact Table (ttk.Treeview embedded with compact default row count)
        table_container = ctk.CTkFrame(self, fg_color=("gray95", "gray14"), corner_radius=6)
        table_container.pack(fill="both", expand=True, padx=8, pady=(3, 8))

        columns = ("idx", "name", "phone", "consent", "status", "notes")
        self.tree = ttk.Treeview(
            table_container,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=6,
        )

        self.tree.heading("idx", text="#")
        self.tree.heading("name", text="Recipient Name")
        self.tree.heading("phone", text="Phone (E.164)")
        self.tree.heading("consent", text="Consent")
        self.tree.heading("status", text="Status")
        self.tree.heading("notes", text="Validation / Notes")

        self.tree.column("idx", width=28, anchor="center")
        self.tree.column("name", width=120, anchor="w")
        self.tree.column("phone", width=110, anchor="w")
        self.tree.column("consent", width=85, anchor="center")
        self.tree.column("status", width=95, anchor="center")
        self.tree.column("notes", width=130, anchor="w")

        # Scrollbars
        scrollbar_y = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar_y.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=(3, 0), pady=3)
        scrollbar_y.pack(side="right", fill="y", padx=(0, 3), pady=3)

        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

    def _create_badge(self, parent, text: str, color: str, row: int, col: int) -> ctk.CTkLabel:
        parent.grid_columnconfigure(col, weight=1)
        lbl = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="white",
            fg_color=color,
            corner_radius=5,
            height=20,
        )
        lbl.grid(row=row, column=col, padx=2, pady=2, sticky="ew")
        return lbl

    def set_contacts(self, contacts: List[Contact], summary: ImportSummary) -> None:
        """Update display with newly loaded contacts and summary counts."""
        self._all_contacts = contacts
        self.lbl_total.configure(text=f"Total: {summary.total_rows}")
        self.lbl_valid.configure(text=f"Valid: {summary.valid_count}")
        self.lbl_eligible.configure(text=f"Eligible: {summary.eligible_count}")
        self.lbl_no_consent.configure(text=f"No Consent: {summary.no_consent_count}")
        self.lbl_suppressed.configure(text=f"Suppressed: {summary.suppressed_count}")
        invalid_and_dups = summary.invalid_count + summary.duplicate_count
        self.lbl_invalid.configure(text=f"Invalid/Dup: {invalid_and_dups}")

        self._apply_filter(self.filter_var.get())

    def refresh_contacts(self, contacts: Optional[List[Contact]] = None) -> None:
        """Refresh the contact table rows with current contact states."""
        if contacts is not None:
            self._all_contacts = contacts
        self._apply_filter(self.filter_var.get())

    def update_contact_status(self, contact: Contact) -> None:
        """Update status of a specific contact row in the table."""
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            if values and int(values[0]) == contact.index:
                self.tree.item(
                    item,
                    values=(
                        contact.index,
                        contact.display_name,
                        contact.formatted_phone or contact.raw_phone,
                        self._get_consent_display(contact),
                        contact.status.get_label(),
                        contact.notes,
                    ),
                )
                break

    @staticmethod
    def _get_consent_display(c: Contact) -> str:
        if c.is_suppressed:
            return "Opt-Out"
        if not c.opted_in:
            return "No"
        return "Yes"

    def _apply_filter(self, filter_name: str) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        if filter_name == "Eligible":
            self._filtered_contacts = [c for c in self._all_contacts if c.is_eligible]
        elif filter_name == "No Consent":
            self._filtered_contacts = [c for c in self._all_contacts if c.is_valid and not c.opted_in]
        elif filter_name == "Suppressed":
            self._filtered_contacts = [c for c in self._all_contacts if c.is_suppressed]
        elif filter_name == "Invalid":
            self._filtered_contacts = [c for c in self._all_contacts if not c.is_valid]
        else:
            self._filtered_contacts = list(self._all_contacts)

        for c in self._filtered_contacts:
            self.tree.insert(
                "",
                "end",
                values=(
                    c.index,
                    c.display_name,
                    c.formatted_phone or c.raw_phone,
                    self._get_consent_display(c),
                    c.status.get_label(),
                    c.notes,
                ),
            )

    def _on_row_select(self, _event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        if not values:
            return
        idx = int(values[0])
        for c in self._all_contacts:
            if c.index == idx:
                if self.on_contact_selected:
                    self.on_contact_selected(c)
                break
