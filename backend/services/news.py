"""AI news feed: Hacker News top stories (keyword filtered) + the arXiv cs.AI RSS."""
import html
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

HN_API = "https://hacker-news.firebaseio.com/v0"
ARXIV_RSS = "https://rss.arxiv.org/rss/cs.AI"
TIMEOUT = 10
HN_SCAN = 90  # how many top stories to inspect
LIMIT = 10
USER_AGENT = "home-dashboard/1.0 (personal desktop dashboard)"

# Word-boundary matching so "AI" does not fire on "said", "chain", "email".
KEYWORDS = re.compile(
    r"\b(a\.?i\.?|llms?|gpts?|claude|machine learning|neural|"
    r"artificial intelligence|openai|anthropic|transformers?|deep learning)\b",
    re.IGNORECASE,
)


class NewsError(RuntimeError):
    """Raised when no source could be reached."""


def _clean(text, limit=280):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip()


def _hacker_news():
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    resp = session.get(f"{HN_API}/topstories.json", timeout=TIMEOUT)
    resp.raise_for_status()
    ids = (resp.json() or [])[:HN_SCAN]

    def item(story_id):
        try:
            r = session.get(f"{HN_API}/item/{story_id}.json", timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=16) as pool:
        stories = list(pool.map(item, ids))

    out = []
    for rank, story in enumerate(stories):
        if not story or story.get("type") != "story":
            continue
        title = story.get("title") or ""
        if not KEYWORDS.search(title):
            continue
        out.append(
            {
                "title": _clean(title, 200),
                "source": "Hacker News",
                "url": story.get("url")
                or f"https://news.ycombinator.com/item?id={story.get('id')}",
                "comments_url": f"https://news.ycombinator.com/item?id={story.get('id')}",
                "score": story.get("score"),
                "published": story.get("time"),
                "rank": rank,
                "summary": "",
            }
        )
    return out


def _arxiv():
    resp = requests.get(
        ARXIV_RSS, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    out = []
    for rank, item in enumerate(root.iterfind(".//channel/item")):
        title = _clean(item.findtext("title") or "", 200)
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append(
            {
                "title": title,
                "source": "arXiv cs.AI",
                "url": link,
                "comments_url": None,
                "score": None,
                "published": None,
                "rank": rank,
                "summary": _clean(item.findtext("description") or "", 220),
            }
        )
    return out


def fetch(limit=LIMIT):
    """Interleave both sources so neither one crowds the list out."""
    errors = []
    results = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {"hn": pool.submit(_hacker_news), "arxiv": pool.submit(_arxiv)}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except Exception as exc:  # noqa: BLE001 - one dead source must not kill the card
                results[name] = []
                errors.append(f"{name}: {exc}")

    hn, arxiv = results.get("hn", []), results.get("arxiv", [])
    if not hn and not arxiv:
        raise NewsError("; ".join(errors) or "no news sources reachable")

    items, seen = [], set()
    for pair in zip_longest_pairs(hn, arxiv):
        for entry in pair:
            if entry is None:
                continue
            key = entry["url"]
            if key in seen:
                continue
            seen.add(key)
            items.append(entry)
            if len(items) >= limit:
                return {
                    "available": True,
                    "items": items,
                    "sources": {"hacker_news": len(hn), "arxiv": len(arxiv)},
                    "errors": errors,
                }
    return {
        "available": True,
        "items": items,
        "sources": {"hacker_news": len(hn), "arxiv": len(arxiv)},
        "errors": errors,
    }


def zip_longest_pairs(left, right):
    for index in range(max(len(left), len(right))):
        yield (
            left[index] if index < len(left) else None,
            right[index] if index < len(right) else None,
        )
