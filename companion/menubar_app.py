#!/usr/bin/env python3
"""ShowStack Listen — macOS menu bar app for the A2 Listen companion (Issue #74).

Wraps CompanionServer so nobody needs a terminal:

* ShowStack's Mic Tracker → 🎧 Listen Setup → "Start on this Mac" opens
  showstack-listen://start?token=…&api=…, which launches this app (after a
  confirmation) for that show.
* The 🎧 menu shows the show, live source and listener count, and picks the
  audio input.
* HTTPS certificates are automatic (certs.py); "Set up a phone…" shows the
  QR codes to install the certificate and open Listen.

Run from the venv for development:   python menubar_app.py
Packaged as "ShowStack Listen.app" by build_app.sh.
"""

import json
import logging
import logging.handlers
import os
import plistlib
import re
import subprocess
import sys
import threading
import uuid
import webbrowser
from urllib.parse import parse_qs, urlparse

import rumps
from AppKit import NSApp, NSPasteboard, NSPasteboardTypeString
from Foundation import NSAppleEventManager, NSObject

import certs
import listen_companion as lc

APP_NAME = certs.APP_NAME
BUNDLE_ID = "io.showstack.listen"
HTTPS_PORT = 8443
LOCAL_PORT = 8480

# Servers a "Start on this Mac" link may pair with. Loopback is allowed for
# local ShowStack development.
ALLOWED_API_HOSTS = {"showstack.io", "www.showstack.io"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

log = logging.getLogger("listen")


def _fourcc(code):
    return int.from_bytes(code.encode("ascii"), "big")


# ──────────────────────────────────────────────────────────────────
# Config / logging / login item
# ──────────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(certs.support_dir(), "config.json")
LOG_DIR = os.path.expanduser("~/Library/Logs/%s" % APP_NAME)
LOG_PATH = os.path.join(LOG_DIR, "companion.log")
LAUNCH_AGENT = os.path.expanduser("~/Library/LaunchAgents/%s.plist" % BUNDLE_ID)


def load_config():
    try:
        with open(CONFIG_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_config(config):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(config, fh, indent=2)
    os.replace(tmp, CONFIG_PATH)


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # aiortc/aioice are chatty at INFO.
    for name in ("aioice", "aiortc"):
        logging.getLogger(name).setLevel(logging.WARNING)


def app_launch_arguments():
    """How launchd should start this app (bundle or dev venv)."""
    if getattr(sys, "frozen", False):
        # …/ShowStack Listen.app/Contents/MacOS/<exe>
        bundle = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", ".."))
        return ["/usr/bin/open", "-g", bundle]
    return [sys.executable, os.path.abspath(__file__)]


def login_item_enabled():
    return os.path.exists(LAUNCH_AGENT)


def set_login_item(enabled):
    if enabled:
        os.makedirs(os.path.dirname(LAUNCH_AGENT), exist_ok=True)
        with open(LAUNCH_AGENT, "wb") as fh:
            plistlib.dump({
                "Label": BUNDLE_ID,
                "ProgramArguments": app_launch_arguments(),
                "RunAtLoad": True,
                "ProcessType": "Interactive",
            }, fh)
    elif os.path.exists(LAUNCH_AGENT):
        os.remove(LAUNCH_AGENT)


def api_allowed(api):
    try:
        u = urlparse(api)
    except ValueError:
        return False
    if u.path not in ("", "/") or u.query or u.fragment or u.username or u.password:
        return False
    host = (u.hostname or "").lower()
    if u.scheme == "https" and host in ALLOWED_API_HOSTS and u.port in (None, 443):
        return True
    return u.scheme in ("http", "https") and host in LOOPBACK_HOSTS


def valid_token(token):
    try:
        uuid.UUID(token)
        return True
    except (TypeError, ValueError):
        return False


def alert(message, ok=None, cancel=None):
    # Menu bar apps aren't frontmost; bring the dialog forward.
    NSApp.activateIgnoringOtherApps_(True)
    return rumps.alert(APP_NAME, message, ok=ok, cancel=cancel)


def show_row(item, text):
    item.title = text or " "
    item._menuitem.setHidden_(not text)


def copy_to_clipboard(text):
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


# ──────────────────────────────────────────────────────────────────
# showstack-listen:// handler
# ──────────────────────────────────────────────────────────────────

class URLEventHandler(NSObject):
    app = None

    def handleURL_withReply_(self, event, reply):
        url = event.paramDescriptorForKeyword_(_fourcc("----")).stringValue()
        if self.app is not None and url:
            self.app.handle_url(str(url))


# ──────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────

class ListenApp(rumps.App):
    def __init__(self):
        super().__init__(APP_NAME, title="🎧", quit_button=None)
        self.config = load_config()
        self.server = None
        self.state = "stopped"          # stopped | starting | live | lost | error
        self.error = ""
        self._lock = threading.Lock()
        self._device_names = None

        self.show_item = rumps.MenuItem("Not paired with a show")
        self.source_item = rumps.MenuItem("")
        self.listeners_item = rumps.MenuItem("")
        self.input_menu = rumps.MenuItem("Audio Input")
        self.phone_item = rumps.MenuItem("Set up a phone…", callback=self.open_phone_setup)
        self.copy_item = rumps.MenuItem("Copy phone Listen address", callback=self.copy_lan_url)
        self.toggle_item = rumps.MenuItem("Start", callback=self.toggle_server)
        self.login_item = rumps.MenuItem("Open at Login", callback=self.toggle_login)
        self.menu = [
            self.show_item, self.source_item, self.listeners_item, None,
            self.input_menu, None,
            self.phone_item, self.copy_item, None,
            self.toggle_item, self.login_item,
            rumps.MenuItem("Show Log", callback=self.show_log), None,
            rumps.MenuItem("Quit %s" % APP_NAME, callback=self.quit_app),
        ]
        for item in (self.show_item, self.source_item, self.listeners_item):
            item.set_callback(None)
        self.login_item.state = login_item_enabled()

        # Register for showstack-listen:// before the run loop starts so a
        # launch-by-link event isn't missed.
        self._url_handler = URLEventHandler.alloc().init()
        URLEventHandler.app = self
        NSAppleEventManager.sharedAppleEventManager() \
            .setEventHandler_andSelector_forEventClass_andEventID_(
                self._url_handler, "handleURL:withReply:", _fourcc("GURL"), _fourcc("GURL"))

        self._probe = lc.make_probe()
        self.refresh(None)
        rumps.Timer(self.refresh, 2).start()

        if self.config.get("token") and self.config.get("autostart", True):
            self.start_server()

    # ── server lifecycle ─────────────────────────────────────────

    def _choose_default_device(self):
        names = self._input_names()
        dante = [n for n in names if "dante" in n.lower()]
        if len(dante) == 1:
            return dante[0]
        return None

    def instance_id(self):
        """Stable id for this Mac, so ShowStack keeps racks apart across restarts."""
        inst = self.config.get("instance")
        if not inst:
            inst = uuid.uuid4().hex
            self.config["instance"] = inst
            save_config(self.config)
        return inst

    def start_server(self):
        if not self.config.get("token"):
            alert("Not paired with a show yet.\n\nIn ShowStack open Mic Tracker → "
                                  "🎧 Listen Setup and click “Start on this Mac”.")
            return
        if not self.config.get("device"):
            device = self._choose_default_device()
            if device is None:
                self.state, self.error = "error", "Choose an audio input"
                self.refresh(None)
                rumps.notification(APP_NAME, "Choose an audio input",
                                   "Pick the input that carries your beltpacks from the 🎧 menu.")
                return
            self.config["device"] = device
            save_config(self.config)
        self.state, self.error = "starting", ""
        self.refresh(None)
        threading.Thread(target=self._start_worker, daemon=True).start()

    def _start_worker(self):
        with self._lock:
            self._stop_locked()
            cfg = dict(self.config)
            try:
                ssl_ctx, _sans = certs.server_ssl_context()
            except Exception as exc:
                log.warning("HTTPS unavailable (%s) — phones won't be able to connect.", exc)
                ssl_ctx = None
            server = lc.CompanionServer(
                token=cfg["token"], api=cfg["api"], device_name=cfg["device"],
                https_port=HTTPS_PORT, ssl_context=ssl_ctx, local_port=LOCAL_PORT,
                ca_profile=certs.ca_mobileconfig,
                instance=self.instance_id(), client_id=cfg.get("client_id", ""),
            )
            try:
                server.start()
            except lc.PairingError as exc:
                self.state, self.error = "error", "Pairing rejected — start again from ShowStack"
                log.warning("%s", exc)
                return
            except OSError as exc:
                self.state = "error"
                self.error = ("Port %d or %d is already in use" % (HTTPS_PORT, LOCAL_PORT)) \
                    if exc.errno == 48 else str(exc)
                log.warning("Could not start: %s", exc)
                return
            except Exception as exc:
                self.state, self.error = "error", str(exc)
                log.exception("Could not start")
                return
            self.server = server
            self.state = "live"
            show = (server.status() or {}).get("show")
            if show and show != self.config.get("show"):
                self.config["show"] = show
                save_config(self.config)

    def _stop_locked(self):
        if self.server is not None:
            try:
                self.server.stop()
            finally:
                self.server = None

    def stop_server(self):
        with self._lock:
            self._stop_locked()
        self.state, self.error = "stopped", ""
        self.refresh(None)

    # ── link handling ─────────────────────────────────────────────

    def handle_url(self, url):
        log.info("Opened by link: %s", re.sub(r"token=[^&]+", "token=…", url))
        u = urlparse(url)
        params = {k: v[0] for k, v in parse_qs(u.query).items()}
        action = u.netloc or u.path.strip("/")
        if u.scheme != "showstack-listen" or action != "start":
            return
        token, api = params.get("token", ""), params.get("api", "").rstrip("/")
        # Which browser asked. Echoed in the heartbeat so ShowStack can tell
        # this Mac's app from another Mac's at the same show.
        client_id = re.sub(r"[^A-Za-z0-9_-]", "", params.get("client", ""))[:64]
        if not valid_token(token) or not api_allowed(api):
            alert("This start link isn't from ShowStack, so it was ignored.\n\n%s"
                        % (api or "(no server)"))
            return

        if token == self.config.get("token") and api == self.config.get("api"):
            # A different browser (or a re-opened one) may be driving now.
            if client_id and client_id != self.config.get("client_id"):
                self.config["client_id"] = client_id
                save_config(self.config)
                self.stop_server()
                self.start_server()
                return
            if self.server is None:
                self.start_server()
            else:
                rumps.notification(APP_NAME, "Already running",
                                   "Listening for %s" % (self.config.get("show") or "this show"))
            return

        try:
            show, _mapping, _sessions = lc.fetch_mapping(api, token)
        except lc.PairingError:
            alert("ShowStack rejected this show's pairing token.")
            return
        host = urlparse(api).hostname
        running = self.server is not None and self.config.get("show")
        message = "Start A2 Listen for “%s” from %s?\n\nThis Mac will stream its audio input " \
                  "to phones that open this show's Listen link." % (show or "this show", host)
        if running:
            message += "\n\nThis stops Listen for “%s”." % self.config.get("show")
        if alert(message, ok="Start", cancel="Cancel") != 1:
            return
        self.config.update({"token": token, "api": api, "show": show, "autostart": True,
                            "client_id": client_id})
        save_config(self.config)
        self.start_server()

    # ── menu actions ─────────────────────────────────────────────

    def toggle_server(self, _sender):
        if self.server is not None or self.state == "starting":
            self.config["autostart"] = False
            save_config(self.config)
            self.stop_server()
        else:
            self.config["autostart"] = True
            save_config(self.config)
            self.start_server()

    def choose_device(self, sender):
        name = sender.title
        self.config["device"] = name
        save_config(self.config)
        if self.server is not None:
            self.server.set_device(name)
        elif self.config.get("token"):
            self.start_server()
        self.refresh(None)

    def open_phone_setup(self, _sender):
        if self.server is None:
            alert("Start Listen first.")
            return
        webbrowser.open("http://localhost:%d/setup" % LOCAL_PORT)

    def copy_lan_url(self, _sender):
        status = self.server.status() if self.server else None
        if status and status.get("lan_url"):
            copy_to_clipboard(status["lan_url"])
            rumps.notification(APP_NAME, "Copied", status["lan_url"])

    def toggle_login(self, sender):
        set_login_item(not sender.state)
        sender.state = login_item_enabled()

    def show_log(self, _sender):
        subprocess.run(["/usr/bin/open", "-a", "Console", LOG_PATH])

    def quit_app(self, _sender):
        self.stop_server()
        rumps.quit_application()

    # ── periodic refresh ─────────────────────────────────────────

    def _input_names(self):
        if self._probe is not None:
            devices = self._probe.input_devices()
            if devices is not None:
                return sorted(devices)
        return sorted(dev["name"] for _i, dev in lc.input_devices())

    def _rebuild_inputs(self):
        names = self._input_names()
        current = self.config.get("device")
        wanted = names + ([current] if current and current not in names else [])
        if wanted != self._device_names:
            self._device_names = wanted
            if self.input_menu._menu is not None:
                self.input_menu.clear()
            for name in wanted:
                self.input_menu.add(rumps.MenuItem(name, callback=self.choose_device))
        for name, item in self.input_menu.items():
            item.state = (name == current)
        self.input_menu.title = "Audio Input: %s" % (current or "choose…")

    def refresh(self, _timer):
        status = self.server.status() if self.server else None
        if status and self.state in ("live", "lost"):
            self.state = "live" if status.get("source") else "lost"

        if self.config.get("show"):
            self.show_item.title = "Show: %s" % self.config["show"]
        elif self.config.get("token"):
            self.show_item.title = "Show: (paired)"
        else:
            self.show_item.title = "Not paired — use “Start on this Mac” in ShowStack"

        if self.state == "live":
            self.title = "🎧"
            show_row(self.source_item, "Source: %s" % status["source"])
            n = status.get("listeners", 0)
            show_row(self.listeners_item, "Listeners: %d" % n)
        elif self.state == "lost":
            self.title = "🎧⚠︎"
            show_row(self.source_item, "⚠︎ Waiting for “%s”…" % status.get("device"))
            show_row(self.listeners_item, "Listeners: %d" % status.get("listeners", 0))
        elif self.state == "starting":
            self.title = "🎧…"
            show_row(self.source_item, "Starting…")
            show_row(self.listeners_item, "")
        elif self.state == "error":
            self.title = "🎧⚠︎"
            show_row(self.source_item, "⚠︎ %s" % self.error)
            show_row(self.listeners_item, "")
        else:
            self.title = "🎧○"
            show_row(self.source_item, "Stopped")
            show_row(self.listeners_item, "")

        running = self.server is not None
        self.toggle_item.title = "Stop" if running or self.state == "starting" else "Start"
        self.phone_item.set_callback(self.open_phone_setup if running else None)
        self.copy_item.set_callback(
            self.copy_lan_url if running and status and status.get("lan_url") else None)
        self._rebuild_inputs()


def main():
    setup_logging()
    log.info("%s %s starting", APP_NAME, lc.__version__)
    ListenApp().run()


if __name__ == "__main__":
    main()
