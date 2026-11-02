"""SQLite database manager for campaigns, message history, idempotency, and opt-outs."""

import csv
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

DEFAULT_DB_FILE = "whatsapp_messenger.db"


class DatabaseManager:
    """Thread-safe SQLite database manager for campaign tracking and suppression."""

    def __init__(self, db_path: str = DEFAULT_DB_FILE):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        """Create database tables and indices if they do not exist."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS campaigns (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        template_text TEXT,
                        template_name TEXT,
                        status TEXT NOT NULL DEFAULT 'CREATED',
                        total_contacts INTEGER DEFAULT 0,
                        sent_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        skipped_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS campaign_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        campaign_id TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        recipient_name TEXT,
                        status TEXT NOT NULL,
                        message_id TEXT,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
                        UNIQUE (campaign_id, phone)
                    );

                    CREATE TABLE IF NOT EXISTS opt_outs (
                        phone TEXT PRIMARY KEY,
                        reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE INDEX IF NOT EXISTS idx_msg_campaign ON campaign_messages(campaign_id);
                    CREATE INDEX IF NOT EXISTS idx_msg_phone ON campaign_messages(phone);
                """)
                conn.commit()
            finally:
                conn.close()

    def close(self) -> None:
        """No-op or cleanup if needed."""
        pass

    # --- Campaign Operations ---
    def create_campaign(
        self,
        campaign_id: str,
        name: str,
        provider: str,
        template_text: str = "",
        template_name: str = "",
        total_contacts: int = 0,
    ) -> Dict[str, Any]:
        """Create a new campaign record."""
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO campaigns (id, name, provider, template_text, template_name, total_contacts, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'CREATED', ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        provider=excluded.provider,
                        template_text=excluded.template_text,
                        template_name=excluded.template_name,
                        total_contacts=excluded.total_contacts,
                        updated_at=excluded.updated_at
                    """,
                    (campaign_id, name, provider, template_text, template_name, total_contacts, now, now),
                )
                conn.commit()
            finally:
                conn.close()
            return self.get_campaign(campaign_id) or {}

    def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single campaign by ID."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
                row = cur.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def list_campaigns(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent campaigns ordered by creation date."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    "SELECT * FROM campaigns ORDER BY created_at DESC LIMIT ?", (limit,)
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()

    def update_campaign_status(self, campaign_id: str, status: str) -> None:
        """Update campaign status (e.g. RUNNING, PAUSED, COMPLETED, STOPPED)."""
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "UPDATE campaigns SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, campaign_id),
                )
                conn.commit()
            finally:
                conn.close()

    def update_campaign_counts(
        self,
        campaign_id: str,
        sent_delta: int = 0,
        failed_delta: int = 0,
        skipped_delta: int = 0,
    ) -> None:
        """Increment progress counters for a campaign."""
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    UPDATE campaigns SET
                        sent_count = sent_count + ?,
                        failed_count = failed_count + ?,
                        skipped_count = skipped_count + ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (sent_delta, failed_delta, skipped_delta, now, campaign_id),
                )
                conn.commit()
            finally:
                conn.close()

    # --- Message Idempotency & History Operations ---
    def record_message(
        self,
        campaign_id: str,
        phone: str,
        recipient_name: str,
        status: str,
        message_id: str = "",
        notes: str = "",
    ) -> bool:
        """Record or update a message attempt with idempotency."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO campaign_messages (campaign_id, phone, recipient_name, status, message_id, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campaign_id, phone) DO UPDATE SET
                        status=excluded.status,
                        message_id=CASE WHEN excluded.message_id != '' THEN excluded.message_id ELSE campaign_messages.message_id END,
                        notes=excluded.notes,
                        created_at=excluded.created_at
                    """,
                    (campaign_id, phone, recipient_name, status, message_id, notes, datetime.now().isoformat()),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()

    def get_completed_phones_for_campaign(self, campaign_id: str) -> Set[str]:
        """Fetch all phones that reached successful terminal status in a campaign."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    """
                    SELECT phone FROM campaign_messages
                    WHERE campaign_id = ? AND status IN ('API_SENT', 'MANUALLY_CONFIRMED', 'DELIVERED', 'ACCEPTED')
                    """,
                    (campaign_id,),
                )
                return {row["phone"] for row in cur.fetchall()}
            finally:
                conn.close()

    def get_campaign_messages(self, campaign_id: str) -> List[Dict[str, Any]]:
        """Fetch all message entries for a given campaign."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute(
                    "SELECT * FROM campaign_messages WHERE campaign_id = ? ORDER BY id ASC",
                    (campaign_id,),
                )
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()

    # --- Suppression / Opt-Out List Operations ---
    def add_opt_out(self, phone: str, reason: str = "User requested opt-out") -> None:
        """Add a phone number to the suppression / opt-out list."""
        clean_phone = phone.strip().lstrip("+")
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO opt_outs (phone, reason, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(phone) DO UPDATE SET reason=excluded.reason
                    """,
                    (clean_phone, reason, datetime.now().isoformat()),
                )
                conn.commit()
            finally:
                conn.close()

    def remove_opt_out(self, phone: str) -> None:
        """Remove a phone number from the suppression list."""
        clean_phone = phone.strip().lstrip("+")
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("DELETE FROM opt_outs WHERE phone = ?", (clean_phone,))
                conn.commit()
            finally:
                conn.close()

    def is_opted_out(self, phone: str) -> bool:
        """Check if a phone number is on the opt-out list."""
        clean_phone = phone.strip().lstrip("+")
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT 1 FROM opt_outs WHERE phone = ?", (clean_phone,))
                return cur.fetchone() is not None
            finally:
                conn.close()

    def get_all_opt_outs(self) -> Set[str]:
        """Fetch all suppressed phone numbers."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("SELECT phone FROM opt_outs")
                return {row["phone"] for row in cur.fetchall()}
            finally:
                conn.close()

    # --- Reporting & Export ---
    def export_campaign_csv(self, campaign_id: str, output_path: str) -> None:
        """Export full campaign results with masked phone numbers for audit privacy."""
        messages = self.get_campaign_messages(campaign_id)
        headers = ["Campaign_ID", "Timestamp", "Masked_Phone", "Recipient_Name", "Status", "Message_ID", "Notes"]

        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for m in messages:
                raw_phone = m.get("phone", "")
                if len(raw_phone) >= 8:
                    masked = raw_phone[:5] + "****" + raw_phone[-3:]
                else:
                    masked = raw_phone
                writer.writerow([
                    campaign_id,
                    m.get("created_at", ""),
                    masked,
                    m.get("recipient_name", ""),
                    m.get("status", ""),
                    m.get("message_id", ""),
                    m.get("notes", ""),
                ])
