"""Everything that talks to yt-dlp: site detection, video info, and the download queue."""
import copy
import os
import queue
import re
import shutil
import sys
import sysconfig
import threading
import time
import uuid

import yt_dlp
from yt_dlp.extractor import gen_extractor_classes
from yt_dlp.utils import DownloadCancelled, DownloadError

# ---------------------------------------------------------------- helpers

def _tool_dirs():
    """The app's own Python environment first (start.command installs ffmpeg
    and deno there with pip, so no Homebrew is needed), then common spots."""
    dirs = [os.path.dirname(sys.executable), sysconfig.get_path("scripts")]
    return dirs + ["/opt/homebrew/bin", "/usr/local/bin"]


def _find_tool(name):
    for folder in _tool_dirs():
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which(name)


def ffmpeg_path():
    """ffmpeg merges separate video+audio streams into one file. Normally it
    comes from the imageio-ffmpeg package (works on Intel and Apple Silicon)."""
    try:
        import imageio_ffmpeg
        found = imageio_ffmpeg.get_ffmpeg_exe()
        if found and os.path.isfile(found):
            return found
    except Exception:  # noqa: BLE001 - package missing or no binary for this Mac
        pass
    return _find_tool("ffmpeg")


def deno_path():
    """yt-dlp needs a JavaScript runtime (deno) to work with YouTube."""
    return _find_tool("deno")


def js_runtime_options():
    """Point yt-dlp at deno even if it isn't on PATH (e.g. Homebrew not in PATH)."""
    deno = deno_path()
    return {"js_runtimes": {"deno": {"path": deno}}} if deno else {}


def ytdlp_version():
    return yt_dlp.version.__version__


_extractors = None


def _dedicated_extractors():
    global _extractors
    if _extractors is None:
        _extractors = [ie for ie in gen_extractor_classes() if ie.ie_key() != "Generic"]
    return _extractors


def looks_like_url(text):
    text = (text or "").strip()
    return text.startswith(("http://", "https://")) and " " not in text and "\n" not in text and len(text) < 2048


def site_for(url):
    """Name of the yt-dlp extractor built for this URL, or None if only the
    generic extractor would try it."""
    if not looks_like_url(url):
        return None
    for ie in _dedicated_extractors():
        try:
            if ie.suitable(url):
                return ie.IE_NAME
        except Exception:  # a broken extractor regex should never take the app down
            continue
    return None


def _download_total(job, d, current_total):
    """Total size of everything this video needs (video and audio tracks
    download one after the other), so progress can say "of 1.2 GB"."""
    info = d.get("info_dict") or {}
    parts = info.get("requested_formats")
    if parts:
        sizes = [p.get("filesize") or p.get("filesize_approx") for p in parts]
        if all(sizes):
            return sum(sizes)
    return current_total


def format_bytes(n, exact=True):
    if not n:
        return "size unknown"
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            break
        n /= 1000
    text = f"{n:.1f} {unit}" if unit in ("GB", "TB") and n < 10 else f"{n:.0f} {unit}"
    return text if exact else "≈" + text


def option_for(info, quality):
    return next((o for o in info.get("options") or [] if o["quality"] == quality), None)


def friendly_error(err):
    msg = str(err)
    msg = msg.replace("ERROR: ", "").strip()
    low = msg.lower()
    if "drm" in low:
        return "This video is DRM-protected, so it can't be downloaded."
    if "unsupported url" in low:
        return "No downloadable video found at this link. The site may not be supported (try the video's own page)."
    if "sign in" in low or "login" in low or "log in" in low:
        return "This site needs you to be logged in to see this video. " + msg[:200]
    if "private video" in low:
        return "This video is private."
    if "http error 403" in low or "http error 429" in low:
        return "The site refused the download. Try updating yt-dlp (Settings), then try again. " + msg[:200]
    return msg[:400]


# ---------------------------------------------------------------- format choice

