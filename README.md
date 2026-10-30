# Video Downloader

A small, private Mac app for saving videos from web pages. It's a friendly front end for [yt-dlp](https://github.com/yt-dlp/yt-dlp), and it works with any browser, with no extension and no account.

- **Copy a video link in Firefox** (or any browser) and a "Download this video?" prompt pops up.
- Or **paste or drag a link** into the app to preview it and pick a quality first.
- Progress bars, cancel and retry, "Show in Finder," and a download history.
- Everything runs on your Mac. The app only listens to your own computer, and your links never go to any outside server: yt-dlp talks directly to the video site, the same way your browser does.

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
