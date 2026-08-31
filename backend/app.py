"""Backend API for the Kali desktop dashboard.

Every endpoint answers with HTTP 200 and an {"available": bool} envelope so the
frontend can render a "no data" card instead of treating an outage as a crash.
"""
import os
import socket

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

from services.activitywatch import ActivityWatchClient, ActivityWatchError
from services.cache import TTLCache
from services.launcher import launch_claude
from services.news import NewsError, fetch as fetch_news
from services.stocks import StocksClient, StocksError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

USAGE_TTL = 30      # ActivityWatch is local and cheap to hit
STOCKS_TTL = 60     # respect the Finnhub free-tier rate limit
NEWS_TTL = 3600     # hourly, per the news sources' etiquette

# How long a failing endpoint may keep serving its last good value before it
# admits defeat and the card switches to "no data".
USAGE_MAX_STALE = 10 * 60
STOCKS_MAX_STALE = 15 * 60
NEWS_MAX_STALE = 6 * 3600

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

cache = TTLCache()
aw_client = ActivityWatchClient(
    os.getenv("ACTIVITYWATCH_URL", "http://localhost:5600/api/0")
)
stocks_client = StocksClient(
    os.getenv("FINNHUB_API_KEY", ""), os.path.join(BASE_DIR, ".cache")
)


def envelope(payload, fetched_at, stale):
    payload = dict(payload)
    payload["fetched_at"] = fetched_at
    payload["stale"] = stale
    return jsonify(payload)


def unavailable(message, **extra):
    body = {"available": False, "error": str(message)}
    body.update(extra)
    return jsonify(body)


@app.get("/api/health")
def health():
    return jsonify(
        {
            "available": True,
            "host": socket.gethostname(),
            "finnhub_key_configured": bool(os.getenv("FINNHUB_API_KEY", "").strip()),
            "activitywatch_url": aw_client.base_url,
        }
    )


@app.get("/api/usage")
def usage():
    try:
        data, at, stale = cache.get_or_refresh(
            "usage", USAGE_TTL, aw_client.usage, USAGE_MAX_STALE
        )
    except ActivityWatchError as exc:
        return unavailable(exc, hint="Start ActivityWatch (aw-server + aw-watcher-window).")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)
    return envelope(data, at, stale)


@app.get("/api/stocks")
def stocks():
    try:
        data, at, stale = cache.get_or_refresh(
            "stocks", STOCKS_TTL, stocks_client.quotes, STOCKS_MAX_STALE
        )
    except StocksError as exc:
        return unavailable(exc, hint="Check FINNHUB_API_KEY in backend/.env.")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)
    return envelope(data, at, stale)


@app.get("/api/ai-news")
def ai_news():
    try:
        data, at, stale = cache.get_or_refresh(
            "news", NEWS_TTL, fetch_news, NEWS_MAX_STALE
        )
    except NewsError as exc:
        return unavailable(exc, hint="Check the internet connection.")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)
    return envelope(data, at, stale)


@app.post("/api/launch/claude")
def launch():
    ok, detail = launch_claude()
    return jsonify({"ok": ok, **detail}), (200 if ok else 500)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
        threaded=True,
    )