def build_options(settings, *, has_ffmpeg, allow_playlist=False):
    """yt-dlp options for the user's quality / compatibility / naming settings."""
    quality = settings.get("quality", "best")
    names = {
        "title": "%(title).180B.%(ext)s",
        "title_id": "%(title).160B [%(id)s].%(ext)s",
        "site_title": "%(extractor_key)s - %(uploader,channel|Unknown).60B - %(title).140B.%(ext)s",
    }
    template = names.get(settings.get("filename"), names["title"])
    if allow_playlist:
        template = os.path.join("%(playlist_title,playlist|Playlist).120B", template)

    opts = {
        "paths": {"home": settings["save_dir"]},
        "outtmpl": template,
        "noplaylist": not allow_playlist,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "windowsfilenames": False,
        "trim_file_name": 240,
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "fragment_retries": 10,
        "ignoreerrors": "only_download" if allow_playlist else False,
    }

    cap = f"[height<={quality}]" if quality.isdigit() else ""
    if has_ffmpeg:
        # best video + best audio merged; fall back to a single combined file, then anything
        opts["format"] = f"bv*{cap}+ba/b{cap}/bv*+ba/b"
        opts["merge_output_format"] = "mp4"
    else:
        # without ffmpeg only single-file formats work (usually capped around 720p)
        opts["format"] = f"b{cap}[ext=mp4]/b{cap}/b"

    if settings.get("mac_compatible", True):
        # prefer codecs QuickTime/Finder play natively; may cap some sites at 1080p
        opts["format_sort"] = ["vcodec:h264", "res", "acodec:aac"]
    return opts


# ---------------------------------------------------------------- info lookup

QUALITIES = ("best", "2160", "1440", "1080", "720", "480")


def fetch_info(url, settings=None):
    """Quick look at a link before downloading: title, thumbnail, playlist size,
    and the estimated file size for each quality choice."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": "in_playlist", "noplaylist": True, **js_runtime_options()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        raw = ydl.extract_info(url, download=False)
    info = ydl.sanitize_info(raw)

    if info.get("_type") == "playlist" and info.get("extractor_key") == "Generic":
        # a page yt-dlp doesn't know, with several videos on it (often ads,
        # previews or related clips next to the one you want): let the user pick
        return _page_videos(url, settings or {})

    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        return {
            "kind": "playlist",
            "title": info.get("title") or "Playlist",
            "site": info.get("extractor_key"),
            "count": len(entries),
            "thumbnail": _thumb(info) or next((_thumb(e) for e in entries if _thumb(e)), None),
            "url": url,
        }

    heights = sorted({f.get("height") for f in info.get("formats") or [] if f.get("height")}, reverse=True)
    options = estimate_options(raw, settings or {}) if not info.get("is_live") else []
    return {
        "kind": "video",
        "title": info.get("title") or "Untitled video",
        "site": info.get("extractor_key"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
        "thumbnail": _thumb(info),
        "heights": heights,
        "options": options,
        "is_live": bool(info.get("is_live")),
        "url": info.get("webpage_url") or url,
    }


MAX_PAGE_VIDEOS = 15
SHORT_CLIP_SECONDS = 60


def _page_videos(url, settings):
    """Every video found on an unsupported page, with length and size, the
    likely main video marked and short clips (probably ads) flagged."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "playlistend": MAX_PAGE_VIDEOS, **js_runtime_options()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        page = ydl.extract_info(url, download=False)
    entries = [e for e in (page.get("entries") or []) if e]

    videos, seen_urls = [], set()
    for pos, entry in enumerate(entries, 1):
        media = entry.get("url") or next((f.get("url") for f in entry.get("formats") or []), None)
        if media in seen_urls:
            continue                     # same video embedded twice
        seen_urls.add(media)
        cache = {}
        try:
            options = estimate_options(entry, settings, cache) if entry.get("formats") else []
        except Exception:  # noqa: BLE001
            options = []
        duration = entry.get("duration") or max(
            (c.get("duration") or 0 for c in cache.values()), default=0) or None
        best = next((o for o in options if o["quality"] == "best"), None)
        height = (best or {}).get("height") or max(
            (c.get("height") or 0 for c in cache.values()), default=0) or None
        if best and not best.get("height") and height:
            best["height"] = height
        videos.append({
            "item": entry.get("playlist_index") or pos,
            "title": entry.get("title") or f"Video {pos}",
            # a real site name (e.g. an embedded YouTube video), not yt-dlp's internal fallbacks
            "site": None if entry.get("extractor_key") in ("Generic", "HTML5MediaEmbed") else entry.get("extractor_key"),
            "duration": duration,
            "thumbnail": _thumb(entry),
            "height": height,
            "options": options,
            "bytes": (best or {}).get("bytes"),
        })

    main = _likely_main(videos)
    for v in videos:
        v["main"] = v is main
        v["short"] = v is not main and _looks_like_extra(v, main)
    page_title = page.get("title") or (main or {}).get("title") or "Videos on this page"
    return {
        "kind": "multi",
        "title": page_title,
        "site": "Generic",
        "url": url,
        "count": len(videos),
        "videos": videos,
        "thumbnail": (main or {}).get("thumbnail"),
    }


