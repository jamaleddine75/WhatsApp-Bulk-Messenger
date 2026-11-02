"""Data models for WhatsApp Bulk Messenger."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class SendStatus(str, Enum):
    """Status enum for message progression."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    API_SENT = "API_SENT"
    MANUALLY_CONFIRMED = "MANUALLY_CONFIRMED"
    DELIVERED = "DELIVERED"
    READ = "READ"
    OPENED = "OPENED"
    SKIPPED = "SKIPPED"
    SKIPPED_NO_CONSENT = "SKIPPED_NO_CONSENT"
    SKIPPED_OPT_OUT = "SKIPPED_OPT_OUT"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    FAILED = "FAILED"
    INVALID = "INVALID"

    def get_color(self) -> str:
        """Return theme color for GUI badges."""
        colors = {
            SendStatus.PENDING: "#9E9E9E",
            SendStatus.ACCEPTED: "#00897B",
            SendStatus.API_SENT: "#00897B",
            SendStatus.MANUALLY_CONFIRMED: "#2E7D32",
            SendStatus.DELIVERED: "#1B5E20",
            SendStatus.READ: "#1565C0",
            SendStatus.OPENED: "#2196F3",
            SendStatus.SKIPPED: "#FF9800",
            SendStatus.SKIPPED_NO_CONSENT: "#FF7043",
            SendStatus.SKIPPED_OPT_OUT: "#D84315",
            SendStatus.ALREADY_PROCESSED: "#78909C",
            SendStatus.FAILED: "#D32F2F",
            SendStatus.INVALID: "#C62828",
        }
        return colors.get(self, "#9E9E9E")

    def get_label(self) -> str:
        """User-friendly label."""
        labels = {
            SendStatus.PENDING: "Pending",
            SendStatus.ACCEPTED: "API Accepted",
            SendStatus.API_SENT: "API Sent",
            SendStatus.MANUALLY_CONFIRMED: "Manually Confirmed",
            SendStatus.DELIVERED: "Delivered",
            SendStatus.READ: "Read",
            SendStatus.OPENED: "Chat Opened",
            SendStatus.SKIPPED: "Skipped",
            SendStatus.SKIPPED_NO_CONSENT: "No Consent",
            SendStatus.SKIPPED_OPT_OUT: "Suppressed (Opt-Out)",
            SendStatus.ALREADY_PROCESSED: "Already Sent",
            SendStatus.FAILED: "Failed",
            SendStatus.INVALID: "Invalid Number",
        }
        return labels.get(self, str(self.value))


@dataclass
class Contact:
    """Represents an imported contact."""
    index: int
    raw_phone: str
    clean_phone: str = ""
    formatted_phone: str = ""
    name: str = ""
    extra_fields: Dict[str, str] = field(default_factory=dict)
    is_valid: bool = False
    validation_error: str = ""
    opted_in: bool = True
    is_suppressed: bool = False
    suppression_reason: str = ""
    consent_source: str = ""
    status: SendStatus = SendStatus.PENDING
    notes: str = ""
    chat_url: str = ""
    message_id: str = ""

    @property
    def display_name(self) -> str:
        return self.name.strip() if self.name.strip() else "Valued Customer"

    @property
    def is_eligible(self) -> bool:
        """Returns True only if contact has valid phone, explicit consent, and is not suppressed."""
        return self.is_valid and self.opted_in and not self.is_suppressed


@dataclass
class LogEntry:
    """Represents a row in sent_log.csv."""
    timestamp: str
    phone: str
    name: str
    status: str
    notes: str
    chat_url: str = ""
    message_id: str = ""


@dataclass
class ImportSummary:
    """Summary of imported CSV contacts."""
    total_rows: int = 0
    valid_count: int = 0
    eligible_count: int = 0
    no_consent_count: int = 0
    suppressed_count: int = 0
    invalid_count: int = 0
    duplicate_count: int = 0
    file_path: str = ""
