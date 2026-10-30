#!/bin/bash
# Installs what Video Downloader needs into its own Python environment in
#   ~/Library/Application Support/Video Downloader/venv
# so nothing is added to the rest of the Mac and the app itself stays read-only.
#
#   setup.sh          install or update (prints progress)
#   setup.sh --check  exit 0 if ready, 1 if setup is needed, 2 if Python is missing
#   setup.sh --python print the environment's python path
#
# Works on Intel and Apple Silicon Macs. No Homebrew needed.

HERE="$(cd "$(dirname "$0")" && pwd)"
SUPPORT="$HOME/Library/Application Support/Video Downloader"
VENV="$SUPPORT/venv"
STAMP="$VENV/.requirements-installed"
export PATH="/Library/Frameworks/Python.framework/Versions/Current/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

if [ "$1" = "--python" ]; then echo "$VENV/bin/python"; exit 0; fi

find_python() {
  for candidate in python3.15 python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      echo "$candidate"; return 0
    fi
  done
  return 1
}

venv_ok() { [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import sys' 2>/dev/null; }
ready() { venv_ok && cmp -s "$HERE/requirements.txt" "$STAMP"; }

if [ "$1" = "--check" ]; then
  ready && exit 0
  venv_ok || find_python >/dev/null || exit 2
  exit 1
fi

echo "== Video Downloader setup $(date) =="
mkdir -p "$SUPPORT"

if ! venv_ok; then
  PY="$(find_python)" || { echo "Python 3.11 or newer is needed: https://www.python.org/downloads/"; exit 2; }
  echo "Creating the app's Python environment with $PY…"
  rm -rf "$VENV"
  "$PY" -m venv "$VENV" || exit 3
fi

PIP=("$VENV/bin/python" -m pip install --disable-pip-version-check --quiet --upgrade --only-binary=:all:)
echo "Installing yt-dlp, ffmpeg, deno and the app window (a few minutes the first time)…"
"$VENV/bin/python" -m pip install --disable-pip-version-check --quiet --upgrade pip

# Ready-made packages only: never compile anything (that would need Apple's
# developer tools). If a brand-new Python lacks a ready-made build of an
# optional yt-dlp extra (brotli, websockets…), install everything else.
if ! "${PIP[@]}" -r "$HERE/requirements.txt"; then
  echo "Some optional extras aren't available for this Python yet; installing the essentials…"
  "${PIP[@]}" "yt-dlp[deno]" imageio-ffmpeg "flask>=3.0" pywebview || exit 3
  for pkg in $("$VENV/bin/python" -c '
import importlib.metadata as m
for r in m.requires("yt-dlp") or []:
    if "extra == \"default\"" in r and not r.startswith("brotlicffi"):
        print(r.split(";")[0].strip().replace(" ", ""))'); do
    "${PIP[@]}" "$pkg" 2>/dev/null || echo "  (skipped optional $pkg)"
  done
fi

cp "$HERE/requirements.txt" "$STAMP"
echo "Setup finished."
