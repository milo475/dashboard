"""Finnhub quotes for a fixed watchlist, plus a locally accumulated sparkline.

The free Finnhub tier does not expose /stock/candle, so the sparkline is built
from the prices we observe on each refresh and persisted between restarts.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

API = "https://finnhub.io/api/v1"
TIMEOUT = 8
MAX_POINTS = 60

SYMBOLS = [
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("NVDA", "NVIDIA"),
    ("GOOGL", "Alphabet"),
    ("AMZN", "Amazon"),
    ("META", "Meta"),
    ("TSLA", "Tesla"),
    ("TSM", "TSMC"),
    ("AVGO", "Broadcom"),
    ("ORCL", "Oracle"),
]


class StocksError(RuntimeError):
    """Raised when quotes cannot be fetched at all."""


class PriceHistory:
    """Rolling per-symbol close prices, persisted so sparklines survive restarts."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle)
            os.replace(tmp, self.path)
        except OSError:
            pass  # a missing sparkline cache is not worth failing the request over

    def append(self, symbol, price):
        if price is None:
            return
        with self._lock:
            series = self._data.setdefault(symbol, [])
            if not series or series[-1] != price:
                series.append(price)
            del series[:-MAX_POINTS]

    def get(self, symbol):
        with self._lock:
            return list(self._data.get(symbol, []))

    def flush(self):
        with self._lock:
            self._save()


class StocksClient:
    def __init__(self, api_key, cache_dir):
        self.api_key = (api_key or "").strip()
        self.history = PriceHistory(os.path.join(cache_dir, "price_history.json"))

    def _quote(self, symbol):
        resp = requests.get(
            f"{API}/quote",
            params={"symbol": symbol, "token": self.api_key},
            timeout=TIMEOUT,
        )
        if resp.status_code == 429:
            raise StocksError("Finnhub rate limit reached")
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise StocksError(str(payload["error"]))
        return payload

    def quotes(self):
        if not self.api_key:
            raise StocksError(
                "FINNHUB_API_KEY is not set - add it to backend/.env"
            )

        def fetch(entry):
            symbol, name = entry
            try:
                data = self._quote(symbol)
            except (requests.RequestException, ValueError, StocksError) as exc:
                return {
                    "symbol": symbol,
                    "name": name,
                    "ok": False,
                    "error": str(exc),
                    "sparkline": self.history.get(symbol),
                }
            price = data.get("c")
            # Finnhub returns all-zero payloads for unknown or unlicensed symbols.
            if not price:
                return {
                    "symbol": symbol,
                    "name": name,
                    "ok": False,
                    "error": "no quote returned",
                    "sparkline": self.history.get(symbol),
                }
            self.history.append(symbol, price)
            return {
                "symbol": symbol,
                "name": name,
                "ok": True,
                "price": price,
                "change": data.get("d"),
                "change_pct": data.get("dp"),
                "previous_close": data.get("pc"),
                "open": data.get("o"),
                "high": data.get("h"),
                "low": data.get("l"),
                "quote_time": data.get("t"),
                "sparkline": self.history.get(symbol),
            }

        with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as pool:
            results = list(pool.map(fetch, SYMBOLS))

        self.history.flush()
        if not any(row["ok"] for row in results):
            first_error = next(
                (row.get("error") for row in results if row.get("error")),
                "no quotes available",
            )
            raise StocksError(first_error)

        return {
            "available": True,
            "stocks": results,
            "sparkline_source": "observed",
            "fetched_at": time.time(),
        }
