"""Run with:  .venv/bin/python -m pytest -q"""
import functools
import http.server
import os
import shutil
import subprocess
import threading
import time

import pytest

from vdl import downloader
from vdl.clipboard import ClipboardWatcher
from vdl.server import API_HEADER, create_app
from vdl.settings import Store

H = {API_HEADER: "1", "Host": "127.0.0.1:8737"}


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "data"))
    s.update_settings({"save_dir": str(tmp_path / "videos"), "native_prompt": False})
    return s


@pytest.fixture
def client(store):
    app = create_app(store=store, port=8737, start_watcher=False)
    return app.test_client()


# ------------------------------------------------------------------ format logic

def test_best_with_ffmpeg_merges_to_mp4(store):
    o = downloader.build_options(store.settings, has_ffmpeg=True)
    assert o["format"].startswith("bv*+ba")
    assert o["merge_output_format"] == "mp4"
    assert o["format_sort"][0] == "vcodec:h264"
    assert o["noplaylist"] is True


def test_height_cap_and_no_ffmpeg_fallback(store):
    s = dict(store.settings, quality="720", mac_compatible=False)
    o = downloader.build_options(s, has_ffmpeg=False)
    assert "[height<=720]" in o["format"] and "+" not in o["format"]
    assert "format_sort" not in o


def test_playlist_goes_in_subfolder(store):
    o = downloader.build_options(store.settings, has_ffmpeg=True, allow_playlist=True)
    assert o["noplaylist"] is False and "playlist" in o["outtmpl"]


# ------------------------------------------------------------------ site detection

def test_site_detection():
    assert downloader.site_for("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert downloader.site_for("https://vimeo.com/76979871")
    assert downloader.site_for("https://example.com/some/article") is None
    assert downloader.site_for("not a url") is None


def test_clipboard_prompts_only_for_video_sites(store):
    w = ClipboardWatcher(store, manager=None, open_app=lambda: None)
    assert w.consider("https://example.com/recipe", background=False) is None
    item = w.consider("https://www.youtube.com/watch?v=dQw4w9WgXcQ", background=False)
    assert item and item["site"]
    assert w.consider("https://www.youtube.com/watch?v=dQw4w9WgXcQ", background=False) is None  # no repeat prompt
    assert w.consider("hello there", background=False) is None
    store.update_settings({"prompt_all_links": True})
    assert w.consider("https://example.com/recipe", background=False)


# ------------------------------------------------------------------ settings + history

def test_removed_choice_falls_back_to_default(tmp_path):
    import json
    d = tmp_path / "old"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"quality": "audio"}))
    assert Store(str(d)).settings["quality"] == "best"


def test_settings_validation(store):
    s = store.update_settings({"quality": "9999", "max_parallel": 50, "bogus": 1, "filename": "title_id"})
    assert s["quality"] == "best" and s["max_parallel"] == 4 and "bogus" not in s
    assert s["filename"] == "title_id"
    reloaded = Store(store.dir)
    assert reloaded.settings["filename"] == "title_id"


def test_turning_history_off_erases_it(store):
    store.add_history({"title": "x", "url": "https://a"})
    assert store.history
    store.update_settings({"keep_history": False})
    assert store.history == []
    store.add_history({"title": "y", "url": "https://b"})
    assert store.history == []


# ------------------------------------------------------------------ server safety

def test_api_requires_app_header_and_local_host(client):
    assert client.get("/api/state").status_code == 403
    assert client.get("/api/state", headers=H).status_code == 200
    assert client.get("/api/state", headers=dict(H, Host="evil.example:8737")).status_code == 403
    assert client.post("/api/download", json={"url": "https://x.com/v"}).status_code == 403


def test_reveal_only_known_files(client):
    r = client.post("/api/reveal", json={"path": "/etc/passwd"}, headers=H)
    assert r.status_code == 400


def test_bad_url_rejected(client):
    assert client.post("/api/info", json={"url": "ftp://nope"}, headers=H).status_code == 400
    assert client.post("/api/download", json={"url": "javascript:alert(1)"}, headers=H).status_code == 400


# ------------------------------------------------------------------ real download (local server)

@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg to make a sample video")
def test_end_to_end_download_from_local_server(tmp_path, client, store):
    site = tmp_path / "site"
    site.mkdir()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
                    "-f", "lavfi", "-i", "sine=duration=2", "-shortest", "-pix_fmt", "yuv420p",
                    str(site / "clip.mp4")], check=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/clip.mp4"
    try:
        info = client.post("/api/info", json={"url": url}, headers=H).get_json()
        assert info["kind"] == "video", info
        assert info["options"][0]["bytes"], info["options"]

        job = client.post("/api/download", json={"url": url}, headers=H).get_json()
        for _ in range(100):
            jobs = client.get("/api/state", headers=H).get_json()["jobs"]
            current = next(j for j in jobs if j["id"] == job["id"])
            if current["status"] in ("done", "error"):
                break
            time.sleep(0.1)
        assert current["status"] == "done", current
        assert os.path.exists(current["filepath"])
        assert current["total_bytes"] == os.path.getsize(current["filepath"])
        assert current["filepath"].startswith(store.settings["save_dir"])
        hist = client.get("/api/history", headers=H).get_json()
        assert hist[0]["exists"] and hist[0]["url"] == url
    finally:
        httpd.shutdown()


