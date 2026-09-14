"""Folder shortcuts, recent files and the "open it" action behind the
Folders / Files card.

The backend only ever opens something it listed itself: a folder by the id
from folders.json, or a file whose real path sits inside one of the recent-
files directories. The browser never gets to name an arbitrary path.
"""
import json
import os
import shutil
import subprocess
import threading
import time

# Shortcuts a fresh install starts with; only the ones that exist are kept.
DEFAULT_FOLDERS = [
    ("home", "Home", "~"),
    ("downloads", "Downloads", "~/Downloads"),
    ("documents", "Documents", "~/Documents"),
    ("pictures", "Pictures", "~/Pictures"),
    ("desktop", "Desktop", "~/Desktop"),
    ("ocirrf", "ocirrf", "~/ocirrf"),
    ("dashboard", "Dashboard", "~/home-dashboard"),
    ("studexa", "Studexa", "~/studexa"),
]
DEFAULT_FILES_DIRS = ["~/Downloads", "~/Desktop", "~/Documents"]
MAX_FOLDERS = 12
MAX_FILES = 8
SKIP_SUFFIXES = (".part", ".crdownload", ".tmp", "~")
OPENERS = [["xdg-open"], ["thunar"], ["nautilus"], ["dolphin"]]


class PlacesError(RuntimeError):
    """Raised when a shortcut cannot be listed or opened."""


def _display(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def _expand(path):
    return os.path.realpath(os.path.expanduser(str(path or "")))


class Places:
    def __init__(self, config_path):
        self.config_path = config_path
        self._lock = threading.Lock()
        self._config = None

    # ---------- config ----------

    def _seed(self):
        folders = [
            {"id": key, "name": name, "path": path}
            for key, name, path in DEFAULT_FOLDERS
            if os.path.isdir(os.path.expanduser(path))
        ]
        return {"folders": folders, "files_dirs": list(DEFAULT_FILES_DIRS)}

    def _load_locked(self):
        if self._config is not None:
            return self._config
        parsed = None
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                parsed = json.load(handle)
        except FileNotFoundError:
            parsed = None
        except (OSError, ValueError):
            try:
                os.replace(self.config_path, f"{self.config_path}.corrupt")
            except OSError:
                pass
            parsed = None

        if not isinstance(parsed, dict):
            self._config = self._seed()
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as handle:
                    json.dump(self._config, handle, indent=2)
            except OSError:
                pass  # a read-only data dir still lets the defaults work
            return self._config

        folders = []
        seen = set()
        for row in parsed.get("folders", []) if isinstance(parsed.get("folders"), list) else []:
            if not isinstance(row, dict):
                continue
            key = str(row.get("id") or "").strip()
            path = str(row.get("path") or "").strip()
            if not key or not path or key in seen:
                continue
            seen.add(key)
            folders.append({"id": key, "name": str(row.get("name") or key)[:32], "path": path})
        files_dirs = parsed.get("files_dirs")
        if not isinstance(files_dirs, list) or not files_dirs:
            files_dirs = list(DEFAULT_FILES_DIRS)
        self._config = {"folders": folders[:MAX_FOLDERS], "files_dirs": [str(d) for d in files_dirs]}
        return self._config

    # ---------- reads ----------

    def folders(self):
        with self._lock:
            config = self._load_locked()
        rows = []
        for folder in config["folders"]:
            full = _expand(folder["path"])
            rows.append(
                {
                    "id": folder["id"],
                    "name": folder["name"],
                    "path": _display(full),
                    "exists": os.path.isdir(full),
                }
            )
        return {"available": True, "folders": rows, "config": _display(self.config_path)}

    def files(self):
        with self._lock:
            config = self._load_locked()
        found = []
        for raw in config["files_dirs"]:
            directory = _expand(raw)
            try:
                entries = list(os.scandir(directory))
            except OSError:
                continue
            for entry in entries:
                name = entry.name
                if name.startswith(".") or name.endswith(SKIP_SUFFIXES):
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                found.append(
                    {
                        "name": name,
                        "path": entry.path,
                        "dir": _display(directory),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "kind": os.path.splitext(name)[1].lstrip(".").lower(),
                    }
                )
        found.sort(key=lambda row: row["modified"], reverse=True)
        return {
            "available": True,
            "files": found[:MAX_FILES],
            "dirs": [_display(_expand(d)) for d in config["files_dirs"]],
            "fetched_at": time.time(),
        }

    # ---------- open ----------

    def _resolve(self, folder=None, file=None):
        with self._lock:
            config = self._load_locked()
        if folder:
            for row in config["folders"]:
                if row["id"] == folder:
                    full = _expand(row["path"])
                    if not os.path.isdir(full):
                        raise PlacesError(f"{_display(full)} does not exist")
                    return full
            raise PlacesError("unknown folder shortcut")
        if file:
            full = _expand(file)
            roots = [_expand(d) for d in config["files_dirs"]]
            inside = any(os.path.dirname(full) == root for root in roots)
            if not inside or not os.path.isfile(full):
                raise PlacesError("that file is not in a listed folder")
            return full
        raise PlacesError("nothing to open")

    def open(self, folder=None, file=None):
        target = self._resolve(folder=folder, file=file)
        env = dict(os.environ)
        # The backend runs as a systemd user service, which does not always
        # inherit the X session; fall back to the usual display so the file
        # manager still appears on the desktop.
        env.setdefault("DISPLAY", ":0")
        xauth = os.path.expanduser("~/.Xauthority")
        if "XAUTHORITY" not in env and os.path.exists(xauth):
            env["XAUTHORITY"] = xauth
        attempts = []
        for command in OPENERS:
            if shutil.which(command[0]) is None:
                attempts.append({"command": command[0], "error": "command not found"})
                continue
            try:
                subprocess.Popen(
                    [*command, target],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return {"ok": True, "opened": _display(target), "with": command[0]}
            except OSError as exc:
                attempts.append({"command": command[0], "error": str(exc)})
        raise PlacesError(f"no opener found ({attempts})")
