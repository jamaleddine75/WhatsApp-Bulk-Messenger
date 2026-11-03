"""Configuration and constants for WhatsApp Bulk Messenger."""

import os
from pathlib import Path
import shutil
import sys
from typing import Dict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Application Metadata
APP_NAME = "WhatsApp Bulk Messenger"
APP_VERSION = "1.0.0"
WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION} (Authorized Contacts Only)"
WINDOW_WIDTH = 1060
WINDOW_HEIGHT = 650
MIN_WINDOW_WIDTH = 840
MIN_WINDOW_HEIGHT = 500


def get_resource_path(relative_path: str = "") -> Path:
    """Return absolute path to resource, working for dev and PyInstaller (_MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    return base_path / relative_path if relative_path else base_path


def get_user_data_dir() -> Path:
    """Return dedicated per-user writable data directory (%LOCALAPPDATA%/WhatsAppBulkMessenger)."""
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data) / "WhatsAppBulkMessenger"
        else:
            base_dir = Path.home() / "AppData" / "Local" / "WhatsAppBulkMessenger"
    else:
        base_dir = Path.home() / ".whatsapp_messenger"

    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def migrate_existing_data(target_dir: Path) -> None:
    """Safely migrate any existing database, logs, sessions, or templates into user data dir.

    Preserves existing user data during updates and never overwrites active databases.
    """
    dev_root = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    files_to_migrate = [
        "whatsapp_messenger.db",
        "sent_log.csv",
        "piwapp_session.json",
        "piwapp_session.json.keys",
        "piwapp_version.json",
    ]

    for fname in files_to_migrate:
        src = dev_root / fname
        dst = target_dir / fname
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

    # Migrate or seed templates
    templates_dst = target_dir / "templates"
    templates_dst.mkdir(parents=True, exist_ok=True)

    templates_src = dev_root / "data" / "templates"
    bundled_templates = get_resource_path("data/templates")

    for tsrc in (templates_src, bundled_templates):
        if tsrc.exists() and tsrc.is_dir():
            for tfile in tsrc.glob("*.json"):
                target_file = templates_dst / tfile.name
                if not target_file.exists():
                    try:
                        shutil.copy2(tfile, target_file)
                    except Exception:
                        pass


# Per-User Persistent Application Paths
USER_DATA_DIR: Path = get_user_data_dir()
migrate_existing_data(USER_DATA_DIR)

DEFAULT_DB_FILE: str = str(USER_DATA_DIR / "whatsapp_messenger.db")
DEFAULT_LOG_FILE: str = str(USER_DATA_DIR / "sent_log.csv")
DEFAULT_TEMPLATES_DIR: Path = USER_DATA_DIR / "templates"
DEFAULT_SESSION_FILE: str = str(USER_DATA_DIR / "piwapp_session.json")
DEFAULT_VERSION_FILE: str = str(USER_DATA_DIR / "piwapp_version.json")
SAMPLE_CONTACTS_FILE: str = str(get_resource_path("sample_contacts.csv"))

# Pacing and Limits
MIN_DELAY_SECONDS = 3
MAX_DELAY_SECONDS = 60
DEFAULT_DELAY_SECONDS = 8
MAX_RECOMMENDED_BATCH = 200

# WhatsApp Click-to-Chat Endpoints (Manual Web Review)
WHATSAPP_WEB_URL = "https://web.whatsapp.com/send"
WHATSAPP_API_URL = "https://api.whatsapp.com/send"

# Official WhatsApp Business Cloud API (Automated Sending)
WHATSAPP_CLOUD_API_BASE = "https://graph.facebook.com"
DEFAULT_CLOUD_API_VERSION = "v20.0"
ENV_WHATSAPP_TOKEN = "WHATSAPP_API_TOKEN"
ENV_WHATSAPP_PHONE_NUMBER_ID = "WHATSAPP_PHONE_NUMBER_ID"
ENV_WHATSAPP_BUSINESS_ACCOUNT_ID = "WHATSAPP_BUSINESS_ACCOUNT_ID"

# Moroccan Dialing Rules
DEFAULT_COUNTRY_CODE = "212"
MOROCCO_NATIONAL_LENGTH = 9  # Number of digits after country code 212
MOROCCO_VALID_FIRST_DIGITS = {"5", "6", "7"}

# Consent & Compliance Text
CONSENT_CONFIRMATION_TEXT = (
    "I confirm that all recipients listed here have provided explicit consent (opted-in) "
    "to receive these communications, and that this broadcast complies with applicable "
    "data protection laws and WhatsApp's Terms of Service."
)

DELIVERY_DISCLAIMER = (
    "NOTICE: Opening a chat in WhatsApp Web only prefills text and does not send or deliver messages. "
    "In Manual mode, messages are recorded as MANUALLY_CONFIRMED by the operator. "
    "In Automated mode, messages are dispatched via official WhatsApp Cloud API and recorded as API_SENT "
    "with a unique WhatsApp Message ID (wamid); delivery receipts are confirmed asynchronously."
)

# Built-in Multilingual Templates
PRESET_TEMPLATES: Dict[str, str] = {
    "French - Confirmation de Commande / RDV": (
        "Bonjour {name},\n\n"
        "Nous vous remercions pour votre confiance. Votre demande a bien été enregistrée.\n"
        "N'hésitez pas à nous répondre directement sur ce numéro si vous avez la moindre question.\n\n"
        "Bien cordialement,\nL'équipe"
    ),
    "Arabic - تأكيد الخدمة والتواصل": (
        "السلام عليكم ورحمة الله وبركاته {name}،\n\n"
        "نود إعلامكم بتحديث مهم بخصوص طلبكم لدينا. نحن دائماً رهن إشارتكم لأي استفسار.\n\n"
        "مع خالص التحيات والتقدير."
    ),
    "Moroccan Darija - سلام وتأكيد الطلب": (
        "Salam {name}!\n\n"
        "Labas alik? Kantmna tkoun bikhir. Hada rissala tawkidiya bkhousous talab dyalk m3ana.\n"
        "Ila kan khassk ay ma3louma wla stifsar, hna f lkhedma.\n\n"
        "Choukran bzaf w nhark mabrouk!"
    ),
    "English - Customer Update / Notification": (
        "Hello {name},\n\n"
        "Thank you for being our valued customer. This is a quick confirmation update regarding your account.\n"
        "Please feel free to reply if you need any assistance.\n\n"
        "Best regards,\nThe Team"
    ),
}

