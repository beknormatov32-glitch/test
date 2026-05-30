#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"

if ! pgrep -f "Xvfb ${DISPLAY}" >/dev/null 2>&1; then
  Xvfb "${DISPLAY}" -screen 0 1280x900x24 &
fi

if ! pgrep -f "fluxbox" >/dev/null 2>&1; then
  fluxbox &
fi

if ! pgrep -f "x11vnc.*${DISPLAY}" >/dev/null 2>&1; then
  x11vnc -display "${DISPLAY}" -forever -shared -nopw -rfbport 5900 &
fi

if ! pgrep -f "websockify.*6080" >/dev/null 2>&1; then
  websockify --web=/usr/share/novnc/ 6080 localhost:5900 &
fi

echo "VNC ready: http://SERVER_IP:6080/vnc.html"
