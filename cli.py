#!/usr/bin/env python3
"""
cli.py
------
Command-line interface for the Binance Futures Testnet trading bot.

Usage examples
--------------
# Market buy
python cli.py order --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

# Limit sell
python cli.py order --symbol BTCUSDT --side SELL --type LIMIT --qty 0.001 --price 100000

# Stop-market (bonus order type)
python cli.py order --symbol BTCUSDT --side SELL --type STOP_MARKET --qty 0.001 --stop-price 90000

# Account info
python cli.py account

# List open orders
python cli.py open-orders --symbol BTCUSDT
"""

from __future__ import annotations

import os
import sys
import logging
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from bot import BinanceFuturesClient, BinanceAPIError, place_order, setup_logging

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv(override=True)               # prefer project .env over stale shell vars
setup_logging()
logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(
    name="trading-bot",
    help="Binance Futures Testnet trading bot — place orders from your terminal.",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


# ── Shared credential resolution ──────────────────────────────────────────────

def _get_client() -> BinanceFuturesClient:
    api_key = os.getenv("BINANCE_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_API_SECRET", "").strip()

    if not api_key or not api_secret:
        console.print(
            "[bold red]Error:[/] BINANCE_API_KEY and BINANCE_API_SECRET must be set.\n"
            "  • Export them in your shell, or\n"
            "  • Create a [bold].env[/] file in the project root:\n\n"
            "    BINANCE_API_KEY=your_key\n"
            "    BINANCE_API_SECRET=your_secret\n"
        )
        raise typer.Exit(code=1)

    return BinanceFuturesClient(api_key=api_key, api_secret=api_secret)


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command("order")
def place_order_cmd(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT"),
    side: str = typer.Option(..., "--side", help="BUY or SELL"),
    order_type: str = typer.Option(..., "--type", "-t", help="MARKET | LIMIT | STOP_MARKET"),
    qty: str = typer.Option(..., "--qty", "-q", help="Order quantity (base asset)"),
    price: Optional[str] = typer.Option(None, "--price", "-p", help="Limit price (LIMIT orders)"),
    stop_price: Optional[str] = typer.Option(None, "--stop-price", help="Stop trigger price (STOP_MARKET)"),
    tif: str = typer.Option("GTC", "--tif", help="Time-in-force for LIMIT orders: GTC | IOC | FOK"),
):
    """Place a MARKET, LIMIT, or STOP_MARKET order on Binance Futures Testnet."""

    # ── Print request summary ─────────────────────────────────────────────────
    req_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    req_table.add_column(style="dim cyan")
    req_table.add_column(style="bold white")
    req_table.add_row("Symbol", symbol.upper())
    req_table.add_row("Side", side.upper())
    req_table.add_row("Type", order_type.upper())
    req_table.add_row("Quantity", qty)
    if price:
        req_table.add_row("Price", price)
    if stop_price:
        req_table.add_row("Stop Price", stop_price)
    if order_type.upper() == "LIMIT":
        req_table.add_row("Time-in-Force", tif)

    console.print(Panel(req_table, title="[bold yellow]▶ Order Request[/]", border_style="yellow"))

    # ── Execute ───────────────────────────────────────────────────────────────
    client = _get_client()
    try:
        result = place_order(
            client=client,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=qty,
            price=price,
            stop_price=stop_price,
            time_in_force=tif,
        )
    except ValueError as exc:
        console.print(f"\n[bold red]✗ Validation Error:[/] {exc}\n")
        logger.warning("Order rejected by local validation: %s", exc)
        raise typer.Exit(code=2)
    except BinanceAPIError as exc:
        if exc.code == -1022:
            console.print(
                "\n[bold red]✗ Binance API Error:[/] Signature is invalid (code -1022).\n"
                "Check that your [bold]BINANCE_API_KEY[/] and [bold]BINANCE_API_SECRET[/] are from "
                "[bold]Binance Futures Testnet[/] and belong to the same key pair.\n"
            )
        else:
            console.print(f"\n[bold red]✗ Binance API Error:[/] {exc}\n")
        logger.error("Binance API error while placing order: %s", exc, exc_info=True)
        raise typer.Exit(code=3)
    except Exception as exc:
        console.print(f"\n[bold red]✗ Unexpected Error:[/] {exc}\n")
        logger.exception("Unexpected error while placing order")
        raise typer.Exit(code=4)

    # ── Print response ────────────────────────────────────────────────────────
    res_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    res_table.add_column(style="dim cyan")
    res_table.add_column(style="bold white")
    for line in result.summary_lines():
        label, _, value = line.partition(":")
        res_table.add_row(label.strip(), value.strip())

    console.print(Panel(res_table, title="[bold green]✓ Order Response[/]", border_style="green"))
    console.print(f"\n[bold green]✓ Order placed successfully![/]  ID: [white]{result.order_id}[/]\n")


@app.command("account")
def account_cmd():
    """Display futures account balances and unrealised PnL."""
    client = _get_client()
    try:
        data = client.get_account()
    except BinanceAPIError as exc:
        if exc.code == -1022:
            console.print(
                "[bold red]✗ API Error:[/] Signature is invalid (code -1022). "
                "Verify your Futures Testnet API key/secret pair in `.env`."
            )
        else:
            console.print(f"[bold red]✗ API Error:[/] {exc}")
        raise typer.Exit(code=3)

    assets = [a for a in data.get("assets", []) if float(a.get("walletBalance", 0)) > 0]
    table = Table(title="Futures Account Balances", box=box.ROUNDED)
    table.add_column("Asset", style="cyan")
    table.add_column("Wallet Balance", justify="right")
    table.add_column("Unrealised PnL", justify="right")
    table.add_column("Margin Balance", justify="right")

    for a in assets:
        pnl = float(a.get("unrealizedProfit", 0))
        pnl_str = f"[green]{pnl:.4f}[/]" if pnl >= 0 else f"[red]{pnl:.4f}[/]"
        table.add_row(
            a["asset"],
            f"{float(a['walletBalance']):.4f}",
            pnl_str,
            f"{float(a.get('marginBalance', 0)):.4f}",
        )

    console.print(table)


@app.command("open-orders")
def open_orders_cmd(
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s", help="Filter by symbol"),
):
    """List all open orders (optionally filtered by symbol)."""
    client = _get_client()
    try:
        orders = client.get_open_orders(symbol=symbol.upper() if symbol else None)
    except BinanceAPIError as exc:
        if exc.code == -1022:
            console.print(
                "[bold red]✗ API Error:[/] Signature is invalid (code -1022). "
                "Verify your Futures Testnet API key/secret pair in `.env`."
            )
        else:
            console.print(f"[bold red]✗ API Error:[/] {exc}")
        raise typer.Exit(code=3)

    if not orders:
        console.print("[dim]No open orders found.[/]")
        return

    table = Table(title="Open Orders", box=box.ROUNDED)
    for col in ("Order ID", "Symbol", "Side", "Type", "Price", "Qty", "Status"):
        table.add_column(col, style="cyan" if col == "Symbol" else "white")

    for o in orders:
        side_style = "green" if o["side"] == "BUY" else "red"
        table.add_row(
            str(o["orderId"]),
            o["symbol"],
            f"[{side_style}]{o['side']}[/]",
            o["type"],
            o.get("price", "—"),
            o.get("origQty", "—"),
            o["status"],
        )

    console.print(table)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
