"""Tiny thread-safe TTL cache used by the API endpoints."""
import threading
import time


class TTLCache:
    """Stores one value per key and serves it until it goes stale.

    On refresh failure the previous (stale) value is served instead, so a
    flaky network shows slightly old data rather than an empty card.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entries = {}

    def get_or_refresh(self, key, ttl, producer, max_stale=None):
        """Serve a cached value while fresh; refresh when stale.

        If a refresh fails, the previous value is served (marked stale) so a
        brief outage does not blank a card - but only up to `max_stale`
        seconds. Past that the error is raised, because a 24/7 dashboard
        showing hours-old numbers as current is worse than showing "no data".
        """
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry and now - entry["at"] < ttl:
                return entry["value"], entry["at_wall"], False

        try:
            value = producer()
        except Exception as exc:  # noqa: BLE001 - surface as stale-or-error, never crash
            with self._lock:
                entry = self._entries.get(key)
            if entry and (
                max_stale is None or time.monotonic() - entry["at"] <= max_stale
            ):
                return entry["value"], entry["at_wall"], True
            raise exc

        with self._lock:
            self._entries[key] = {
                "value": value,
                "at": time.monotonic(),
                "at_wall": time.time(),
            }
        return value, self._entries[key]["at_wall"], False

    def peek(self, key):
        with self._lock:
            entry = self._entries.get(key)
        return entry["value"] if entry else None
