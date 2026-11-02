"""Message personalization and WhatsApp Web URL construction."""

import re
import urllib.parse
from typing import Dict, List, Optional
from src.config import WHATSAPP_WEB_URL, WHATSAPP_API_URL
from src.models import Contact


class MessageEngine:
    """Handles template interpolation, multilingual encoding, and WhatsApp URL generation."""

    def __init__(self, endpoint_url: str = WHATSAPP_WEB_URL):
        self.endpoint_url = endpoint_url

    def personalize_message(
        self,
        template: str,
        contact: Contact,
        default_name_fallback: str = "Client",
        custom_variables: Optional[Dict[str, str]] = None,
    ) -> str:
        """Replace placeholders with contact attributes and custom variable defaults.

        Supported placeholders:
            {name} - Contact's full name (or fallback if empty)
            {phone} - Formatted or raw phone
            {clean_phone} - International clean digits (e.g. 212612345678)
            {formatted_phone} - Formatted display phone (e.g. +212 612-345678)
            {<extra_field>} - Any extra column present in CSV or defined custom variable (e.g. {product}, {price})
        """
        if not template:
            return ""

        # Determine effective name
        effective_name = contact.name.strip() if contact.name and contact.name.strip() else default_name_fallback

        replacements: Dict[str, str] = {
            "name": effective_name,
            "nom": effective_name,
            "phone": contact.formatted_phone or contact.raw_phone,
            "clean_phone": contact.clean_phone,
            "formatted_phone": contact.formatted_phone,
        }

        # Apply custom variable defaults first if provided
        if custom_variables:
            for k, default_val in custom_variables.items():
                if default_val is not None and str(default_val).strip():
                    clean_k = k.strip().lower().lstrip("{").rstrip("}")
                    replacements[clean_k] = str(default_val).strip()

        # Contact extra_fields override custom defaults
        if hasattr(contact, "extra_fields") and contact.extra_fields:
            for k, v in contact.extra_fields.items():
                if v is not None and str(v).strip():
                    clean_k = k.strip().lower().lstrip("{").rstrip("}")
                    replacements[clean_k] = str(v).strip()

        # Case-insensitive placeholder replacement using regex
        def replace_match(match: re.Match) -> str:
            placeholder = match.group(1).lower().strip()
            return replacements.get(placeholder, match.group(0))

        personalized = re.sub(r"\{([a-zA-Z0-9_\u0600-\u06FF]+)\}", replace_match, template)
        return personalized

    def get_missing_variables(
        self,
        template: str,
        contact: Optional[Contact],
        custom_variables: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """Find placeholders in template that have no value in contact or custom variable defaults."""
        if not template:
            return []

        placeholders = self.extract_placeholders(template)
        # Standard built-in variables always have a value (or built-in fallback)
        standard_vars = {"name", "nom", "phone", "clean_phone", "formatted_phone"}
        missing = []

        custom_defaults = {}
        if custom_variables:
            for k, v in custom_variables.items():
                if v is not None and str(v).strip():
                    custom_defaults[k.strip().lower().lstrip("{").rstrip("}")] = str(v).strip()

        contact_extras = {}
        if contact and hasattr(contact, "extra_fields") and contact.extra_fields:
            for k, v in contact.extra_fields.items():
                if v is not None and str(v).strip():
                    contact_extras[k.strip().lower().lstrip("{").rstrip("}")] = str(v).strip()

        for p in placeholders:
            if p in standard_vars:
                continue
            # Check if contact provides value
            if p in contact_extras:
                continue
            # Check if custom variable default provides value
            if p in custom_defaults:
                continue
            missing.append(p)

        return missing

    def build_click_to_chat_url(
        self,
        clean_phone: str,
        personalized_message: str,
        use_api_endpoint: bool = False,
    ) -> str:
        """Construct standard WhatsApp click-to-chat URL with proper percent-encoding.

        Args:
            clean_phone: Normalized phone number without '+' (e.g. '212612345678').
            personalized_message: Message text to prefill (supports Arabic, Darija, accents, emojis).
            use_api_endpoint: If True, uses 'api.whatsapp.com/send', else 'web.whatsapp.com/send'.

        Returns:
            Fully formed click-to-chat URL string.
        """
        base = WHATSAPP_API_URL if use_api_endpoint else self.endpoint_url
        # urllib.parse.quote with safe='' ensures full percent-encoding including spaces (%20) and newlines (%0A)
        encoded_text = urllib.parse.quote(personalized_message, safe="")
        return f"{base}?phone={clean_phone}&text={encoded_text}"

    @staticmethod
    def extract_placeholders(template: str) -> List[str]:
        """Extract all unique placeholder variable names from template."""
        if not template:
            return []
        matches = re.findall(r"\{([a-zA-Z0-9_\u0600-\u06FF]+)\}", template)
        return sorted(list(set(m.lower() for m in matches)))

