"""Local web server for the app. Listens on 127.0.0.1 only, so nothing outside
this Mac can reach it, and rejects requests from other websites."""
import os
import platform
import subprocess
import sys
import threading

from flask import Flask, abort, jsonify, request, send_from_directory

from . import downloader
from .clipboard import ClipboardWatcher
from .settings import Store

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
API_HEADER = "X-Video-Downloader"


def create_app(store=None, port=8737, start_watcher=True):
    app = Flask(__name__, static_folder=None)
    store = store or Store()
    manager = downloader.DownloadManager(store)
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    def open_app():
        open_in_browser(port)

    watcher = ClipboardWatcher(store, manager, open_app)
    if start_watcher:
        watcher.start()
    app.config.update(store=store, manager=manager, watcher=watcher)
    update_state = {"running": False, "output": "", "ok": None}

    @app.before_request
    def guard():
        # Blocks DNS-rebinding tricks and other web pages poking this server:
        # the custom header can't be sent cross-site without a CORS preflight,
        # which this server never approves.
        if request.host not in allowed_hosts:
            abort(403)
        if request.path.startswith("/api/") and request.headers.get(API_HEADER) != "1":
            abort(403)

    # ------------------------------------------------------------------ pages
    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    # ------------------------------------------------------------------ status
    @app.get("/api/state")
    def state():
        return jsonify(
            jobs=manager.list(),
            pending=watcher.pending,
            ffmpeg=bool(downloader.ffmpeg_path()),
            deno=bool(downloader.deno_path()),
            clipboard_available=watcher.available,
            ytdlp_version=downloader.ytdlp_version(),
            update=update_state,
        )

    @app.get("/api/settings")
    def get_settings():
        return jsonify(store.settings)

    @app.post("/api/settings")
    def set_settings():
        return jsonify(store.update_settings(request.get_json(force=True) or {}))

    # ------------------------------------------------------------------ videos
    @app.post("/api/info")
    def info():
        url = (request.get_json(force=True) or {}).get("url", "").strip()
        if not downloader.looks_like_url(url):
            return jsonify(error="That doesn't look like a web link."), 400
        try:
            return jsonify(downloader.fetch_info(url, store.settings))
        except Exception as err:  # noqa: BLE001
            return jsonify(error=downloader.friendly_error(err)), 422

    @app.post("/api/download")
    def download():
        body = request.get_json(force=True) or {}
        url = body.get("url", "").strip()
        if not downloader.looks_like_url(url):
            return jsonify(error="That doesn't look like a web link."), 400
        quality = body.get("quality")
        if quality not in (None, "best", "2160", "1440", "1080", "720", "480"):
            quality = None
        if body.get("pending_id"):
            watcher.dismiss(body["pending_id"])
        job = manager.add(url, body.get("title"), quality, bool(body.get("playlist")))
        return jsonify(job.to_dict())

    @app.post("/api/jobs/<job_id>/cancel")
    def cancel(job_id):
        return jsonify(ok=manager.cancel(job_id))

    @app.post("/api/jobs/<job_id>/retry")
    def retry(job_id):
        job = manager.retry(job_id)
        return jsonify(job.to_dict() if job else {"error": "Can't retry that one."})

    @app.post("/api/jobs/clear")
    def clear_jobs():
        manager.clear_finished()
        return jsonify(ok=True)

    @app.post("/api/pending/<item_id>/dismiss")
    def dismiss(item_id):
        watcher.dismiss(item_id)
        return jsonify(ok=True)

    # ------------------------------------------------------------------ history
    @app.get("/api/history")
    def history():
        items = [dict(h, exists=bool(h.get("path")) and os.path.exists(h["path"])) for h in store.history]
        return jsonify(items)

    @app.post("/api/history/clear")
    def clear_history():
        store.clear_history()
        return jsonify(ok=True)

    # ------------------------------------------------------------------ Finder
    @app.post("/api/reveal")
    def reveal():
        path = (request.get_json(force=True) or {}).get("path")
        target = store.settings["save_dir"] if path is None else path
        if path is not None and path not in manager.known_paths():
            return jsonify(error="Unknown file."), 400
        if not os.path.exists(target):
            if path is None:
                os.makedirs(target, exist_ok=True)
            else:
                return jsonify(error="That file has been moved or deleted."), 404
        reveal_in_finder(target, select=path is not None)
        return jsonify(ok=True)

    @app.post("/api/choose-folder")
    def choose_folder():
        folder = choose_folder_dialog(store.settings["save_dir"])
        if folder:
            store.update_settings({"save_dir": folder})
        return jsonify(store.settings)

    # ------------------------------------------------------------------ maintenance
    @app.post("/api/update-ytdlp")
    def update_ytdlp():
        if update_state["running"]:
            return jsonify(update_state)

        def run():
            update_state.update(running=True, output="", ok=None)
            try:
                out = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                    capture_output=True, text=True, timeout=300)
                update_state["ok"] = out.returncode == 0
                update_state["output"] = (out.stdout + out.stderr)[-1500:]
            except Exception as err:  # noqa: BLE001
                update_state.update(ok=False, output=str(err))
            finally:
                update_state["running"] = False

        threading.Thread(target=run, daemon=True).start()
        return jsonify(update_state | {"running": True})

    @app.post("/api/quit")
    def quit_app():
        threading.Timer(0.3, lambda: os._exit(0)).start()
        return jsonify(ok=True)

    return app


# ---------------------------------------------------------------------- Mac glue

def is_mac():
    return platform.system() == "Darwin"


def open_in_browser(port):
    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{port}/")


def reveal_in_finder(path, select=True):
    if is_mac():
        subprocess.Popen(["open", "-R", path] if select else ["open", path])


def choose_folder_dialog(current):
    if not is_mac():
        return None
    script = [
        "on run argv",
        "set f to choose folder with prompt \"Save downloaded videos to:\" default location (POSIX file (item 1 of argv))",
        "return POSIX path of f",
        "end run",
    ]
    args = ["osascript"]
    for line in script:
        args += ["-e", line]
    start = current if os.path.isdir(current) else os.path.expanduser("~")
    out = subprocess.run(args + [start], capture_output=True, text=True)
    path = out.stdout.strip()
    return path.rstrip("/") or None
