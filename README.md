# WhatsApp Bulk Messenger

A secure, compliant, and privacy-respecting desktop application built in Python 3.11+ using CustomTkinter for sending personalized WhatsApp messages to **opted-in contacts** on Windows PCs.

Supports two delivery providers:
1. **WhatsApp Web Click-to-Chat (Manual Review - Default):** Safe, official click-to-chat opening in your browser with operator inspection and manual confirm/skip. Zero setup or credentials required.
2. **piwapp (Experimental Pure-Python Automation):** Unattended direct messaging using the pure-Python `piwapp` library over WhatsApp multi-device WebSockets. Pairs via QR code scan without browser automation or external bridges.

---

## 🌟 Key Principles & Safety

1. **Default Safe Fallback (WhatsApp Web Manual Review):**
   Uses standard `https://web.whatsapp.com/send?phone=...&text=...` links to open each contact's conversation in your default web browser with the personalized message prefilled. The operator reviews the prefilled message, clicks Send in WhatsApp Web, and clicks **"Confirm Sent & Next"** in the app.
2. **Experimental Pure-Python Automation (`piwapp`):**
   Implemented as an alternative provider in `src/providers/piwapp_provider.py`. It uses `piwapp` to connect to WhatsApp's multi-device WebSocket protocol natively in Python (Noise handshake + Signal protocol encryption) without Selenium, Puppeteer, or external binaries.
3. **Delivery Integrity:**
   Distinguishes between `OPENED`, `MANUALLY_CONFIRMED`, `API_SENT`, `SKIPPED`, `ALREADY_PROCESSED`, and `FAILED`. In manual mode, `OPENED` means a chat window was opened in the browser and does **never count as sent**. Only explicit operator confirmation marks a message as sent.
4. **Campaign Identity & Safe Deduplication:**
   Each broadcast has an independent Campaign identity. Resuming an active campaign safely skips contacts already completed within that campaign. Starting a **✨ New Campaign** cleanly resets contact queues to `Pending` so you can broadcast new messages without being blocked by previous runs, while offering optional **Global History Suppression** if you want to skip any contact previously confirmed in `sent_log.csv`.

---

## ⚠️ Important Disclaimer & Limitations for piwapp

- **Unofficial Protocol:** `piwapp` is an unofficial third-party implementation of WhatsApp's multi-device protocol. WhatsApp does not officially endorse or support third-party socket clients.
- **Account Ban Risk:** Sending unsolicited messages, spamming, or sending at high frequencies using unofficial clients can result in temporary or permanent phone number bans by WhatsApp's anti-abuse algorithms.
- **Recommended Usage:** Use conservative cooldown delays (15s–30s minimum) and test with secondary/testing phone numbers. Only message users who have explicitly consented (opted in).
- **Socket Disconnections:** WhatsApp updates its binary protocol from time to time. If protocol mismatch occurs, socket connections may drop. You can always switch back to **WhatsApp Web Manual Review** at any time.

---

## 🚀 Features

- **Moroccan & International Phone Validation:**
  - Full support for Moroccan national formats (`06XXXXXXXX`, `07XXXXXXXX`, `05XXXXXXXX`, `+212...`, `00212...`, `661XXXXXX`).
  - Automatically converts Moroccan phone numbers to international standard E.164 digits (`2126XXXXXXXX`).
  - Supports international numbers with country codes (e.g., France `+33`, USA `+1`).
  - Filters out malformed numbers, non-numeric values, and invalid prefixes (`01`, `02`, etc.).
- **Message Personalization & Multilingual Support:**
  - Dynamic placeholders: `{name}`, `{phone}`, `{clean_phone}`, `{formatted_phone}`, plus any custom column from your CSV (e.g., `{city}`, `{order_id}`).
  - Built-in multilingual templates: **Moroccan Darija (الدارجة)**, **Arabic (العربية)**, **French (Français)**, and **English**.
  - Full UTF-8 support for Arabic script, French accents (`é`, `à`, `ç`), and emojis (👍, 🎉, 📦).
  - Real-time live preview for any selected contact.
- **CustomTkinter Responsive GUI:**
  - Responsive 2-column layout housed in a `CTkScrollableFrame` that fits all screen resolutions.
  - Dark and Light mode toggle.
  - Interactive table of contacts with status badges.
  - Pacing cooldown slider (3s to 60s) between messages.
  - Progress bar with percentage and remaining contact count.
  - Pause, Resume, and Stop controls.
- **Audit Logging & Campaign History:**
  - Real-time activity log console with one-click opening of `sent_log.csv`.
  - SQLite database storing campaigns and messages with masked CSV audit export (`21261****678`) to protect client privacy.

---

## 📁 Project Directory Structure

