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
  # Ready-made packages only: never try to compile anything (that would need
  # Apple's developer tools). If a brand-new Python lacks a ready-made build of
  # an optional speed-up (brotli, websockets…), install everything else.
  if ! .venv/bin/python -m pip install --quiet --upgrade --only-binary=:all: -r requirements.txt; then
    echo "Some optional extras aren't available for this Python yet; installing the essentials…"
    .venv/bin/python -m pip install --quiet --upgrade --only-binary=:all: \
      "yt-dlp[deno]" imageio-ffmpeg "flask>=3.0" || pause_and_exit
    # the rest of yt-dlp's recommended extras, one at a time, skipping any that can't install
    for pkg in $(.venv/bin/python -c '
import re, importlib.metadata as m
for r in m.requires("yt-dlp") or []:
    if "extra == \"default\"" in r:
        spec = r.split(";")[0].strip().replace(" ", "")
        if not re.match(r"brotlicffi", spec): print(spec)'); do
      .venv/bin/python -m pip install --quiet --only-binary=:all: "$pkg" 2>/dev/null \
        || echo "  (skipped optional $pkg)"
    done
  fi
  cp requirements.txt "$STAMP"
fi

exec .venv/bin/python app.py