def _likely_main(videos):
    """The main video is usually by far the longest (or, without lengths, the biggest)."""
    if not videos:
        return None
    if any(v["duration"] for v in videos):
        return max(videos, key=lambda v: v["duration"] or 0)
    if any(v["bytes"] for v in videos):
        return max(videos, key=lambda v: v["bytes"] or 0)
    return videos[0]


def _looks_like_extra(video, main):
    if video["duration"]:
        return video["duration"] < SHORT_CLIP_SECONDS
    if video["bytes"] and main and main.get("bytes"):
        return video["bytes"] < main["bytes"] * 0.1
    return False


def _format_size(fmt, duration):
    """Bytes for one format: exact if the site says, else estimated from bitrate."""
    if fmt.get("filesize"):
        return fmt["filesize"], True
    if fmt.get("filesize_approx"):
        return fmt["filesize_approx"], False
    if fmt.get("tbr") and duration:
        return int(fmt["tbr"] * 1000 / 8 * duration), False
    return None, False


def _open(url, headers=None, method="GET", timeout=8):
    from yt_dlp.networking import Request
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "socket_timeout": timeout}) as ydl:
        return ydl.urlopen(Request(url, method=method, headers=headers or {}))


def _content_length(url, headers=None):
    """Size of a file on the server without downloading it: a HEAD request,
    or (for servers that refuse HEAD) a request for just its first byte."""
    try:
        resp = _open(url, headers, "HEAD")
        length = resp.headers.get("Content-Length")
        resp.close()
        if length and int(length) > 0:
            return int(length)
    except Exception:  # noqa: BLE001
        pass
    try:
        resp = _open(url, dict(headers or {}, Range="bytes=0-0"))
        total = (resp.headers.get("Content-Range") or "").rpartition("/")[2]
        resp.close()
        if total.isdigit():
            return int(total)
    except Exception:  # noqa: BLE001
        pass
    return None


def _absolute(url):
    return "https:" + url if url.startswith("//") else url


def probe_hls(url, headers=None):
    """Chunked streams (HLS) come as a playlist of short pieces. Read the
    playlist to get the total length, then size = bitrate x length, or the
    size of one piece scaled up to the whole video. Downloads only the small
    playlist text (and asks the size of one piece)."""
    from urllib.parse import urljoin
    url = _absolute(url)
    try:
        resp = _open(url, headers)
        text = resp.read(2_000_000).decode("utf-8", "replace")
        resp.close()
    except Exception:  # noqa: BLE001
        return {}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    result = {}
    if any(ln.startswith("#EXT-X-STREAM-INF") for ln in lines):
        # master playlist: pick the highest-bandwidth variant
        best = None
        for k, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF") and k + 1 < len(lines):
                bw = re.search(r"[^-]BANDWIDTH=(\d+)", ln) or re.search(r"BANDWIDTH=(\d+)", ln)
                res = re.search(r"RESOLUTION=\d+x(\d+)", ln)
                cand = (int(bw.group(1)) if bw else 0, int(res.group(1)) if res else None, urljoin(url, lines[k + 1]))
                if best is None or cand[0] > best[0]:
                    best = cand
        if not best:
            return {}
        inner = probe_hls(best[2], headers)
        if best[1]:
            inner["height"] = best[1]
        if best[0] and inner.get("duration") and not inner.get("bytes"):
            inner["bytes"] = int(best[0] / 8 * inner["duration"])
        return inner

    durations, ranges, first_seg, first_len = [], 0, None, None
    pending = None
    for ln in lines:
        if ln.startswith("#EXTINF:"):
            try:
                pending = float(ln[8:].split(",")[0])
            except ValueError:
                pending = None
        elif ln.startswith("#EXT-X-BYTERANGE:"):
            try:
                ranges += int(ln.split(":")[1].split("@")[0])
            except ValueError:
                pass
        elif not ln.startswith("#") and pending is not None:
            durations.append(pending)
            if first_seg is None:
                first_seg, first_len = urljoin(url, ln), pending
            pending = None
    if not durations:
        return {}
    result["duration"] = sum(durations)
    if ranges:
        result["bytes"] = ranges
    elif first_seg and first_len:
        piece = _content_length(first_seg, headers)
        if piece:
            result["bytes"] = int(piece / first_len * result["duration"])
    return result


def _probe(fmt, cache):
    """Last resort for a format with no size information: ask the server."""
    url = fmt.get("url")
    if not url:
        return {}
    if url not in cache:
        protocol = fmt.get("protocol") or ""
        if protocol.startswith("m3u8") or ".m3u8" in url:
            cache[url] = probe_hls(url, fmt.get("http_headers"))
        elif protocol in ("http", "https", ""):
            size = _content_length(_absolute(url), fmt.get("http_headers"))
            cache[url] = {"bytes": size, "exact": True} if size else {}
        else:
            cache[url] = {}
    return cache[url]


