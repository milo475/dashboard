"""Backend API for the Kali desktop dashboard.

Every endpoint answers with HTTP 200 and an {"available": bool} envelope so the
frontend can render a "no data" card instead of treating an outage as a crash.
"""
import os
import socket

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from services.activitywatch import ActivityWatchClient, ActivityWatchError
from services.cache import TTLCache
from services.focus import FocusError, FocusStore, FocusValidationError
from services.github import GitHubClient, GitHubError
from services.launcher import launch_claude
from services.news import NewsError, fetch as fetch_news
from services.photos import PhotoError, PhotoLibrary
from services.places import Places, PlacesError
from services.planner import PlannerError, PlannerStore, PlannerValidationError
from services.productivity import ProductivityService
from services.stocks import StocksClient, StocksError
from services.system import SystemError, SystemMonitor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

USAGE_TTL = 30      # ActivityWatch is local and cheap to hit
STOCKS_TTL = 60     # respect the Finnhub free-tier rate limit
NEWS_TTL = 3600     # hourly, per the news sources' etiquette
SYSTEM_TTL = 2      # kernel counters; the card polls every 5s
GITHUB_TTL = 300    # 60 req/h unauthenticated, so 5 minutes is plenty
PRODUCTIVITY_TTL = 60
FILES_TTL = 20      # a directory scan; the card polls every 30s
PHOTOS_TTL = 10     # one directory scan; the card polls every 20s

# How long a failing endpoint may keep serving its last good value before it
# admits defeat and the card switches to "no data".
USAGE_MAX_STALE = 10 * 60
STOCKS_MAX_STALE = 15 * 60
NEWS_MAX_STALE = 6 * 3600
SYSTEM_MAX_STALE = 60           # vitals go meaningless fast; fail loudly instead
GITHUB_MAX_STALE = 30 * 60
PRODUCTIVITY_MAX_STALE = 10 * 60

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # a batch of phone photos

cache = TTLCache()
aw_client = ActivityWatchClient(
    os.getenv("ACTIVITYWATCH_URL", "http://localhost:5600/api/0")
)
stocks_client = StocksClient(
    os.getenv("FINNHUB_API_KEY", ""), os.path.join(BASE_DIR, ".cache")
)
system_monitor = SystemMonitor()
focus_store = FocusStore(os.path.join(BASE_DIR, "data", "goals.json"))
github_client = GitHubClient(
    os.getenv("GITHUB_USER", "milo475"), os.getenv("GITHUB_TOKEN", "")
)
productivity = ProductivityService(
    aw_client, os.path.join(BASE_DIR, "productivity_rules.json")
)
planner_store = PlannerStore(os.path.join(BASE_DIR, "data", "planner.json"))
places = Places(os.path.join(BASE_DIR, "data", "folders.json"))
photos = PhotoLibrary(os.getenv("PHOTOS_DIR", os.path.join(BASE_DIR, "data", "photos")))


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
            "github_user": github_client.user,
            "github_token_configured": bool(github_client.token),
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


@app.get("/api/system")
def system():
    try:
        data, at, stale = cache.get_or_refresh(
            "system", SYSTEM_TTL, system_monitor.snapshot, SYSTEM_MAX_STALE
        )
    except SystemError as exc:
        return unavailable(exc, hint="Install psutil, then restart the backend.")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)
    return envelope(data, at, stale)


@app.get("/api/github")
def github():
    try:
        data, at, stale = cache.get_or_refresh(
            "github", GITHUB_TTL, github_client.activity, GITHUB_MAX_STALE
        )
    except GitHubError as exc:
        return unavailable(
            exc, hint="Set GITHUB_TOKEN in backend/.env to raise the rate limit."
        )
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)
    return envelope(data, at, stale)


@app.get("/api/productivity")
def productivity_report():
    try:
        data, at, stale = cache.get_or_refresh(
            "productivity",
            PRODUCTIVITY_TTL,
            productivity.report,
            PRODUCTIVITY_MAX_STALE,
        )
    except ActivityWatchError as exc:
        return unavailable(exc, hint="Start ActivityWatch (aw-server + aw-watcher-window).")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)
    return envelope(data, at, stale)


# Goals and pomodoros are local state, not a cached upstream: read and write
# them straight through so a click is never undone by a stale cache.
@app.get("/api/goals")
def get_goals():
    try:
        return jsonify(focus_store.state())
    except FocusError as exc:
        return unavailable(exc, hint="Check that backend/data/ is writable.")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)


