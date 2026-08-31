"""Recent public GitHub activity for a single user.

Works unauthenticated (60 requests/hour per IP, and the 5-minute cache keeps us
far under that). If GITHUB_TOKEN is present in backend/.env it is used purely to
raise the rate limit - no private data is requested either way.
"""
import os
import time
from datetime import datetime, timezone

import requests

API = "https://api.github.com"
TIMEOUT = 10
EVENT_LIMIT = 5
REPO_LIMIT = 5
MAX_COMPARES = 4        # cap the extra requests spent recovering a commit count
RATE_FLOOR = 12         # leave this much rate limit unspent for the next refresh

# GitHub emits a lot of event types; these are the ones worth a line on a
# dashboard. Push/PR/issue are the headline three, the rest keep the feed from
# looking dead during a week of repo setup and releases.
EVENT_LABELS = {
    "PushEvent": "push",
    "PullRequestEvent": "pr",
    "IssuesEvent": "issue",
    "IssueCommentEvent": "comment",
    "PullRequestReviewEvent": "review",
    "CreateEvent": "create",
    "ReleaseEvent": "release",
    "ForkEvent": "fork",
}


class GitHubError(RuntimeError):
    """Raised when GitHub cannot be reached or refuses the request."""


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _describe(event):
    """One short human line for an event, plus a URL worth opening."""
    kind = event.get("type")
    payload = event.get("payload") or {}
    full_name = (event.get("repo") or {}).get("name") or ""
    repo_url = f"https://github.com/{full_name}"

    if kind == "PushEvent":
        count = payload.get("distinct_size")
        if count is None:
            count = payload.get("size")
        branch = str(payload.get("ref") or "").rsplit("/", 1)[-1]
        commits = payload.get("commits") or []
        message = ""
        if commits:
            message = str(commits[-1].get("message") or "").splitlines()[0]
        if count is None:
            # Minimal payload with no commit count - don't claim "0 commits".
            action = f"pushed to {branch}" if branch else "pushed"
        else:
            action = f"pushed {count} commit{'' if count == 1 else 's'} to {branch}"
        return action, message, repo_url
    if kind == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        number = payload.get("number") or pr.get("number") or "?"
        return (
            f"{payload.get('action', 'updated')} PR #{number}",
            str(pr.get("title") or ""),
            pr.get("html_url") or repo_url,
        )
    if kind == "IssuesEvent":
        issue = payload.get("issue") or {}
        number = issue.get("number", "?")
        return (
            f"{payload.get('action', 'updated')} issue #{number}",
            str(issue.get("title") or ""),
            issue.get("html_url") or repo_url,
        )
    if kind == "IssueCommentEvent":
        issue = payload.get("issue") or {}
        return (
            f"commented on #{issue.get('number', '?')}",
            str(issue.get("title") or ""),
            (payload.get("comment") or {}).get("html_url") or repo_url,
        )
    if kind == "PullRequestReviewEvent":
        pr = payload.get("pull_request") or {}
        return (
            f"reviewed PR #{pr.get('number', '?')}",
            str(pr.get("title") or ""),
            pr.get("html_url") or repo_url,
        )
    if kind == "CreateEvent":
        what = payload.get("ref_type") or "ref"
        ref = payload.get("ref")
        return (f"created {what}" + (f" {ref}" if ref else ""), "", repo_url)
    if kind == "ReleaseEvent":
        release = payload.get("release") or {}
        return (
            f"released {release.get('tag_name') or ''}".strip(),
            str(release.get("name") or ""),
            release.get("html_url") or repo_url,
        )
    if kind == "ForkEvent":
        return "forked", "", repo_url
    return EVENT_LABELS.get(kind, str(kind or "activity")), "", repo_url


