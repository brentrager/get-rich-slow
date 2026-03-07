import requests
import base64
import time
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature


class KalshiClient:
    """Client for the Kalshi trading API."""

    BASE_URL = "https://api.elections.kalshi.com"
    TRADE_API = "/trade-api/v2"

    def __init__(self, key_id: str, private_key: rsa.RSAPrivateKey):
        self.key_id = key_id
        self.private_key = private_key
        self.last_api_call = datetime.now()

    @classmethod
    def from_key_file(cls, key_id: str, key_path: str) -> "KalshiClient":
        with open(key_path, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
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

    def _rate_limit(self):
        now = datetime.now()
        if now - self.last_api_call < timedelta(milliseconds=100):
            time.sleep(0.1)
        self.last_api_call = datetime.now()

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        self._rate_limit()
        url = self.BASE_URL + path
        resp = requests.get(url, headers=self._headers("GET", path), params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> Any:
        self._rate_limit()
        url = self.BASE_URL + path
        resp = requests.post(url, json=body, headers=self._headers("POST", path))
        resp.raise_for_status()
        return resp.json()

    def get_balance(self) -> Dict:
        return self._get(f"{self.TRADE_API}/portfolio/balance")

    def get_events(
        self,
        status: str = "open",
        series_ticker: Optional[str] = None,
        with_nested_markets: bool = True,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> Dict:
        params = {
            "status": status,
            "with_nested_markets": str(with_nested_markets).lower(),
            "limit": limit,
        }
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        return self._get(f"{self.TRADE_API}/events", params)

    def get_markets(
        self,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> Dict:
        params = {"limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        return self._get(f"{self.TRADE_API}/markets", params)

    def get_series(self, category: Optional[str] = None) -> Dict:
        params = {}
        if category:
            params["category"] = category
        return self._get(f"{self.TRADE_API}/series", params)

    def create_order(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        yes_price: Optional[int] = None,
        no_price: Optional[int] = None,
        time_in_force: str = "good_till_canceled",
    ) -> Dict:
        body = {
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
        return self._post(f"{self.TRADE_API}/portfolio/orders", body)

    def get_positions(self, **kwargs) -> Dict:
        params = {k: v for k, v in kwargs.items() if v is not None}
        return self._get(f"{self.TRADE_API}/portfolio/positions", params)

    def get_fills(self, **kwargs) -> Dict:
        params = {k: v for k, v in kwargs.items() if v is not None}
        return self._get(f"{self.TRADE_API}/portfolio/fills", params)
