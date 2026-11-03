"""Template storage and lifecycle management for WhatsApp Bulk Messenger."""

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from src.config import DEFAULT_TEMPLATES_DIR, PRESET_TEMPLATES
from src.diagnostics import get_logger

_logger = get_logger()


@dataclass
class MessageTemplate:
    """Represents a message template with metadata and custom variable definitions."""
    name: str
    body: str
    custom_variables: Dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "body": self.body,
            "custom_variables": self.custom_variables,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MessageTemplate":
        return cls(
            name=str(data.get("name", "Untitled Template")),
            body=str(data.get("body", "")),
            custom_variables=dict(data.get("custom_variables", {})),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


class TemplateManager:
    """Manages saving, loading, listing, and deleting message templates on disk."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_TEMPLATES_DIR
        self._ensure_storage_dir()
        self._seed_default_templates_if_empty()

    def _ensure_storage_dir(self) -> None:
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            _logger.error("Failed to create template storage directory '%s': %s", self.storage_dir, e)

    def _seed_default_templates_if_empty(self) -> None:
        """Seed default templates if directory is empty."""
        try:
            existing = list(self.storage_dir.glob("*.json"))
            if not existing:
                now = datetime.now().isoformat()
                for preset_name, preset_body in PRESET_TEMPLATES.items():
                    tpl = MessageTemplate(
                        name=preset_name,
                        body=preset_body,
                        custom_variables={},
                        created_at=now,
                        updated_at=now,
                    )
                    self.save_template(tpl, overwrite=True)

                # Add product offer example template demonstrating custom variables
                offer_tpl = MessageTemplate(
                    name="Product Offer (with Custom Variables)",
                    body=(
                        "Bonjour {name},\n\n"
                        "Nous vous contactons concernant votre intérêt pour {product}.\n"
                        "Le tarif spécial pour vous est de {price} MAD (disponible à {city}).\n\n"
                        "Répondez OUI pour confirmer votre commande.\n"
                        "Bien cordialement,\nL'équipe commerciale"
                    ),
                    custom_variables={"product": "Formation Python", "price": "500", "city": "Casablanca"},
                    created_at=now,
                    updated_at=now,
                )
                self.save_template(offer_tpl, overwrite=True)
        except Exception as e:
            _logger.warning("Could not seed default templates: %s", e)

    def _sanitize_filename(self, name: str) -> str:
        """Produce safe filesystem name from template name."""
        clean = re.sub(r'[\\/*?:"<>|]', '_', name.strip())
        return clean[:100] or "unnamed_template"

    def list_templates(self) -> List[str]:
        """Return names of all valid saved templates, sorted alphabetically."""
        templates = []
        if not self.storage_dir.exists():
            return templates

        for path in self.storage_dir.glob("*.json"):
            try:
                content = path.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, dict) and "name" in data and isinstance(data["name"], str):
                    templates.append(data["name"])
            except Exception as e:
                _logger.warning("Skipping corrupted template file '%s': %s", path.name, e)

        return sorted(templates, key=lambda s: s.lower())

    def get_template(self, name: str) -> Optional[MessageTemplate]:
        """Load a template by name. Handles corrupted files gracefully."""
        if not self.storage_dir.exists():
            return None

        for path in self.storage_dir.glob("*.json"):
            try:
                content = path.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, dict) and data.get("name") == name:
                    return MessageTemplate.from_dict(data)
            except Exception as e:
                _logger.warning("Corrupted template file '%s': %s", path.name, e)

        return None

    def save_template(self, template: MessageTemplate, overwrite: bool = False) -> Tuple[bool, str]:
        """Save a template to disk.

        Args:
            template: MessageTemplate instance.
            overwrite: If True, allow overwriting existing template with same name.

        Returns:
            Tuple[bool, str]: (Success, Message)
        """
        if not template.name or not template.name.strip():
            return False, "Template name cannot be empty."

        clean_name = template.name.strip()
        filename = f"{self._sanitize_filename(clean_name)}.json"
        target_path = self.storage_dir / filename

        existing = self.get_template(clean_name)
        if existing and not overwrite:
            return False, f"A template named '{clean_name}' already exists. Use Save As or confirm overwrite."

        now = datetime.now().isoformat()
        if not template.created_at:
            template.created_at = now
        template.updated_at = now

        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            temp_path = target_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(template.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            if target_path.exists():
                target_path.unlink()
            temp_path.rename(target_path)
            return True, f"Template '{clean_name}' saved successfully."
        except Exception as e:
            _logger.error("Failed writing template '%s': %s", clean_name, e)
            return False, f"Failed to save template: {str(e)}"

    def delete_template(self, name: str) -> Tuple[bool, str]:
        """Delete a saved template by name."""
        if not self.storage_dir.exists():
            return False, "Template directory not found."

        for path in self.storage_dir.glob("*.json"):
            try:
                content = path.read_text(encoding="utf-8")
                data = json.loads(content)
                if isinstance(data, dict) and data.get("name") == name:
                    path.unlink()
                    return True, f"Template '{name}' deleted successfully."
            except Exception as e:
                _logger.warning("Error inspecting file '%s' during deletion: %s", path.name, e)

        return False, f"Template '{name}' not found."

