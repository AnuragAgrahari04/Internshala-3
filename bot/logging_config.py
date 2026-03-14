"""
logging_config.py
-----------------
Sets up structured logging:
  - Human-readable console output (INFO+)
    - Structured JSON file output (DEBUG+) → trading_bot.log
    - Order-type specific JSON file output for MARKET and LIMIT orders
"""

import logging
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path


LOG_FILE = Path("trading_bot.log")
LOGS_DIR = Path("logs")
MARKET_LOG_FILE = LOGS_DIR / "market_order.log"
LIMIT_LOG_FILE = LOGS_DIR / "limit_order.log"


class OrderTypeFilter(logging.Filter):
    """Allow records tagged with a specific order type."""

    def __init__(self, order_type: str) -> None:
        super().__init__()
        self.order_type = order_type

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "x_order_type", None) == self.order_type


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
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

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

    market_handler = logging.FileHandler(MARKET_LOG_FILE, encoding="utf-8")
    market_handler.setLevel(logging.DEBUG)
    market_handler.setFormatter(JSONFormatter())
    market_handler.addFilter(OrderTypeFilter("MARKET"))

    limit_handler = logging.FileHandler(LIMIT_LOG_FILE, encoding="utf-8")
    limit_handler.setLevel(logging.DEBUG)
    limit_handler.setFormatter(JSONFormatter())
    limit_handler.addFilter(OrderTypeFilter("LIMIT"))

    # Avoid duplicate handlers if called multiple times (e.g., in tests)
    if not root.handlers:
        root.addHandler(console)
        root.addHandler(file_handler)
        root.addHandler(market_handler)
        root.addHandler(limit_handler)
    else:
        root.handlers.clear()
        root.addHandler(console)
        root.addHandler(file_handler)
        root.addHandler(market_handler)
        root.addHandler(limit_handler)