@app.post("/api/goals")
def post_goals():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(focus_store.replace_goals(body.get("goals", [])))
    except FocusValidationError as exc:
        return unavailable(exc, hint="The dashboard sent an invalid goal list.")
    except FocusError as exc:
        return unavailable(exc, hint="Check that backend/data/ is writable.")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)


@app.post("/api/pomodoro")
def post_pomodoro():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(
            focus_store.bump_pomodoro(
                delta=int(body.get("delta", 1)), reset=bool(body.get("reset"))
            )
        )
    except (FocusError, ValueError, TypeError) as exc:
        return unavailable(exc, hint="Check that backend/data/ is writable.")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)


@app.post("/api/launch/claude")
def launch():
    ok, detail = launch_claude()
    return jsonify({"ok": ok, **detail}), (200 if ok else 500)


# ---------- Planner page ----------
# To-do lists, the weekly schedule and the morning routine are local state like
# the goals: read and written straight through, never cached.
def _planner_read(producer):
    try:
        return jsonify(producer())
    except PlannerError as exc:
        return unavailable(exc, hint="Check that backend/data/ is writable.")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)


def _planner_write(producer):
    try:
        return jsonify(producer())
    except PlannerValidationError as exc:
        return unavailable(exc, hint="The dashboard sent an invalid planner update.")
    except PlannerError as exc:
        return unavailable(exc, hint="Check that backend/data/ is writable.")
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc)


@app.get("/api/todos")
def get_todos():
    return _planner_read(planner_store.todos)


@app.post("/api/todos")
def post_todos():
    body = request.get_json(silent=True) or {}
    return _planner_write(lambda: planner_store.replace_todos(body.get("lists", {})))


@app.get("/api/schedule")
def get_schedule():
    return _planner_read(planner_store.schedule)


@app.post("/api/schedule")
def post_schedule():
    body = request.get_json(silent=True) or {}
    return _planner_write(lambda: planner_store.replace_schedule(body.get("days", {})))


@app.get("/api/routine")
def get_routine():
    return _planner_read(planner_store.routine)


@app.post("/api/routine")
def post_routine():
    body = request.get_json(silent=True) or {}
    if "toggle" in body:
        return _planner_write(
            lambda: planner_store.set_routine_done(body.get("toggle"), bool(body.get("done", True)))
        )
    return _planner_write(lambda: planner_store.replace_routine(body.get("items", [])))


@app.get("/api/folders")
def get_folders():
    try:
        return jsonify(places.folders())
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc, hint="Check backend/data/folders.json.")


@app.get("/api/files")
def get_files():
    try:
        data, at, stale = cache.get_or_refresh("files", FILES_TTL, places.files, 5 * 60)
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc, hint="Check files_dirs in backend/data/folders.json.")
    return envelope(data, at, stale)


@app.post("/api/open")
def post_open():
    body = request.get_json(silent=True) or {}
    try:
        result = places.open(folder=body.get("folder"), file=body.get("file"))
    except PlacesError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify(result)


@app.get("/api/photos")
def get_photos():
    try:
        data, at, stale = cache.get_or_refresh("photos", PHOTOS_TTL, photos.list, 10 * 60)
    except Exception as exc:  # noqa: BLE001
        return unavailable(exc, hint="Create backend/data/photos and drop images in it.")
    if not data.get("available", True):
        return jsonify(data)
    return envelope(data, at, stale)


@app.get("/api/photos/<path:name>")
def get_photo(name):
    # send_from_directory refuses anything that escapes the photos directory.
    return send_from_directory(photos.directory, name, max_age=3600)


@app.post("/api/photos")
def post_photos():
    files = request.files.getlist("photos")
    if not files:
        return jsonify({"available": False, "error": "no files in the upload"}), 400
    try:
        saved, rejected = photos.save(files)
    except OSError as exc:
        return unavailable(exc, hint="Check that backend/data/photos is writable.")
    cache.invalidate("photos")
    data = photos.list()
    data.update({"saved": saved, "rejected": rejected})
    return jsonify(data)


@app.delete("/api/photos/<path:name>")
def delete_photo(name):
    try:
        removed = photos.remove(name)
    except PhotoError as exc:
        return jsonify({"available": False, "error": str(exc)}), 404
    except OSError as exc:
        return unavailable(exc)
    cache.invalidate("photos")
    data = photos.list()
    data["removed"] = removed
    return jsonify(data)


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
        threaded=True,
    )
