# Video Downloader: notes for Claude

Local Mac app: a front end for yt-dlp. Python + Flask backend, plain HTML/CSS/JS frontend (no build step). The owner uses Firefox, doesn't want browser extensions or accounts, and isn't a developer, so keep setup to double-clicking `start.command`.

## Principles
- Everything stays on the Mac. No telemetry, no outside servers, no remote "downloader" services. The only outside contact besides the video sites is updating yt-dlp from PyPI.
- Server binds to 127.0.0.1 only. Every `/api/` request must carry the `X-Video-Downloader: 1` header and a local Host header (blocks other websites and DNS rebinding). Keep that guard on any new endpoint.
- `/api/reveal` only opens files the app downloaded (jobs or history).
- Never add DRM circumvention.
- Settings and history live in `~/Library/Application Support/Video Downloader/` so updating the code never loses them. New settings need a default in `vdl/settings.py` `DEFAULTS` (and validation if it's a choice).

## Layout
- `vdl/downloader.py`: `build_options()` maps settings to yt-dlp options; `DownloadManager` runs a worker queue with progress/cancel hooks.
- `vdl/clipboard.py`: polls `pbpaste` each second; prompts only for URLs a dedicated (non-Generic) extractor matches, unless `prompt_all_links`. Native prompt is `osascript display dialog`.
- `vdl/server.py`: Flask routes. `static/app.js` polls `/api/state`.
- External tools: ffmpeg (merging HD video+audio) and deno (YouTube's JS challenges). Both are pip-installed into `.venv` (`imageio-ffmpeg`, yt-dlp's `deno` extra); found there first, then PATH/Homebrew dirs.
- Owner's Mac: Mid 2015 Intel MacBook Pro, macOS Monterey 12.7.6. Homebrew no longer supports Intel, so never rely on `brew`. Python comes from the python.org installer; yt-dlp needs Python 3.11+.

## Testing
`.venv/bin/python -m pytest -q`. The end-to-end test downloads a generated clip from a local HTTP server, so it needs ffmpeg but no internet.
