# Video Downloader

A small, private Mac app for saving videos from web pages. It's a friendly front end for [yt-dlp](https://github.com/yt-dlp/yt-dlp), and it works with any browser, with no extension and no account.

- **Copy a video link in Firefox** (or any browser) and a "Download this video?" prompt pops up.
- Or **paste or drag a link** into the app to preview it and pick a quality first.
- Progress bars, cancel and retry, "Show in Finder," and a download history.
- Everything runs on your Mac. The app only listens to your own computer, and your links never go to any outside server: yt-dlp talks directly to the video site, the same way your browser does.

## Current status

- **Version 1 built (Oct 29, 2026).** Clipboard watcher with Mac pop-up, paste/drag preview with quality choice, download queue (progress, cancel, retry, Show in Finder), history, settings, yt-dlp updater, and the `start.command` launcher.
- Tested in a Linux sandbox: all 13 automated tests pass, including a real download start to finish, and the screens were checked in light and dark mode.
- **Oct 30: setup no longer needs Homebrew.** Homebrew dropped Intel Macs, and the owner's Mac is a Mid 2015 Intel MacBook Pro on macOS Monterey 12.7.6. `start.command` now installs yt-dlp, ffmpeg (imageio-ffmpeg) and deno (the `deno` pip package) into the app's own `.venv`. Python comes from the python.org installer.
- Setup only installs ready-made packages (never compiles), and skips optional yt-dlp extras that don't have a build for the installed Python yet. The owner has Python 3.15.2 from python.org.
- **Runs on the owner's Mac** (Oct 30). Not yet tested there: the clipboard pop-up, Finder buttons and the folder picker.

## Known issues and next steps

- **Open: launching needs a Terminal window and a browser tab.** `start.command` opens Terminal, and closing that window stops the app. The owner wants this fixed, same as in their other local apps (like the Video Organizer). Likely fix: a double-clickable `.app` that runs in the background with a menu-bar icon (Open, Pause clipboard watching, Quit) and optional start at login, no Terminal window.
- Setup confirmed on the Intel/Monterey Mac (Oct 30): the app opens. Still to check: the clipboard pop-up (macOS may ask permission the first time), a real YouTube download, Show in Finder, and the folder picker.
- The bundled ffmpeg doesn't include ffprobe. Merging and audio-only downloads work without it; if a site needs ffprobe, yt-dlp will say so.
- The pop-up is a plain macOS dialog and may open behind other windows. If that's annoying, consider a menu-bar icon or notification instead.
- Changing "Downloads at once" to a lower number only takes effect after restarting the app.
- Ideas not built yet: saving straight into the Video Organizer's folder or passing tags to it, subtitles download.

## Key decisions

- **Standalone app, not a browser extension.** Unsigned Firefox extensions need re-loading every launch, Developer Edition, or a Mozilla account, and the owner didn't want any of those.
- **yt-dlp as the engine** (free, open source, 1,000+ sites, actively maintained), rather than Video DownloadHelper (watermark or paid license, broad page access) or a downloader website (receives your links).
- **Detection by clipboard** instead of reading browser traffic, which a standalone app can't see. Prompts only for sites with a dedicated yt-dlp extractor, to avoid nagging on every copied link.
- **Local only:** server bound to 127.0.0.1; API requires a custom header and local Host header so other websites can't trigger downloads.
- **Python + Flask + plain HTML/JS, running in the browser**, same style as the owner's Video Organizer. No build step.
- **Mac-friendly H.264 by default** so files play in QuickTime and Finder previews.
- **Settings and history stored outside the repo** (`~/Library/Application Support/Video Downloader/`), so code updates never wipe them.
- **No DRM circumvention.**
- **No Homebrew.** It only supports Apple Silicon now. Everything installs with pip into `.venv`, which works on Intel and Apple Silicon and keeps the rest of the Mac untouched.
- **Get the code as a ZIP from GitHub** rather than `git clone`, so no developer tools are needed on the Mac.

## First-time setup

Works on Intel and Apple Silicon Macs. No Homebrew needed.

1. **Install Python:** go to [python.org/downloads](https://www.python.org/downloads/), click the yellow **Download Python** button, open the downloaded file and click through the installer.
2. **Get the app:** on the [repo page](https://github.com/kingbuck11/Video-downloader), click the green **Code** button → **Download ZIP**. Open the ZIP in Finder and move the `Video-downloader-main` folder somewhere permanent, such as your home folder.
3. **Double-click `start.command`** in that folder. The first run takes a few minutes: it installs yt-dlp, ffmpeg (combines HD video with its sound) and deno (needed for YouTube) inside the app's folder only. Then the app opens in your browser.

**Updating the app later:** download the ZIP again and replace the folder. Your settings and history are kept, because they're stored outside it.

If macOS says `start.command` can't be opened, right-click it, choose **Open**, then **Open** again. You only need to do this once.

## Everyday use

- Double-click `start.command`. Leave the Terminal window it opens running in the background.
- Copy a video page's link. Choose **Download** in the pop-up (default quality), or **Open App** to preview it and choose a quality.
- Videos save to `~/Downloads/Videos` unless you choose another folder in **Settings**.
- To stop the app, click **Quit** in the app, or press Ctrl+C in the Terminal window.

The pop-up only appears for links from sites yt-dlp specifically supports (the [supported sites list](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)). You can switch it to ask about every link in Settings, or paste any link into the app to try it.

## Settings

| Setting | What it does |
|---|---|
| Save videos to | Folder for downloads |
| Default quality | Best, a resolution cap (4K down to 480p), or audio only |
| File names | Title, title plus video ID, or site, uploader and title |
| Mac-friendly files | Prefers H.264 so files play in QuickTime and Finder previews (may cap some sites at 1080p) |
| Watch the clipboard / Pop-up prompt | Turn the copy-to-download behavior on or off |
| Keep download history | Stored only on this Mac; turning it off erases it |

Settings and history live in `~/Library/Application Support/Video Downloader/`.

## When downloads start failing

Sites change their pages often, which breaks yt-dlp until its volunteers fix it (usually within days). Open **Settings → Update yt-dlp**, then quit and reopen the app.

## What it can't do

DRM-protected video (Netflix, Disney+, purchased movies and similar) can't be downloaded, and the app doesn't try. Some sites' terms prohibit downloading, so check before you save.

## For developers

```
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

| Path | Purpose |
|---|---|
| `app.py` | Starts the local server on port 8737 and opens the browser |
| `vdl/downloader.py` | yt-dlp options, video info lookup, download queue and progress |
| `vdl/clipboard.py` | Clipboard watcher and the macOS pop-up prompt |
| `vdl/server.py` | Flask API, restricted to this Mac and to the app's own page |
| `vdl/settings.py` | Settings and history JSON files |
| `static/` | The app's page (HTML, CSS, JS, no build step) |
| `start.command` | Double-click launcher: finds Python 3.11+, sets up `.venv` with yt-dlp, ffmpeg and deno |
