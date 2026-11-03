"""Experimental pure-Python WhatsApp messaging provider using the piwapp library."""

import asyncio
import json
from pathlib import Path
import re
import threading
import time
import urllib.request
from typing import Any, Callable, Optional, Tuple

from src.config import DEFAULT_SESSION_FILE, DEFAULT_VERSION_FILE
from src.diagnostics import get_logger
from src.models import Contact, SendStatus
from src.providers.base import BaseMessageProvider, ProviderResult

_logger = get_logger()

# Known good WhatsApp Web client revision used as reliable fallback
FALLBACK_WA_VERSION: Tuple[int, int, int] = (2, 3000, 1052682108)


def fetch_latest_wa_version(timeout: float = 4.0) -> Optional[Tuple[int, int, int]]:
    """Fetch the latest WhatsApp Web client revision from official servers or Baileys tracker."""
    # 1. Primary: Official WhatsApp Web service worker (direct client_revision)
    try:
        req = urllib.request.Request(
            "https://web.whatsapp.com/sw.js",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r'client_revision.*?(\d{8,12})', text)
            if m:
                rev = int(m.group(1))
                return (2, 3000, rev)
    except Exception as e:
        _logger.debug("Failed fetching WhatsApp version from sw.js: %s", e)

    # 2. Secondary fallback: Baileys upstream version tracker
    try:
        req = urllib.request.Request(
            "https://raw.githubusercontent.com/WhiskeySockets/Baileys/master/src/Defaults/baileys-version.json",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            ver = data.get("version")
            if ver and isinstance(ver, list) and len(ver) == 3:
                return (int(ver[0]), int(ver[1]), int(ver[2]))
    except Exception as e:
        _logger.debug("Failed fetching WhatsApp version from Baileys tracker: %s", e)

    return None

try:
    from piwapp import AuthenticationCreds, Client, ConnectionConfig
    from piwapp.auth.qr import save_qr_png
    PIWAPP_AVAILABLE = True
except ImportError:
    PIWAPP_AVAILABLE = False
    AuthenticationCreds = None
    Client = None
    ConnectionConfig = None
    save_qr_png = None


class PiwappProvider(BaseMessageProvider):
    """Experimental automated messaging provider using the pure-Python piwapp library.

    Connects directly to WhatsApp multi-device WebSockets without headless browsers.
    Communicates via QR code pairing and persistent local session credentials.
    """

    def __init__(
        self,
        session_path: Optional[str] = None,
        keys_path: Optional[str] = None,
        client_factory: Optional[Callable[..., Any]] = None,
        version_cache_path: Optional[str] = None,
    ):
        actual_session = session_path if session_path is not None else DEFAULT_SESSION_FILE
        self.session_path = Path(actual_session)
        self.keys_path = Path(keys_path) if keys_path else self.session_path.with_suffix(self.session_path.suffix + ".keys")
        actual_version = version_cache_path if version_cache_path is not None else DEFAULT_VERSION_FILE
        self.version_cache_path = Path(actual_version) if actual_version else None
        self.client_factory = client_factory

        self._client: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._is_connected = False
        self._is_connecting = False
        self._paired_id: Optional[str] = self.get_saved_account_id()
        self._last_qr_payload: Optional[str] = None
        self._runner_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()

        self._on_qr: Optional[Callable[[str], None]] = None
        self._on_status: Optional[Callable[[str], None]] = None
        self._on_connected: Optional[Callable[[str], None]] = None

    def get_resolved_wa_version(self, force_refresh: bool = False) -> Tuple[int, int, int]:
        """Resolve current WhatsApp Web client version using cached value, live fetch, or fallback."""
        # 1. Check cache if not forcing refresh
        if not force_refresh and self.version_cache_path and self.version_cache_path.exists():
            try:
                data = json.loads(self.version_cache_path.read_text(encoding="utf-8"))
                cached_ver = data.get("version")
                cached_ts = data.get("timestamp", 0)
                # Cache valid for 12 hours (43200 seconds)
                if cached_ver and len(cached_ver) == 3 and (time.time() - cached_ts < 43200):
                    return (int(cached_ver[0]), int(cached_ver[1]), int(cached_ver[2]))
            except Exception as e:
                _logger.debug("Error reading version cache: %s", e)

        # 2. Fetch live version
        live_version = fetch_latest_wa_version()
        resolved = live_version or FALLBACK_WA_VERSION

        # 3. Save to cache
        if self.version_cache_path:
            try:
                cache_data = {
                    "version": list(resolved),
                    "timestamp": time.time(),
                }
                self.version_cache_path.write_text(json.dumps(cache_data), encoding="utf-8")
            except Exception as e:
                _logger.debug("Error saving version cache: %s", e)

        return resolved

    def invalidate_version_cache(self) -> None:
        """Clear cached protocol version when server reports protocol mismatch (code 405)."""
        if self.version_cache_path and self.version_cache_path.exists():
            try:
                self.version_cache_path.unlink()
                _logger.debug("piwapp: Invalidated version cache at %s", self.version_cache_path)
            except Exception as e:
                _logger.debug("Error removing version cache: %s", e)

    def has_saved_session(self) -> bool:
        """Check whether a valid, authenticated session exists on disk."""
        if not self.session_path.exists():
            return False
        try:
            text = self.session_path.read_text(encoding="utf-8")
            if not text.strip():
                return False
            creds = AuthenticationCreds.from_json(text)
            me = getattr(creds, "me", None)
            return me is not None and getattr(me, "id", None) is not None
        except Exception as e:
            _logger.debug("Failed reading saved session: %s", e)
            return False

    def get_saved_account_id(self) -> Optional[str]:
        """Extract paired WhatsApp JID from saved session if available."""
        if not self.session_path.exists() or AuthenticationCreds is None:
            return None
        try:
            text = self.session_path.read_text(encoding="utf-8")
            if not text.strip():
                return None
            creds = AuthenticationCreds.from_json(text)
            me = getattr(creds, "me", None)
            if me and getattr(me, "id", None):
                return str(me.id)
        except Exception:
            pass
        return None

    @property
    def name(self) -> str:
        return "piwapp (Experimental Pure-Python Automation)"

    @property
    def is_automated(self) -> bool:
        return True

    @property
    def is_connected(self) -> bool:
        with self._lock:
            if self._client is not None and hasattr(self._client, "is_open"):
                return bool(self._client.is_open and self._is_connected)
            return self._is_connected

    @property
    def is_connecting(self) -> bool:
        return self._is_connecting

    @property
    def paired_id(self) -> Optional[str]:
        return self._paired_id

    @property
    def last_qr(self) -> Optional[str]:
        return self._last_qr_payload

    def validate_configuration(self) -> Tuple[bool, str]:
        """Verify that piwapp is available and authenticated."""
        if not PIWAPP_AVAILABLE:
            return (
                False,
                "piwapp library is not installed in the environment. Install via 'pip install piwapp'.",
            )

        if not self.is_connected:
            if self.has_saved_session():
                return (
                    False,
                    f"piwapp saved session found ({self.paired_id or 'Saved Account'}), but not currently connected. Please click '🔗 Connect / Pair QR' to connect.",
                )
            return (
                False,
                "piwapp is not currently connected (pairing required). Please click '🔗 Connect / Pair QR' to scan the QR code and link your account.",
            )

        return True, f"piwapp connected and active (Account: {self.paired_id or 'Authorized'})."

    def connect(
        self,
        on_qr: Optional[Callable[[str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_connected: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Start the async piwapp client in a dedicated daemon thread.

        Args:
            on_qr: Callback receiving raw QR payload string when pairing is needed.
            on_status: Callback receiving human-readable status text updates.
            on_connected: Callback receiving paired JID when connection opens.
        """
        if not PIWAPP_AVAILABLE:
            if on_status:
                on_status("piwapp is not installed. Install via pip install piwapp.")
            return

        with self._lock:
            if self.is_connected or self._is_connecting:
                if on_status:
                    on_status("Already connected or connecting.")
                return

            self._is_connecting = True
            self._on_qr = on_qr
            self._on_status = on_status
            self._on_connected = on_connected

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        """Dedicated asyncio thread running the piwapp connection loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._async_connect_and_run())
        except Exception as e:
            _logger.error("Error in piwapp loop: %s", e)
            if self._on_status:
                self._on_status(f"Connection error: {e}")
        finally:
            with self._lock:
                self._is_connected = False
                self._is_connecting = False
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                self._loop.close()
            except Exception:
                pass

    def _load_or_init_creds(self) -> Any:
        """Load saved credentials from disk or create fresh initial credentials."""
        if self.session_path.exists():
            try:
                text = self.session_path.read_text(encoding="utf-8")
                return AuthenticationCreds.from_json(text)
            except Exception as e:
                _logger.warning("Could not read saved session: %s. Initializing fresh credentials.", e)

        creds = AuthenticationCreds.initial()
        try:
            self.session_path.write_text(creds.to_json(), encoding="utf-8")
        except Exception as e:
            _logger.warning("Could not write initial session: %s", e)
        return creds

    async def _async_connect_and_run(self) -> None:
        """Async worker connecting to WhatsApp and wiring event handlers."""
        creds = self._load_or_init_creds()

        def save_creds(updated: Any) -> None:
            try:
                self.session_path.write_text(updated.to_json(), encoding="utf-8")
            except Exception as ex:
                _logger.warning("Error saving updated creds: %s", ex)

        wa_version = self.get_resolved_wa_version()
        _logger.info("piwapp: Using WhatsApp Web protocol version %s", ".".join(map(str, wa_version)))
        config = ConnectionConfig(version=wa_version)

        if self.client_factory:
            self._client = self.client_factory(
                creds,
                config,
                on_creds_update=save_creds,
                keys_path=self.keys_path,
            )
        else:
            self._client = Client(
                creds,
                config,
                on_creds_update=save_creds,
                keys_path=self.keys_path,
            )

        async def on_connection_update(update: dict) -> None:
            conn_state = update.get("connection")
            if conn_state == "connecting":
                _logger.info("piwapp: Connecting to WhatsApp servers...")
                if self._on_status:
                    self._on_status("Connecting to WhatsApp...")

            if "qr" in update:
                qr_val = update["qr"]
                self._last_qr_payload = qr_val
                _logger.info("piwapp: QR code received for pairing.")
                if self._on_qr:
                    self._on_qr(qr_val)
                if self._on_status:
                    self._on_status("Scan QR code in WhatsApp > Linked Devices.")

            if conn_state == "open":
                me_data = update.get("me") or {}
                self._paired_id = me_data.get("id") or (getattr(creds, "me", None) and getattr(creds.me, "id", None))
                with self._lock:
                    self._is_connected = True
                    self._is_connecting = False
                msg = f"Connected as {self._paired_id or 'WhatsApp User'}"
                _logger.info("piwapp: %s", msg)
                if self._on_status:
                    self._on_status(msg)
                if self._on_connected:
                    self._on_connected(self._paired_id or "")

            if conn_state == "close":
                with self._lock:
                    self._is_connected = False
                    self._is_connecting = False
                reason = update.get("reason", "closed")
                logged_out = update.get("logged_out", False)
                _logger.info("piwapp: Connection closed (reason=%s, logged_out=%s)", reason, logged_out)
                if reason == 405 or str(reason) == "405":
                    _logger.warning("piwapp: WhatsApp rejected protocol version (reason 405). Invalidating cache and stopping client loop.")
                    self.invalidate_version_cache()
                    if self._client:
                        try:
                            await self._client.stop()
                        except Exception:
                            pass
                    status_msg = "WhatsApp protocol outdated (405). Cache refreshed; please reconnect."
                elif logged_out:
                    self._paired_id = None
                    try:
                        if self.session_path.exists():
                            self.session_path.unlink()
                        if self.keys_path.exists():
                            self.keys_path.unlink()
                    except Exception as err:
                        _logger.debug("Error cleaning up logged out session: %s", err)
                    status_msg = "Logged out from phone. Re-pairing required."
                else:
                    status_msg = f"Disconnected ({reason})"

                if self._on_status:
                    self._on_status(status_msg)

        self._client.on("connection.update", on_connection_update)

        self._runner_task = asyncio.create_task(self._client.start())
        try:
            await self._runner_task
        except asyncio.CancelledError:
            pass

    def disconnect(self) -> None:
        """Disconnect active piwapp session cleanly."""
        with self._lock:
            self._is_connecting = False
            self._is_connected = False

        if self._loop and self._client and self._loop.is_running():
            try:
                stop_future = asyncio.run_coroutine_threadsafe(self._client.stop(), self._loop)
                stop_future.result(timeout=5.0)
            except Exception as e:
                _logger.debug("piwapp stop exception: %s", e)

        if self._runner_task and not self._runner_task.done():
            self._loop.call_soon_threadsafe(self._runner_task.cancel)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        _logger.info("piwapp disconnected.")
        if self._on_status:
            self._on_status("Disconnected.")

    def logout(self) -> None:
        """Disconnect and remove saved session files so a fresh QR scan is forced next time."""
        self.disconnect()
        self.invalidate_version_cache()
        try:
            if self.session_path.exists():
                self.session_path.unlink()
            if self.keys_path.exists():
                self.keys_path.unlink()
            _logger.info("piwapp session files deleted.")
        except Exception as e:
            _logger.warning("Error deleting session files: %s", e)

    def send(
        self,
        contact: Contact,
        personalized_message: str,
        **kwargs,
    ) -> ProviderResult:
        """Send message via piwapp's active WebSocket connection."""
        valid, err_msg = self.validate_configuration()
        if not valid:
            _logger.error("piwapp send blocked: %s", err_msg)
            return ProviderResult(
                success=False,
                status=SendStatus.FAILED,
                notes=f"piwapp not ready: {err_msg}",
            )

        # Standard WhatsApp JID format for direct messages
        clean_phone = contact.clean_phone.strip().lstrip("+")
        to_jid = f"{clean_phone}@s.whatsapp.net"

        _logger.info("Dispatching via piwapp to %s (%s)...", contact.display_name, to_jid)

        try:
            coro = self._client.send_text(to_jid, personalized_message)
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)

            # Wait for socket stanza transmission acknowledgement
            msg_id = future.result(timeout=25.0)
            contact.message_id = msg_id
            _logger.info("piwapp message dispatched successfully. msg_id=%s", msg_id)

            return ProviderResult(
                success=True,
                status=SendStatus.API_SENT,
                message_id=msg_id,
                notes=f"Server-acknowledged via piwapp socket (ID: {msg_id})",
                requires_manual_confirmation=False,
            )

        except TimeoutError:
            notes = "Transmission unconfirmed: piwapp socket timed out waiting for server acknowledgement."
            _logger.error(notes)
            return ProviderResult(
                success=False,
                status=SendStatus.FAILED,
                notes=notes,
            )
        except Exception as ex:
            notes = f"Transmission attempt failed: {str(ex)}"
            _logger.error(notes)
            return ProviderResult(
                success=False,
                status=SendStatus.FAILED,
                notes=notes,
            )

