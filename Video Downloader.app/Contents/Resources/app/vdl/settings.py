"""Settings and download history, stored as JSON files on this Mac only."""
import json
import os
import platform
import threading
from datetime import datetime

APP_NAME = "Video Downloader"


def data_dir():
    """Where settings.json and history.json live."""
    override = os.environ.get("VDL_DATA_DIR")
    if override:
        path = override
    elif platform.system() == "Darwin":
        path = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    else:
        path = os.path.expanduser("~/.video-downloader")
    os.makedirs(path, exist_ok=True)
    return path


DEFAULTS = {
    "save_dir": os.path.expanduser("~/Downloads/Videos"),
    "quality": "best",            # best | 2160 | 1440 | 1080 | 720 | 480
    "mac_compatible": True,       # prefer H.264/AAC so files play in QuickTime and Finder previews
    "filename": "title",          # title | title_id | site_title
    "watch_clipboard": True,      # notice video links copied in any browser
    "native_prompt": True,        # pop up a macOS dialog, not just a banner in the app tab
    "prompt_all_links": False,    # prompt for any link, not only sites yt-dlp has a dedicated extractor for
    "keep_history": True,
    "max_parallel": 2,
}

VALID = {
    "quality": {"best", "2160", "1440", "1080", "720", "480"},
    "filename": {"title", "title_id", "site_title"},
}

HISTORY_LIMIT = 500


class Store:
    def __init__(self, directory=None):
        self.dir = directory or data_dir()
        os.makedirs(self.dir, exist_ok=True)
        self.settings_path = os.path.join(self.dir, "settings.json")
        self.history_path = os.path.join(self.dir, "history.json")
        self._lock = threading.Lock()
        self.settings = dict(DEFAULTS)
        self.settings.update(self._load(self.settings_path, {}))
        for key, allowed in VALID.items():     # e.g. a choice that's since been removed
            if self.settings.get(key) not in allowed:
                self.settings[key] = DEFAULTS[key]
        self.history = self._load(self.history_path, [])

    @staticmethod
    def _load(path, fallback):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, type(fallback)) else fallback
        except (OSError, ValueError):
            return fallback

    def _save(self, path, data):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)

    def update_settings(self, changes):
        """Apply only known keys with sane values; returns the full settings."""
        with self._lock:
            for key, value in changes.items():
                if key not in DEFAULTS:
                    continue
                default = DEFAULTS[key]
                if isinstance(default, bool):
                    value = bool(value)
                elif key == "max_parallel":
                    try:
                        value = max(1, min(4, int(value)))
                    except (TypeError, ValueError):
                        continue
                elif key == "save_dir":
                    value = os.path.expanduser(str(value).strip())
                    if not value:
                        continue
                elif key in VALID and value not in VALID[key]:
                    continue
                self.settings[key] = value
            if not self.settings["keep_history"]:
                self.history = []
                self._save(self.history_path, self.history)
            self._save(self.settings_path, self.settings)
            return dict(self.settings)

    def add_history(self, entry):
        with self._lock:
            if not self.settings["keep_history"]:
                return
            entry = dict(entry, date=datetime.now().isoformat(timespec="seconds"))
            self.history.insert(0, entry)
            del self.history[HISTORY_LIMIT:]
            self._save(self.history_path, self.history)

    def clear_history(self):
        with self._lock:
            self.history = []
            self._save(self.history_path, self.history)
