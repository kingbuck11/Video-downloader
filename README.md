# Video Downloader

A small, private Mac app for saving videos from web pages. It's a friendly front end for [yt-dlp](https://github.com/yt-dlp/yt-dlp), and it works with any browser, with no extension and no account.

- **Copy a video link in Firefox** (or any browser) and a "Download this video?" prompt pops up.
- Or **paste or drag a link** into the app to preview it and pick a quality first.
- Progress bars, cancel and retry, "Show in Finder," and a download history.
- Everything runs on your Mac. The app only listens to your own computer, and your links never go to any outside server: yt-dlp talks directly to the video site, the same way your browser does.

## Current status

- **Version 1 built (Oct 29, 2026).** Clipboard watcher with Mac pop-up, paste/drag preview with quality choice, download queue (progress, cancel, retry, Show in Finder), history, settings, yt-dlp updater, and the `start.command` launcher.
- Tested in a Linux sandbox: all 13 automated tests pass, including a real download start to finish, and the screens were checked in light and dark mode.
- **Not yet tested on the Mac:** the clipboard pop-up, Finder buttons, the folder picker, and `start.command` itself.

## Known issues and next steps

- First Mac run: confirm setup works, and that the pop-up appears (macOS may ask permission the first time).
- The pop-up is a plain macOS dialog and may open behind other windows. If that's annoying, consider a menu-bar icon or notification instead.
- Changing "Downloads at once" to a lower number only takes effect after restarting the app.
- Ideas not built yet: menu-bar icon, auto-start at login, a launcher `.app` instead of `start.command`, saving straight into the Video Organizer's folder or passing tags to it, subtitles download.

## Key decisions

- **Standalone app, not a browser extension.** Unsigned Firefox extensions need re-loading every launch, Developer Edition, or a Mozilla account, and the owner didn't want any of those.
- **yt-dlp as the engine** (free, open source, 1,000+ sites, actively maintained), rather than Video DownloadHelper (watermark or paid license, broad page access) or a downloader website (receives your links).
- **Detection by clipboard** instead of reading browser traffic, which a standalone app can't see. Prompts only for sites with a dedicated yt-dlp extractor, to avoid nagging on every copied link.
- **Local only:** server bound to 127.0.0.1; API requires a custom header and local Host header so other websites can't trigger downloads.
- **Python + Flask + plain HTML/JS, running in the browser**, same style as the owner's Video Organizer. No build step.
- **Mac-friendly H.264 by default** so files play in QuickTime and Finder previews.
- **Settings and history stored outside the repo** (`~/Library/Application Support/Video Downloader/`), so code updates never wipe them.
- **No DRM circumvention.**

## First-time setup

1. **Install Homebrew** if you don't have it: see [brew.sh](https://brew.sh).
2. **Install the helper tools** in Terminal:
   ```
   brew install python ffmpeg deno
   ```
   - `ffmpeg` combines HD video with its sound track.
   - `deno` is needed for YouTube.
3. **Get the app:**
   ```
   git clone https://github.com/kingbuck11/video-downloader.git ~/Video-downloader
   ```
4. **Double-click `start.command`** in that folder. The first run takes about a minute to set itself up, then the app opens in your browser.

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
| `start.command` | Double-click launcher: sets up `.venv`, checks ffmpeg and deno |
