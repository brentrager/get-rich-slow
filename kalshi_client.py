import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

import httpx
import websockets
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

log = logging.getLogger(__name__)


class KalshiClient:
    """Async client for the Kalshi trading API."""

    BASE_URL = "https://api.elections.kalshi.com"
    TRADE_API = "/trade-api/v2"

    def __init__(self, key_id: str, private_key: rsa.RSAPrivateKey):
        self.key_id = key_id
        self.private_key = private_key
        self.last_api_call = datetime.now()
        self._client = httpx.AsyncClient(timeout=30)

    @classmethod
    def from_key_file(cls, key_id: str, key_path: str) -> "KalshiClient":
        with open(key_path, "rb") as f:
            private_key: PrivateKeyTypes = serialization.load_pem_private_key(
                f.read(), password=None
            )
        assert isinstance(private_key, rsa.RSAPrivateKey)
        return cls(key_id, private_key)

    @classmethod
    def from_key_string(cls, key_id: str, key_pem: str) -> "KalshiClient":
        private_key: PrivateKeyTypes = serialization.load_pem_private_key(
            key_pem.encode("utf-8"), password=None
        )
        assert isinstance(private_key, rsa.RSAPrivateKey)
        return cls(key_id, private_key)

    def _sign(self, text: str) -> str:
        message = text.encode("utf-8")
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _headers(self, method: str, path: str) -> Dict[str, str]:
        ts = str(int(time.time() * 1000))
        clean_path = path.split("?")[0]
        sig = self._sign(ts + method + clean_path)
        return {
            "Content-Type": "application/json",
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }

    async def _rate_limit(self):
        now = datetime.now()
        if now - self.last_api_call < timedelta(milliseconds=100):
            import asyncio

            await asyncio.sleep(0.1)
        self.last_api_call = datetime.now()

    async def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        await self._rate_limit()
        url = self.BASE_URL + path
        resp = await self._client.get(url, headers=self._headers("GET", path), params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, body: dict) -> Any:
        await self._rate_limit()
        url = self.BASE_URL + path
        resp = await self._client.post(url, json=body, headers=self._headers("POST", path))
        resp.raise_for_status()
        return resp.json()

    async def get_balance(self) -> Dict:
        return await self._get(f"{self.TRADE_API}/portfolio/balance")

    async def get_events(
        self,
        status: str = "open",
        series_ticker: Optional[str] = None,
        with_nested_markets: bool = True,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> Dict:
        params: dict[str, str | int] = {
            "status": status,
            "with_nested_markets": str(with_nested_markets).lower(),
            "limit": limit,
        }
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        return await self._get(f"{self.TRADE_API}/events", params)

    async def get_markets(
        self,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> Dict:
        params: dict[str, str | int] = {"limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        return await self._get(f"{self.TRADE_API}/markets", params)

    async def get_series(self, category: Optional[str] = None) -> Dict:
        params = {}
        if category:
            params["category"] = category
        return await self._get(f"{self.TRADE_API}/series", params)

    async def create_order(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        yes_price: Optional[int] = None,
        no_price: Optional[int] = None,
        time_in_force: str = "good_till_canceled",
    ) -> Dict:
        body: dict[str, str | int] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "time_in_force": time_in_force,
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        return await self._post(f"{self.TRADE_API}/portfolio/orders", body)

    async def get_market(self, ticker: str) -> Dict:
        data = await self._get(f"{self.TRADE_API}/markets/{ticker}")
        return data.get("market", data)

    async def get_positions(self, **kwargs) -> Dict:
        params = {k: v for k, v in kwargs.items() if v is not None}
        return await self._get(f"{self.TRADE_API}/portfolio/positions", params)

    async def get_fills(self, **kwargs) -> Dict:
        params = {k: v for k, v in kwargs.items() if v is not None}
        return await self._get(f"{self.TRADE_API}/portfolio/fills", params)

    def ws_headers(self) -> Dict[str, str]:
        """Generate auth headers for WebSocket handshake."""
        return self._headers("GET", "/trade-api/ws/v2")


class KalshiWebSocket:
    """WebSocket client for streaming Kalshi market data."""

    WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"

    def __init__(self, client: KalshiClient):
        self.client = client
        self._ws: websockets.ClientConnection | None = None
        self._cmd_id = 0
        self._subs: dict[int, dict] = {}  # sid -> subscription info
        self._handlers: dict[str, list[Callable]] = {}
        self._running = False

    def on(self, msg_type: str, handler: Callable):
        """Register a handler for a message type (ticker, fill, market_lifecycle_v2, etc)."""
        self._handlers.setdefault(msg_type, []).append(handler)

    async def connect(self):
        """Connect to the WebSocket with auth headers."""
        headers = self.client.ws_headers()
        self._ws = await websockets.connect(self.WS_URL, additional_headers=headers)
        self._running = True
        log.info("Kalshi WebSocket connected")

    async def subscribe(
        self,
        channels: list[str],
        market_tickers: list[str] | None = None,
    ) -> int:
        """Subscribe to channels, optionally filtered by market tickers."""
        self._cmd_id += 1
        cmd: dict[str, Any] = {
            "id": self._cmd_id,
            "cmd": "subscribe",
            "params": {"channels": channels},
        }
        if market_tickers:
            cmd["params"]["market_tickers"] = market_tickers
        assert self._ws is not None
        await self._ws.send(json.dumps(cmd))
        log.info(f"WS subscribe cmd={self._cmd_id} channels={channels} tickers={market_tickers}")
        return self._cmd_id

    async def update_subscription(
        self,
        sid: int,
        market_tickers: list[str],
        action: str = "add_markets",
    ):
        """Add or remove markets from an existing subscription."""
        self._cmd_id += 1
        cmd = {
            "id": self._cmd_id,
            "cmd": "update_subscription",
            "params": {
                "sids": [sid],
                "market_tickers": market_tickers,
                "action": action,
            },
        }
        assert self._ws is not None
        await self._ws.send(json.dumps(cmd))

    async def close(self):
        self._running = False
        if self._ws:
            await self._ws.close()

    async def listen(self):
        """Listen for messages and dispatch to handlers. Reconnects on failure."""
        while self._running:
            try:
                assert self._ws is not None
                async for raw in self._ws:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")

                    # Track subscription IDs from responses
                    if msg_type == "subscribed":
                        sid = msg.get("sid")
                        if sid:
                            self._subs[sid] = msg

                    # Dispatch to registered handlers
                    for handler in self._handlers.get(msg_type, []):
                        try:
                            result = handler(msg)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            log.warning(f"WS handler error for {msg_type}: {e}")

            except websockets.ConnectionClosed:
                if not self._running:
                    break
                log.warning("Kalshi WS disconnected, reconnecting in 5s...")
                await asyncio.sleep(5)
                try:
                    await self.connect()
                except Exception as e:
                    log.warning(f"WS reconnect failed: {e}")
            except Exception as e:
                if not self._running:
                    break
                log.warning(f"WS listen error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)
                try:
                    await self.connect()
                except Exception:
                    pass
