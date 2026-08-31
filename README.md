# home-dashboard

A personal desktop dashboard for Kali Linux, built to run 24/7 pinned to the
desktop as a frameless Chromium app window.

![layout](docs/layout.png)

- **App usage** — 7 days of per-application active time from ActivityWatch
- **Productivity** — that same time scored productive / neutral / leisure
- **System** — CPU, RAM, disk, network, temperature, uptime and load
- **Focus** — today's goals plus a 25/5 Pomodoro timer
- **Markets** — the ten largest US tech companies, via Finnhub
- **GitHub** — recent repos, today's commits and a public activity feed
- **AI feed** — Hacker News (AI-filtered) + the arXiv `cs.AI` RSS feed
- **Claude** — a launcher button for Claude Desktop

Backend: Flask on `:5000`. Frontend: React + Vite on `:3300`.

> **Why :3300 and not :3000?** Port 3000 on this machine is already taken by the
> `ursGAL` backend. To move the dashboard back to 3000, change the port in
> `frontend/vite.config.js`, `systemd/dashboard-frontend.service`, and
> `start.sh` — or just run with `DASHBOARD_PORT=3000 ./start.sh`.

---

## 1. Requirements

- Python 3.11+, Node 18+, and `chromium` (all present on stock Kali)
- ActivityWatch (see below) for the usage and productivity cards
- A free Finnhub API key for the markets card
- `psutil` for the system card — installed by `requirements.txt`
- **Optional:** `lm-sensors` for the CPU temperature

### CPU temperature

The system card reads the temperature from `psutil.sensors_temperatures()`
first, and falls back to parsing `sensors` output. If neither has a reading the
card shows **n/a** for temperature and everything else keeps working — nothing
about this is required.

To enable it:

```bash
sudo apt install lm-sensors
sudo sensors-detect --auto   # answer yes; it writes /etc/modules
sensors                      # should now print "Package id 0: +45.0°C"
```

`coretemp` (Intel) and `k10temp` (AMD) are preferred over the `acpitz`
motherboard zone, which reports a case temperature rather than the CPU's.

## 2. Install

```bash
cd ~/home-dashboard

# backend
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt

# frontend
cd frontend && npm install && cd ..
```

## 3. The Finnhub API key

1. Register at <https://finnhub.io/register> — the free tier is enough
   (60 calls/minute; the dashboard uses 10 per minute).
2. Copy your key from the dashboard at <https://finnhub.io/dashboard>.
3. Put it in `backend/.env`:

```bash
cp backend/.env.example backend/.env
$EDITOR backend/.env      # set FINNHUB_API_KEY=...
chmod 600 backend/.env
```

`backend/.env` is listed in `.gitignore` and is the only place the key lives —
it is never committed and never sent to the frontend. Upstream errors are
scrubbed before they leave the backend, so a failing Finnhub request cannot leak
the key into the browser through its own error text.

> The free tier does **not** include `/stock/candle`, so the sparklines are built
> from the prices the backend observes while it runs (cached in
> `backend/.cache/price_history.json`). They start as a flat dash and fill in
> over the first hour.

## 4. ActivityWatch

Download the Linux build from <https://activitywatch.net/downloads/> and unzip
it into your home directory:

```bash
unzip ~/Downloads/activitywatch-v0.13.2-linux-x86_64.zip -d ~/
```

That gives `~/activitywatch/` with `aw-server`, `aw-watcher-window` and
`aw-watcher-afk`. The units in `systemd/` run those three directly (rather than
the `aw-qt` tray app), which is what you want for an always-on machine.

The window watcher needs X11 and `xprop` (`apt install x11-utils`), and reads
`DISPLAY=:0` — adjust that in `systemd/aw-watcher-window.service` if your
session uses a different display.

Data lives in `~/.local/share/activitywatch/`. Nothing leaves the machine.

## 4b. GitHub (optional token)

The GitHub card reads public data only and works with no configuration —
unauthenticated requests are limited to 60/hour per IP, and the 5-minute cache
uses about 24 of them. Add a token only if you share the IP or want headroom:

```bash
# backend/.env
GITHUB_USER=milo475          # whose activity to show
GITHUB_TOKEN=ghp_...         # optional; a classic token with NO scopes is enough
```

Two quirks worth knowing:

- The public events feed reaches back roughly 90 days / 300 events, so an empty
  activity list is not the same as an inactive account.
