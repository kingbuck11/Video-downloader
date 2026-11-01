# Video Downloader

A small, private Mac app for saving videos from web pages. It's a friendly front end for [yt-dlp](https://github.com/yt-dlp/yt-dlp): a real Mac app with its own window and a menu-bar icon, that works alongside any browser, with no extension and no account.

- **Copy a video link in Firefox** (or any browser) and a "Download this video?" prompt pops up.
- Or **paste or drag a link** into the app to preview it and pick a quality first.
- The file size is shown before you download.
- Progress bars, cancel and retry, "Show in Finder," and a download history.
- Everything runs on your Mac. The app only listens to your own computer, and your links never go to any outside server: yt-dlp talks directly to the video site, the same way your browser does.

## Current status

- **Version 1 built (Oct 29, 2026).** Clipboard watcher with Mac pop-up, paste/drag preview with quality choice, download queue (progress, cancel, retry, Show in Finder), history, settings, yt-dlp updater, and the `start.command` launcher.
- Tested in a Linux sandbox: all 13 automated tests pass, including a real download start to finish, and the screens were checked in light and dark mode.
- **Oct 30: setup no longer needs Homebrew.** Homebrew dropped Intel Macs, and the owner's Mac is a Mid 2015 Intel MacBook Pro on macOS Monterey 12.7.6. `start.command` now installs yt-dlp, ffmpeg (imageio-ffmpeg) and deno (the `deno` pip package) into the app's own `.venv`. Python comes from the python.org installer.
- Setup only installs ready-made packages (never compiles), and skips optional yt-dlp extras that don't have a build for the installed Python yet. The owner has Python 3.15.2 from python.org.
- **Oct 30: file size shown before downloading** (like the old RealPlayer). The pop-up looks the video up first and offers "Download (≈310 MB)" / "Choose Quality…" / "Ignore", noting the smallest option when it's much smaller. The preview's quality menu lists a size for each choice, and the download list shows "42% of 1.2 GB" with one progress bar covering video and audio.
- **Runs on the owner's Mac** (Oct 30): clipboard pop-up, a real YouTube download, Show in Finder and the folder picker all confirmed working (with the old `start.command` + browser launch).
- **Oct 30: standalone Mac app.** `Video Downloader.app` opens the app in its own window (pywebview, using the Mac's built-in WebKit); no browser tab and no Terminal. Closing the window keeps it watching the clipboard; a ⬇ menu-bar icon has Show, Watch Clipboard (on/off), Open Downloads Folder and Quit. First launch shows a "Setting up…" message while it installs. Built and smoke-tested in the sandbox against stand-in macOS modules; **not yet tried on the Mac.**

## Known issues and next steps

- **Nov 1 fix:** the first Mac launch crashed. Setup couldn't install pywebview 6 because its helper `proxy_tools` only exists as source code; the fallback then quietly installed an old pywebview without the `events` API. Now setup allows that one pure-Python source package, requires pywebview 6+, and checks the essentials before finishing. If the window still can't open, the app falls back to a browser tab, and any crash shows an error message with **Show Log** instead of vanishing. Opening the app again during setup no longer starts a second setup.
- **First run of the new app on the Mac:** check the setup message, the window, the menu-bar icon, closing and reopening (from the menu bar and by double-clicking the app), Cmd+Q, and the size display on real sites. If something fails, the details are in `~/Library/Logs/Video Downloader.log`; `start.command` runs the same thing with messages shown in Terminal.
- While the app runs, the Dock may label it "Python" in places (the app is run by Python); the menu bar and icon say Video Downloader.
- The same no-Terminal approach (native window + menu-bar icon, self-contained `.app`) could be applied to the owner's other local apps, like the Video Organizer.
- Possible next: start at login (option in Settings).
- Sizes marked ≈ are estimates from the stream's bitrate (most streaming sites don't publish exact sizes); expect them to be within roughly 10–20%. Some sites give no bitrate, so the size shows as unknown. Playlists don't show sizes.
- The bundled ffmpeg doesn't include ffprobe. Merging video and audio works without it; if a site needs ffprobe, yt-dlp will say so.
- The pop-up is a plain macOS dialog and may open behind other windows.
- Changing "Downloads at once" to a lower number only takes effect after restarting the app.
- Ideas not built yet: saving straight into the Video Organizer's folder or passing tags to it, subtitles download.

## Key decisions

