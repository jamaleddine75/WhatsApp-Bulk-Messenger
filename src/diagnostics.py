"""Diagnostic logging system for WhatsApp Bulk Messenger."""

import logging
import sys
import traceback
from typing import Callable, Optional

# Logger name
LOGGER_NAME = "WhatsAppMessenger"

_logger = logging.getLogger(LOGGER_NAME)
_logger.setLevel(logging.DEBUG)

# Console handler (stdout)
if not _logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    _logger.addHandler(console_handler)


class UILogHandler(logging.Handler):
    """Logging handler that routes messages to a UI callback."""

    def __init__(self, callback: Callable[[str], None]):
        super().__init__()
        self.callback = callback
        self.setFormatter(
            logging.Formatter("[%(levelname)s] %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.callback(msg)
        except Exception:
            self.handleError(record)


def get_logger() -> logging.Logger:
    """Return the application logger."""
    return _logger


def attach_ui_log_callback(callback: Callable[[str], None]) -> UILogHandler:
    """Attach a UI callback to receive log messages."""
    handler = UILogHandler(callback)
    handler.setLevel(logging.INFO)
    _logger.addHandler(handler)
    return handler


def log_startup_diagnostics(
    screen_w: int,
    screen_h: int,
    win_w: int,
    win_h: int,
    scaling: float,
) -> None:
    """Log environment and window geometry on startup."""
    _logger.info(
        "Application startup: Screen size=%dx%d, Initial window=%dx%d, Scaling=%.2f",
        screen_w,
        screen_h,
        win_w,
        win_h,
        scaling,
    )


def log_exception(msg: str, exc: Optional[Exception] = None) -> None:
    """Log an exception with its complete traceback."""
    if exc:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _logger.error("%s\n%s", msg, tb)
    else:
        _logger.error("%s\n%s", msg, traceback.format_exc())

