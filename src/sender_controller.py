"""Threaded controller for managing WhatsApp dispatch sessions safely."""

import enum
import threading
import time
import traceback
from typing import Callable, Dict, List, Optional, Set

from src.config import DEFAULT_DELAY_SECONDS
from src.database import DatabaseManager
from src.diagnostics import get_logger
from src.logger_service import LoggerService
from src.message_engine import MessageEngine
from src.models import Contact, SendStatus
from src.providers.base import BaseMessageProvider, ProviderResult
from src.providers.cloud_api_provider import WhatsAppCloudApiProvider
from src.providers.piwapp_provider import PiwappProvider
from src.providers.web_provider import WhatsAppWebManualProvider

_logger = get_logger()


class ControllerState(str, enum.Enum):
    """Operational states for the sender controller."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    STOPPED = "STOPPED"
    FINISHED = "FINISHED"


class DispatchMode(str, enum.Enum):
    """Dispatch workflow mode."""
    WEB_MANUAL_REVIEW = "WEB_MANUAL_REVIEW"      # WhatsApp Web click-to-chat with manual review (Default)
    PIWAPP_AUTOMATED = "PIWAPP_AUTOMATED"        # piwapp pure-Python socket automation (Experimental)
    CLOUD_API_AUTOMATED = "CLOUD_API_AUTOMATED"  # Official WhatsApp Cloud API unattended sending
    STEP_BY_STEP = "STEP_BY_STEP"                # Backward compatibility alias for WEB_MANUAL_REVIEW
    ASSISTED_PACING = "ASSISTED_PACING"          # Timed browser pacing


class SenderController:
    """Manages the background sending loop, pacing, provider execution, idempotency, and state machine."""

    def __init__(
        self,
        message_engine: MessageEngine,
        logger_service: LoggerService,
        provider: Optional[BaseMessageProvider] = None,
        db_manager: Optional[DatabaseManager] = None,
        on_progress_update: Optional[Callable[[int, int, Optional[Contact]], None]] = None,
        on_state_change: Optional[Callable[[ControllerState, str], None]] = None,
        on_log_message: Optional[Callable[[str], None]] = None,
    ):
        self.message_engine = message_engine
        self.logger_service = logger_service
        self.provider = provider
        self.db_manager = db_manager
        self.on_progress_update = on_progress_update
        self.on_state_change = on_state_change
        self.on_log_message = on_log_message

        self.state: ControllerState = ControllerState.IDLE
        self.mode: DispatchMode = DispatchMode.WEB_MANUAL_REVIEW
        self.delay_seconds: int = DEFAULT_DELAY_SECONDS
        self.template: str = ""
        self.template_name: Optional[str] = None
        self.template_parameters: Optional[List[str]] = None
        self.language_code: str = "fr"
        self.campaign_id: str = ""
        self.campaign_name: str = ""
        self.contacts_queue: List[Contact] = []
        self.current_index: int = 0
        self.current_contact: Optional[Contact] = None
        self.skip_already_sent: bool = True
        self.global_deduplication: bool = False
        self.is_new_campaign: bool = True

        self._worker_thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._pause_event = threading.Event()
        self._step_decision_event = threading.Event()
        self._step_decision: Optional[str] = None  # "CONFIRM", "SKIP", or "STOP"
        self._lock = threading.RLock()

    def set_state(self, new_state: ControllerState, note: str = "") -> None:
        """Update controller state and notify listeners."""
        with self._lock:
            old_state = self.state
            self.state = new_state
        _logger.info("Controller state transition: %s -> %s (%s)", old_state.value, new_state.value, note)
        if self.on_state_change:
            self.on_state_change(new_state, note)

    def log(self, message: str) -> None:
        """Forward human-readable message to UI logger."""
        _logger.info("SenderController: %s", message)
        if self.on_log_message:
            self.on_log_message(message)

    def get_or_create_provider(self, mode: DispatchMode) -> BaseMessageProvider:
        """Resolve active provider based on mode or explicit configuration."""
        if self.provider is not None:
            if mode == DispatchMode.PIWAPP_AUTOMATED and isinstance(self.provider, PiwappProvider):
                return self.provider
            if mode == DispatchMode.CLOUD_API_AUTOMATED and isinstance(self.provider, WhatsAppCloudApiProvider):
                return self.provider
            if mode in (
                DispatchMode.WEB_MANUAL_REVIEW,
                DispatchMode.STEP_BY_STEP,
                DispatchMode.ASSISTED_PACING,
            ) and isinstance(self.provider, WhatsAppWebManualProvider):
                return self.provider

        if mode == DispatchMode.PIWAPP_AUTOMATED:
            return PiwappProvider()

        if mode == DispatchMode.CLOUD_API_AUTOMATED:
            return WhatsAppCloudApiProvider()

        # Default fallback: WhatsApp Web manual click-to-chat
        return WhatsAppWebManualProvider(self.message_engine)

    def start_batch(
        self,
        contacts: List[Contact],
        template: str,
        mode: DispatchMode = DispatchMode.WEB_MANUAL_REVIEW,
        delay_seconds: int = DEFAULT_DELAY_SECONDS,
        has_consent: bool = False,
        provider: Optional[BaseMessageProvider] = None,
        skip_already_sent: bool = True,
        campaign_id: Optional[str] = None,
        campaign_name: Optional[str] = None,
        template_name: Optional[str] = None,
        template_parameters: Optional[List[str]] = None,
        language_code: str = "fr",
        is_new_campaign: bool = True,
        global_deduplication: bool = False,
        custom_variables: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Start a new dispatch batch.

        Args:
            contacts: List of valid contacts.
            template: Message template with placeholders.
            mode: CLOUD_API_AUTOMATED, WEB_MANUAL_REVIEW, STEP_BY_STEP, or ASSISTED_PACING.
            delay_seconds: Cooldown between contacts.
            has_consent: Explicit boolean certifying recipient consent.
            provider: Optional explicit provider override.
            skip_already_sent: Prevent sending duplicates on resume/re-run.
            campaign_id: Unique campaign identifier for tracking and idempotency.
            campaign_name: User-defined name for campaign.
            template_name: Approved WhatsApp template name (Cloud API).
            template_parameters: Optional list of parameter values for template.
            language_code: Language code for template (e.g., 'fr', 'ar', 'en_US').

        Returns:
            True if started successfully, False otherwise.
        """
        _logger.info(
            "start_batch called: %d contacts, mode=%s, delay=%ds, consent=%s",
            len(contacts) if contacts else 0,
            mode.value if mode else "None",
            delay_seconds,
            has_consent,
        )

        if not has_consent:
            self.log("ERROR: Broadcast blocked. Recipient consent confirmation is required.")
            return False

        if not contacts:
            self.log("ERROR: No valid contacts in queue to process.")
            return False

        if not template.strip() and not template_name:
            self.log("ERROR: Message template is empty.")
            return False

        # Resolve provider
        active_provider = provider or self.get_or_create_provider(mode)
        valid_cfg, cfg_msg = active_provider.validate_configuration()
        if not valid_cfg:
            self.log(f"ERROR: Provider configuration invalid: {cfg_msg}")
            return False

        # Initialize or generate campaign metadata
        camp_id = campaign_id or f"camp_{int(time.time())}"
        camp_name = campaign_name or f"Campaign {time.strftime('%Y-%m-%d %H:%M')}"

        # If this is a genuinely new campaign, reset in-memory operational contact states
        if is_new_campaign:
            for c in contacts:
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

        if self.db_manager:
            try:
                self.db_manager.create_campaign(
                    campaign_id=camp_id,
                    name=camp_name,
                    provider=active_provider.name,
                    template_text=template,
                    template_name=template_name or "",
                    total_contacts=len(contacts),
                )
                self.db_manager.update_campaign_status(camp_id, "RUNNING")
            except Exception as e:
                _logger.warning("Could not initialize campaign in database: %s", e)

        with self._lock:
            if self.state in (ControllerState.RUNNING, ControllerState.AWAITING_CONFIRMATION):
                self.log("WARNING: Session already active.")
                return False

            self.provider = active_provider
            self.contacts_queue = contacts
            self.template = template
            self.template_name = template_name
            self.template_parameters = template_parameters
            self.language_code = language_code
            self.campaign_id = camp_id
            self.campaign_name = camp_name
            self.mode = mode
            self.delay_seconds = max(0, delay_seconds)
            self.current_index = 0
            self.current_contact = None
            self.skip_already_sent = skip_already_sent
            self.global_deduplication = global_deduplication
            self.is_new_campaign = is_new_campaign
            self.custom_variables = custom_variables or {}

            self._stop_requested.clear()
            self._pause_event.set()
            self._step_decision_event.clear()
            self._step_decision = None

        self.set_state(ControllerState.RUNNING, "Starting session")
        self.log(
            f"Starting session with {active_provider.name} (Campaign: {camp_name}). "
            f"Contacts: {len(contacts)}, Cooldown: {delay_seconds}s, Auto: {active_provider.is_automated}."
        )

        self._worker_thread = threading.Thread(target=self._run_worker, daemon=True)
        self._worker_thread.start()
        return True

    def pause(self) -> None:
        """Pause the current session."""
        with self._lock:
            if self.state in (ControllerState.RUNNING, ControllerState.AWAITING_CONFIRMATION):
                self._pause_event.clear()
                self.set_state(ControllerState.PAUSED, "Session paused by user")
                if self.db_manager and self.campaign_id:
                    self.db_manager.update_campaign_status(self.campaign_id, "PAUSED")
                self.log("Session PAUSED. Click Resume to continue.")

    def resume(self) -> None:
        """Resume a paused session."""
        with self._lock:
            if self.state == ControllerState.PAUSED:
                self._pause_event.set()
                self.set_state(ControllerState.RUNNING, "Session resumed")
                if self.db_manager and self.campaign_id:
                    self.db_manager.update_campaign_status(self.campaign_id, "RUNNING")
                self.log("Session RESUMED.")

    def stop(self) -> None:
        """Stop and abort the current session."""
        with self._lock:
            if self.state in (ControllerState.IDLE, ControllerState.STOPPED, ControllerState.FINISHED):
                return
            self._stop_requested.set()
            self._pause_event.set()
            self._step_decision = "STOP"
            self._step_decision_event.set()
            self.set_state(ControllerState.STOPPED, "Session stopped by user")
            if self.db_manager and self.campaign_id:
                self.db_manager.update_campaign_status(self.campaign_id, "STOPPED")
            self.log("Session STOPPED by operator.")

    def confirm_current_sent(self) -> None:
        """Operator marks current contact message as manually confirmed sent."""
        with self._lock:
            if self.state == ControllerState.AWAITING_CONFIRMATION and self.current_contact:
                _logger.info("Operator confirmed sent for contact %s", self.current_contact.clean_phone)
                self._step_decision = "CONFIRM"
                self._step_decision_event.set()

    def skip_current_contact(self) -> None:
        """Operator skips current contact."""
        with self._lock:
            if self.state == ControllerState.AWAITING_CONFIRMATION and self.current_contact:
                _logger.info("Operator skipped contact %s", self.current_contact.clean_phone)
                self._step_decision = "SKIP"
                self._step_decision_event.set()

    def _run_worker(self) -> None:
        """Background thread executing the dispatch loop."""
        total = len(self.contacts_queue)
        provider = self.provider or self.get_or_create_provider(self.mode)

        # 1. Fetch already sent phones to prevent duplicates after interruption
        already_sent_phones: Set[str] = set()
        if self.skip_already_sent:
            try:
                if self.db_manager and self.campaign_id:
                    # Campaign-scoped deduplication (safe resume of current campaign)
                    completed_db = self.db_manager.get_completed_phones_for_campaign(self.campaign_id)
                    already_sent_phones = already_sent_phones.union(completed_db)
                    # Include global historical sent records if requested
                    if self.global_deduplication:
                        historical_sent = self.logger_service.get_already_sent_phones()
                        already_sent_phones = already_sent_phones.union(historical_sent)
                else:
                    # Fallback when running without SQLite database manager: use logger_service
                    already_sent_phones = self.logger_service.get_already_sent_phones()

                if already_sent_phones:
                    _logger.info(
                        "Resuming/Deduplicating: Found %d already processed numbers (global=%s, campaign=%s).",
                        len(already_sent_phones),
                        self.global_deduplication,
                        self.campaign_id,
                    )
            except Exception as e:
                _logger.warning("Could not read prior sent records for deduplication: %s", e)

        sent_count = 0
        failed_count = 0
        skipped_count = 0

        try:
            while self.current_index < total:
                if self._stop_requested.is_set():
                    break

                self._pause_event.wait()
                if self._stop_requested.is_set():
                    break

                contact = self.contacts_queue[self.current_index]
                self.current_contact = contact

                # Consent and suppression enforcement for automated sending
                if provider.is_automated and not contact.is_eligible:
                    if contact.is_suppressed:
                        contact.status = SendStatus.SKIPPED_OPT_OUT
                        contact.notes = "Skipped: Recipient opted out (suppression list)"
                    else:
                        contact.status = SendStatus.SKIPPED_NO_CONSENT
                        contact.notes = "Skipped: No explicit opt-in consent"

                    skipped_count += 1
                    if self.db_manager and self.campaign_id:
                        self.db_manager.record_message(
                            self.campaign_id,
                            contact.clean_phone,
                            contact.display_name,
                            contact.status.value,
                            notes=contact.notes,
                        )
                        self.db_manager.update_campaign_counts(self.campaign_id, skipped_delta=1)

                    self.logger_service.log_attempt(
                        phone=contact.clean_phone,
                        name=contact.display_name,
                        status=contact.status,
                        notes=contact.notes,
                    )
                    self.log(
                        f"[{self.current_index + 1}/{total}] Skipping non-eligible: {contact.display_name} - {contact.notes}"
                    )
                    if self.on_progress_update:
                        self.on_progress_update(self.current_index + 1, total, contact)
                    self.current_index += 1
                    continue

                # Check if contact was already sent (deduplication on resume or global history)
                is_prior_sent = contact.clean_phone in already_sent_phones

                if self.skip_already_sent and is_prior_sent:
                    contact.status = SendStatus.ALREADY_PROCESSED
                    contact.notes = (
                        "Skipped: already sent in previous run (global history)"
                        if self.global_deduplication
                        else "Skipped: already sent in this campaign"
                    )
                    skipped_count += 1
                    if self.db_manager and self.campaign_id:
                        self.db_manager.record_message(
                            self.campaign_id,
                            contact.clean_phone,
                            contact.display_name,
                            contact.status.value,
                            notes=contact.notes,
                        )
                        self.db_manager.update_campaign_counts(self.campaign_id, skipped_delta=1)

                    self.log(
                        f"[{self.current_index + 1}/{total}] Skipping already-sent: {contact.display_name} ({contact.formatted_phone})"
                    )
                    if self.on_progress_update:
                        self.on_progress_update(self.current_index + 1, total, contact)
                    self.current_index += 1
                    continue

                # Notify UI of current progress
                if self.on_progress_update:
                    self.on_progress_update(self.current_index + 1, total, contact)

                # 2. Build personalized message
                personalized_msg = self.message_engine.personalize_message(
                    self.template, contact, custom_variables=getattr(self, "custom_variables", None)
                )

                # 3. Dispatch using active provider
                self.log(
                    f"[{self.current_index + 1}/{total}] Processing {contact.display_name} "
                    f"({contact.formatted_phone}) via {provider.name}..."
                )

                result: ProviderResult = provider.send(
                    contact,
                    personalized_msg,
                    template_name=self.template_name,
                    language_code=self.language_code,
                    template_parameters=self.template_parameters,
                )

                # --- AUTOMATED PROVIDER BRANCH (Official WhatsApp Cloud API) ---
                if provider.is_automated:
                    if result.success:
                        contact.status = result.status
                        contact.notes = result.notes
                        contact.message_id = result.message_id
                        sent_count += 1
                        already_sent_phones.add(contact.clean_phone)

                        if self.db_manager and self.campaign_id:
                            self.db_manager.record_message(
                                self.campaign_id,
                                contact.clean_phone,
                                contact.display_name,
                                result.status.value,
                                message_id=result.message_id,
                                notes=result.notes,
                            )
                            self.db_manager.update_campaign_counts(self.campaign_id, sent_delta=1)

                        self.logger_service.log_attempt(
                            phone=contact.clean_phone,
                            name=contact.display_name,
                            status=result.status,
                            notes=result.notes,
                            chat_url=result.chat_url,
                            message_id=result.message_id,
                        )
                        self.log(
                            f"SUCCESS: Sent to {contact.display_name} (ID: {result.message_id or 'N/A'})."
                        )
                    else:
                        contact.status = SendStatus.FAILED
                        contact.notes = result.notes
                        failed_count += 1

                        if self.db_manager and self.campaign_id:
                            self.db_manager.record_message(
                                self.campaign_id,
                                contact.clean_phone,
                                contact.display_name,
                                SendStatus.FAILED.value,
                                notes=result.notes,
                            )
                            self.db_manager.update_campaign_counts(self.campaign_id, failed_delta=1)

                        self.logger_service.log_attempt(
                            phone=contact.clean_phone,
                            name=contact.display_name,
                            status=SendStatus.FAILED,
                            notes=result.notes,
                            chat_url=result.chat_url,
                        )
                        self.log(f"FAILED for {contact.display_name}: {result.notes}")

                    # Automated cooldown pacing between messages
                    if self.delay_seconds > 0 and self.current_index < total - 1:
                        for _ in range(self.delay_seconds):
                            if self._stop_requested.is_set():
                                break
                            self._pause_event.wait()
                            time.sleep(1)

                # --- MANUAL REVIEW BRANCH (WhatsApp Web Click-to-Chat) ---
                else:
                    if not result.success:
                        contact.status = SendStatus.FAILED
                        contact.notes = result.notes
                        failed_count += 1

                        if self.db_manager and self.campaign_id:
                            self.db_manager.record_message(
                                self.campaign_id,
                                contact.clean_phone,
                                contact.display_name,
                                SendStatus.FAILED.value,
                                notes=result.notes,
                            )
                            self.db_manager.update_campaign_counts(self.campaign_id, failed_delta=1)

                        self.logger_service.log_attempt(
                            phone=contact.clean_phone,
                            name=contact.display_name,
                            status=SendStatus.FAILED,
                            notes=result.notes,
                            chat_url=result.chat_url,
                        )
                        self.log(f"FAILED: {result.notes}")
                        self.current_index += 1
                        continue

                    # Mode: Step-by-Step with human confirmation
                    if self.mode in (DispatchMode.WEB_MANUAL_REVIEW, DispatchMode.STEP_BY_STEP):
                        contact.status = SendStatus.OPENED
                        contact.notes = result.notes
                        self.logger_service.log_attempt(
                            phone=contact.clean_phone,
                            name=contact.display_name,
                            status=SendStatus.OPENED,
                            notes=contact.notes,
                            chat_url=result.chat_url,
                        )

                        self.set_state(
                            ControllerState.AWAITING_CONFIRMATION,
                            f"Reviewing {contact.display_name}",
                        )
                        self.log(
                            f"Awaiting confirmation for {contact.display_name}: "
                            f"Review in WhatsApp Web and click 'Confirm Sent' or 'Skip'."
                        )

                        # Reset and wait for user's explicit action
                        self._step_decision_event.clear()
                        self._step_decision = None
                        self._step_decision_event.wait()

                        if self._stop_requested.is_set() or self._step_decision == "STOP":
                            break

                        if self._step_decision == "CONFIRM":
                            contact.status = SendStatus.MANUALLY_CONFIRMED
                            contact.notes = "Manually confirmed sent by operator"
                            sent_count += 1
                            already_sent_phones.add(contact.clean_phone)

                            if self.db_manager and self.campaign_id:
                                self.db_manager.record_message(
                                    self.campaign_id,
                                    contact.clean_phone,
                                    contact.display_name,
                                    SendStatus.MANUALLY_CONFIRMED.value,
                                    notes=contact.notes,
                                )
                                self.db_manager.update_campaign_counts(self.campaign_id, sent_delta=1)

                            self.logger_service.log_attempt(
                                phone=contact.clean_phone,
                                name=contact.display_name,
                                status=SendStatus.MANUALLY_CONFIRMED,
                                notes=contact.notes,
                                chat_url=result.chat_url,
                            )
                            self.log(f"Confirmed: {contact.display_name} marked as SENT.")
                        elif self._step_decision == "SKIP":
                            contact.status = SendStatus.SKIPPED
                            contact.notes = "Skipped by operator"
                            skipped_count += 1

                            if self.db_manager and self.campaign_id:
                                self.db_manager.record_message(
                                    self.campaign_id,
                                    contact.clean_phone,
                                    contact.display_name,
                                    SendStatus.SKIPPED.value,
                                    notes=contact.notes,
                                )
                                self.db_manager.update_campaign_counts(self.campaign_id, skipped_delta=1)

                            self.logger_service.log_attempt(
                                phone=contact.clean_phone,
                                name=contact.display_name,
                                status=SendStatus.SKIPPED,
                                notes=contact.notes,
                                chat_url=result.chat_url,
                            )
                            self.log(f"Skipped: {contact.display_name}.")

                        self.set_state(ControllerState.RUNNING, "Continuing queue")

                        if self.delay_seconds > 0:
                            time.sleep(min(self.delay_seconds, 2))

                    elif self.mode == DispatchMode.ASSISTED_PACING:
                        contact.status = SendStatus.OPENED
                        self.logger_service.log_attempt(
                            phone=contact.clean_phone,
                            name=contact.display_name,
                            status=SendStatus.OPENED,
                            notes="Chat opened in assisted pacing mode",
                            chat_url=result.chat_url,
                        )
                        for _ in range(self.delay_seconds):
                            if self._stop_requested.is_set():
                                break
                            self._pause_event.wait()
                            time.sleep(1)

                self.current_index += 1

            # Final state update
            if self._stop_requested.is_set():
                self.set_state(ControllerState.STOPPED, "Session terminated")
                if self.db_manager and self.campaign_id:
                    self.db_manager.update_campaign_status(self.campaign_id, "STOPPED")
                self.log(
                    f"Session stopped. Sent: {sent_count}, Failed: {failed_count}, Skipped: {skipped_count}."
                )
            else:
                self.set_state(ControllerState.FINISHED, "All contacts processed")
                if self.db_manager and self.campaign_id:
                    self.db_manager.update_campaign_status(self.campaign_id, "COMPLETED")
                self.log(
                    f"Batch complete! Summary: {sent_count} sent, {failed_count} failed, {skipped_count} skipped (Total: {total})."
                )
                if self.on_progress_update:
                    self.on_progress_update(total, total, None)

        except Exception as e:
            tb = traceback.format_exc()
            _logger.error("Unexpected error in sender controller: %s\n%s", e, tb)
            self.log(f"Unexpected error in sender controller: {str(e)}")
            self.set_state(ControllerState.STOPPED, f"Error: {e}")
            if self.db_manager and self.campaign_id:
                self.db_manager.update_campaign_status(self.campaign_id, "ERROR")
        finally:
            self.current_contact = None