def estimate_options(processed, settings, probe_cache=None):
    """For each quality choice, ask yt-dlp which format(s) it would really pick
    (same rules as the download) and add up their sizes. No network needed:
    it reuses the format list already fetched."""
    settings = {"save_dir": "", "mac_compatible": True, **settings}
    has_ffmpeg = bool(ffmpeg_path())
    duration = processed.get("duration")
    by_id = {f.get("format_id"): f for f in processed.get("formats") or []}
    results, seen = [], set()
    head_cache = probe_cache if probe_cache is not None else {}
    for quality in QUALITIES:
        opts = build_options(dict(settings, quality=quality), has_ffmpeg=has_ffmpeg)
        pick = {k: opts[k] for k in ("format", "format_sort") if k in opts}
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, **pick}) as ydl:
                fresh = copy.deepcopy(processed)
                for stale in ("requested_formats", "requested_downloads", "format_id", "format"):
                    fresh.pop(stale, None)   # left over from the first lookup's own choice
                chosen = ydl.process_video_result(fresh, download=False)
        except Exception:  # noqa: BLE001 - no format matches this choice
            continue
        ids = [f.get("format_id") for f in chosen.get("requested_formats") or []] or [chosen.get("format_id")]
        fmts = [by_id.get(i) or chosen for i in ids]
        key = "+".join(str(i) for i in ids)
        duplicate = key in seen   # same file as a higher choice (e.g. video tops out at 720p)
        seen.add(key)
        total, exact = 0, True
        for f in fmts:
            size, is_exact = _format_size(f, duration)
            if size is None:
                found = _probe(f, head_cache)
                if found.get("duration") and not duration:
                    duration = found["duration"]
                if found.get("bytes"):
                    size, is_exact = found["bytes"], bool(found.get("exact"))
                elif f.get("tbr") and found.get("duration"):
                    size, is_exact = int(f["tbr"] * 1000 / 8 * found["duration"]), False
            if size is None:
                total = None
                break
            total += size
            exact = exact and is_exact
        video = next((f for f in fmts if f.get("vcodec") not in (None, "none")), None)
        results.append({
            "quality": quality,
            "height": video.get("height") if video else None,
            "bytes": total,
            "exact": bool(total) and exact,
            "duplicate": duplicate,
        })
    return results


def _thumb(info):
    if not info:
        return None
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = info.get("thumbnails") or []
    return thumbs[-1].get("url") if thumbs else None


# ---------------------------------------------------------------- jobs

class Job:
    def __init__(self, url, title=None, quality=None, playlist=False, item=None):
        self.id = uuid.uuid4().hex[:10]
        self.url = url
        self.title = title or url
        self.quality = quality
        self.playlist = playlist
        self.item = item          # one video picked from a page with several
        self.status = "queued"   # queued | downloading | processing | done | error | cancelled
        self.percent = 0.0
        self.speed = None
        self.eta = None
        self.total_bytes = None
        self._video_id = None
        self._parts_done = 0
        self.detail = ""
        self.filepath = None
        self.files = []
        self.error = None
        self.site = None
        self.created = time.time()
        self.cancel_requested = False

    def to_dict(self):
        return {k: getattr(self, k) for k in (
            "id", "url", "title", "quality", "playlist", "item", "status", "percent", "speed", "eta", "total_bytes",
            "detail", "filepath", "error", "site", "created")} | {"file_count": len(self.files)}


