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


def test_audio_only(store):
    o = downloader.build_options(dict(store.settings, quality="audio"), has_ffmpeg=True)
    assert o["format"].startswith("ba")
    assert o["postprocessors"][0]["preferredcodec"] == "m4a"


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
    assert w.consider("https://example.com/recipe") is None
    item = w.consider("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert item and item["site"]
    assert w.consider("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is None  # no repeat prompt
    assert w.consider("hello there") is None
    store.update_settings({"prompt_all_links": True})
    assert w.consider("https://example.com/recipe")


# ------------------------------------------------------------------ settings + history

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

        job = client.post("/api/download", json={"url": url}, headers=H).get_json()
        for _ in range(100):
            jobs = client.get("/api/state", headers=H).get_json()["jobs"]
            current = next(j for j in jobs if j["id"] == job["id"])
            if current["status"] in ("done", "error"):
                break
            time.sleep(0.1)
        assert current["status"] == "done", current
        assert os.path.exists(current["filepath"])
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
