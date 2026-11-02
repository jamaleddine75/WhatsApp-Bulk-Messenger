"""Message editor and template preview component with advanced template and custom variable management."""

from datetime import datetime
import re
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Optional
import customtkinter as ctk

from src.diagnostics import get_logger
from src.message_engine import MessageEngine
from src.models import Contact
from src.template_manager import MessageTemplate, TemplateManager

_logger = get_logger()

STANDARD_VARIABLES = ["{name}", "{phone}", "{clean_phone}"]


class MessageEditor(ctk.CTkFrame):
    """Component for composing message templates with variable chips, template management, and live preview."""

    def __init__(
        self,
        master,
        message_engine: MessageEngine,
        template_manager: Optional[TemplateManager] = None,
        on_template_changed: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.message_engine = message_engine
        self.template_manager = template_manager or TemplateManager()
        self.on_template_changed = on_template_changed

        self._current_template_name: str = "Untitled Template"
        self._custom_variables: Dict[str, str] = {}  # var_name -> default_value
        self._current_preview_contact: Optional[Contact] = None
        self._is_dirty: bool = False

        self._chip_buttons: List[ctk.CTkButton] = []

        self._build_ui()
        self._load_initial_template()

    # --- UI Layout Construction ---
    def _build_ui(self) -> None:
        # Header Row: Title & Active Template Badge
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=8, pady=(6, 2))

        title_label = ctk.CTkLabel(
            top_bar,
            text="2. Message Customization",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        title_label.pack(side="left")

        # Quick Preset / Saved Template Dropdown
        self.preset_combo = ctk.CTkComboBox(
            top_bar,
            values=self._get_template_names_list(),
            command=self._on_preset_dropdown_selected,
            width=220,
            height=26,
            font=ctk.CTkFont(size=11),
        )
        self.preset_combo.pack(side="right")
        self.preset_combo.set("Select Template...")

        # Active Template Status Indicator
        self.lbl_active_template = ctk.CTkLabel(
            self,
            text=f"Template: {self._current_template_name}",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color="#4CAF50",
            anchor="w",
        )
        self.lbl_active_template.pack(fill="x", padx=10, pady=(0, 2))

        # --- Template Management Toolbar ---
        toolbar = ctk.CTkFrame(self, fg_color=("gray90", "gray18"), corner_radius=6)
        toolbar.pack(fill="x", padx=8, pady=(2, 4))
        toolbar.grid_columnconfigure((0, 1, 2), weight=1)

        # Row 1 of toolbar
        self.btn_new = ctk.CTkButton(
            toolbar,
            text="➕ New Template",
            command=self._handle_new_template,
            height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1E88E5",
            hover_color="#1565C0",
        )
        self.btn_new.grid(row=0, column=0, padx=2, pady=2, sticky="ew")

        self.btn_add_var = ctk.CTkButton(
            toolbar,
            text="➕ Add Variable",
            command=self._open_add_variable_dialog,
            height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#00897B",
            hover_color="#00695C",
        )
        self.btn_add_var.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

        self.btn_save = ctk.CTkButton(
            toolbar,
            text="💾 Save Template",
            command=self._handle_save_template,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
        )
        self.btn_save.grid(row=0, column=2, padx=2, pady=2, sticky="ew")

        # Row 2 of toolbar
        self.btn_save_as = ctk.CTkButton(
            toolbar,
            text="💾 Save As...",
            command=self._open_save_as_dialog,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
        )
        self.btn_save_as.grid(row=1, column=0, padx=2, pady=2, sticky="ew")

        self.btn_load = ctk.CTkButton(
            toolbar,
            text="📂 Load Template",
            command=self._open_load_template_dialog,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color=("gray75", "gray28"),
            hover_color=("gray65", "gray35"),
        )
        self.btn_load.grid(row=1, column=1, padx=2, pady=2, sticky="ew")

        self.btn_delete = ctk.CTkButton(
            toolbar,
            text="🗑️ Delete Template",
            command=self._handle_delete_template,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color=("#E57373", "#B71C1C"),
            hover_color=("#EF5350", "#C62828"),
        )
        self.btn_delete.grid(row=1, column=2, padx=2, pady=2, sticky="ew")

        # --- Dynamic Variable Placeholders Chips Bar ---
        self.chips_container = ctk.CTkFrame(self, fg_color="transparent")
        self.chips_container.pack(fill="x", padx=8, pady=(1, 3))

        hint_lbl = ctk.CTkLabel(
            self.chips_container,
            text="Insert variable:",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color="gray",
        )
        hint_lbl.pack(side="left", padx=(0, 4))

        self.chips_scroll = ctk.CTkFrame(self.chips_container, fg_color="transparent")
        self.chips_scroll.pack(side="left", fill="x", expand=True)

        self._rebuild_variable_chips()

        # --- Tabview for Message Editor & Live Preview ---
        self.tabs = ctk.CTkTabview(self, height=130)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        tab_edit = self.tabs.add("✏️ Message Template")
        tab_preview = self.tabs.add("👁️ Live Preview")

        # Editor Textbox
        self.textbox = ctk.CTkTextbox(
            tab_edit,
            height=95,
            font=ctk.CTkFont(size=12),
            wrap="word",
        )
        self.textbox.pack(fill="both", expand=True, padx=3, pady=3)
        self.textbox.bind("<KeyRelease>", self._on_text_modified)

        # Preview Textbox (read-only)
        self.preview_box = ctk.CTkTextbox(
            tab_preview,
            height=95,
            font=ctk.CTkFont(size=12),
            wrap="word",
            state="disabled",
            fg_color=("gray92", "gray16"),
        )
        self.preview_box.pack(fill="both", expand=True, padx=3, pady=3)

    def _get_template_names_list(self) -> List[str]:
        names = self.template_manager.list_templates()
        return names if names else ["(No Saved Templates)"]

    def _load_initial_template(self) -> None:
        """Load default or first available saved template on startup."""
        templates = self.template_manager.list_templates()
        if templates:
            first = self.template_manager.get_template(templates[0])
            if first:
                self.load_template(first)
                return

        # Fallback starter template
        default_tpl = MessageTemplate(
            name="Default Welcome",
            body="Bonjour {name},\n\nMerci pour votre confiance. Votre demande a bien été enregistrée.\n\nBien cordialement,\nL'équipe",
            custom_variables={},
        )
        self.load_template(default_tpl)

    def _update_template_badge(self) -> None:
        star = " *" if self._is_dirty else ""
        self.lbl_active_template.configure(text=f"Template: {self._current_template_name}{star}")
        if self._current_template_name in self.template_manager.list_templates():
            self.preset_combo.set(self._current_template_name)
        else:
            self.preset_combo.set("Select Template...")

    # --- Variable Chips Management ---
    def _rebuild_variable_chips(self) -> None:
        """Clear and re-render buttons for built-in and custom variables."""
        for btn in self._chip_buttons:
            try:
                btn.destroy()
            except Exception:
                pass
        self._chip_buttons.clear()

        # 1. Standard Built-in Variables
        for var_name in STANDARD_VARIABLES:
            btn = ctk.CTkButton(
                self.chips_scroll,
                text=var_name,
                width=58,
                height=20,
                font=ctk.CTkFont(size=10),
                fg_color=("gray80", "gray25"),
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray35"),
                command=lambda v=var_name: self.insert_variable_at_cursor(v),
            )
            btn.pack(side="left", padx=2)
            self._chip_buttons.append(btn)

        # 2. Custom Template Variables
        for var_name, default_val in self._custom_variables.items():
            formatted = f"{{{var_name}}}"
            disp_text = f"✨ {formatted}"
            btn = ctk.CTkButton(
                self.chips_scroll,
                text=disp_text,
                width=65,
                height=20,
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=("#C8E6C9", "#1B5E20"),
                text_color=("#1B5E20", "#E8F5E9"),
                hover_color=("#A5D6A7", "#2E7D32"),
                command=lambda v=formatted: self.insert_variable_at_cursor(v),
            )
            btn.pack(side="left", padx=2)
            self._chip_buttons.append(btn)

    def insert_variable_at_cursor(self, placeholder: str) -> None:
        """Insert placeholder variable at the current cursor position."""
        clean = placeholder.strip()
        if not (clean.startswith("{") and clean.endswith("}")):
            clean = f"{{{clean}}}"
        self.textbox.insert("insert", clean)
        self._on_text_modified()

    def insert_text_at_cursor(self, text: str) -> None:
        """Insert arbitrary text at the current cursor position."""
        self.textbox.insert("insert", text)
        self._on_text_modified()

    # --- Public API for Controller & Integration ---
    def get_custom_variables(self) -> Dict[str, str]:
        """Return dict of defined custom variables and their default fallback values."""
        return dict(self._custom_variables)

    def set_custom_variables(self, variables: Dict[str, str]) -> None:
        """Set custom variables dict, refresh UI chips, and update preview."""
        self._custom_variables = dict(variables)
        self._rebuild_variable_chips()
        self.update_preview(self._current_preview_contact)

    def get_template_text(self) -> str:
        return self.textbox.get("1.0", "end-1c")

    def set_template_text(self, text: str) -> None:
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self._is_dirty = False
        self._update_template_badge()
        self.update_preview(self._current_preview_contact)
        if self.on_template_changed:
            self.on_template_changed(text)

    def load_template(self, template: MessageTemplate) -> None:
        """Load a MessageTemplate into the editor and preview."""
        self._current_template_name = template.name
        self._custom_variables = dict(template.custom_variables)
        self._is_dirty = False
        self.set_template_text(template.body)
        self._rebuild_variable_chips()
        self._update_template_badge()

    # --- Live Preview Engine ---
    def update_preview(self, contact: Optional[Contact]) -> None:
        """Update live preview box with contact's real details or sample contact."""
        self._current_preview_contact = contact
        template = self.get_template_text()

        # Sample contact fallback if no contact imported/selected yet
        target = contact
        is_sample = False
        if not target:
            target = Contact(
                index=0,
                raw_phone="0661123456",
                clean_phone="212661123456",
                formatted_phone="+212 661-123456",
                name="Karim Tazi",
                extra_fields={"city": "Casablanca", "product": "Formation Python", "price": "500"},
            )
            is_sample = True

        preview_text = self.message_engine.personalize_message(
            template, target, custom_variables=self._custom_variables
        )
        missing_vars = self.message_engine.get_missing_variables(
            template, target if not is_sample else None, custom_variables=self._custom_variables
        )

        header_title = (
            f"--- [Sample Preview] {target.display_name} ({target.formatted_phone or target.raw_phone}) ---"
            if is_sample
            else f"--- Preview for: {target.display_name} ({target.formatted_phone or target.raw_phone}) ---"
        )

        warning_section = ""
        if missing_vars:
            vars_list = ", ".join(f"{{{v}}}" for v in missing_vars)
            warning_section = (
                f"\n⚠️ WARNING: The following variable(s) have no value: {vars_list}\n"
                f"   (Ensure corresponding CSV columns exist or define default values via '➕ Add Variable'.)\n"
            )

        full_preview = f"{header_title}\n{warning_section}\n{preview_text}"

        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", "end")
        self.preview_box.insert("1.0", full_preview)
        self.preview_box.configure(state="disabled")

    def _on_text_modified(self, _event=None) -> None:
        self._is_dirty = True
        self._update_template_badge()
        text = self.get_template_text()
        self.update_preview(self._current_preview_contact)
        if self.on_template_changed:
            self.on_template_changed(text)

    def _on_preset_dropdown_selected(self, preset_name: str) -> None:
        if preset_name and preset_name != "(No Saved Templates)" and preset_name != "Select Template...":
            tpl = self.template_manager.get_template(preset_name)
            if tpl:
                self.load_template(tpl)

    # --- Toolbar Actions ---
    def _handle_new_template(self) -> None:
        """Create a fresh, blank template."""
        if self._is_dirty:
            if not messagebox.askyesno(
                "New Template",
                "You have unsaved changes in the current template. Create a new template anyway?",
            ):
                return

        self._current_template_name = "Untitled Template"
        self._custom_variables.clear()
        self._is_dirty = False
        self.set_template_text("")
        self._rebuild_variable_chips()
        self._update_template_badge()

    def _handle_save_template(self) -> None:
        """Save current template; prompts for name if unsaved."""
        if self._current_template_name == "Untitled Template" or not self.template_manager.get_template(
            self._current_template_name
        ):
            self._open_save_as_dialog()
            return

        tpl = MessageTemplate(
            name=self._current_template_name,
            body=self.get_template_text(),
            custom_variables=dict(self._custom_variables),
        )
        ok, msg = self.template_manager.save_template(tpl, overwrite=True)
        if ok:
            self._is_dirty = False
            self._update_template_badge()
            self._refresh_preset_dropdown()
            messagebox.showinfo("Template Saved", f"Template '{self._current_template_name}' saved successfully.")
        else:
            messagebox.showerror("Save Failed", msg)

    def _open_save_as_dialog(self) -> None:
        """Modal dialog to save template under a specified name."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Save Template As")
        dialog.geometry("380x190")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Save Template As",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=20, pady=(15, 6), anchor="w")

        ctk.CTkLabel(
            dialog,
            text="Enter template name:",
            font=ctk.CTkFont(size=11),
        ).pack(padx=20, pady=(2, 2), anchor="w")

        entry_name = ctk.CTkEntry(dialog, width=320, placeholder_text="e.g. Ramadan Offer 2026")
        entry_name.pack(padx=20, pady=(2, 10))
        if self._current_template_name != "Untitled Template":
            entry_name.insert(0, f"{self._current_template_name} (Copy)")
        entry_name.focus()

        def do_save():
            name = entry_name.get().strip()
            if not name:
                messagebox.showwarning("Validation Error", "Template name cannot be empty.", parent=dialog)
                return

            # Check if name exists
            if name in self.template_manager.list_templates():
                if not messagebox.askyesno(
                    "Confirm Overwrite",
                    f"A template named '{name}' already exists. Overwrite it?",
                    parent=dialog,
                ):
                    return

            tpl = MessageTemplate(
                name=name,
                body=self.get_template_text(),
                custom_variables=dict(self._custom_variables),
            )
            ok, msg = self.template_manager.save_template(tpl, overwrite=True)
            if ok:
                self._current_template_name = name
                self._is_dirty = False
                self._update_template_badge()
                self._refresh_preset_dropdown()
                dialog.destroy()
                messagebox.showinfo("Template Saved", f"Template '{name}' saved successfully.")
            else:
                messagebox.showerror("Save Failed", msg, parent=dialog)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(6, 12))

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=dialog.destroy,
            width=80,
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray90"),
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_row,
            text="💾 Save",
            command=do_save,
            width=90,
            fg_color="#1E88E5",
            hover_color="#1565C0",
        ).pack(side="right")

    def _open_load_template_dialog(self) -> None:
        """Modal dialog to select, preview, and load saved templates."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Load Saved Template")
        dialog.geometry("520x420")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="Saved Message Templates",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=16, pady=(12, 4), anchor="w")

        # Table showing saved templates
        tree_frame = ctk.CTkFrame(dialog, fg_color=("gray95", "gray14"))
        tree_frame.pack(fill="both", expand=True, padx=16, pady=(4, 6))

        cols = ("name", "variables", "updated")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=7)
        tree.heading("name", text="Template Name")
        tree.heading("variables", text="Custom Variables")
        tree.heading("updated", text="Last Modified")

        tree.column("name", width=220)
        tree.column("variables", width=120)
        tree.column("updated", width=140)
        tree.pack(fill="both", expand=True)

        # Preview box below list
        preview_label = ctk.CTkLabel(
            dialog, text="Template Content Preview:", font=ctk.CTkFont(size=11, weight="bold")
        )
        preview_label.pack(padx=16, pady=(2, 2), anchor="w")

        txt_preview = ctk.CTkTextbox(dialog, height=80, font=ctk.CTkFont(size=11), wrap="word")
        txt_preview.pack(fill="x", padx=16, pady=(0, 8))
        txt_preview.configure(state="disabled")

        def populate_tree():
            for item in tree.get_children():
                tree.delete(item)
            for tpl_name in self.template_manager.list_templates():
                tpl = self.template_manager.get_template(tpl_name)
                if tpl:
                    var_count = len(tpl.custom_variables)
                    var_desc = f"{var_count} var(s)" if var_count else "None"
                    dt_str = tpl.updated_at[:16].replace("T", " ") if tpl.updated_at else "-"
                    tree.insert("", "end", iid=tpl_name, values=(tpl_name, var_desc, dt_str))

        populate_tree()

        def on_tree_select(_event):
            selected = tree.selection()
            if not selected:
                return
            tpl_name = selected[0]
            tpl = self.template_manager.get_template(tpl_name)
            if tpl:
                txt_preview.configure(state="normal")
                txt_preview.delete("1.0", "end")
                vars_info = (
                    f"[Custom Variables: {', '.join(tpl.custom_variables.keys())}]\n\n"
                    if tpl.custom_variables
                    else ""
                )
                txt_preview.insert("1.0", vars_info + tpl.body)
                txt_preview.configure(state="disabled")

        tree.bind("<<TreeviewSelect>>", on_tree_select)

        def do_load():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Select Template", "Please select a template to load.", parent=dialog)
                return
            tpl_name = selected[0]
            tpl = self.template_manager.get_template(tpl_name)
            if tpl:
                self.load_template(tpl)
                dialog.destroy()

        def do_delete_from_dialog():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Select Template", "Please select a template to delete.", parent=dialog)
                return
            tpl_name = selected[0]
            if messagebox.askyesno(
                "Confirm Delete",
                f"Are you sure you want to permanently delete template '{tpl_name}'?",
                parent=dialog,
            ):
                self.template_manager.delete_template(tpl_name)
                populate_tree()
                txt_preview.configure(state="normal")
                txt_preview.delete("1.0", "end")
                txt_preview.configure(state="disabled")
                self._refresh_preset_dropdown()

        tree.bind("<Double-1>", lambda _e: do_load())

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 12))

        ctk.CTkButton(
            btn_row,
            text="🗑️ Delete",
            command=do_delete_from_dialog,
            width=80,
            fg_color=("#E57373", "#B71C1C"),
            hover_color=("#EF5350", "#C62828"),
        ).pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=dialog.destroy,
            width=80,
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray90"),
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_row,
            text="📂 Load Template",
            command=do_load,
            width=110,
            fg_color="#1E88E5",
            hover_color="#1565C0",
        ).pack(side="right")

    def _handle_delete_template(self) -> None:
        """Delete currently loaded template after explicit confirmation."""
        if self._current_template_name not in self.template_manager.list_templates():
            messagebox.showinfo(
                "Delete Template",
                f"Template '{self._current_template_name}' has not been saved to disk.",
            )
            return

        if not messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete template '{self._current_template_name}'? This cannot be undone.",
        ):
            return

        ok, msg = self.template_manager.delete_template(self._current_template_name)
        if ok:
            messagebox.showinfo("Template Deleted", msg)
            self._handle_new_template()
            self._refresh_preset_dropdown()
        else:
            messagebox.showerror("Delete Failed", msg)

    # --- Custom Variable Dialog ---
    def _open_add_variable_dialog(self) -> None:
        """Modal dialog to define a new custom variable with validation."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Custom Variable")
        dialog.geometry("380x250")
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text="➕ Create Custom Variable",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=20, pady=(15, 4), anchor="w")

        ctk.CTkLabel(
            dialog,
            text="Variable name (e.g. product, price, city):",
            font=ctk.CTkFont(size=11),
        ).pack(padx=20, pady=(4, 2), anchor="w")

        entry_name = ctk.CTkEntry(dialog, width=320, placeholder_text="product")
        entry_name.pack(padx=20, pady=(2, 8))
        entry_name.focus()

        ctk.CTkLabel(
            dialog,
            text="Optional default value (used if contact has no value):",
            font=ctk.CTkFont(size=11),
        ).pack(padx=20, pady=(2, 2), anchor="w")

        entry_default = ctk.CTkEntry(dialog, width=320, placeholder_text="e.g. Standard Offer")
        entry_default.pack(padx=20, pady=(2, 8))

        lbl_error = ctk.CTkLabel(
            dialog, text="", font=ctk.CTkFont(size=11), text_color="#D32F2F", anchor="w"
        )
        lbl_error.pack(padx=20, pady=(0, 6), fill="x")

        def do_add():
            raw_name = entry_name.get().strip().lstrip("{").rstrip("}").strip()
            default_val = entry_default.get().strip()

            if not raw_name:
                lbl_error.configure(text="Please enter a variable name.")
                return

            # Alphanumeric + underscore validation
            if not re.match(r"^[a-zA-Z0-9_\u0600-\u06FF]+$", raw_name):
                lbl_error.configure(text="Name must contain only letters, numbers, and underscores.")
                return

            clean_name = raw_name.lower()

            # Prevent duplicate check
            built_in_names = [v.lstrip("{").rstrip("}").lower() for v in STANDARD_VARIABLES]
            if clean_name in built_in_names or clean_name in self._custom_variables:
                lbl_error.configure(text=f"Variable '{{{raw_name}}}' already exists.")
                return

            # Store in custom variables
            self._custom_variables[raw_name] = default_val
            self._rebuild_variable_chips()
            self.insert_variable_at_cursor(f"{{{raw_name}}}")
            self._is_dirty = True
            self._update_template_badge()
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 12))

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=dialog.destroy,
            width=80,
            fg_color=("gray75", "gray30"),
            text_color=("gray10", "gray90"),
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_row,
            text="➕ Add & Insert",
            command=do_add,
            width=110,
            fg_color="#00897B",
            hover_color="#00695C",
        ).pack(side="right")

    def _refresh_preset_dropdown(self) -> None:
        names = self._get_template_names_list()
        self.preset_combo.configure(values=names)
        if self._current_template_name in names:
            self.preset_combo.set(self._current_template_name)
