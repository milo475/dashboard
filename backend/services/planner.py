"""Planner state behind the Planner page: two to-do lists, the weekly
schedule and the morning routine.

One small JSON file, read-through and write-through like FocusStore, so a click
is never undone by a stale cache. Every payload carries {"available": True}.
"""
import json
import os
import re
import threading
import time
import uuid
from datetime import date, timedelta

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
LISTS = ["work", "personal"]
MAX_TODOS = 12     # per list; the paper note in the reference holds about six
MAX_BLOCKS = 8     # per weekday
MAX_ROUTINE = 8
MAX_TEXT = 120
MAX_TIME = 24      # "10:00–12:00" or "All day"
MAX_NOTE = 60      # room · teacher, under a class block
KEEP_DAYS = 90     # routine tick history

# What a fresh dashboard shows so the page never opens empty. All of it is
# editable from the cards; nothing here is re-applied once the file exists.
SEED = {
    "todos": {
        "work": [
            "Review yesterday's commits",
            "Plan today's 3 tasks",
            "Ship one small improvement",
        ],
        "personal": [
            "Yoga or a walk",
            "Read 20 pages",
            "Self-care night: tidy room, prep snacks",
        ],
    },
    "routine": ["Tidy up + stretch", "Plan the day", "Breakfast + coffee"],
    "schedule": {
        "mon": [
            ("10:00–12:00", "Deep work"),
            ("12:00–14:00", "Lunch & walk"),
            ("14:00–16:00", "Project work"),
            ("19:00–20:00", "Yoga"),
        ],
        "tue": [
            ("10:00–12:00", "Deep work"),
            ("12:00–14:00", "Lunch & meal prep"),
            ("14:00–16:00", "Reviews & admin"),
        ],
        "wed": [
            ("10:00–12:00", "Deep work"),
            ("12:00–14:00", "Lunch & walk"),
            ("14:00–16:00", "Project work"),
            ("19:00–20:00", "Yoga"),
        ],
        "thu": [
            ("11:00–13:00", "Deep work & admin"),
            ("13:00–15:00", "Lunch & walk"),
            ("15:00–16:00", "Project work"),
            ("19:00–21:00", "Self-care night"),
        ],
        "fri": [("11:00–12:00", "Weekly review"), ("All day", "Rest & hobbies")],
        "sat": [("All day", "Rest & hobbies")],
        "sun": [("All day", "Plan the week")],
    },
}

_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})")


class PlannerError(RuntimeError):
    """Raised when the planner file cannot be read or written."""


class PlannerValidationError(PlannerError):
    """Raised when the client sent something the store will not accept."""


def today_key():
    return date.today().isoformat()


def today_day():
    return DAYS[date.today().weekday()]


def _clean(value, limit=MAX_TEXT):
    return " ".join(str(value or "").split())[:limit]


def _new_id():
    return uuid.uuid4().hex[:8]


def _block_sort_key(block):
    """Blocks with a clock time sort by it; 'All day' style blocks come first."""
    match = _TIME_RE.match(block.get("time", ""))
    if not match:
        return -1
    return int(match.group(1)) * 60 + int(match.group(2))


def _unique_id(item, seen):
    item_id = _clean(item.get("id"), 32) if isinstance(item, dict) else ""
    while not item_id or item_id in seen:
        item_id = _new_id()
    seen.add(item_id)
    return item_id


class PlannerStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._data = None

    # ---------- persistence ----------

    def _seed(self):
        return {
            "todos": {
                name: [{"id": _new_id(), "text": text, "done": False} for text in items]
                for name, items in SEED["todos"].items()
            },
            "routine": {
                "items": [{"id": _new_id(), "text": text} for text in SEED["routine"]],
                "done": {},
            },
            "schedule": {
                day: [
                    {"id": _new_id(), "time": when, "title": title}
                    for when, title in SEED["schedule"].get(day, [])
                ]
                for day in DAYS
            },
        }

    def _load_locked(self):
        if self._data is not None:
            return self._data
        parsed = None
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                parsed = json.load(handle)
        except FileNotFoundError:
            parsed = None
        except (OSError, ValueError):
            # A corrupt file must not take the page down; start from the seed
            # and keep the damaged copy around in case it mattered.
            try:
                os.replace(self.path, f"{self.path}.corrupt")
            except OSError:
                pass
            parsed = None

        if not isinstance(parsed, dict):
            self._data = self._seed()
            self._save_locked()
            return self._data

        todos = parsed.get("todos") if isinstance(parsed.get("todos"), dict) else {}
        routine = parsed.get("routine") if isinstance(parsed.get("routine"), dict) else {}
        schedule = parsed.get("schedule") if isinstance(parsed.get("schedule"), dict) else {}
        self._data = {
            "todos": {
                name: [t for t in todos.get(name, []) if isinstance(t, dict)]
                if isinstance(todos.get(name), list)
                else []
                for name in LISTS
            },
            "routine": {
                "items": [i for i in routine.get("items", []) if isinstance(i, dict)]
                if isinstance(routine.get("items"), list)
                else [],
                "done": routine.get("done") if isinstance(routine.get("done"), dict) else {},
            },
            "schedule": {
                day: [b for b in schedule.get(day, []) if isinstance(b, dict)]
                if isinstance(schedule.get(day), list)
                else []
                for day in DAYS
            },
        }
        return self._data

    def _prune_locked(self):
        cutoff = (date.today() - timedelta(days=KEEP_DAYS)).isoformat()
        done = self._data["routine"]["done"]
        for key in [k for k in done if k < cutoff]:
            done.pop(key, None)

    def _save_locked(self):
        self._prune_locked()
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except OSError as exc:
            raise PlannerError(f"Could not write {self.path}: {exc}") from exc

    # ---------- to-do lists ----------

    def _todos_payload_locked(self):
        lists = {}
        for name in LISTS:
            seen = set()
            lists[name] = [
                {"id": _unique_id(item, seen), "text": _clean(item.get("text")), "done": bool(item.get("done"))}
                for item in self._data["todos"][name]
            ][:MAX_TODOS]
        return {
            "available": True,
            "lists": lists,
            "max_items": MAX_TODOS,
            "updated_at": time.time(),
        }

    def todos(self):
        with self._lock:
            self._load_locked()
            return self._todos_payload_locked()

    def replace_todos(self, lists):
        """Store both lists wholesale - the card always sends everything."""
        if not isinstance(lists, dict):
            raise PlannerValidationError("`lists` must be an object")
        cleaned = {}
        for name in LISTS:
            items = lists.get(name, [])
            if not isinstance(items, list):
                raise PlannerValidationError(f"`{name}` must be a list")
            if len(items) > MAX_TODOS:
                raise PlannerValidationError(f"At most {MAX_TODOS} items per list")
            seen = set()
            rows = []
            for item in items:
                if not isinstance(item, dict):
                    raise PlannerValidationError("each item must be an object")
                text = _clean(item.get("text"))
                if not text:
                    continue  # drop blanks rather than storing empty rows
                rows.append({"id": _unique_id(item, seen), "text": text, "done": bool(item.get("done"))})
            cleaned[name] = rows
        with self._lock:
            self._load_locked()
            self._data["todos"] = cleaned
            self._save_locked()
            return self._todos_payload_locked()

    # ---------- weekly schedule ----------

    def _schedule_payload_locked(self):
        days = {}
        for day in DAYS:
            seen = set()
            blocks = [
                {
                    "id": _unique_id(block, seen),
                    "time": _clean(block.get("time"), MAX_TIME),
                    "title": _clean(block.get("title"), 60),
                    "note": _clean(block.get("note"), MAX_NOTE),
                }
                for block in self._data["schedule"][day]
            ][:MAX_BLOCKS]
            days[day] = sorted(blocks, key=_block_sort_key)
        return {
            "available": True,
            "days": days,
            "today": today_day(),
            "max_blocks": MAX_BLOCKS,
            "updated_at": time.time(),
        }

    def schedule(self):
        with self._lock:
            self._load_locked()
            return self._schedule_payload_locked()

    def replace_schedule(self, days):
        if not isinstance(days, dict):
            raise PlannerValidationError("`days` must be an object")
        cleaned = {}
        for day in DAYS:
            blocks = days.get(day, [])
            if not isinstance(blocks, list):
                raise PlannerValidationError(f"`{day}` must be a list")
            if len(blocks) > MAX_BLOCKS:
                raise PlannerValidationError(f"At most {MAX_BLOCKS} blocks per day")
            seen = set()
            rows = []
            for block in blocks:
                if not isinstance(block, dict):
                    raise PlannerValidationError("each block must be an object")
                title = _clean(block.get("title"), 60)
                if not title:
                    continue
                rows.append(
                    {
                        "id": _unique_id(block, seen),
                        "time": _clean(block.get("time"), MAX_TIME) or "All day",
                        "title": title,
                        "note": _clean(block.get("note"), MAX_NOTE),
                    }
                )
            cleaned[day] = sorted(rows, key=_block_sort_key)
        with self._lock:
            self._load_locked()
            self._data["schedule"] = cleaned
            self._save_locked()
            return self._schedule_payload_locked()

    # ---------- morning routine ----------

    def _routine_payload_locked(self, key):
        done_today = set(self._data["routine"]["done"].get(key) or [])
        seen = set()
        items = [
            {"id": _unique_id(item, seen), "text": _clean(item.get("text"))}
            for item in self._data["routine"]["items"]
        ][:MAX_ROUTINE]
        rows = [{**item, "done": item["id"] in done_today} for item in items]
        return {
            "available": True,
            "date": key,
            "items": rows,
            "done_count": sum(1 for r in rows if r["done"]),
            "max_items": MAX_ROUTINE,
            "updated_at": time.time(),
        }

    def routine(self):
        with self._lock:
            self._load_locked()
            return self._routine_payload_locked(today_key())

    def replace_routine(self, items):
        """Replace the checklist; ticks for ids that survive are kept."""
        if not isinstance(items, list):
            raise PlannerValidationError("`items` must be a list")
        if len(items) > MAX_ROUTINE:
            raise PlannerValidationError(f"At most {MAX_ROUTINE} routine items")
        seen = set()
        rows = []
        for item in items:
            if not isinstance(item, dict):
                raise PlannerValidationError("each item must be an object")
            text = _clean(item.get("text"))
            if not text:
                continue
            rows.append({"id": _unique_id(item, seen), "text": text})
        key = today_key()
        with self._lock:
            self._load_locked()
            self._data["routine"]["items"] = rows
            self._save_locked()
            return self._routine_payload_locked(key)

    def set_routine_done(self, item_id, done):
        item_id = _clean(item_id, 32)
        key = today_key()
        with self._lock:
            self._load_locked()
            known = {str(i.get("id")) for i in self._data["routine"]["items"]}
            if item_id not in known:
                raise PlannerValidationError("unknown routine item")
            ticks = set(self._data["routine"]["done"].get(key) or [])
            if done:
                ticks.add(item_id)
            else:
                ticks.discard(item_id)
            self._data["routine"]["done"][key] = sorted(ticks)
            self._save_locked()
            return self._routine_payload_locked(key)
