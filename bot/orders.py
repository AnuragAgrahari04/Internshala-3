"""
orders.py
---------
Business-logic layer for order placement.

Each function:
  1. Validates inputs (delegates to validators.py)
  2. Constructs the correct parameter dict for the exchange
  3. Calls client.place_order()
  4. Returns a normalised OrderResult dataclass

This layer is fully testable without a live exchange connection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_UP
from typing import Optional

from .client import BinanceFuturesClient
from .validators import (
    cross_validate,
    validate_order_type,
    validate_price,
    validate_quantity,
    validate_side,
    validate_stop_price,
    validate_symbol,
)

logger = logging.getLogger(__name__)


def _filter_by_type(symbol_info: dict, filter_type: str) -> Optional[dict]:
    for f in symbol_info.get("filters", []):
        if f.get("filterType") == filter_type:
            return f
    return None


def _precheck_min_notional(
    client: BinanceFuturesClient,
    symbol: str,
    quantity: Decimal,
    order_type: str,
    limit_price: Optional[Decimal] = None,
) -> None:
    """
    Reject too-small notional orders before hitting the signed order endpoint.

    If exchange metadata/price fetch fails, we do not block placement.
    """
    if order_type not in {"MARKET", "LIMIT"}:
        return

    try:
        symbol_info = client.get_symbol_info(symbol)
        notional_filter = _filter_by_type(symbol_info, "MIN_NOTIONAL")
        lot_filter = _filter_by_type(symbol_info, "LOT_SIZE")
        if not notional_filter:
            return

        min_notional = Decimal(str(notional_filter.get("notional", "0")))
        if min_notional <= 0:
            return

        if order_type == "LIMIT":
            if limit_price is None:
                return
            ref_price = limit_price
            price_source = "limit price"
        else:
            ref_price = Decimal(client.get_ticker_price(symbol))
            price_source = "latest ticker price"

        if ref_price <= 0:
            return

        current_notional = quantity * ref_price
        if current_notional >= min_notional:
            return

        required_qty = min_notional / ref_price
        step_size = Decimal("0")
        if lot_filter and lot_filter.get("stepSize") is not None:
            step_size = Decimal(str(lot_filter["stepSize"]))
        if step_size > 0:
            required_qty = (required_qty / step_size).to_integral_value(rounding=ROUND_UP) * step_size

        raise ValueError(
            "Order notional too small before API call: "
            f"qty*price ~= {current_notional:.4f} USDT using {price_source}; "
            f"minimum is {min_notional} USDT. "
            f"Increase --qty to at least {required_qty}."
        )
    except ValueError:
        raise
    except Exception as exc:
        logger.warning(
            "Skipping MIN_NOTIONAL precheck due to metadata/price lookup issue: %s",
            exc,
        )


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class OrderResult:
    """Normalised view of an exchange order response."""
    order_id: int
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    orig_qty: str
    executed_qty: str
    avg_price: str
    price: str
    stop_price: str
    time_in_force: str
    raw: dict = field(repr=False)   # full exchange response kept for logging

    @classmethod
    def from_response(cls, data: dict) -> "OrderResult":
        return cls(
            order_id=data.get("orderId", 0),
            client_order_id=data.get("clientOrderId", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            order_type=data.get("type", ""),
            status=data.get("status", ""),
            orig_qty=data.get("origQty", "0"),
            executed_qty=data.get("executedQty", "0"),
            avg_price=data.get("avgPrice", "0"),
            price=data.get("price", "0"),
            stop_price=data.get("stopPrice", "0"),
            time_in_force=data.get("timeInForce", ""),
            raw=data,
        )

    def summary_lines(self) -> list[str]:
        """Human-readable lines suitable for CLI output."""
        lines = [
            f"  Order ID       : {self.order_id}",
            f"  Client OID     : {self.client_order_id}",
            f"  Symbol         : {self.symbol}",
            f"  Side           : {self.side}",
            f"  Type           : {self.order_type}",
            f"  Status         : {self.status}",
            f"  Orig Qty       : {self.orig_qty}",
            f"  Executed Qty   : {self.executed_qty}",
            f"  Avg Fill Price : {self.avg_price}",
        ]
        if self.order_type == "LIMIT":
            lines.append(f"  Limit Price    : {self.price}")
            lines.append(f"  Time In Force  : {self.time_in_force}")
        if self.order_type == "STOP_MARKET":
            lines.append(f"  Stop Price     : {self.stop_price}")
        return lines


# ── Order placement functions ─────────────────────────────────────────────────

def place_market_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: str | float | Decimal,
) -> OrderResult:
    """Place a MARKET order on Binance Futures Testnet."""
    symbol = validate_symbol(symbol)
    side = validate_side(side)
    qty = validate_quantity(quantity)

    logger.info(
        "Placing MARKET order",
        extra={"x_symbol": symbol, "x_side": side, "x_qty": str(qty)},
    )

    _precheck_min_notional(
        client=client,
        symbol=symbol,
        quantity=qty,
        order_type="MARKET",
    )

    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": str(qty),
    }

    raw = client.place_order(**params)
    result = OrderResult.from_response(raw)

    logger.info(
        "MARKET order placed successfully",
        extra={
            "x_order_id": result.order_id,
            "x_status": result.status,
            "x_executed_qty": result.executed_qty,
            "x_avg_price": result.avg_price,
        },
    )
    return result


def place_limit_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: str | float | Decimal,
    price: str | float | Decimal,
    time_in_force: str = "GTC",
) -> OrderResult:
    """Place a LIMIT order on Binance Futures Testnet."""
    symbol = validate_symbol(symbol)
    side = validate_side(side)
    qty = validate_quantity(quantity)
    lmt_price = validate_price(price)
    cross_validate("LIMIT", lmt_price, None)

    logger.info(
        "Placing LIMIT order",
        extra={
            "x_symbol": symbol,
            "x_side": side,
            "x_qty": str(qty),
            "x_price": str(lmt_price),
            "x_tif": time_in_force,
        },
    )

    _precheck_min_notional(
        client=client,
        symbol=symbol,
        quantity=qty,
        order_type="LIMIT",
        limit_price=lmt_price,
    )

    params = {
        "symbol": symbol,
        "side": side,
        "type": "LIMIT",
        "quantity": str(qty),
        "price": str(lmt_price),
        "timeInForce": time_in_force,
    }

    raw = client.place_order(**params)
    result = OrderResult.from_response(raw)

    logger.info(
        "LIMIT order placed successfully",
        extra={
            "x_order_id": result.order_id,
            "x_status": result.status,
            "x_price": result.price,
        },
    )
    return result


def place_stop_market_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: str | float | Decimal,
    stop_price: str | float | Decimal,
) -> OrderResult:
    """
    Place a STOP_MARKET order (bonus: third order type).

    When the mark price hits `stop_price`, a market order fires automatically.
    Useful for stop-losses and breakout entries.
    """
    symbol = validate_symbol(symbol)
    side = validate_side(side)
    qty = validate_quantity(quantity)
    stp = validate_stop_price(stop_price)
    cross_validate("STOP_MARKET", None, stp)

    logger.info(
        "Placing STOP_MARKET order",
        extra={
            "x_symbol": symbol,
            "x_side": side,
            "x_qty": str(qty),
            "x_stop_price": str(stp),
        },
    )

    params = {
        "symbol": symbol,
        "side": side,
        "type": "STOP_MARKET",
        "quantity": str(qty),
        "stopPrice": str(stp),
        "closePosition": "false",
    }

    raw = client.place_order(**params)
    result = OrderResult.from_response(raw)

    logger.info(
        "STOP_MARKET order placed successfully",
        extra={"x_order_id": result.order_id, "x_status": result.status},
    )
    return result


# ── Dispatcher ────────────────────────────────────────────────────────────────

def place_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    order_type: str,
    quantity: str | float | Decimal,
    price: Optional[str | float | Decimal] = None,
    stop_price: Optional[str | float | Decimal] = None,
    time_in_force: str = "GTC",
) -> OrderResult:
    """
    Unified dispatcher — the CLI calls this instead of the individual helpers.
    Performs cross-validation before dispatching.
    """
    order_type = validate_order_type(order_type)
    p = validate_price(price)
    sp = validate_stop_price(stop_price)
    cross_validate(order_type, p, sp)

    if order_type == "MARKET":
        return place_market_order(client, symbol, side, quantity)
    if order_type == "LIMIT":
        return place_limit_order(client, symbol, side, quantity, price, time_in_force)
    if order_type == "STOP_MARKET":
        return place_stop_market_order(client, symbol, side, quantity, stop_price)

    raise ValueError(f"Unsupported order type: {order_type}")
