"""Images for the Photos collage: whatever is dropped into backend/data/photos.

Listing is cheap (one directory scan) and the files are served straight from
that directory, so adding a photo is copying a file - no upload flow needed on
a dashboard that lives on the same machine.
"""
import os
import re
import time
from urllib.parse import quote

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
MAX_PHOTOS = 24
MAX_BYTES = 25 * 1024 * 1024  # per photo


class PhotoError(RuntimeError):
    """Raised when an upload or removal is refused."""


def _safe_name(filename):
    """'IMG 01 (2).JPEG' -> ('IMG-01-2', '.jpg'); Cyrillic letters are kept."""
    base = os.path.basename(str(filename or ""))
    stem, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    stem = re.sub(r"[^\w\-]+", "-", stem).strip("-_") or "photo"
    return stem[:60], ext


class PhotoLibrary:
    def __init__(self, directory):
        self.directory = directory

    def list(self):
        try:
            os.makedirs(self.directory, exist_ok=True)
            entries = list(os.scandir(self.directory))
        except OSError as exc:
            return {"available": False, "error": str(exc), "dir": self.directory}
        photos = []
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if os.path.splitext(entry.name)[1].lower() not in IMAGE_EXT:
                continue
            try:
                if not entry.is_file():
                    continue
                modified = entry.stat().st_mtime
            except OSError:
                continue
            photos.append({"name": entry.name, "url": f"/api/photos/{quote(entry.name)}", "modified": modified})
        # Newest first, so a photo added today lands in the collage right away.
        photos.sort(key=lambda row: row["modified"], reverse=True)
        return {
            "available": True,
            "photos": photos[:MAX_PHOTOS],
            "count": len(photos),
            "dir": self.directory,
            "fetched_at": time.time(),
        }

    def save(self, files):
        """Store uploaded images (werkzeug FileStorage objects). Returns
        (saved names, rejected [{name, error}]); a bad file never blocks the
        good ones next to it."""
        os.makedirs(self.directory, exist_ok=True)
        saved, rejected = [], []
        for item in files:
            stem, ext = _safe_name(item.filename)
            if ext not in IMAGE_EXT:
                rejected.append({"name": item.filename, "error": "not an image"})
                continue
            data = item.read(MAX_BYTES + 1)
            if not data:
                rejected.append({"name": item.filename, "error": "empty file"})
                continue
            if len(data) > MAX_BYTES:
                rejected.append({"name": item.filename, "error": "larger than 25 MB"})
                continue
            name = f"{stem}{ext}"
            counter = 1
            while os.path.exists(os.path.join(self.directory, name)):
                counter += 1
                name = f"{stem}-{counter}{ext}"
            with open(os.path.join(self.directory, name), "wb") as handle:
                handle.write(data)
            saved.append(name)
        return saved, rejected

    def remove(self, name):
        base = os.path.basename(str(name or ""))
        if not base or base != name or base.startswith("."):
            raise PhotoError("bad photo name")
        path = os.path.join(self.directory, base)
        if not os.path.isfile(path):
            raise PhotoError("no such photo")
        os.remove(path)
        return base
