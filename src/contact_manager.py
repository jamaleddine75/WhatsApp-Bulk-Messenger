"""Contact manager for importing, deduplicating, validating, and checking consent/suppression on CSV contacts."""

import csv
import io
import os
from typing import Dict, List, Optional, Set

from src.database import DatabaseManager
from src.models import Contact, ImportSummary, SendStatus
from src.validator import normalize_and_validate_phone

# Accepted header name patterns (lowercased)
PHONE_HEADER_CANDIDATES = {
    "phone",
    "phone_number",
    "phonenumber",
    "mobile",
    "telephone",
    "tel",
    "gsm",
    "numero",
    "numéro",
    "num_tel",
    "contact",
}

NAME_HEADER_CANDIDATES = {
    "name",
    "full_name",
    "fullname",
    "nom",
    "nom_complet",
    "prenom",
    "prénom",
    "client",
    "destinataire",
}

CONSENT_HEADER_CANDIDATES = {
    "optin",
    "opt_in",
    "optedin",
    "opted_in",
    "consent",
    "consentement",
    "accord",
    "autorise",
    "autorisé",
    "allowed",
}

TRUTHY_VALUES = {"1", "true", "yes", "oui", "y", "vrai", "ok"}


class ContactManager:
    """Manages contact loading, validation, deduplication, and suppression check."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db_manager = db_manager
        self.contacts: List[Contact] = []
        self.valid_contacts: List[Contact] = []
        self.invalid_contacts: List[Contact] = []
        self.duplicate_contacts: List[Contact] = []
        self.summary: ImportSummary = ImportSummary()

    def get_eligible_contacts(self) -> List[Contact]:
        """Return contacts that are valid, consented, and unsuppressed."""
        return [c for c in self.valid_contacts if c.is_eligible]

    def reset_contacts_for_new_campaign(self) -> None:
        """Reset operational execution statuses on contacts for a new campaign run.
        
        Preserves validation integrity, opt-in consent, and suppression records.
        """
        for c in self.valid_contacts:
            if c.is_suppressed:
                c.status = SendStatus.SKIPPED_OPT_OUT
                c.notes = "Skipped: Recipient opted out (suppression list)"
            elif not c.opted_in:
                c.status = SendStatus.SKIPPED_NO_CONSENT
                c.notes = "Skipped: No explicit opt-in consent"
            else:
                c.status = SendStatus.PENDING
                c.notes = ""
            c.chat_url = ""
            c.message_id = ""


    def load_from_csv(
        self, file_path: str, db_manager: Optional[DatabaseManager] = None
    ) -> ImportSummary:
        """Load and parse contacts from a CSV file with automatic encoding detection.

        Args:
            file_path: Absolute or relative path to CSV file.
            db_manager: Optional DatabaseManager instance to check suppression lists.

        Returns:
            ImportSummary object with import statistics.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If CSV is empty or required columns are missing.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        active_db = db_manager or self.db_manager
        suppressed_phones: Set[str] = set()
        if active_db:
            try:
                suppressed_phones = active_db.get_all_opt_outs()
            except Exception:
                suppressed_phones = set()

        # Attempt decoding with robust fallbacks
        encodings = ["utf-8-sig", "utf-8", "cp1256", "cp1252", "latin-1"]
        content: Optional[str] = None

        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            raise ValueError(f"Could not decode file '{file_path}' with supported encodings.")

        if not content.strip():
            raise ValueError(f"The CSV file '{file_path}' is completely empty.")

        # Detect dialect (delimiter: comma, semicolon, tab, pipe)
        first_lines = "\n".join(content.splitlines()[:5])
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(first_lines, delimiters=";,|\t,")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ";" if ";" in first_lines and "," not in first_lines else ","

        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = list(reader)

        if not rows:
            raise ValueError("CSV contains no rows.")

        # Header detection
        headers = [h.strip() for h in rows[0]]
        headers_lower = [h.lower() for h in headers]

        phone_col_idx = self._find_column_index(headers_lower, PHONE_HEADER_CANDIDATES)
        name_col_idx = self._find_column_index(headers_lower, NAME_HEADER_CANDIDATES)
        consent_col_idx = self._find_column_index(headers_lower, CONSENT_HEADER_CANDIDATES)

        # If header match fails, check if first row itself looks like phone data
        if phone_col_idx is None:
            first_val_valid, _, _, _ = normalize_and_validate_phone(headers[0])
            if first_val_valid:
                phone_col_idx = 0
                name_col_idx = 1 if len(headers) > 1 else None
                data_rows = rows
                extra_headers = [f"col_{i}" for i in range(len(headers))]
            else:
                raise ValueError(
                    f"Could not find a 'phone' column in headers: {headers}. "
                    f"Please include a header named 'phone' or 'mobile'."
                )
        else:
            data_rows = rows[1:]
            extra_headers = headers

        # Reset collections
        self.contacts.clear()
        self.valid_contacts.clear()
        self.invalid_contacts.clear()
        self.duplicate_contacts.clear()

        seen_phones: Set[str] = set()
        row_counter = 0

        for row in data_rows:
            if not row or not any(cell.strip() for cell in row):
                continue

            row_counter += 1
            raw_phone = row[phone_col_idx].strip() if phone_col_idx < len(row) else ""
            raw_name = (
                row[name_col_idx].strip()
                if name_col_idx is not None and name_col_idx < len(row)
                else ""
            )

            # Opt-in detection
            opted_in = True
            if consent_col_idx is not None and consent_col_idx < len(row):
                raw_consent = row[consent_col_idx].strip().lower()
                opted_in = raw_consent in TRUTHY_VALUES

            # Extra fields
            extra_fields: Dict[str, str] = {}
            for idx, col_name in enumerate(extra_headers):
                if idx not in (phone_col_idx, name_col_idx, consent_col_idx) and idx < len(row):
                    clean_header_key = col_name.strip().lower()
                    extra_fields[clean_header_key] = row[idx].strip()

            # Phone validation
            is_valid, clean_phone, formatted_phone, error_msg = normalize_and_validate_phone(
                raw_phone
            )

            # Suppression check
            is_suppressed = clean_phone in suppressed_phones if clean_phone else False
            suppression_reason = "Recipient is on the opt-out / suppression list" if is_suppressed else ""

            # Determine initial status
            if not is_valid:
                initial_status = SendStatus.INVALID
                notes = error_msg
            elif is_suppressed:
                initial_status = SendStatus.SKIPPED_OPT_OUT
                notes = "Suppressed: recipient opted out"
            elif not opted_in:
                initial_status = SendStatus.SKIPPED_NO_CONSENT
                notes = "Skipped: no opt-in consent recorded"
            else:
                initial_status = SendStatus.PENDING
                notes = ""

            contact = Contact(
                index=row_counter,
                raw_phone=raw_phone,
                clean_phone=clean_phone,
                formatted_phone=formatted_phone,
                name=raw_name,
                extra_fields=extra_fields,
                is_valid=is_valid,
                validation_error=error_msg,
                opted_in=opted_in,
                is_suppressed=is_suppressed,
                suppression_reason=suppression_reason,
                status=initial_status,
                notes=notes,
            )

            self.contacts.append(contact)

            if not is_valid:
                self.invalid_contacts.append(contact)
            else:
                if clean_phone in seen_phones:
                    contact.is_valid = False
                    contact.status = SendStatus.INVALID
                    contact.validation_error = f"Duplicate phone number (already loaded: {formatted_phone})"
                    contact.notes = contact.validation_error
                    self.duplicate_contacts.append(contact)
                else:
                    seen_phones.add(clean_phone)
                    self.valid_contacts.append(contact)

        eligible_count = len([c for c in self.valid_contacts if c.is_eligible])
        no_consent_count = len([c for c in self.valid_contacts if not c.opted_in])
        suppressed_count = len([c for c in self.valid_contacts if c.is_suppressed])

        self.summary = ImportSummary(
            total_rows=row_counter,
            valid_count=len(self.valid_contacts),
            eligible_count=eligible_count,
            no_consent_count=no_consent_count,
            suppressed_count=suppressed_count,
            invalid_count=len(self.invalid_contacts),
            duplicate_count=len(self.duplicate_contacts),
            file_path=file_path,
        )

        return self.summary

    @staticmethod
    def _find_column_index(headers: List[str], candidates: Set[str]) -> Optional[int]:
        """Find the index of the first header that matches one of the candidate names."""
        for idx, h in enumerate(headers):
            if h in candidates:
                return idx
            if any(cand in h for cand in candidates):
                return idx
        return None
