"""The Mac app shell: a native window (pywebview, using the same WebKit engine
as Safari) showing the app's local page, plus a menu-bar icon so clipboard
watching keeps going after the window is closed. No browser, no Terminal.

Everything here only runs on macOS; the rest of the app doesn't depend on it.
"""
import inspect
import logging
import os
import subprocess
import threading

log = logging.getLogger("video-downloader")

APP_NAME = "Video Downloader"
ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "icon-512.png")


def available():
    """True if the native window can be used (macOS with pywebview installed)."""
    try:
        from importlib.metadata import version
        if int(version("pywebview").split(".")[0]) < 6:
            log.warning("pywebview %s is too old for the app window", version("pywebview"))
            return False
        import webview  # noqa: F401
        import AppKit  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def notify(text):
    try:
        subprocess.Popen(["osascript", "-e",
                          f'display notification {applescript_string(text)} with title "{APP_NAME}"'])
    except OSError:
        pass


def applescript_string(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


class Desktop:
    def __init__(self, url, store):
        self.url = url
        self.store = store
        self.window = None
        self.status_item = None
        self.watch_item = None
        self._told_about_hiding = False
        self._menu_target = None

    # ------------------------------------------------------------------ start
    def run(self):
        """Blocks until the app quits. Must be called on the main thread."""
        import webview

        self._name_the_app()
        self.window = webview.create_window(
            APP_NAME, self.url, width=920, height=780, min_size=(560, 520),
            background_color="#f6f4f1", text_select=True,
        )
        self.window.events.closing += self._on_closing
        webview.start(self._after_start, gui="cocoa", private_mode=False,
                      storage_path=os.path.join(self.store.dir, "webview"))

    def _name_the_app(self):
        """Python runs this app, so macOS would call it "Python". Rename it
        (menu bar title) and give it the app's own Dock icon."""
        try:
            from Foundation import NSBundle
            bundle = NSBundle.mainBundle()
            for info in (bundle.localizedInfoDictionary(), bundle.infoDictionary()):
                if info is not None:
                    info["CFBundleName"] = APP_NAME
                    info["CFBundleDisplayName"] = APP_NAME
        except Exception:  # noqa: BLE001
            log.exception("couldn't rename the app")

    def _after_start(self):
        """Runs once the window system is up (on a background thread)."""
        from PyObjCTools import AppHelper
        AppHelper.callAfter(self._setup_main_thread)

    def _setup_main_thread(self):
        try:
            from AppKit import NSApplication, NSImage
            if os.path.exists(ICON):
                image = NSImage.alloc().initWithContentsOfFile_(ICON)
                if image is not None:
                    NSApplication.sharedApplication().setApplicationIconImage_(image)
        except Exception:  # noqa: BLE001
            log.exception("couldn't set the Dock icon")
        try:
            self._make_status_item()
        except Exception:  # noqa: BLE001
            log.exception("couldn't add the menu-bar icon")
        try:
            self._handle_reopen()
        except Exception:  # noqa: BLE001
            log.exception("couldn't listen for reopen")

    def _handle_reopen(self):
        """Double-clicking the app (or its Dock icon) while it's already running
        sends a "reopen" event; show the window when that happens."""
        from Foundation import NSAppleEventManager
        global _desktop
        _desktop = self
        if self._menu_target is None:
            self._menu_target = _menu_target_class().alloc().init()

        def fourcc(code):
            return int.from_bytes(code.encode("ascii"), "big")
        NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(
            self._menu_target, "handleReopen:withReplyEvent:", fourcc("aevt"), fourcc("rapp"))

    # ------------------------------------------------------------------ menu bar
    def _make_status_item(self):
        from AppKit import (NSImage, NSMenu, NSMenuItem, NSStatusBar,
                            NSVariableStatusItemLength)

        global _desktop
        _desktop = self
        target = _menu_target_class().alloc().init()
        self._menu_target = target          # keep a strong reference

        item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = item.button()
        image = None
        if hasattr(NSImage, "imageWithSystemSymbolName_accessibilityDescription_"):
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "arrow.down.circle", APP_NAME)
        if image is not None:
            image.setTemplate_(True)        # follows light/dark menu bar
            button.setImage_(image)
        else:
            button.setTitle_("⬇︎")
        button.setToolTip_(APP_NAME)

        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        def add(title, action, key=""):
            mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
            mi.setTarget_(target)
            menu.addItem_(mi)
            return mi

        add(f"Show {APP_NAME}", "show:")
        menu.addItem_(NSMenuItem.separatorItem())
        self.watch_item = add("Watch Clipboard", "toggleWatch:")
        add("Open Downloads Folder", "openFolder:")
        add("Supported Sites…", "supportedSites:")
        menu.addItem_(NSMenuItem.separatorItem())
        add(f"Quit {APP_NAME}", "quit:", "q")
        menu.setDelegate_(target)           # refresh the checkmark each time it opens
        item.setMenu_(menu)
        self.status_item = item
        self._refresh_watch_item()

    def _refresh_watch_item(self):
        if self.watch_item is not None:
            self.watch_item.setState_(1 if self.store.settings.get("watch_clipboard") else 0)

    # ------------------------------------------------------------------ actions
    def show(self):
        """Bring the window back (from the menu bar, a second launch, or a copied link).
        Safe to call from any thread."""
        from PyObjCTools import AppHelper

        def policy():
            from AppKit import NSApplication
            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(0)     # regular app: Dock icon and menus
            app.activateIgnoringOtherApps_(True)
        AppHelper.callAfter(policy)
        if self.window is not None:
            self.window.show()              # pywebview hops to the main thread itself
            self.window.restore()

    def hide(self):
        from PyObjCTools import AppHelper

        def policy():
            from AppKit import NSApplication
            # no Dock icon while hidden; the menu-bar icon stays
            NSApplication.sharedApplication().setActivationPolicy_(1)
        if self.window is not None:
            self.window.hide()
        AppHelper.callAfter(policy)

    def toggle_watch(self):
        self.store.update_settings({"watch_clipboard": not self.store.settings.get("watch_clipboard")})
        self._refresh_watch_item()

    def open_folder(self):
        folder = self.store.settings["save_dir"]
        os.makedirs(folder, exist_ok=True)
        subprocess.Popen(["open", folder])

    def supported_sites(self):
        from .server import LINKS, open_url
        open_url(LINKS["supported_sites"])

    def quit(self):
        os._exit(0)

    def _on_closing(self):
        """Red close button: hide instead of quitting, so the clipboard is still
        watched. Cmd+Q (or Quit in the menu) really quits."""
        if any(f.function == "applicationShouldTerminate_" for f in inspect.stack()):
            return None
        self.hide()
        if not self._told_about_hiding:
            self._told_about_hiding = True
            threading.Timer(0.3, notify, args=(
                "Still watching for copied video links. Use the ⬇ icon in the menu bar to reopen or quit.",)).start()
        return False


_target_cls = None
_desktop = None


def _menu_target_class():
    """NSObject subclass that receives the menu-bar menu's clicks (created
    lazily so importing this module never needs pyobjc)."""
    global _target_cls
    if _target_cls is None:
        import objc
        from Foundation import NSObject

        class VDLMenuTarget(NSObject):
            def show_(self, sender):
                _desktop.show()

            def toggleWatch_(self, sender):
                _desktop.toggle_watch()

            def openFolder_(self, sender):
                _desktop.open_folder()

            def supportedSites_(self, sender):
                _desktop.supported_sites()

            def quit_(self, sender):
                _desktop.quit()

            def menuWillOpen_(self, menu):
                _desktop._refresh_watch_item()

            @objc.typedSelector(b"v@:@@")
            def handleReopen_withReplyEvent_(self, event, reply):
                _desktop.show()

        _target_cls = VDLMenuTarget
    return _target_cls