- **Standalone app, not a browser extension.** Unsigned Firefox extensions need re-loading every launch, Developer Edition, or a Mozilla account, and the owner didn't want any of those.
- **yt-dlp as the engine** (free, open source, 1,000+ sites, actively maintained), rather than Video DownloadHelper (watermark or paid license, broad page access) or a downloader website (receives your links).
- **Detection by clipboard** instead of reading browser traffic, which a standalone app can't see. Prompts only for sites with a dedicated yt-dlp extractor, to avoid nagging on every copied link.
- **Local only:** server bound to 127.0.0.1; API requires a custom header and local Host header so other websites can't trigger downloads.
- **Python + Flask + plain HTML/JS**, same style as the owner's Video Organizer, shown in a **native window via pywebview** (Mac's own WebKit) instead of a browser tab. pywebview and its pyobjc packages have ready-made builds for Intel Macs and Python 3.15.
- **Self-contained `.app`:** the app carries its own copy of the code (built by `tools/build_app.py`), so it works from anywhere, including Applications, and isn't broken by macOS moving downloaded apps to a temporary location on first open. Its Python environment lives in `~/Library/Application Support/Video Downloader/venv`; the log in `~/Library/Logs/Video Downloader.log`.
- **Closing the window hides it** (clipboard watching continues, no Dock icon while hidden); Cmd+Q or Quit in the menu-bar icon actually quits.
- **Mac-friendly H.264 by default** so files play in QuickTime and Finder previews.
- **Settings and history stored outside the repo** (`~/Library/Application Support/Video Downloader/`), so code updates never wipe them.
- **Size comes from yt-dlp's own format choice** for each quality (same rules as the download, including Mac-friendly), so the number shown matches the file you'd get. Direct video files that don't list a size get a HEAD request to the server (nothing downloaded).
- **The pop-up waits for the lookup** (a few seconds) so it can show the size, rather than asking instantly without one.
- **No audio-only option** (removed Oct 30 at the owner's request).
- **No DRM circumvention.**
- **No Homebrew.** It only supports Apple Silicon now. Everything installs with pip into the app's own environment, which works on Intel and Apple Silicon and keeps the rest of the Mac untouched.
- **Get the code as a ZIP from GitHub** rather than `git clone`, so no developer tools are needed on the Mac.

## First-time setup

Works on Intel and Apple Silicon Macs. No Homebrew needed.

1. **Install Python:** go to [python.org/downloads](https://www.python.org/downloads/), click the yellow **Download Python** button, open the downloaded file and click through the installer. Then double-click **Install Certificates.command** in Applications → Python 3.x.
2. **Get the app:** on the [repo page](https://github.com/kingbuck11/Video-downloader), click the green **Code** button → **Download ZIP**, and open the ZIP. Drag **Video Downloader.app** from the `Video-downloader-main` folder into your **Applications** folder.
3. **Open it the first time with a right-click:** right-click (or Control-click) **Video Downloader** → **Open** → **Open**. macOS asks this once because the app isn't from the App Store.
4. A **"Setting up Video Downloader…"** message appears for a few minutes while it installs yt-dlp, ffmpeg (combines HD video with its sound), deno (needed for YouTube) and the app window. Then the app opens by itself.

**Updating later:** download the ZIP again and drag the new **Video Downloader.app** into Applications, replacing the old one. Settings, history and the installed tools are kept.

## Everyday use

- Open **Video Downloader** from Applications, Launchpad or Spotlight. Add it to your Dock if you like.
- Copy a video page's link in any browser. A pop-up shows the title and size: choose **Download**, or **Choose Quality…** to see the sizes for each quality in the app window.
- Or paste or drag a link into the app window.
- Videos save to `~/Downloads/Videos` unless you choose another folder in **Settings**.
- **Closing the window doesn't quit:** the app keeps watching for copied links. Use the **⬇ icon in the menu bar** to show the window again, pause clipboard watching, or quit. Cmd+Q also quits.

The pop-up only appears for links from sites yt-dlp specifically supports (the [supported sites list](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)). You can switch it to ask about every link in Settings, or paste any link into the app to try it.

## If something goes wrong

- Details are logged in `~/Library/Logs/Video Downloader.log` (Finder → Go → Go to Folder… → `~/Library/Logs`).
- `start.command` in the downloaded folder runs the same app but shows setup and error messages in a Terminal window.
- To reinstall the tools from scratch, quit the app and delete `~/Library/Application Support/Video Downloader/venv`; the next launch sets up again. (Your settings and history in the same folder are separate files and are kept.)

## Settings

| Setting | What it does |
|---|---|
| Save videos to | Folder for downloads |
| Default quality | Best, or a resolution cap (4K down to 480p) |
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
python3 -m pytest -q          # needs yt-dlp, flask and pytest installed
python3 tools/build_app.py    # after ANY change to app code: rebuilds Video Downloader.app
```

The `.app` contains a copy of the code, and a test fails if that copy is out of date.

| Path | Purpose |
|---|---|
| `app.py` | Starts the local server on port 8737 and opens the app window (`--browser` for a browser tab) |
| `vdl/desktop.py` | Mac shell: pywebview window, close-to-hide, menu-bar icon, reopen handling |
| `vdl/downloader.py` | yt-dlp options, video info lookup, download queue and progress |
| `vdl/clipboard.py` | Clipboard watcher and the macOS pop-up prompt |
| `vdl/server.py` | Flask API, restricted to this Mac and to the app's own page |
| `vdl/settings.py` | Settings and history JSON files |
| `static/` | The app's page (HTML, CSS, JS, no build step) |
| `setup.sh` | Finds Python 3.11+ and installs everything into `~/Library/Application Support/Video Downloader/venv` (ready-made packages only) |
| `Video Downloader.app` | The Mac app (built by `tools/build_app.py`; launcher is `tools/launcher.sh`, icon from `tools/make_icon.py`) |
| `start.command` | Troubleshooting launcher that shows messages in Terminal |
