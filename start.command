#!/bin/bash
# Double-click this file in Finder to start Video Downloader.
# The first run sets things up (about a minute); later runs start right away.

cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

pause_and_exit() { echo; read -r -p "Press Return to close this window." _; exit 1; }

# --- Python 3.10+ -----------------------------------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Video Downloader needs Python 3.10 or newer."
  echo "Install Homebrew (https://brew.sh), then run:  brew install python ffmpeg"
  pause_and_exit
fi

# --- private Python environment for this app ---------------------------------
if [ ! -x .venv/bin/python ]; then
  echo "First-time setup: creating the app's Python environment…"
  "$PY" -m venv .venv || pause_and_exit
fi
STAMP=".venv/.requirements-installed"
if [ ! -f "$STAMP" ] || ! cmp -s requirements.txt "$STAMP"; then
  echo "Installing yt-dlp and Flask…"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet --upgrade -r requirements.txt || pause_and_exit
  cp requirements.txt "$STAMP"
fi

# --- helper tools from Homebrew -----------------------------------------------
#   ffmpeg: combines HD video with its audio track
#   deno:   lets yt-dlp read YouTube's player code (YouTube fails without it)
MISSING=()
command -v ffmpeg >/dev/null 2>&1 || MISSING+=(ffmpeg)
command -v deno   >/dev/null 2>&1 || MISSING+=(deno)
if [ ${#MISSING[@]} -gt 0 ]; then
  echo
  echo "Missing helper tools: ${MISSING[*]}"
  echo "  ffmpeg is needed for HD video with sound; deno is needed for YouTube."
  if command -v brew >/dev/null 2>&1; then
    read -r -p "Install them now with Homebrew? [Y/n] " answer
    if [ -z "$answer" ] || [[ "$answer" =~ ^[Yy] ]]; then brew install "${MISSING[@]}"; fi
  else
    echo "Install Homebrew (https://brew.sh), then run:  brew install ${MISSING[*]}"
  fi
fi

exec .venv/bin/python app.py
