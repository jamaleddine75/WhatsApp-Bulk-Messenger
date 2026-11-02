"""Configuration and constants for WhatsApp Bulk Messenger."""

import os
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

# Paths
DEFAULT_LOG_FILE = "sent_log.csv"
SAMPLE_CONTACTS_FILE = "sample_contacts.csv"

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

