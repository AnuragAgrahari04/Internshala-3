# 🤖 Binance Futures Testnet Trading Bot

A clean, production-grade Python CLI trading bot for Binance Futures Testnet (USDT-M).  
Supports Market, Limit, and Stop-Market orders with structured logging, full error handling, and a rich terminal UI.

---

## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py          # Package exports
│   ├── client.py            # Binance REST API layer (auth, signing, HTTP)
│   ├── orders.py            # Order placement logic + OrderResult dataclass
│   ├── validators.py        # Input validation (pure functions, no I/O)
│   └── logging_config.py   # Dual logging: console (INFO) + JSON file (DEBUG)
├── cli.py                   # Typer CLI entry point
├── logs/                    # Sample log files (market + limit orders)
├── .env.example             # Template for credentials
├── requirements.txt
└── README.md
```

**Architecture principle:** the CLI layer (`cli.py`) calls the business logic layer (`orders.py`), which calls the API layer (`client.py`). Each layer is independently testable.

---

## Setup

### 1. Get Testnet Credentials

1. Visit [https://testnet.binancefuture.com](https://testnet.binancefuture.com)
2. Log in or register with your Binance account
3. Click **API Management** → **Create API Key**
4. Copy your **API Key** and **Secret Key** — store them securely

### 2. Clone & Install

```bash
git clone https://github.com/AnuragAgrahari04/Internshala-3.git
cd trading_bot

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Credentials

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```env
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
```

Alternatively, export them directly in your shell:

```bash
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"
```

---

## How to Run

### Place a MARKET order

```bash
# Buy 0.001 BTC at market price
python cli.py order --symbol BTCUSDT --side BUY --type MARKET --qty 0.001

# Sell 0.01 ETH at market price
python cli.py order --symbol ETHUSDT --side SELL --type MARKET --qty 0.01
```

### Place a LIMIT order

```bash
# Sell 0.001 BTC when price reaches $90,000 (GTC = Good Till Cancelled)
python cli.py order --symbol BTCUSDT --side SELL --type LIMIT --qty 0.001 --price 90000

# Buy 0.001 BTC with Immediate-Or-Cancel fill behaviour
python cli.py order --symbol BTCUSDT --side BUY --type LIMIT --qty 0.001 --price 80000 --tif IOC
```

### Place a STOP_MARKET order (bonus order type)

```bash
# Trigger a market SELL if price drops below $82,000 (stop-loss)
python cli.py order --symbol BTCUSDT --side SELL --type STOP_MARKET --qty 0.001 --stop-price 82000
```

### View account balances

```bash
python cli.py account
```

### List open orders

```bash
python cli.py open-orders                    # all symbols
python cli.py open-orders --symbol BTCUSDT   # filtered
```

### Cancel an open order

```bash
python cli.py cancel-order --symbol BTCUSDT --order-id 123456789
```

### Built-in help

```bash
python cli.py --help
python cli.py order --help
```

---

## Sample Terminal Output

```
╭─────────────── ▶ Order Request ─────────────────╮
│  Symbol    BTCUSDT                               │
│  Side      BUY                                   │
│  Type      MARKET                                │
│  Quantity  0.001                                 │
╰──────────────────────────────────────────────────╯

╭─────────────── ✓ Order Response ────────────────╮
│  Order ID        3951823011                      │
│  Client OID      x-Cb7ytekJfbb12345678           │
│  Symbol          BTCUSDT                         │
│  Side            BUY                             │
│  Type            MARKET                          │
│  Status          FILLED                          │
│  Orig Qty        0.001                           │
│  Executed Qty    0.001                           │
│  Avg Fill Price  84251.50000                     │
╰──────────────────────────────────────────────────╯

✓ Order placed successfully!  ID: 3951823011
```

---

## Logging

Every run appends to `trading_bot.log` in the project root.  
Each line is a self-contained JSON object — easy to ingest into any log aggregator (Datadog, CloudWatch, ELK).

Successful MARKET and LIMIT order activity is also written automatically to dedicated files in `logs/`:
- `logs/market_order.log` — MARKET order lifecycle entries
- `logs/limit_order.log` — LIMIT order lifecycle entries

```json
{"timestamp": "2026-03-14T13:34:11.72+00:00", "level": "INFO", "logger": "bot.orders", 
 "message": "MARKET order placed successfully", "order_id": 12809540875, "status": "FILLED"}
```

The repository already includes example entries in those files, and any new MARKET or LIMIT orders will append to them automatically.

---

## Validation & Error Handling

| Scenario | Behaviour |
|---|---|
| Missing `--price` on LIMIT | Rejected before API call with clear message |
| `--price` provided on MARKET | Rejected — price is meaningless for MARKET |
| Missing `--stop-price` on STOP_MARKET | Rejected before API call |
| Negative / zero quantity | Rejected with message |
| Order notional below exchange minimum | Rejected before API call with suggested minimum `--qty` |
| Invalid symbol characters | Rejected with message |
| Binance API error (e.g. insufficient margin) | Printed with Binance error code + message; logged |
| Network timeout / connection failure | Retried up to 3× with backoff; error logged |
| Missing API credentials | Clear instructions printed; exit code 1 |

---

## Assumptions

1. **Testnet only** — the base URL is hardcoded to `https://testnet.binancefuture.com`. Switching to live requires changing `TESTNET_BASE_URL` in `client.py` (and real funds — be careful).
2. **USDT-M futures** — all orders target USDT-margined perpetual contracts.
3. **Hedge mode disabled** — orders use `positionSide=BOTH` (one-way / default mode). If your testnet account uses hedge mode, pass `positionSide=LONG/SHORT` manually.
4. **Quantity precision** — you are responsible for using the correct quantity precision for each symbol (e.g., BTCUSDT minimum is 0.001 BTC). The exchange will reject orders with wrong precision.
5. **No position management** — this bot places orders; it does not track open positions or PnL beyond what the `account` command shows.

---

## Bonus Features Implemented

- ✅ **Third order type**: `STOP_MARKET` (stop-loss trigger)
- ✅ **Enhanced CLI UX**: Rich panels, colour-coded output, structured tables
- ✅ **Structured JSON logging**: Machine-parseable, production-ready log format

---

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP client for REST API calls |
| `typer[all]` | CLI framework (argparse replacement) |
| `rich` | Terminal formatting, tables, panels |
| `python-dotenv` | Load credentials from `.env` file |

---

## Running Tests (optional extension)

```bash
pip install pytest pytest-mock
pytest tests/
```

The `validators.py` and `orders.py` modules are pure functions with no side-effects, making them easy to unit test without network access.
