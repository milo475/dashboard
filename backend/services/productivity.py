"""Turns ActivityWatch window time into a productive / neutral / leisure split.

The classification rules live in backend/productivity_rules.json so they can be
tuned without touching code; the file is re-read whenever its mtime changes.
"""
import json
import os
import threading
from datetime import datetime

from .activitywatch import ActivityWatchError

CATEGORIES = ("productive", "neutral", "leisure")

DEFAULT_RULES = {
    "productive": ["code", "vs code", "terminal", "gnome-terminal", "claude"],
    "neutral": ["files", "settings"],
    "leisure": ["youtube", "netflix", "steam"],
}

# A browser is whatever its front tab is, so it is classified on the title.
DEFAULT_BROWSER_TITLES = {
    "productive": [
        "github",
        "stackoverflow",
        "stack overflow",
        "localhost",
        "docs",
        "developer.mozilla",
        "claude.ai",
    ],
    "leisure": ["youtube", "netflix", "twitch", "instagram", "tiktok", "reddit"],
}

BROWSER_APPS = (
    "chrome",
    "chromium",
    "firefox",
    "navigator",
    "brave",
    "msedge",
    "microsoft-edge",
    "vivaldi",
    "opera",
)

TOP_N = 5


def _is_browser(app):
    app = (app or "").lower()
    return any(token in app for token in BROWSER_APPS)


class RulesFile:
    """The rules JSON, reloaded on demand when the file changes on disk."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._mtime = None
        self._rules = None
        self._error = None

    def _normalise(self, raw):
        rules = {}
        for category in CATEGORIES:
            values = raw.get(category) if isinstance(raw, dict) else None
            rules[category] = [
                str(v).strip().lower()
                for v in (values if isinstance(values, list) else [])
                if str(v).strip()
            ]
        browser = (raw or {}).get("browser_titles")
        if not isinstance(browser, dict):
            browser = DEFAULT_BROWSER_TITLES
        rules["browser_titles"] = {
            "productive": [
                str(v).strip().lower()
                for v in browser.get("productive", DEFAULT_BROWSER_TITLES["productive"])
                if str(v).strip()
            ],
            "leisure": [
                str(v).strip().lower()
                for v in browser.get("leisure", DEFAULT_BROWSER_TITLES["leisure"])
                if str(v).strip()
            ],
        }
        return rules

    def get(self):
        with self._lock:
            try:
                mtime = os.path.getmtime(self.path)
            except OSError:
                # No rules file: run on the built-in defaults rather than
                # refusing to score anything.
                if self._rules is None:
                    self._rules = self._normalise(DEFAULT_RULES)
                    self._error = f"{os.path.basename(self.path)} not found - using defaults"
                return self._rules, self._error
            if mtime != self._mtime or self._rules is None:
                try:
                    with open(self.path, "r", encoding="utf-8") as handle:
                        self._rules = self._normalise(json.load(handle))
                    self._error = None
                except (OSError, ValueError) as exc:
                    self._rules = self._normalise(DEFAULT_RULES)
                    self._error = f"rules file is invalid ({exc}) - using defaults"
                self._mtime = mtime
            return self._rules, self._error


def classify(app, title, rules):
    """Category for one window.

    Matching is case-insensitive substring, and the *longest* matching keyword
    wins so a specific rule beats a generic one ("vs code" over "code") no
    matter which category each sits in. Anything unmatched is neutral.
    """
    app_l = (app or "").lower()
    title_l = (title or "").lower()

    if _is_browser(app_l):
        browser = rules["browser_titles"]
        best = (0, "neutral")
        for category in ("leisure", "productive"):
            for keyword in browser[category]:
                if keyword in title_l and len(keyword) > best[0]:
                    best = (len(keyword), category)
        return best[1]

    best_len, best_category = 0, "neutral"
    for category in CATEGORIES:
        for keyword in rules[category]:
            if len(keyword) <= best_len:
                continue
            if keyword in app_l or keyword in title_l:
                best_len, best_category = len(keyword), category
    return best_category


def _score(productive_s, leisure_s):
    """Productive share of deliberate time. Neutral time is excluded on purpose:
    it is neither a win nor a loss, and counting it would dilute both."""
    denominator = productive_s + leisure_s
    if denominator <= 0:
        return None
    return round(productive_s / denominator * 100, 1)


class ProductivityService:
    def __init__(self, aw_client, rules_path):
        self.aw = aw_client
        self.rules = RulesFile(rules_path)

    def report(self, days=7):
        rules, rules_error = self.rules.get()
        sessions = self.aw.sessions(days)

        daily = []
        today_apps = {}
        for index, day in enumerate(sessions["days"]):
            buckets = {category: 0.0 for category in CATEGORIES}
            is_today = index == len(sessions["days"]) - 1
            for row in day["rows"]:
                category = classify(row["app"], row["title"], rules)
                buckets[category] += row["seconds"]
                if is_today:
                    key = (row["pretty"], category)
                    today_apps[key] = today_apps.get(key, 0.0) + row["seconds"]
            entry = {
                "date": day["date"],
                "label": datetime.strptime(day["date"], "%Y-%m-%d").strftime("%a"),
                "score": _score(buckets["productive"], buckets["leisure"]),
            }
            for category in CATEGORIES:
                entry[f"{category}_minutes"] = round(buckets[category] / 60, 1)
            entry["total_minutes"] = round(sum(buckets.values()) / 60, 1)
            daily.append(entry)

        top = [
            {"app": app, "category": category, "minutes": round(seconds / 60, 1)}
            for (app, category), seconds in sorted(
                today_apps.items(), key=lambda kv: kv[1], reverse=True
            )[:TOP_N]
        ]

        today = daily[-1] if daily else {
            "date": None,
            "label": "",
            "score": None,
            "total_minutes": 0.0,
            **{f"{c}_minutes": 0.0 for c in CATEGORIES},
        }
        week = {
            f"{category}_minutes": round(
                sum(d[f"{category}_minutes"] for d in daily), 1
            )
            for category in CATEGORIES
        }
        week["score"] = _score(week["productive_minutes"], week["leisure_minutes"])

        return {
            "available": True,
            "today": today,
            "daily": daily,
            "week": week,
            "top": top,
            "afk_filtered": sessions["afk_filtered"],
            "rules_path": self.rules.path,
            "rules_error": rules_error,
        }
