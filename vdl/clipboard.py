"""Watches the Mac clipboard for copied video links, like the old RealPlayer
download prompt. Runs entirely on this Mac: the clipboard is read with the
built-in `pbpaste` command and nothing is sent anywhere."""
import shutil
import subprocess
import threading
import time
import uuid

from .downloader import looks_like_url, site_for

POLL_SECONDS = 1.0

_DIALOG_SCRIPT = [
    "on run argv",
    'set theButtons to {"Ignore", "Open App", "Download"}',
    'set r to display dialog ("Download the video from this link?" & return & return & item 1 of argv)'
    ' with title "Video Downloader" buttons theButtons default button "Download"'
    ' cancel button "Ignore" giving up after 30 with icon note',
    "if gave up of r then return \"Ignore\"",
    "return button returned of r",
    "end run",
]


class ClipboardWatcher:
    def __init__(self, store, manager, open_app):
        self.store = store
        self.manager = manager
        self.open_app = open_app       # callback that brings the app's browser tab forward
        self.pending = []              # links waiting for an answer in the app tab
        self._seen = set()
        self._last = None
        self._lock = threading.Lock()
        self._dialog_open = False
        self.available = shutil.which("pbpaste") is not None

    def start(self):
        if self.available:
            threading.Thread(target=self._loop, daemon=True).start()

    # ------------------------------------------------------------------ polling
    def _read(self):
        try:
            out = subprocess.run(["pbpaste"], capture_output=True, timeout=2)
            return out.stdout.decode("utf-8", "replace").strip()
        except (OSError, subprocess.SubprocessError):
            return None

    def _loop(self):
        self._last = self._read()      # ignore whatever was already copied at launch
        while True:
            time.sleep(POLL_SECONDS)
            if not self.store.settings.get("watch_clipboard"):
                continue
            text = self._read()
            if not text or text == self._last:
                continue
            self._last = text
            self.consider(text)

    def consider(self, text):
        """Decide whether a newly copied piece of text deserves a prompt."""
        url = text.strip()
        if not looks_like_url(url) or url in self._seen:
            return None
        site = site_for(url)
        if not site and not self.store.settings.get("prompt_all_links"):
            return None
        self._seen.add(url)
        item = {"id": uuid.uuid4().hex[:10], "url": url, "site": site, "time": time.time()}
        with self._lock:
            self.pending.insert(0, item)
            del self.pending[10:]
        if self.store.settings.get("native_prompt") and not self._dialog_open:
            threading.Thread(target=self._ask_natively, args=(item,), daemon=True).start()
        return item

    # ------------------------------------------------------------------ answers
    def dismiss(self, item_id):
        with self._lock:
            self.pending = [p for p in self.pending if p["id"] != item_id]

    def _ask_natively(self, item):
        if not shutil.which("osascript"):
            return
        self._dialog_open = True
        try:
            args = ["osascript"]
            for line in _DIALOG_SCRIPT:
                args += ["-e", line]
            args.append(item["url"])
            out = subprocess.run(args, capture_output=True, timeout=60)
            answer = out.stdout.decode().strip()
        except (OSError, subprocess.SubprocessError):
            return
        finally:
            self._dialog_open = False
        if item not in self.pending:
            return                     # already handled from the app tab
        if answer == "Download":
            self.dismiss(item["id"])
            self.manager.add(item["url"])
        elif answer == "Open App":
            self.open_app()            # leave it pending so the tab shows the full preview
        else:
            self.dismiss(item["id"])
