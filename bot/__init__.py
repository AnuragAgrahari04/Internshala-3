"""
trading_bot.bot
---------------
Public re-exports for the bot package.
"""

from .client import BinanceFuturesClient, BinanceAPIError
from .orders import OrderResult, place_order
from .logging_config import setup_logging

__all__ = [
    "BinanceFuturesClient",
    "BinanceAPIError",
    "OrderResult",
    "place_order",
    "setup_logging",
]
