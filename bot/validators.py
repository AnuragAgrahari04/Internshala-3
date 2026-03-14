"""
validators.py
-------------
Pure-function validation helpers.
Each function raises ValueError with a human-readable message on failure
and returns the (possibly coerced) value on success.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

# ── Allowed enumerations ───────────────────────────────────────────────────────
VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_MARKET"}   # extendable


def validate_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if len(s) < 3 or not s.isalnum():
        raise ValueError(
            f"Invalid symbol '{symbol}'. Must be alphanumeric, e.g. BTCUSDT."
        )
    return s


def validate_side(side: str) -> str:
    s = side.strip().upper()
    if s not in VALID_SIDES:
        raise ValueError(
            f"Invalid side '{side}'. Must be one of: {', '.join(sorted(VALID_SIDES))}."
        )
    return s


def validate_order_type(order_type: str) -> str:
    t = order_type.strip().upper()
    if t not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type '{order_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )
    return t


def validate_quantity(quantity: str | float | Decimal) -> Decimal:
    try:
        q = Decimal(str(quantity))
    except InvalidOperation:
        raise ValueError(f"Invalid quantity '{quantity}'. Must be a positive number.")
    if q <= 0:
        raise ValueError(f"Quantity must be greater than zero, got {q}.")
    return q


def validate_price(price: Optional[str | float | Decimal]) -> Optional[Decimal]:
    """Returns None for MARKET orders where price is legitimately absent."""
    if price is None:
        return None
    try:
        p = Decimal(str(price))
    except InvalidOperation:
        raise ValueError(f"Invalid price '{price}'. Must be a positive number.")
    if p <= 0:
        raise ValueError(f"Price must be greater than zero, got {p}.")
    return p


def validate_stop_price(stop_price: Optional[str | float | Decimal]) -> Optional[Decimal]:
    return validate_price(stop_price)   # same rules, different semantic label


def cross_validate(order_type: str, price: Optional[Decimal], stop_price: Optional[Decimal]) -> None:
    """Raise ValueError for illogical combinations."""
    if order_type == "LIMIT" and price is None:
        raise ValueError("LIMIT orders require a --price.")
    if order_type == "MARKET" and price is not None:
        raise ValueError("MARKET orders must not have a --price (it is ignored by the exchange).")
    if order_type == "STOP_MARKET" and stop_price is None:
        raise ValueError("STOP_MARKET orders require a --stop-price.")
