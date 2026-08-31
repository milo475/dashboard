"""Daily goals and the Pomodoro counter, persisted to a small JSON file.

History is kept per calendar day so the card resets visually every morning
without losing what was there yesterday.
"""
import json
import os
import threading
import time
import uuid
from datetime import date, timedelta

MAX_GOALS = 5
MAX_TEXT = 120
KEEP_DAYS = 180  # bound the file; nobody scrolls back half a year of to-dos


class FocusError(RuntimeError):
    """Raised when the goals file cannot be read or written."""


class FocusValidationError(FocusError):
    """Raised when the client sent something the store will not accept."""


def today_key():
    return date.today().isoformat()


def _clean_text(value):
    text = " ".join(str(value or "").split())
    return text[:MAX_TEXT]


class FocusStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = None

    # ---------- persistence ----------

    def _load_locked(self):
        if self._data is not None:
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                parsed = json.load(handle)
        except FileNotFoundError:
            parsed = {}
        except (OSError, ValueError):
            # A corrupt file must not take the card down; start clean and keep
            # the damaged copy around in case it mattered.
            try:
                os.replace(self.path, f"{self.path}.corrupt")
            except OSError:
                pass
            parsed = {}
        days = parsed.get("days") if isinstance(parsed, dict) else None
        self._data = {"days": days if isinstance(days, dict) else {}}
        return self._data

    def _prune_locked(self):
        cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
        days = self._data["days"]
        for key in [k for k in days if k < cutoff]:
            days.pop(key, None)

    def _save_locked(self):
        self._prune_locked()
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except OSError as exc:
            raise FocusError(f"Could not write {self.path}: {exc}") from exc

    def _day_locked(self, key):
        day = self._data["days"].get(key)
        if not isinstance(day, dict):
            day = {}
        goals = day.get("goals")
        return {
            "goals": [g for g in goals if isinstance(g, dict)]
            if isinstance(goals, list)
            else [],
            "pomodoros": int(day.get("pomodoros") or 0),
        }

    # ---------- reads ----------

    def _payload_locked(self, key):
        day = self._day_locked(key)
        goals = [
            {
                "id": str(goal.get("id") or uuid.uuid4().hex[:8]),
                "text": _clean_text(goal.get("text")),
                "done": bool(goal.get("done")),
            }
            for goal in day["goals"]
        ][:MAX_GOALS]
        return {
            "available": True,
            "date": key,
            "goals": goals,
            "done_count": sum(1 for g in goals if g["done"]),
            "max_goals": MAX_GOALS,
            "pomodoros": day["pomodoros"],
            "updated_at": time.time(),
        }

    def state(self):
        key = today_key()
        with self._lock:
            self._load_locked()
            return self._payload_locked(key)

    # ---------- writes ----------

    def replace_goals(self, goals):
        """Store today's list wholesale - the client always sends all of it."""
        if not isinstance(goals, list):
            raise FocusValidationError("`goals` must be a list")
        if len(goals) > MAX_GOALS:
            raise FocusValidationError(f"At most {MAX_GOALS} goals per day")

        cleaned = []
        seen = set()
        for item in goals:
            if not isinstance(item, dict):
                raise FocusValidationError("each goal must be an object")
            text = _clean_text(item.get("text"))
            if not text:
                continue  # silently drop blanks rather than storing empty rows
            goal_id = str(item.get("id") or "").strip() or uuid.uuid4().hex[:8]
            while goal_id in seen:
                goal_id = uuid.uuid4().hex[:8]
            seen.add(goal_id)
            cleaned.append({"id": goal_id, "text": text, "done": bool(item.get("done"))})

        key = today_key()
        with self._lock:
            self._load_locked()
            day = self._day_locked(key)
            day["goals"] = cleaned
            self._data["days"][key] = day
            self._save_locked()
            return self._payload_locked(key)

    def bump_pomodoro(self, delta=1, reset=False):
        key = today_key()
        with self._lock:
            self._load_locked()
            day = self._day_locked(key)
            day["pomodoros"] = 0 if reset else max(0, day["pomodoros"] + int(delta))
            self._data["days"][key] = day
            self._save_locked()
            return self._payload_locked(key)