def test_cancel_queued_job(client, store):
    store.update_settings({"max_parallel": 1})
    mgr = client.application.config["manager"]
    job = mgr.add("http://127.0.0.1:9/never")
    mgr.cancel(job.id)
    time.sleep(0.3)
    assert mgr.jobs[job.id].status == "cancelled"


# ------------------------------------------------------------------ size estimates

def _fake_youtube_info():
    import copy
    import yt_dlp
    fmts = []
    for h, tbr, vc in [(2160, 16000, "vp9"), (1080, 4500, "vp9"), (1080, 3000, "avc1.640028"),
                       (720, 1500, "avc1.4d401f"), (480, 800, "avc1.4d401e")]:
        fmts.append(dict(format_id=f"v{h}{vc[:3]}", url=f"https://x/{h}{vc}",
                         ext="mp4" if vc.startswith("avc") else "webm", height=h, width=h * 16 // 9,
                         vcodec=vc, acodec="none", tbr=tbr, protocol="https"))
    fmts.append(dict(format_id="a1", url="https://x/a", ext="m4a", vcodec="none", acodec="mp4a.40.2",
                     abr=128, tbr=128, filesize=9_000_000, protocol="https"))
    raw = dict(id="abc", title="Ten minute talk", extractor="youtube", extractor_key="Youtube",
               webpage_url="https://www.youtube.com/watch?v=abc", duration=600, formats=fmts)
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as y:
        return y.process_ie_result(copy.deepcopy(raw), download=False)


def test_sizes_follow_the_real_format_choice():
    info = _fake_youtube_info()
    mac = {o["quality"]: o for o in downloader.estimate_options(info, {"mac_compatible": True})}
    # Mac-friendly best is the 1080p H.264 file: 3000 kbps * 600 s = 225 MB, + 9 MB audio
    assert mac["best"]["height"] == 1080 and mac["best"]["bytes"] == 234_000_000
    assert mac["best"]["exact"] is False                 # estimated from bitrate
    assert mac["1080"]["duplicate"] and not mac["720"]["duplicate"]
    assert mac["480"]["bytes"] == 69_000_000
    assert "audio" not in mac
    anyc = {o["quality"]: o for o in downloader.estimate_options(info, {"mac_compatible": False})}
    assert anyc["best"]["height"] == 2160 and anyc["best"]["bytes"] == 1_209_000_000


def test_prompt_text_shows_size_and_smaller_option():
    from vdl.clipboard import describe
    info = {"title": "Ten minute talk", "site": "Youtube", "duration": 600,
            "options": downloader.estimate_options(_fake_youtube_info(), {"mac_compatible": False})}
    text, size = describe(info, "best")
    assert size == "≈1.2 GB"
    assert "Size at best quality, 2160p: ≈1.2 GB" in text
    assert "Smallest: 480p, ≈69 MB" in text
    assert downloader.format_bytes(None) == "size unknown"


def test_clipboard_looks_up_before_asking(store):
    store.update_settings({"native_prompt": False})
    w = ClipboardWatcher(store, manager=None, open_app=lambda: None,
                         lookup=lambda url: {"kind": "video", "title": "Clip", "options": []})
    item = w.consider("https://vimeo.com/76979871", background=False)
    assert item["state"] == "looking"
    w._look_up_and_ask(item)
    assert item["state"] == "ready" and item["info"]["title"] == "Clip"

    def boom(url):
        raise RuntimeError("ERROR: Private video")
    w.lookup = boom
    item2 = w.consider("https://vimeo.com/1", background=False)
    w._look_up_and_ask(item2)
    assert item2["state"] == "error" and "private" in item2["error"].lower()


# ------------------------------------------------------------------ Mac app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tree(base):
    out = {}
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            if f.endswith(".pyc"):
                continue
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, base)] = (fh.read(), os.stat(p).st_mode & 0o111 != 0)
    return out


def test_app_bundle_matches_source(tmp_path):
    """The .app carries its own copy of the code. If this fails, run
    python3 tools/build_app.py and commit the result."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_app", os.path.join(ROOT, "tools", "build_app.py"))
    build_app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_app)
    fresh = build_app.build(str(tmp_path))
    committed = os.path.join(ROOT, "Video Downloader.app")
    assert _tree(fresh) == _tree(committed)
    launcher = os.path.join(committed, "Contents", "MacOS", "Video Downloader")
    assert os.access(launcher, os.X_OK)


def test_setup_check_reports_state(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path))
    r = subprocess.run(["bash", os.path.join(ROOT, "setup.sh"), "--check"], env=env)
    assert r.returncode == 1                       # Python found, nothing installed yet
    out = subprocess.run(["bash", os.path.join(ROOT, "setup.sh"), "--python"], env=env,
                         capture_output=True, text=True).stdout.strip()
    assert out == f"{tmp_path}/Library/Application Support/Video Downloader/venv/bin/python"


def test_close_button_hides_but_quit_quits(store):
    from vdl import desktop
    shell = desktop.Desktop("http://127.0.0.1:8737/", store)
    hidden = []
    shell.hide = lambda: hidden.append(True)
    shell._told_about_hiding = True
    assert shell._on_closing() is False and hidden          # red button: keep running

    def applicationShouldTerminate_():                      # what Cmd+Q goes through
        return shell._on_closing()
    assert applicationShouldTerminate_() is None


def test_show_endpoint_uses_window_hook(client):
    shown = []
    client.application.config["show_window"] = lambda: shown.append(True)
    assert client.post("/api/show", headers=H).status_code == 200
    assert shown == [True]
