"""Builds "Video Downloader.app" at the top of the repo from the source files.

The app is self-contained (it carries its own copy of the code), so it works
wherever it's put, including Applications, and survives macOS moving it to a
temporary place on first open. Its Python environment lives in
~/Library/Application Support/Video Downloader, not inside the app.

Run after changing any app code:  python3 tools/build_app.py
(tests/test_app.py fails if the app's copy is out of date.)
"""
import os
import plistlib
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_NAME = "Video Downloader"
VERSION = "1.3"

# what goes inside the app: (source, destination under Contents/Resources/app)
PAYLOAD = ["app.py", "requirements.txt", "setup.sh", "vdl", "static"]
EXECUTABLE = {"setup.sh"}


def info_plist():
    return {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.kingbuck11.video-downloader",
        "CFBundleExecutable": APP_NAME,
        "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.utilities",
    }


def _ignore(_dir, names):
    return [n for n in names if n == "__pycache__" or n.endswith(".pyc") or n == ".DS_Store"]


def build(dest_root=ROOT):
    app = os.path.join(dest_root, f"{APP_NAME}.app")
    if os.path.exists(app):
        shutil.rmtree(app)
    contents = os.path.join(app, "Contents")
    macos = os.path.join(contents, "MacOS")
    res = os.path.join(contents, "Resources")
    payload = os.path.join(res, "app")
    os.makedirs(macos)
    os.makedirs(payload)

    with open(os.path.join(contents, "Info.plist"), "wb") as f:
        plistlib.dump(info_plist(), f, sort_keys=True)
    with open(os.path.join(contents, "PkgInfo"), "w") as f:
        f.write("APPL????")

    launcher = os.path.join(macos, APP_NAME)
    shutil.copyfile(os.path.join(ROOT, "tools", "launcher.sh"), launcher)
    os.chmod(launcher, 0o755)
    shutil.copyfile(os.path.join(ROOT, "tools", "AppIcon.icns"), os.path.join(res, "AppIcon.icns"))

    for item in PAYLOAD:
        src, dst = os.path.join(ROOT, item), os.path.join(payload, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=_ignore)
        else:
            shutil.copyfile(src, dst)
            os.chmod(dst, 0o755 if item in EXECUTABLE else 0o644)
    return app


if __name__ == "__main__":
    out = build(sys.argv[1] if len(sys.argv) > 1 else ROOT)
    print("built", out)
