"""
client.py
---------
Low-level Binance Futures Testnet REST client.

Responsibilities:
  • HMAC-SHA256 request signing
  • Timestamp injection
  • HTTP execution with retry on transient errors
  • Raw response logging (request params + response body)
  • Raising BinanceAPIError for non-2xx responses

This layer knows nothing about order semantics — that lives in orders.py.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
TESTNET_BASE_URL = "https://testnet.binancefuture.com"
DEFAULT_TIMEOUT = 10          # seconds
MAX_RETRIES = 3
RECV_WINDOW = 60_000          # ms — increased for Windows clock skew tolerance


class BinanceAPIError(Exception):
    """Raised when Binance returns a non-2xx response or an error payload."""

    def __init__(self, status_code: int, code: int, msg: str) -> None:
        self.status_code = status_code
        self.code = code
        self.msg = msg
        super().__init__(f"[HTTP {status_code}] Binance error {code}: {msg}")


class BinanceFuturesClient:
    """
    Thin, authenticated wrapper around Binance Futures Testnet REST API.

    Parameters
    ----------
    api_key:    Your testnet API key
    api_secret: Your testnet API secret
    base_url:   Override for live vs testnet (defaults to testnet)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = TESTNET_BASE_URL,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret must both be non-empty strings.")

        self._api_key = api_key
        self._api_secret = api_secret.strip().encode('utf-8')   # bytes for HMAC, strip Windows line endings
        self.base_url = base_url.rstrip("/")

        # Build a session with automatic retry on connection/timeout errors
        self._session = self._build_session()
        logger.info(
            "BinanceFuturesClient initialised",
            extra={"x_base_url": self.base_url},
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=MAX_RETRIES,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "DELETE"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _sign(self, params: dict) -> dict:
        """
        Add timestamp, recvWindow, and HMAC signature to params.
        Returns the complete signed params dict.
        """
        signed_params = {k: v for k, v in params.items() if v is not None}
        signed_params["timestamp"] = int(time.time() * 1000)
        signed_params["recvWindow"] = RECV_WINDOW

        query_string = urlencode(signed_params, doseq=True)
        signature = hmac.new(
            self._api_secret,
            query_string.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        signed_params["signature"] = signature
        return signed_params

    def _headers(self) -> dict:
        return {
            "X-MBX-APIKEY": self._api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _handle_response(self, response: requests.Response) -> Any:
        """Parse JSON response; raise BinanceAPIError on failure."""
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            return {}

        if not response.ok:
            code = data.get("code", response.status_code)
            msg = data.get("msg", response.text)
            logger.error(
                "Binance API error response",
                extra={"x_status": response.status_code, "x_code": code, "x_msg": msg},
            )
            raise BinanceAPIError(response.status_code, code, msg)

        return data

    # ── Public API methods ────────────────────────────────────────────────────

    def get_exchange_info(self) -> dict:
        """Fetch exchange info (symbol details, filters). No auth required."""
        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        logger.debug("GET exchangeInfo", extra={"x_url": url})
        resp = self._session.get(url, timeout=DEFAULT_TIMEOUT)
        return self._handle_response(resp)

    def get_symbol_info(self, symbol: str) -> dict:
        """Return exchange metadata for one symbol (e.g. filters, precision)."""
        symbol_upper = symbol.upper()
        info = self.get_exchange_info()
        for item in info.get("symbols", []):
            if item.get("symbol") == symbol_upper:
                return item
        raise ValueError(f"Symbol '{symbol_upper}' not found in exchangeInfo.")

    def get_ticker_price(self, symbol: str) -> str:
        """Fetch latest ticker price for a symbol (unauthenticated endpoint)."""
        symbol_upper = symbol.upper()
        url = f"{self.base_url}/fapi/v1/ticker/price"
        resp = self._session.get(url, params={"symbol": symbol_upper}, timeout=DEFAULT_TIMEOUT)
        data = self._handle_response(resp)
        return str(data.get("price", "0"))

    def get_account(self) -> dict:
        """Fetch futures account info (balances, positions)."""
        signed_params = self._sign({})
        url = f"{self.base_url}/fapi/v2/account"
        logger.debug("GET account", extra={"x_url": url})
        resp = self._session.get(
            url,
            params=signed_params,
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        return self._handle_response(resp)

    def place_order(self, **kwargs: Any) -> dict:
        """
        POST /fapi/v1/order

        Keyword arguments are forwarded directly as form params after signing.
        Callers should use the helpers in orders.py rather than calling this directly.
        """
        signed_params = self._sign(dict(kwargs))
        url = f"{self.base_url}/fapi/v1/order"

        # Sanitise for logging: never log the signature itself
        log_params = {k: v for k, v in signed_params.items() if k != "signature"}
        logger.debug(
            "POST /fapi/v1/order — request params",
            extra={
                "x_order_type": str(kwargs.get("type", "")).upper(),
                "x_params": log_params,
            },
        )

        resp = self._session.post(
            url,
            data=urlencode(signed_params),
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        data = self._handle_response(resp)

        logger.debug(
            "POST /fapi/v1/order — response",
            extra={
                "x_order_type": str(kwargs.get("type", "")).upper(),
                "x_response": data,
            },
        )
        return data

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order by orderId."""
        signed_params = self._sign({"symbol": symbol, "orderId": order_id})
        url = f"{self.base_url}/fapi/v1/order"
        logger.debug(
            "DELETE /fapi/v1/order",
            extra={"x_symbol": symbol, "x_order_id": order_id},
        )
        resp = self._session.delete(
            url,
            params=signed_params,
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        return self._handle_response(resp)

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Return all open orders, optionally filtered by symbol."""
        params: dict = {}
        if symbol:
            params["symbol"] = symbol
        signed_params = self._sign(params)
        url = f"{self.base_url}/fapi/v1/openOrders"
        resp = self._session.get(
            url,
            params=signed_params,
            headers=self._headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        return self._handle_response(resp)
