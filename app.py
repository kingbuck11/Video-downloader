"""Video Downloader: start the local app and open it in your browser.

Usually launched by double-clicking start.command. Press Ctrl+C in the
Terminal window (or use Quit in the app) to stop it.
"""
import json
import socket
import sys
import threading
import urllib.request

PORT = 8737

if sys.version_info < (3, 11):
    sys.exit("Video Downloader needs Python 3.11 or newer. Get the macOS installer from https://www.python.org/downloads/")

try:
    from vdl.server import API_HEADER, create_app, open_in_browser
except ModuleNotFoundError as err:
    sys.exit(f"Missing package ({err.name}). Run start.command, which installs everything it needs.")


def already_running():
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/state", headers={API_HEADER: "1"})
        with urllib.request.urlopen(req, timeout=1) as r:
            return "jobs" in json.load(r)
    except Exception:  # noqa: BLE001
        return False


def port_free():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) != 0


def main():
    if already_running():
        print("Video Downloader is already running; opening it.")
        open_in_browser(PORT)
        return
    if not port_free():
        sys.exit(f"Port {PORT} is being used by another program. Change PORT in app.py and try again.")

    import logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)   # keep the Terminal window quiet
    app = create_app(port=PORT)
    print(f"\n  Video Downloader is running at http://127.0.0.1:{PORT}")
    print("  Copy a video link in any browser, or paste it into the app.")
    print("  Leave this window open. Press Ctrl+C to quit.\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, open_in_browser, args=(PORT,)).start()
    app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
