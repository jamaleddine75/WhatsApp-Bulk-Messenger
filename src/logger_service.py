"""Audit and event logging service for message attempts."""

import csv
import datetime
import os
import threading
from typing import List, Optional, Set
from src.config import DEFAULT_LOG_FILE, DELIVERY_DISCLAIMER
from src.models import LogEntry, SendStatus

LOG_HEADERS = [
    "Timestamp_UTC",
    "Local_Time",
    "Phone",
    "Name",
    "Status",
    "Notes",
    "Message_ID",
    "WhatsApp_URL",
]


class LoggerService:
    """Thread-safe CSV logger for message sending attempts and outcomes."""

    def __init__(self, log_file_path: str = DEFAULT_LOG_FILE):
        self.log_file_path = log_file_path
        self._lock = threading.Lock()
        self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        """Create the log file with standard headers if it does not exist."""
        with self._lock:
            if not os.path.exists(self.log_file_path):
                # Using utf-8-sig so Excel on Windows opens multilingual text (Arabic/French) cleanly
                with open(self.log_file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(LOG_HEADERS)

    def log_attempt(
        self,
        phone: str,
        name: str,
        status: SendStatus,
        notes: str = "",
        chat_url: str = "",
        message_id: str = "",
    ) -> LogEntry:
        """Append a message attempt outcome to sent_log.csv.

        IMPORTANT: Delivery is never claimed unless independently verified.
        Statuses distinguish between OPENED, MANUALLY_CONFIRMED, API_SENT, SKIPPED, FAILED, INVALID.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        now_local = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = LogEntry(
            timestamp=now_local,
            phone=phone,
            name=name,
            status=status.value,
            notes=notes,
            chat_url=chat_url,
            message_id=message_id,
        )

        row = [
            now_utc,
            now_local,
            phone,
            name,
            status.value,
            notes,
            message_id,
            chat_url,
        ]

        with self._lock:
            with open(self.log_file_path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(row)

        return entry

    def get_already_sent_phones(self) -> Set[str]:
        """Return set of normalized phones that were successfully sent or confirmed.

        Prevents duplicate dispatches when resuming or rerunning after an interruption.
        """
        already_sent: Set[str] = set()
        if not os.path.exists(self.log_file_path):
            return already_sent

        with self._lock:
            try:
                with open(self.log_file_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    if len(rows) > 1:
                        for row in rows[1:]:
                            if len(row) >= 5:
                                phone = row[2].strip()
                                status = row[4].strip()
                                if status in (
                                    SendStatus.MANUALLY_CONFIRMED.value,
                                    SendStatus.API_SENT.value,
                                    SendStatus.DELIVERED.value,
                                ):
                                    if phone:
                                        already_sent.add(phone)
            except Exception:
                pass
        return already_sent

    def get_recent_entries(self, limit: int = 50) -> List[LogEntry]:
        """Read and return recent log entries for UI display."""
        entries: List[LogEntry] = []
        if not os.path.exists(self.log_file_path):
            return entries

        with self._lock:
            try:
                with open(self.log_file_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    if len(rows) > 1:
                        data_rows = rows[1:]  # skip header
                        for row in data_rows[-limit:]:
                            if len(row) >= 6:
                                msg_id = row[6] if len(row) > 7 else ""
                                chat_url = row[7] if len(row) > 7 else (row[6] if len(row) > 6 else "")
                                entries.append(
                                    LogEntry(
                                        timestamp=row[1],
                                        phone=row[2],
                                        name=row[3],
                                        status=row[4],
                                        notes=row[5],
                                        message_id=msg_id,
                                        chat_url=chat_url,
                                    )
                                )
            except Exception:
                pass
        return entries
