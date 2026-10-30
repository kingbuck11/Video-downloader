#!/bin/bash
# Double-click this file in Finder to start Video Downloader.
# The first run sets things up (a few minutes); later runs start right away.
# Works on Intel and Apple Silicon Macs. No Homebrew needed.

cd "$(dirname "$0")" || exit 1
export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

pause_and_exit() { echo; read -r -p "Press Return to close this window." _; exit 1; }

# --- Python 3.11+ -----------------------------------------------------------
PY=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Video Downloader needs Python 3.11 or newer."
  echo
  echo "  1. Go to https://www.python.org/downloads/ and download the macOS installer."
  echo "  2. Open it and click through the steps."
  echo "  3. Double-click start.command again."
  open "https://www.python.org/downloads/" 2>/dev/null
  pause_and_exit
fi

# --- private Python environment for this app ---------------------------------
# yt-dlp, ffmpeg (imageio-ffmpeg) and deno all install here with pip,
# so nothing is added to the rest of the Mac.
if [ ! -x .venv/bin/python ]; then
  echo "First-time setup: creating the app's Python environment…"
  "$PY" -m venv .venv || pause_and_exit
fi
STAMP=".venv/.requirements-installed"
if [ ! -f "$STAMP" ] || ! cmp -s requirements.txt "$STAMP"; then
  echo "Installing yt-dlp, ffmpeg, deno and Flask (this takes a few minutes the first time)…"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet --upgrade -r requirements.txt || pause_and_exit
  cp requirements.txt "$STAMP"
fi

exec .venv/bin/python app.py
