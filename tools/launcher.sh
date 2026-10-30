#!/bin/bash
# The program inside "Video Downloader.app" (Contents/MacOS/Video Downloader).
# Sets things up on first launch, with a message instead of a Terminal window,
# then starts the app in its own window. Output goes to
#   ~/Library/Logs/Video Downloader.log

RES="$(cd "$(dirname "$0")/../Resources/app" && pwd)"
LOG="$HOME/Library/Logs/Video Downloader.log"
mkdir -p "$HOME/Library/Logs"
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 2000000 ]; then
  mv -f "$LOG" "$LOG.old"
fi
echo "=== launched $(date) ===" >> "$LOG"

ask() {  # ask "message" "button1" "button2" -> prints the clicked button
  osascript - "$@" <<'OSA' 2>/dev/null
on run argv
  set r to display dialog (item 1 of argv) with title "Video Downloader" buttons {item 2 of argv, item 3 of argv} default button (item 3 of argv) with icon caution
  return button returned of r
end run
OSA
}

"$RES/setup.sh" --check
status=$?

if [ $status -eq 2 ]; then
  answer=$(ask "Video Downloader needs Python 3.11 or newer.

Download the macOS installer from python.org, install it, then open Video Downloader again." "Cancel" "Open python.org")
  [ "$answer" = "Open python.org" ] && open "https://www.python.org/downloads/"
  exit 1
fi

if [ $status -ne 0 ]; then
  # first launch (or an update that needs new packages): say so while installing
  osascript - <<'OSA' >/dev/null 2>&1 &
display dialog "Setting up Video Downloader…" & return & return & "The first launch installs what the app needs. This takes a few minutes, and the app opens by itself when it is done." with title "Video Downloader" buttons {"OK"} default button "OK" giving up after 1200 with icon note
OSA
  dialog=$!
  "$RES/setup.sh" >> "$LOG" 2>&1
  status=$?
  kill $dialog 2>/dev/null
  if [ $status -ne 0 ]; then
    answer=$(ask "Setup did not finish. Check your internet connection and try again.

Details are in the log file (Video Downloader.log)." "OK" "Show Log")
    [ "$answer" = "Show Log" ] && open -R "$LOG"
    exit 1
  fi
fi

cd "$RES" || exit 1
exec "$("$RES/setup.sh" --python)" app.py >> "$LOG" 2>&1
