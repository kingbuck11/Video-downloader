#!/bin/bash
# Troubleshooting launcher: does the same as "Video Downloader.app" but shows
# all setup and app messages in this Terminal window.
# For everyday use, open "Video Downloader.app" instead.

cd "$(dirname "$0")" || exit 1
pause_and_exit() { echo; read -r -p "Press Return to close this window." _; exit 1; }

./setup.sh --check
if [ $? -ne 0 ]; then
  ./setup.sh || pause_and_exit
fi

echo
echo "Starting Video Downloader (close its window or press Ctrl+C here to stop)…"
"$(./setup.sh --python)" app.py "$@" || pause_and_exit