```
whtsap/
│
├── src/
│   ├── __init__.py               # Package declaration & metadata
│   ├── config.py                 # Configuration, limits, Moroccan rules, preset templates
│   ├── database.py               # SQLite DatabaseManager (campaign history, idempotency, opt-outs)
│   ├── diagnostics.py            # Diagnostic logging and window metrics
│   ├── models.py                 # Dataclasses: Contact, LogEntry, SendStatus, ImportSummary
│   ├── validator.py              # Moroccan & E.164 phone normalization & validation logic
│   ├── contact_manager.py        # CSV import, opt-in detection, suppression checks, deduplication
│   ├── message_engine.py         # Dynamic placeholders, UTF-8 encoding, WhatsApp URL generator
│   ├── logger_service.py         # Thread-safe audit trail logger (sent_log.csv in utf-8-sig)
│   ├── sender_controller.py      # Threaded controller state machine (Pacing, Pause, Resume, Stop)
│   ├── providers/                # Pluggable delivery provider layer
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract provider and ProviderResult interface
│   │   ├── web_provider.py       # WhatsApp Web manual review provider (DEFAULT)
│   │   └── piwapp_provider.py    # piwapp pure-Python socket automation provider (EXPERIMENTAL)
│   └── ui/
│       ├── __init__.py
│       ├── app.py                # Responsive CustomTkinter application window
│       └── components/
│           ├── __init__.py
│           ├── contact_view.py   # Contacts table and import summary cards with status badges
│           ├── message_editor.py # Template composer, variable buttons, live preview
│           ├── control_panel.py  # Broadcast controls, progress bar, manual confirm/skip & piwapp pairing
│           └── log_console.py    # Real-time console log and CSV viewer shortcut
│
├── tests/
│   ├── __init__.py
│   ├── test_validator.py             # Phone normalization and validation tests
│   ├── test_contact_manager.py       # CSV parser, consent detection, suppression checks
│   ├── test_message_engine.py        # Multilingual interpolation and URL encoding
│   ├── test_sender_controller.py     # Controller states, pacing, and human review loop
│   ├── test_ui_layout.py             # Responsive layout and scrollable containers
│   ├── test_database.py              # SQLite campaigns and audit log export
│   └── test_piwapp_provider.py       # piwapp provider tests with mock clients
│
├── sample_contacts.csv           # Ready-to-use sample dataset with opt-in status
├── sent_log.csv                  # Audit log recording outcomes
├── requirements.txt              # Project dependencies
├── .gitignore                    # Version control ignore rules
├── README.md                     # Documentation and user manual
└── main.py                       # Application entry point
```

---

## 🛠️ Installation & Execution (Windows 10/11)

### 1. Prerequisites
- **Python 3.10+** (Python 3.11 or newer recommended).
  Ensure **"Add python.exe to PATH"** was checked during Python installation.

### 2. Install Dependencies
Open PowerShell or Command Prompt in the project folder:
```powershell
cd C:\Users\mee\OneDrive\Desktop\whtsap
pip install -r requirements.txt
```

### 3. Launch the Application
```powershell
python main.py
```

---

## 📖 How to Use

### Mode 1: WhatsApp Web Manual Review (Default, Recommended)
1. **Import Contacts:** Click `📂 Import CSV` and select `sample_contacts.csv` (or your own CSV).
2. **Write or Select a Template:** Choose a preset (Arabic, Darija, French, English) or type your custom message with placeholders like `{name}` or `{city}`.
3. **Certify Consent:** Check the consent certification checkbox.
4. **Start Broadcast:** Click `▶️ Start Broadcast`.
5. **Review & Confirm:**
   - WhatsApp Web opens in your browser with the recipient's chat and prefilled message.
   - Click **Send** in WhatsApp Web.
   - Return to the app and click `✅ Confirm Sent & Next`.

### Mode 2: piwapp Pure-Python Automation (Experimental)
1. In the **Delivery Provider** dropdown, select **piwapp (Experimental Automation)**.
2. Click `🔗 Connect / Pair QR`.
3. A pairing window will appear with a live QR code:
   - Open WhatsApp on your mobile phone.
   - Go to **Linked Devices > Link a Device**.
   - Scan the QR code shown on screen.
4. Once paired, the status will show **piwapp: Connected (+212...)**.
5. Set your delay cooldown (e.g. 15s–20s conservative delay).
6. Check the consent certification checkbox and click `▶️ Start Broadcast`.
7. Messages will be sent automatically directly through WhatsApp sockets without opening browser tabs.

---

## 🧪 Running Unit & Integration Tests

Run the full automated test suite:
```powershell
python -m unittest discover tests
```
All 64 tests run fully offline with mocks, verifying phone validation, consent enforcement, SQLite campaign idempotency, pause/resume state machine, provider selection, and piwapp provider behavior.
