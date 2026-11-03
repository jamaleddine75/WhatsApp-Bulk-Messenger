# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for WhatsApp Bulk Messenger.

Produces a standalone, production-ready Windows executable without console window.
Bundles CustomTkinter assets, piwapp submodules, default message templates, and app icon.
User data (database, session credentials, sent logs, custom templates) is strictly isolated
to %LOCALAPPDATA%\\WhatsAppBulkMessenger at runtime.
"""

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Base directory of the repository
BASE_DIR = Path(os.path.abspath(SPECPATH))

# Collect dynamic data files from packages
customtkinter_datas = collect_data_files("customtkinter")
piwapp_datas = collect_data_files("piwapp")

# Collect submodules
piwapp_submodules = collect_submodules("piwapp")

# Application data files to bundle (read-only assets and presets)
datas = [
    (str(BASE_DIR / "data" / "templates"), "data/templates"),
    (str(BASE_DIR / "app_icon.ico"), "."),
]
datas += customtkinter_datas
datas += piwapp_datas

# Hidden imports that may not be detected by static analysis
hidden_imports = [
    "customtkinter",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "qrcode",
    "qrcode.image",
    "qrcode.image.pil",
    "cryptography",
    "pydantic",
    "websockets",
    "requests",
    "urllib3",
    "sqlite3",
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "src.config",
    "src.contact_manager",
    "src.database",
    "src.diagnostics",
    "src.logger_service",
    "src.message_engine",
    "src.models",
    "src.template_manager",
    "src.sender_controller",
    "src.providers.base",
    "src.providers.piwapp_provider",
    "src.providers.web_provider",
    "src.ui.app",
    "src.ui.components",
] + piwapp_submodules

a = Analysis(
    ["main.py"],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "unittest",
        "pytest",
        "tests",
        "test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WhatsAppBulkMessenger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(BASE_DIR / "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WhatsAppBulkMessenger",
)

