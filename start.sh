#!/usr/bin/env bash
# Starts the dashboard (backend + frontend) and opens it as a frameless window.
#
# Safe to run repeatedly: anything already listening is left alone, so this
# works whether or not the systemd user services are enabled.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-5000}"
FRONTEND_PORT="${DASHBOARD_PORT:-3300}"
URL="http://localhost:${FRONTEND_PORT}"
LOGS="$DIR/logs"
mkdir -p "$LOGS"

listening() { ss -ltn 2>/dev/null | grep -q ":$1 "; }

wait_for() { # port, seconds
  for _ in $(seq "$2"); do
    listening "$1" && return 0
    sleep 1
  done
  return 1
}

# --- ActivityWatch (optional; the usage card degrades gracefully without it) ---
if ! listening 5600; then
  if systemctl --user list-unit-files activitywatch.service >/dev/null 2>&1; then
    systemctl --user start activitywatch.service aw-watcher-window.service aw-watcher-afk.service
  elif [ -x "$HOME/activitywatch/aw-server/aw-server" ]; then
    setsid nohup "$HOME/activitywatch/aw-server/aw-server" >"$LOGS/aw-server.log" 2>&1 </dev/null &
    setsid nohup "$HOME/activitywatch/aw-watcher-window/aw-watcher-window" >"$LOGS/aw-window.log" 2>&1 </dev/null &
    setsid nohup "$HOME/activitywatch/aw-watcher-afk/aw-watcher-afk" >"$LOGS/aw-afk.log" 2>&1 </dev/null &
  else
    echo "! ActivityWatch not found - the usage card will show 'no data'."
  fi
fi

# --- backend ---
if listening "$BACKEND_PORT"; then
  echo "= backend already on :$BACKEND_PORT"
elif systemctl --user list-unit-files dashboard-backend.service >/dev/null 2>&1; then
  systemctl --user start dashboard-backend.service
else
  setsid nohup "$DIR/backend/venv/bin/python" "$DIR/backend/app.py" \
    >"$LOGS/backend.log" 2>&1 </dev/null &
fi
wait_for "$BACKEND_PORT" 25 || { echo "! backend did not come up - see $LOGS/backend.log"; }

# --- frontend ---
if listening "$FRONTEND_PORT"; then
  echo "= frontend already on :$FRONTEND_PORT"
elif systemctl --user list-unit-files dashboard-frontend.service >/dev/null 2>&1; then
  systemctl --user start dashboard-frontend.service
else
  ( cd "$DIR/frontend" && setsid nohup npm run dev -- --port "$FRONTEND_PORT" --host 127.0.0.1 \
      >"$LOGS/frontend.log" 2>&1 </dev/null & )
fi
wait_for "$FRONTEND_PORT" 40 || { echo "! frontend did not come up - see $LOGS/frontend.log"; exit 1; }

# --- window ---
BROWSER="$(command -v chromium || command -v chromium-browser || command -v google-chrome)"
if [ -z "$BROWSER" ]; then
  echo "! no chromium/chrome found - open $URL manually"
  exit 1
fi

# Which monitor to pin the dashboard to. Override with DASHBOARD_MONITOR=eDP-1.
MONITOR="${DASHBOARD_MONITOR:-HDMI-1}"

# "W H X Y" for a connected output, empty if it is not attached.
monitor_geometry() {
  xrandr --query 2>/dev/null | awk -v out="$1" '
    $1 == out && $2 == "connected" {
      for (i = 3; i <= NF; i++)
        if ($i ~ /^[0-9]+x[0-9]+\+[-0-9]+\+[-0-9]+$/) {
          split($i, a, /[x+]/); print a[1], a[2], a[3], a[4]; exit
        }
    }'
}

GEO="$(monitor_geometry "$MONITOR")"
if [ -z "$GEO" ]; then
  # Fall back to the primary output, then to whatever is connected first.
  FALLBACK="$(xrandr --query 2>/dev/null | awk '/ connected primary/ {print $1; exit}')"
  [ -z "$FALLBACK" ] && FALLBACK="$(xrandr --query 2>/dev/null | awk '/ connected/ {print $1; exit}')"
  if [ -n "$FALLBACK" ]; then
    echo "= $MONITOR not attached - using $FALLBACK"
    MONITOR="$FALLBACK"
    GEO="$(monitor_geometry "$MONITOR")"
  fi
fi

# Already open? Just focus it - re-running must not stack up windows (autostart
# and a manual run on the same login would otherwise give you two dashboards).
if command -v xdotool >/dev/null; then
  EXISTING="$(xdotool search --name 'HOME // DASHBOARD' 2>/dev/null | tail -1)"
  if [ -n "$EXISTING" ]; then
    echo "= dashboard window already open - focusing it"
    xdotool windowactivate "$EXISTING" 2>/dev/null || true
    exit 0
  fi
fi

CHROME_ARGS=(
  --app="$URL"
  --start-fullscreen
  --user-data-dir="$HOME/.config/home-dashboard-chromium"
  --no-first-run
  --disable-features=TranslateUI
)

if [ -n "$GEO" ]; then
  read -r MW MH MX MY <<<"$GEO"
  echo "= opening on $MONITOR (${MW}x${MH} at +${MX}+${MY})"
  CHROME_ARGS+=( --window-position="${MX},${MY}" --window-size="${MW},${MH}" )
fi

"$BROWSER" "${CHROME_ARGS[@]}" >/dev/null 2>&1 &
BROWSER_PID=$!

# Chromium remembers its last placement in the profile and will happily reopen
# on the wrong monitor, so nudge the window onto the target output once it maps.
if [ -n "$GEO" ] && command -v xdotool >/dev/null; then
  for _ in $(seq 20); do
    WID="$(xdotool search --name 'HOME // DASHBOARD' 2>/dev/null | tail -1)"
    [ -n "$WID" ] && break
    sleep 1
  done
  if [ -n "${WID:-}" ]; then
    eval "$(xdotool getwindowgeometry --shell "$WID" 2>/dev/null)"
    # Is the window's centre already inside the target monitor?
    CX=$(( ${X:-0} + ${WIDTH:-0} / 2 ))
    CY=$(( ${Y:-0} + ${HEIGHT:-0} / 2 ))
    if [ "$CX" -lt "$MX" ] || [ "$CX" -ge "$((MX + MW))" ] ||
       [ "$CY" -lt "$MY" ] || [ "$CY" -ge "$((MY + MH))" ]; then
      echo "= window opened on the wrong output - moving it to $MONITOR"
      xdotool windowmove "$WID" "$MX" "$MY"
      xdotool windowsize "$WID" "$MW" "$MH"
    fi
    xdotool windowactivate "$WID" 2>/dev/null || true
  fi
fi

wait "$BROWSER_PID"