- GitHub sometimes returns push events with no commit count in them. When that
  happens the backend recovers the real number with one `compare` request per
  branch touched today; if even that is unavailable it shows **pushes today**
  instead of **commits today** rather than quietly mislabelling the number.

## 4c. Productivity rules

`backend/productivity_rules.json` decides what counts as productive:

```json
{
  "productive": ["code", "vs code", "terminal", "gnome-terminal", "claude"],
  "neutral": ["files", "settings"],
  "leisure": ["youtube", "netflix", "steam"]
}
```

Keywords are matched case-insensitively as substrings against both the
application name and the window title. The **longest** matching keyword wins, so
a specific rule beats a generic one (`"vs code"` over `"code"`) whichever
category each sits in. Anything unmatched counts as neutral.

Browsers are special-cased on the window title, because a browser is whatever
tab is in front. Override the defaults by adding an optional block:

```json
{
  "productive": ["code"],
  "neutral": [],
  "leisure": [],
  "browser_titles": {
    "productive": ["github", "stackoverflow", "localhost", "docs"],
    "leisure": ["youtube", "netflix", "twitch"]
  }
}
```

The file is re-read whenever its mtime changes — edit it and the next refresh
picks it up, no restart needed. A missing or malformed file falls back to the
built-in defaults and the card's subtitle says `default rules`.

The score is `productive / (productive + leisure)`. Neutral time is deliberately
excluded: it is neither a win nor a loss, and including it would just drag every
score toward the middle.

## 5. Run it

```bash
./start.sh
```

This brings up ActivityWatch, the backend and the frontend (skipping anything
already running), then opens Chromium fullscreen in app mode.

### Which monitor

By default the window is pinned to **HDMI-1**. Override it per run:

```bash
DASHBOARD_MONITOR=eDP-1 ./start.sh
```

`start.sh` reads the output's geometry from `xrandr` and passes it to Chromium.
If the named output is not attached it falls back to the primary output (then to
the first connected one) and says so. Chromium remembers its last window
placement inside `~/.config/home-dashboard-chromium`, so if it ever reopens on
the wrong screen the script nudges it back with `xdotool`.

Above 2400px wide the UI scales up (`zoom: 1.45`) so it stays readable on an
ultrawide instead of leaving small text stranded.

## 6. Run on login (systemd)

```bash
cp systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now \
  activitywatch.service aw-watcher-window.service aw-watcher-afk.service \
  dashboard-backend.service dashboard-frontend.service
```

To keep the services running when you are not logged in graphically:

```bash
loginctl enable-linger "$USER"
```

Useful commands:

```bash
systemctl --user status dashboard-backend.service
journalctl --user -u dashboard-backend.service -f
systemctl --user restart dashboard-frontend.service
```

### Opening the window on login

The systemd units above start the *services*; they do not open the window. That
is a desktop-session job, so it ships as an autostart entry:

```bash
mkdir -p ~/.config/autostart
cp autostart/home-dashboard.desktop ~/.config/autostart/
```

It appears in **Settings → Session and Startup → Application Autostart** as
"Home Dashboard", where you can untick it without deleting anything.

The entry sleeps 8 seconds before running `start.sh`, so the XFCE panel and the
monitor layout are up and `xrandr` reports the real geometry before the window
is placed. `Exec` holds an absolute path - edit it if you move the project.

Running `start.sh` when a dashboard window is already open just focuses the
existing one, so autostart plus a manual run will not leave you with two.

## 7. API

| Endpoint | Cache | Returns |
|---|---|---|
| `GET /api/health` | — | backend status, whether the Finnhub key is set |
| `GET /api/usage` | 30s | per-app totals for today and each of the last 7 days |
| `GET /api/stocks` | 60s | price, change %, previous close, sparkline |
| `GET /api/ai-news` | 1h | top 10 AI items with title, source, URL |
| `GET /api/system` | 2s | CPU %, RAM, disk, net rates, temperature, uptime, load, 10-minute history |
| `GET /api/productivity` | 60s | productive/neutral/leisure minutes and score, today and per day for 7 days |
| `GET /api/github` | 5m | last 5 events, 5 most recently pushed repos, today's commit count |
| `GET /api/goals` | — | today's goals and Pomodoro count |
| `POST /api/goals` | — | replaces today's list (`{"goals":[{id,text,done}]}`, max 5) |
| `POST /api/pomodoro` | — | `{"delta":1}` to add one, `{"reset":true}` to zero today |
| `POST /api/launch/claude` | — | starts Claude Desktop |

