"""Watches the Mac clipboard for copied video links, like the old RealPlayer
download prompt. Runs entirely on this Mac: the clipboard is read with the
built-in `pbpaste` command and nothing is sent anywhere except the lookup of
the video page itself (the same request your browser already made)."""
import shutil
import subprocess
import threading
import time
import uuid

from . import downloader
from .downloader import looks_like_url, site_for

POLL_SECONDS = 1.0
QUALITY_NAMES = {"best": "best quality"}

# argv: 1 message, 2 download-button label, 3 middle-button label
_ASK_SCRIPT = [
    "on run argv",
    'set dl to item 2 of argv',
    'set r to display dialog (item 1 of argv) with title "Video Downloader"'
    ' buttons {"Ignore", (item 3 of argv), dl} default button dl'
    ' cancel button "Ignore" giving up after 45 with icon note',
    'if gave up of r then return "Ignore"',
    "set b to button returned of r",
    'if b is dl then return "Download"',
    "return b",
    "end run",
]

_FAIL_SCRIPT = [
    "on run argv",
    'display dialog (item 1 of argv) with title "Video Downloader" buttons {"OK"}'
    ' default button "OK" giving up after 20 with icon caution',
    "end run",
]


def _quality_label(quality, option):
    if quality in QUALITY_NAMES:
        name = QUALITY_NAMES[quality]
        if quality == "best" and option and option.get("height"):
            name += f", {option['height']}p"
        return name
    return f"{option['height']}p" if option and option.get("height") else f"up to {quality}p"


def describe(info, quality):
    """Text for the prompt: title, length, size at the default quality, and the
    smallest alternative so a huge file is obvious before downloading."""
    option = downloader.option_for(info, quality)
    size = downloader.format_bytes(option["bytes"], option["exact"]) if option else "size unknown"
    lines = [info.get("title") or "Untitled video"]
    meta = [info.get("site"), info.get("uploader")]
    if info.get("duration"):
        mins, secs = divmod(int(info["duration"]), 60)
        meta.append(f"{mins // 60}:{mins % 60:02d}:{secs:02d}" if mins >= 60 else f"{mins}:{secs:02d}")
    lines.append(" · ".join(m for m in meta if m))
    lines.append("")
    lines.append(f"Size at {_quality_label(quality, option)}: {size}")
    # mention the smallest video option if it's much smaller
    videos = [o for o in info.get("options") or []
              if o.get("bytes") and not o.get("duplicate")]
    if option and option.get("bytes") and videos:
        small = min(videos, key=lambda o: o["bytes"])
        if small["bytes"] < option["bytes"] * 0.6:
            lines.append(f"Smallest: {small.get('height') or '?'}p, "
                         f"{downloader.format_bytes(small['bytes'], small['exact'])}")
    return "\n".join(lines), size


def describe_page(info):
    """Prompt for an unsupported page with several videos: offer the likely
    main one, mention the short clips (probably ads) being skipped."""
    videos = info.get("videos") or []
    main = next((v for v in videos if v.get("main")), None)
    extras = sum(1 for v in videos if v.get("short"))
    lines = [info.get("title") or "Videos on this page", f"{len(videos)} videos found on this page.", ""]
    if not main:
        return "\n".join(lines + ["Choose Quality… to pick one."]), "Open App", None
    facts = []
    if main.get("duration"):
        mins, secs = divmod(int(main["duration"]), 60)
        facts.append(f"{mins // 60}:{mins % 60:02d}:{secs:02d}" if mins >= 60 else f"{mins}:{secs:02d}")
    if main.get("height"):
        facts.append(f"{main['height']}p")
    size = downloader.format_bytes(main.get("bytes"), False)
    facts.append(size)
    lines.append("Main video: " + " · ".join(facts))
    if extras:
        lines.append(f"Skipping {extras} short clip{'s' if extras != 1 else ''} (probably ads or previews).")
    label = f"Download Main ({size})" if main.get("bytes") else "Download Main"
    return "\n".join(lines), label, main


class ClipboardWatcher:
    def __init__(self, store, manager, open_app, lookup=None):
        self.store = store
        self.manager = manager
        self.open_app = open_app       # callback that brings the app's browser tab forward
        self.lookup = lookup or (lambda url: downloader.fetch_info(url, self.store.settings))
        self.pending = []              # links waiting for an answer in the app tab
        self._seen = set()
        self._last = None
        self._lock = threading.Lock()
        self._dialog_lock = threading.Lock()
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

    def consider(self, text, background=True):
        """Decide whether a newly copied piece of text deserves a prompt; if so,
        look the video up (title and sizes) and then ask."""
        url = text.strip()
        if not looks_like_url(url) or url in self._seen:
            return None
        site = site_for(url)
        if not site and not self.store.settings.get("prompt_all_links"):
            return None
        self._seen.add(url)
        item = {"id": uuid.uuid4().hex[:10], "url": url, "site": site, "time": time.time(),
                "state": "looking", "info": None, "error": None}
        with self._lock:
            self.pending.insert(0, item)
            del self.pending[10:]
        if background:
            threading.Thread(target=self._look_up_and_ask, args=(item,), daemon=True).start()
        return item

    def _look_up_and_ask(self, item):
        try:
            item["info"] = self.lookup(item["url"])
            item["state"] = "ready"
        except Exception as err:  # noqa: BLE001
            item["state"] = "error"
            item["error"] = downloader.friendly_error(err)
        if item not in self.pending:
            return                     # dismissed while we were looking
        if self.store.settings.get("native_prompt"):
            self._ask_natively(item)

    # ------------------------------------------------------------------ answers
    def dismiss(self, item_id):
        with self._lock:
            self.pending = [p for p in self.pending if p["id"] != item_id]

    def _ask_natively(self, item):
        if not shutil.which("osascript"):
            return
        with self._dialog_lock:        # one dialog at a time
            if item not in self.pending:
                return
            if item["state"] == "error":
                self._osascript(_FAIL_SCRIPT, "Couldn't get a video from this link.\n\n"
                                f"{item['error']}\n\n{item['url']}")
                self.dismiss(item["id"])
                return
            info = item["info"] or {}
            main = None
            if info.get("kind") == "multi":
                message, label, main = describe_page(info)
            elif info.get("kind") == "playlist":
                message = f"{info.get('title')}\n{info.get('count')} videos (playlist)\n\nChoose Quality… to download them."
                label = "Open App"
            else:
                message, size = describe(info, self.store.settings.get("quality", "best"))
                label = f"Download ({size})" if size != "size unknown" else "Download"
            middle = "Choose Video…" if info.get("kind") == "multi" else "Choose Quality…"
            answer = self._osascript(_ASK_SCRIPT, message, label, middle)
        if answer is None or item not in self.pending:
            return                     # already handled from the app tab
        if answer == "Download" and main:
            self.dismiss(item["id"])
            self.manager.add(info.get("url") or item["url"], info.get("title"), item=main["item"])
        elif answer == "Download" and info.get("kind") not in ("playlist", "multi"):
            self.dismiss(item["id"])
            self.manager.add(info.get("url") or item["url"], info.get("title"))
        elif answer in ("Choose Quality…", "Choose Video…", "Download"):
            self.open_app()            # stays pending: the app tab shows sizes per quality
        else:
            self.dismiss(item["id"])

    @staticmethod
    def _osascript(script, *args):
        cmd = ["osascript"]
        for line in script:
            cmd += ["-e", line]
        try:
            out = subprocess.run(cmd + list(args), capture_output=True, timeout=90)
            return out.stdout.decode().strip()
        except (OSError, subprocess.SubprocessError):
            return None
