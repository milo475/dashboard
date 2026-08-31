"""Reads per-application active time out of a local ActivityWatch server."""
from datetime import datetime, timedelta

import requests

DEFAULT_BASE = "http://localhost:5600/api/0"
TIMEOUT = 8
DAYS = 7
TOP_N = 8

# ActivityWatch reports the raw X11 class, which is not always presentable.
ALIASES = {
    "navigator": "Firefox",
    "firefox-esr": "Firefox",
    "google-chrome": "Chrome",
    "chromium": "Chromium",
    "code": "VS Code",
    "code-oss": "VS Code",
    "gnome-terminal-server": "Terminal",
    "xfce4-terminal": "Terminal",
    "qterminal": "Terminal",
    "org.wezfurlong.wezterm": "WezTerm",
    "jetbrains-idea": "IntelliJ",
    "thunar": "Files",
    "com.anthropic.claude": "Claude",
}


# Desktop-shell components are not "apps the user used" - the panel, the
# desktop backdrop and the window manager would otherwise crowd the ranking.
IGNORED_APPS = {
    "wrapper-2.0",
    "xfce4-panel",
    "xfdesktop",
    "xfwm4",
    "xfsettingsd",
    "xfce4-session",
    "desktop",
    "",
}


class ActivityWatchError(RuntimeError):
    """Raised when the ActivityWatch server is unreachable or unusable."""


def _pretty(app):
    if not app:
        return "Unknown"
    app = app.strip()
    key = app.lower()
    if key in ALIASES:
        return ALIASES[key]
    # Reverse-DNS ids ("com.anthropic.Claude", "org.gnome.Nautilus") are far too
    # long for an axis label - keep the trailing name.
    parts = app.split(".")
    if len(parts) >= 3 and all(part and part.isalnum() for part in parts):
        app = parts[-1]
        if app.lower() in ALIASES:
            return ALIASES[app.lower()]
    return app if any(c.isupper() for c in app) else app.capitalize()


def _day_bounds(days=DAYS):
    """Local-midnight boundaries for the last `days` days, oldest first."""
    now = datetime.now().astimezone()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    starts = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    return [(start, start + timedelta(days=1)) for start in starts]


def _has_events(per_day_events):
    """True if any period returned at least one event with real duration."""
    for events in per_day_events or []:
        for event in events or []:
            if float((event or {}).get("duration") or 0) > 0:
                return True
    return False