Polling intervals: system 5s, usage / productivity / markets 60s, GitHub 5m,
AI feed 1h. The system endpoint is local and cheap, which is why it can be read
that much faster than the ones that cost somebody else's rate limit.

Goals and Pomodoro counts live in `backend/data/goals.json`, keyed by date, so
the card resets every morning without losing history. That file is gitignored —
it is personal, not configuration.

Every GET replies `200` with an `{"available": true|false}` envelope. When an
upstream is down the endpoint returns `available: false` with an `error` and a
`hint`, and the matching card shows a "no data" state — the dashboard never
crashes because ActivityWatch or the internet went away. If a refresh fails but
an earlier result is cached, the cached value is served with `"stale": true`.

The Claude button tries `claude-desktop` first, then
`flatpak run com.anthropic.ClaudeDesktop`, and reports a JSON error if neither
is installed.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Usage card: "ActivityWatch is not reachable" | `systemctl --user start activitywatch.service`; check `curl localhost:5600/api/0/info` |
| Usage card: "No activity recorded yet" | The watchers only just started — events appear within a minute |
| Subtitle says "AFK filter off" | The AFK watcher has no events yet, so idle time is not being subtracted. It corrects itself once `aw-watcher-afk` records its first event |
| Markets: "FINNHUB_API_KEY is not set" | Add the key to `backend/.env` and restart the backend |
| Markets: rate limit | Free tier is 60 calls/min; the 60s cache keeps usage at 10 |
| Markets: rows say "no quote" | Usually a Finnhub outage. `curl -o /dev/null -w '%{http_code}' https://finnhub.io/` — a 503 there is upstream, not you |
| System card: temperature reads "n/a" | No usable sensor. `sudo apt install lm-sensors && sudo sensors-detect --auto`, then check `sensors` |
| System card: "psutil is not installed" | `backend/venv/bin/pip install -r backend/requirements.txt`, then restart the backend |
| Focus card: goals will not save | `backend/data/` must be writable by the backend user |
| GitHub card: "rate limit reached" | Unauthenticated is 60/hour per IP — set `GITHUB_TOKEN` in `backend/.env` |
| GitHub card says "pushes today" | GitHub returned events with no commit counts and the fallback could not run; the number shown is pushes, not commits |
| Productivity: everything is neutral | Your apps do not match any keyword — edit `backend/productivity_rules.json` (no restart needed) |
| Frontend won't start | Port in use — `ss -ltnp \| grep 3300`, or set `DASHBOARD_PORT` |

## 9. Layout

```
+---------------------------------------------------------------------------+
|  20:04  MONDAY, AUGUST 31, 2026                                [ CLAUDE ] |
+------------------------+---------------------+--------------------------+
|  APP USAGE   [ch|tbl]  |  SYSTEM             |  MARKETS                 |
|   - time by app, 7d    |   temp / uptime /   |   AAPL Apple 319.70 +1.6%|
|   - daily breakdown    |   load, 3 meters,   |   ...                    |
|                        |   cpu + net trends  +--------------------------+
|                        +---------------------+  GITHUB                  |
+------------------------+  FOCUS              |   9 commits today        |
|  PRODUCTIVITY          |   25:00             |   repos + activity       |
|   92%  ▮▮▮▮▮▯▯         |   goals checklist   +--------------------------+
|   top contributors     |   add a goal…       |  AI FEED                 |
+------------------------+---------------------+--------------------------+
        35%                       31%                     34%
```

Eight cards on a 3-column, 12-row grid. Each card spans rows rather than
claiming pixels, so the whole board scales with the viewport and never needs a
page scrollbar at 1920x1080. The charts sit left because they are the reason the
dashboard exists; the two cards meant to be read from across the room (System,
Focus) run down the middle; the three feeds that scroll are on the right.

Below 1200px wide the grid folds to two columns and the page is allowed to
scroll — three columns of this density stop being readable before that.

Chart colors are not arbitrary: the eight series slots were generated for the
`#0a0e14` surface and checked with a palette validator (lightness band, chroma
floor, colour-blind separation, contrast). The neon `#00ffcc` / `#a78bfa`
accents are reserved for chrome — they are too light to be readable as fills.
Each app keeps its colour across refreshes (stored in `localStorage`), so
"VS Code is purple" stays true even as the ranking changes. See the comment at
the top of `frontend/src/theme.js` before changing a slot.