class DownloadManager:
    def __init__(self, store):
        self.store = store
        self.jobs = {}
        self._order = []
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._workers = []
        self._ensure_workers()

    def _ensure_workers(self):
        wanted = int(self.store.settings.get("max_parallel", 2))
        while len([w for w in self._workers if w.is_alive()]) < wanted:
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self._workers.append(t)

    # public ---------------------------------------------------------------
    def add(self, url, title=None, quality=None, playlist=False, item=None):
        job = Job(url, title, quality or self.store.settings["quality"], playlist, item)
        with self._lock:
            self.jobs[job.id] = job
            self._order.append(job.id)
        self._ensure_workers()
        self._queue.put(job.id)
        return job

    def list(self):
        with self._lock:
            return [self.jobs[i].to_dict() for i in reversed(self._order)]

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            return False
        job.cancel_requested = True
        if job.status == "queued":
            job.status = "cancelled"
        return True

    def retry(self, job_id):
        job = self.jobs.get(job_id)
        if not job or job.status not in ("error", "cancelled"):
            return None
        return self.add(job.url, job.title, job.quality, job.playlist, job.item)

    def clear_finished(self):
        with self._lock:
            keep = [i for i in self._order if self.jobs[i].status in ("queued", "downloading", "processing")]
            for i in self._order:
                if i not in keep:
                    del self.jobs[i]
            self._order = keep

    def known_paths(self):
        paths = {p for j in self.jobs.values() for p in j.files}
        paths |= {h.get("path") for h in self.store.history if h.get("path")}
        return paths

    # worker ---------------------------------------------------------------
    def _worker(self):
        while True:
            job_id = self._queue.get()
            job = self.jobs.get(job_id)
            if job and job.status == "queued" and not job.cancel_requested:
                self._run(job)
            self._queue.task_done()

    def _run(self, job):
        settings = dict(self.store.settings, quality=job.quality)
        os.makedirs(settings["save_dir"], exist_ok=True)
        ffmpeg = ffmpeg_path()
        opts = build_options(settings, has_ffmpeg=bool(ffmpeg), allow_playlist=job.playlist)
        if job.item:
            # just the chosen video from the page, saved like a single video,
            # named after the page rather than yt-dlp's "Title (3)"
            opts.update(noplaylist=False, playlist_items=str(job.item))
            if job.title and job.title != job.url:
                from yt_dlp.utils import sanitize_filename
                name = sanitize_filename(job.title)[:180].replace("%", "%%")
                opts["outtmpl"] = name + ".%(ext)s"
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
        opts.update(js_runtime_options())
        opts["progress_hooks"] = [lambda d: self._on_progress(job, d)]
        opts["postprocessor_hooks"] = [lambda d: self._on_post(job, d)]
        job.status = "downloading"
        job.detail = "Starting…"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
                info = ydl.sanitize_info(info) if info else {}
            job.site = info.get("extractor_key")
            if info.get("title"):
                job.title = info["title"]
            for item in [info] + [e for e in (info.get("entries") or []) if e]:
                for req in item.get("requested_downloads") or []:
                    path = req.get("filepath")
                    if path and path not in job.files:
                        job.files.append(path)
            if not job.files and job.playlist:
                raise DownloadError("None of the playlist's videos could be downloaded.")
            if not job.files and job.item:
                raise DownloadError("That video is no longer on the page. Look the link up again.")
            job.filepath = job.files[0] if job.files else None
            sizes = [os.path.getsize(f) for f in job.files if os.path.exists(f)]
            if sizes:
                job.total_bytes = sum(sizes)          # the real size on disk
            job.status = "done"
            job.percent = 100.0
            job.detail = f"{len(job.files)} files" if len(job.files) > 1 else ""
            self.store.add_history({
                "title": job.title, "url": job.url, "site": job.site,
                "path": job.filepath, "files": len(job.files),
            })
        except DownloadCancelled:
            job.status = "cancelled"
            job.detail = ""
        except Exception as err:  # noqa: BLE001 - surface any failure to the user
            if job.cancel_requested:
                job.status = "cancelled"
            else:
                job.status = "error"
                job.error = friendly_error(err)
        finally:
            job.speed = job.eta = None

    def _on_progress(self, job, d):
        if job.cancel_requested:
            raise DownloadCancelled("Cancelled")
        info = d.get("info_dict") or {}
        if info.get("title") and job.title == job.url:
            job.title = info["title"]
        if info.get("id") != job._video_id:      # next video in a playlist
            job._video_id, job._parts_done = info.get("id"), 0
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            if total:
                job.total_bytes = _download_total(job, d, total)
                # video and audio tracks download one after another: show one 0-100% for both
                overall = (job._parts_done + done) * 100 / max(job.total_bytes, job._parts_done + total)
                job.percent = round(min(99.9, overall), 1)
            elif d.get("fragment_count"):
                job.percent = round(min(99.9, (d.get("fragment_index") or 0) * 100 / d["fragment_count"]), 1)
            job.speed = d.get("speed")
            job.eta = d.get("eta")
            parts = []
            if job.playlist and info.get("playlist_index"):
                parts.append(f"Video {info['playlist_index']} of {info.get('n_entries') or '?'}")
            job.detail = " · ".join(parts)
        elif d["status"] == "finished":
            job.speed = job.eta = None
            if info.get("requested_formats"):
                job._parts_done += d.get("total_bytes") or d.get("downloaded_bytes") or 0

    def _on_post(self, job, d):
        if d.get("status") == "started":
            job.status = "processing"
            job.detail = {
                "Merger": "Combining video and audio…",
            }.get(d.get("postprocessor"), "Finishing up…")
        elif d.get("status") == "finished" and job.status == "processing":
            job.status = "downloading"