class ActivityWatchClient:
    def __init__(self, base_url=DEFAULT_BASE):
        self.base_url = base_url.rstrip("/")

    def _get(self, path, **kwargs):
        return requests.get(f"{self.base_url}{path}", timeout=TIMEOUT, **kwargs)

    def buckets(self):
        try:
            resp = self._get("/buckets/")
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise ActivityWatchError(f"ActivityWatch is not reachable: {exc}") from exc
        except ValueError as exc:
            raise ActivityWatchError("ActivityWatch returned an invalid response") from exc

    def _pick_buckets(self):
        buckets = self.buckets()
        window = afk = None
        for bucket_id, meta in buckets.items():
            btype = (meta or {}).get("type", "")
            if btype == "currentwindow" and window is None:
                window = bucket_id
            elif btype == "afkstatus" and afk is None:
                afk = bucket_id
        if window is None:
            # Fall back to a name match in case the bucket type is missing.
            window = next(
                (b for b in buckets if b.startswith("aw-watcher-window")), None
            )
        if window is None:
            raise ActivityWatchError(
                "No aw-watcher-window bucket found - is the window watcher running?"
            )
        return window, afk

    def _query(self, window_bucket, afk_bucket, periods):
        """One query2 request covering every day, so we hit the server once."""
        lines = [f'window = query_bucket("{window_bucket}");']
        if afk_bucket:
            lines += [
                f'afk = query_bucket("{afk_bucket}");',
                'afk = filter_keyvals(afk, "status", ["not-afk"]);',
                "window = filter_period_intersect(window, afk);",
            ]
        lines += [
            'merged = merge_events_by_keys(window, ["app"]);',
            "RETURN = sort_by_duration(merged);",
        ]
        payload = {
            "query": lines,
            "timeperiods": [
                f"{start.isoformat()}/{end.isoformat()}" for start, end in periods
            ],
        }
        try:
            resp = requests.post(
                f"{self.base_url}/query/", json=payload, timeout=TIMEOUT * 3
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise ActivityWatchError(f"ActivityWatch query failed: {exc}") from exc
        except ValueError as exc:
            raise ActivityWatchError("ActivityWatch query returned invalid JSON") from exc

    def _raw_fallback(self, window_bucket, periods):
        """Aggregate raw events when query2 is unavailable (older servers)."""
        out = []
        for start, end in periods:
            try:
                resp = self._get(
                    f"/buckets/{window_bucket}/events",
                    params={
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "limit": -1,
                    },
                )
                resp.raise_for_status()
                events = resp.json()
            except (requests.RequestException, ValueError):
                events = []
            out.append(events)
        return out

    def usage(self, days=DAYS, top_n=TOP_N):
        window_bucket, afk_bucket = self._pick_buckets()
        periods = _day_bounds(days)
        afk_filtered = bool(afk_bucket)
        try:
            per_day_events = self._query(window_bucket, afk_bucket, periods)
        except ActivityWatchError:
            per_day_events = self._raw_fallback(window_bucket, periods)
            afk_filtered = False

        # An AFK watcher that is stopped (or has only just started) leaves an
        # empty afk bucket, and the period intersect would then discard every
        # window event. Fall back to unfiltered time rather than showing zero.
        if afk_bucket and not _has_events(per_day_events):
            try:
                unfiltered = self._query(window_bucket, None, periods)
            except ActivityWatchError:
                unfiltered = self._raw_fallback(window_bucket, periods)
            if _has_events(unfiltered):
                per_day_events = unfiltered
                afk_filtered = False

        # date -> {app: seconds}
        per_day = []
        totals = {}
        for (start, _end), events in zip(periods, per_day_events):
            day_totals = {}
            for event in events or []:
                data = (event or {}).get("data") or {}
                raw = (data.get("app") or "").strip()
                if raw.lower() in IGNORED_APPS:
                    continue
                app = _pretty(raw)
                seconds = float((event or {}).get("duration") or 0)
                if seconds <= 0:
                    continue
                day_totals[app] = day_totals.get(app, 0.0) + seconds
                totals[app] = totals.get(app, 0.0) + seconds
            per_day.append({"date": start.strftime("%Y-%m-%d"), "apps": day_totals})

        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        top_apps = [app for app, _ in ranked[:top_n]]
        top_set = set(top_apps)
        has_other = len(ranked) > len(top_apps)

        daily = []
        for row in per_day:
            entry = {
                "date": row["date"],
                "label": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%a"),
            }
            other = 0.0
            for app, seconds in row["apps"].items():
                if app in top_set:
                    entry[app] = round(seconds / 3600, 3)
                else:
                    other += seconds
            for app in top_apps:
                entry.setdefault(app, 0.0)
            if has_other:
                entry["Other"] = round(other / 3600, 3)
            entry["total"] = round(sum(row["apps"].values()) / 3600, 3)
            daily.append(entry)

        today_apps = per_day[-1]["apps"] if per_day else {}
        today = [
            {"app": app, "hours": round(seconds / 3600, 3)}
            for app, seconds in sorted(
                today_apps.items(), key=lambda kv: kv[1], reverse=True
            )
        ]

        return {
            "available": True,
            "bucket": window_bucket,
            "afk_filtered": afk_filtered,
            "top_apps": top_apps + (["Other"] if has_other else []),
            "totals": [
                {"app": app, "hours": round(seconds / 3600, 3)}
                for app, seconds in ranked[:top_n]
            ],
            "daily": daily,
            "today": today,
            "today_total_hours": round(sum(today_apps.values()) / 3600, 3),
            "week_total_hours": round(sum(totals.values()) / 3600, 3),
        }
