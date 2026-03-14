"""
logging_config.py
-----------------
Sets up dual logging:
  - Human-readable console output (INFO+)
  - Structured JSON file output (DEBUG+) → trading_bot.log
"""

import logging
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path


LOG_FILE = Path("trading_bot.log")


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach any extra fields passed via `extra=`
        for key, value in record.__dict__.items():
            if key.startswith("x_"):          # convention: extra keys prefixed x_
                payload[key[2:]] = value

        if record.exc_info:
            payload["exception"] = traceback.format_exception(*record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging(log_file: Path = LOG_FILE, console_level: int = logging.INFO) -> None:
    """
    Call once at application startup.
    All modules should then use `logging.getLogger(__name__)`.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)           # capture everything; handlers filter

    # ── Console handler ────────────────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    # ── File handler (JSON, always DEBUG) ──────────────────────────────────────
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())

    # Avoid duplicate handlers if called multiple times (e.g., in tests)
    if not root.handlers:
        root.addHandler(console)
        root.addHandler(file_handler)
    else:
        root.handlers.clear()
        root.addHandler(console)
        root.addHandler(file_handler)