class GitHubClient:
    def __init__(self, user, token=""):
        self.user = (user or "").strip()
        self.token = (token or "").strip()
        self._rate_remaining = None

    def _budget(self):
        """Requests we are willing to spend beyond the two mandatory ones."""
        try:
            return max(0, int(self._rate_remaining) - RATE_FLOOR)
        except (TypeError, ValueError):
            return MAX_COMPARES if self.token else 0

    def _commits_from_compare(self, pushes):
        """Recover a commit count when the events feed omits `size`.

        Some GitHub responses carry a minimal PushEvent payload with no commit
        count at all. Collapsing every push on a branch into one before...head
        compare gets the real number back for one request per branch touched.
        """
        by_ref = {}
        for event in pushes:
            payload = event.get("payload") or {}
            before, head = payload.get("before"), payload.get("head")
            if not before or not head:
                continue
            key = ((event.get("repo") or {}).get("name"), payload.get("ref"))
            if not key[0]:
                continue
            span = by_ref.setdefault(key, {"before": before, "head": head, "at": None})
            created = _parse_ts(event.get("created_at"))
            # Keep the oldest `before` and the newest `head` for the branch.
            if span["at"] is None or (created and created > span["at"]):
                span["head"], span["at"] = head, created
            if span.get("first_at") is None or (created and created < span["first_at"]):
                span["before"], span["first_at"] = before, created

        total = 0
        spent = 0
        allowance = min(MAX_COMPARES, self._budget())
        for (repo, _ref), span in by_ref.items():
            if spent >= allowance:
                return None  # partial numbers are worse than an honest fallback
            spent += 1
            try:
                diff = self._get(
                    f"/repos/{repo}/compare/{span['before']}...{span['head']}",
                    _soft404=True,
                )
            except GitHubError:
                return None
            if not isinstance(diff, dict):
                return None
            total += int(diff.get("total_commits") or 0)
        return total if by_ref else 0

    def _headers(self):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "home-dashboard",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, path, _soft404=False, **params):
        """GET one endpoint. `_soft404` returns None instead of raising, for
        optional lookups (a force-pushed or deleted ref compares to nothing)."""
        try:
            resp = requests.get(
                f"{API}{path}",
                headers=self._headers(),
                params=params or None,
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise GitHubError(f"GitHub is not reachable: {exc}") from exc

        self._rate_remaining = resp.headers.get("X-RateLimit-Remaining")
        if resp.status_code == 404:
            if _soft404:
                return None
            raise GitHubError(f"No such GitHub user: {self.user}")
        if resp.status_code in (403, 429):
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining == "0":
                reset = resp.headers.get("X-RateLimit-Reset")
                when = ""
                if reset and reset.isdigit():
                    minutes = max(0, int((int(reset) - time.time()) / 60))
                    when = f" (resets in ~{minutes}m)"
                raise GitHubError(
                    f"GitHub rate limit reached{when} - "
                    "set GITHUB_TOKEN in backend/.env for a higher limit"
                )
            raise GitHubError("GitHub refused the request (403)")
        try:
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise GitHubError(f"GitHub request failed: {exc}") from exc
        except ValueError as exc:
            raise GitHubError("GitHub returned invalid JSON") from exc

    def activity(self):
        if not self.user:
            raise GitHubError("No GitHub user configured - set GITHUB_USER in backend/.env")

        events = self._get(f"/users/{self.user}/events/public", per_page=100)
        if not isinstance(events, list):
            raise GitHubError("Unexpected events payload from GitHub")

        # "Today" means the user's local day, not UTC - the dashboard sits on a
        # desk, and a commit at 09:00 local should count for today.
        local_midnight = (
            datetime.now()
            .astimezone()
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )

        pushes_today = []
        counted = 0
        counts_present = False
        feed = []
        for event in sorted(
            events, key=lambda e: str(e.get("created_at") or ""), reverse=True
        ):
            created = _parse_ts(event.get("created_at"))
            if created is None:
                continue
            if event.get("type") == "PushEvent" and created.astimezone() >= local_midnight:
                payload = event.get("payload") or {}
                size = payload.get("distinct_size")
                if size is None:
                    size = payload.get("size")
                if size is not None:
                    counts_present = True
                    counted += int(size)
                pushes_today.append(event)
            if event.get("type") not in EVENT_LABELS or len(feed) >= EVENT_LIMIT:
                continue
            action, detail, url = _describe(event)
            feed.append(
                {
                    "id": str(event.get("id") or f"{created.timestamp()}"),
                    "kind": EVENT_LABELS[event["type"]],
                    "repo": ((event.get("repo") or {}).get("name") or "").split("/")[-1],
                    "action": action,
                    "detail": detail,
                    "url": url,
                    "at": created.astimezone(timezone.utc).isoformat(),
                }
            )

        if counts_present:
            commits_today, commits_source = counted, "events"
        else:
            recovered = self._commits_from_compare(pushes_today)
            if recovered is None:
                # Out of budget or the refs are gone: report what we know for
                # certain - how many times the user pushed - and say so.
                commits_today, commits_source = len(pushes_today), "pushes"
            else:
                commits_today, commits_source = recovered, "compare"

        repos = self._get(
            f"/users/{self.user}/repos", sort="pushed", per_page=REPO_LIMIT, type="owner"
        )
        if not isinstance(repos, list):
            repos = []
        recent_repos = [
            {
                "name": repo.get("name"),
                "url": repo.get("html_url"),
                "language": repo.get("language"),
                "private": bool(repo.get("private")),
                "stars": repo.get("stargazers_count") or 0,
                "pushed_at": repo.get("pushed_at"),
            }
            for repo in repos[:REPO_LIMIT]
            if repo.get("name")
        ]

        return {
            "available": True,
            "user": self.user,
            "authenticated": bool(self.token),
            "commits_today": commits_today,
            # "events" = GitHub gave us commit counts, "compare" = we derived
            # them, "pushes" = the number is pushes, not commits. The card
            # labels itself accordingly instead of quietly mislabelling.
            "commits_source": commits_source,
            "pushes_today": len(pushes_today),
            "events": feed,
            "repos": recent_repos,
            # The public events feed only reaches back ~90 days / 300 events,
            # so an empty feed is not the same as an inactive account.
            "events_scanned": len(events),
            "fetched_at": time.time(),
        }
