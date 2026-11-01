"""Video Downloader: start the app.

Normally launched by double-clicking "Video Downloader.app", which opens the
app in its own window (no browser, no Terminal). Run with --browser to use a
browser tab instead (the old way, handy for troubleshooting).
"""
import json
import socket
import sys
import threading
import urllib.request

PORT = 8737
URL = f"http://127.0.0.1:{PORT}/"

if sys.version_info < (3, 11):
    sys.exit("Video Downloader needs Python 3.11 or newer. Get the macOS installer from https://www.python.org/downloads/")

try:
    from vdl import desktop
    from vdl.server import API_HEADER, create_app, open_in_browser
except ModuleNotFoundError as err:
    sys.exit(f"Missing package ({err.name}). Open Video Downloader.app (or start.command), which installs everything it needs.")


def call_running_app(path, method="GET"):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method,
                                     headers={API_HEADER: "1", "Content-Type": "application/json"},
                                     data=b"{}" if method == "POST" else None)
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def port_free():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) != 0


def main():
    use_window = "--browser" not in sys.argv and desktop.available()

    running = call_running_app("/api/state")
    if running and "jobs" in running:
        print("Video Downloader is already running; bringing it forward.")
        call_running_app("/api/show", "POST")
        return
    if not port_free():
        sys.exit(f"Port {PORT} is being used by another program. Change PORT in app.py and try again.")

    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app = create_app(port=PORT)

    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", PORT, app, threaded=True)
    print(f"Video Downloader is running at {URL}", flush=True)

    if use_window:
        shell = desktop.Desktop(URL, app.config["store"])
        app.config["show_window"] = shell.show
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            shell.run()                 # blocks until the app quits
            return
        except Exception:  # noqa: BLE001 - never just vanish: fall back to a browser tab
            logging.exception("The app window couldn't open; using a browser tab instead")
            app.config["show_window"] = None
            open_in_browser(PORT)
            threading.Event().wait()    # keep serving until Quit in the page

    print("Copy a video link in any browser, or paste it into the app. Press Ctrl+C to quit.", flush=True)
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, open_in_browser, args=(PORT,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
