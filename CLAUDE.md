# Video Downloader: notes for Claude

Local Mac app: a front end for yt-dlp. Python + Flask backend, plain HTML/CSS/JS frontend, shown in a native pywebview window by `Video Downloader.app` (no browser tab, no Terminal). The owner uses Firefox, doesn't want browser extensions or accounts, and isn't a developer, so keep setup to downloading the ZIP and opening the app.

**After changing any app code, run `python3 tools/build_app.py` and commit `Video Downloader.app` too** (the app carries its own copy; a test checks it's in sync).

## Principles
- Everything stays on the Mac. No telemetry, no outside servers, no remote "downloader" services. The only outside contact besides the video sites is updating yt-dlp from PyPI.
- Server binds to 127.0.0.1 only. Every `/api/` request must carry the `X-Video-Downloader: 1` header and a local Host header (blocks other websites and DNS rebinding). Keep that guard on any new endpoint.
- `/api/reveal` only opens files the app downloaded (jobs or history).
- Never add DRM circumvention.
- Settings and history live in `~/Library/Application Support/Video Downloader/` so updating the code never loses them. New settings need a default in `vdl/settings.py` `DEFAULTS` (and validation if it's a choice).

## Layout
- `vdl/downloader.py`: `build_options()` maps settings to yt-dlp options; `DownloadManager` runs a worker queue with progress/cancel hooks.
- `vdl/downloader.py` `estimate_options()`: per-quality size by re-running yt-dlp's `process_video_result` with each quality's format options on the fetched info (strip stale `requested_formats`/`format_id` first); falls back to tbr×duration, then a HEAD request.
- `vdl/downloader.py` `_page_videos()`: Generic-extractor playlists become `kind: "multi"` (entries with item index, duration, size, `main`, `short`); a Job with `item` downloads one entry via `playlist_items` and names the file after the page. `probe_hls()` sizes chunked streams from their playlist; `_content_length()` tries HEAD then a 1-byte range request.
- `vdl/clipboard.py`: polls `pbpaste` each second; prompts only for URLs a dedicated (non-Generic) extractor matches, unless `prompt_all_links`. Looks the video up first (pending item states: looking/ready/error), then shows an `osascript display dialog` with title and size.
- `vdl/server.py`: Flask routes. `static/app.js` polls `/api/state`. `app.config["show_window"]` is the hook for bringing the window forward (clipboard "Choose Quality…", `/api/show` from a second launch).
- `vdl/desktop.py`: pywebview window; closing hides it (returns False from the closing event unless called via `applicationShouldTerminate_`, i.e. Cmd+Q); NSStatusItem menu; Apple-event reopen handler. Can't run in the Linux sandbox: test with stand-in modules and ask the owner to try it.
- `setup.sh`: venv in `~/Library/Application Support/Video Downloader/venv`, pip `--only-binary=:all:`. `tools/launcher.sh` is the .app's executable (setup dialog via osascript, log in `~/Library/Logs/Video Downloader.log`).
- External tools: ffmpeg (merging HD video+audio) and deno (YouTube's JS challenges). Both are pip-installed into the app's venv (`imageio-ffmpeg`, yt-dlp's `deno` extra); found there first, then PATH/Homebrew dirs.
- Owner's Mac: Mid 2015 Intel MacBook Pro, macOS Monterey 12.7.6. Homebrew no longer supports Intel, so never rely on `brew`. Python comes from the python.org installer; yt-dlp needs Python 3.11+.

## Testing
`python3 -m pytest -q` (with yt-dlp, flask, pytest installed). The end-to-end test downloads a generated clip from a local HTTP server, so it needs ffmpeg but no internet.
