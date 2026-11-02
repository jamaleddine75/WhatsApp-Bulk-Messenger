"""Phone number validation and normalization for WhatsApp."""

import re
from typing import Tuple
from src.config import DEFAULT_COUNTRY_CODE, MOROCCO_NATIONAL_LENGTH, MOROCCO_VALID_FIRST_DIGITS


def normalize_and_validate_phone(
    raw_phone: str, default_country: str = DEFAULT_COUNTRY_CODE
) -> Tuple[bool, str, str, str]:
    """Validate and normalize a phone number for WhatsApp Web.

    Supports Moroccan phone formats and standard international E.164 numbers.

    Returns:
        Tuple of (is_valid, clean_e164_digits, formatted_display, error_message)
        where clean_e164_digits contains only digits without '+' or symbols,
        matching WhatsApp click-to-chat URL requirements.
    """
    if not raw_phone or not str(raw_phone).strip():
        return False, "", "", "Empty phone number"

    phone_str = str(raw_phone).strip()

    # Reject if it contains alphabetic characters
    if re.search(r"[a-zA-Z]", phone_str):
        return False, "", phone_str, "Contains invalid alphabetic characters"

    # Detect if user entered leading '+' or '00'
    has_plus = phone_str.startswith("+")
    has_double_zero = phone_str.startswith("00")

    # Remove all non-numeric characters
    digits = re.sub(r"\D", "", phone_str)

    if not digits:
        return False, "", phone_str, "No digits found"

    # If it started with 00, treat as international prefix
    if has_double_zero and digits.startswith("00"):
        digits = digits[2:]

    # --- 1. MOROCCAN NUMBER HANDLING ---
    # Case A: Domestic format with leading 0 (e.g. 0612345678, 0712345678, 0522123456) -> 10 digits total
    if (
        not has_plus
        and len(digits) == 1 + MOROCCO_NATIONAL_LENGTH
        and digits.startswith("0")
    ):
        national = digits[1:]
        first_digit = national[0]
        if first_digit not in MOROCCO_VALID_FIRST_DIGITS:
            return (
                False,
                "",
                phone_str,
                f"Invalid Moroccan prefix '0{first_digit}'. Expected 05, 06, or 07.",
            )
        clean = f"{default_country}{national}"
        formatted = f"+{default_country} {national[0:3]}-{national[3:]}"
        return True, clean, formatted, ""

    # Case B: Moroccan domestic missing the leading 0 (e.g. 612345678, 712345678, 9 digits)
    if (
        not has_plus
        and len(digits) == MOROCCO_NATIONAL_LENGTH
        and digits[0] in MOROCCO_VALID_FIRST_DIGITS
    ):
        clean = f"{default_country}{digits}"
        formatted = f"+{default_country} {digits[0:3]}-{digits[3:]}"
        return True, clean, formatted, ""

    # Case C: Moroccan number starting with country code 212 (e.g. 212612345678, +212612345678)
    if digits.startswith(default_country):
        national = digits[len(default_country) :]
        if len(national) != MOROCCO_NATIONAL_LENGTH:
            return (
                False,
                "",
                phone_str,
                f"Moroccan number has {len(national)} digits after +{default_country}. Expected exactly {MOROCCO_NATIONAL_LENGTH}.",
            )
        first_digit = national[0] if national else ""
        if first_digit not in MOROCCO_VALID_FIRST_DIGITS:
            return (
                False,
                "",
                phone_str,
                f"Invalid Moroccan prefix '+{default_country}{first_digit}'. Expected +212 followed by 5, 6, or 7.",
            )
        clean = digits
        formatted = f"+{default_country} {national[0:3]}-{national[3:]}"
        return True, clean, formatted, ""

    # --- 2. GENERAL INTERNATIONAL E.164 HANDLING ---
    # International numbers must be between 8 and 15 digits total (ITU-T E.164)
    if 8 <= len(digits) <= 15:
        # If it has a '+' or was prefixed with 00 or has standard international length
        if has_plus or has_double_zero or len(digits) >= 10:
            formatted = f"+{digits}"
            return True, digits, formatted, ""
        else:
            return (
                False,
                "",
                phone_str,
                f"Ambiguous local number '{phone_str}'. Please include country code (+ or 00).",
            )

    return (
        False,
        "",
        phone_str,
        f"Invalid phone length ({len(digits)} digits). Must be 8 to 15 digits.",
    )

