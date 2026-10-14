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
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import rumps
from AppKit import NSApp, NSPasteboard, NSPasteboardTypeString
from Foundation import NSAppleEventManager, NSBundle, NSObject

import certs
import listen_companion as lc

def _bundle_info(key):
    try:
        value = NSBundle.mainBundle().objectForInfoDictionaryKey_(key)
        return str(value) if value is not None else ""
    except Exception:
        return ""


# "ShowStack Listen Beta.app" (io.showstack.listen.beta) shares the installed
# app's certificates and config — so phones already trust it and it starts on
# the same show — but has its own name, login item and log. Both use the same
# ports, so only one of the two can run at a time.
BETA = _bundle_info("CFBundleIdentifier").endswith(".beta")
APP_NAME = certs.APP_NAME                       # support folder: shared
DISPLAY_NAME = APP_NAME + (" Beta" if BETA else "")
BUNDLE_ID = "io.showstack.listen" + (".beta" if BETA else "")
BUILD = _bundle_info("ShowStackBuild") if BETA else ""
ICON = "🎧β" if BETA else "🎧"
DEFAULT_API = "https://showstack.io"
# Beta only: "Test signal" swaps the input for --simulate's fake show, for a
# home test with no Dante. Held in memory, never saved, so a relaunch is
# always back on the real input.
SIMULATE_CHANNELS = 24
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
LOG_DIR = os.path.expanduser("~/Library/Logs/%s" % DISPLAY_NAME)
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


# The beta's first launch copies the shared settings folder (certificates +
# config) here before touching it, so the installed app's exact state can be
# put back. Only ever made once; never overwritten.
BETA_BACKUP_DIR = os.path.expanduser(
    "~/Library/Application Support/%s (before beta)" % APP_NAME)


def backup_settings_before_beta():
    if not BETA or os.path.exists(BETA_BACKUP_DIR):
        return
    src = certs.support_dir()
    if not any(os.path.exists(os.path.join(src, f)) for f in ("config.json", "ca.pem")):
        return                          # nothing installed before the beta
    try:
        shutil.copytree(src, BETA_BACKUP_DIR)   # copy2: keeps the keys' 0600 mode
        log.info("Backed up settings to %s", BETA_BACKUP_DIR)
    except OSError as exc:
        log.warning("Could not back up settings (%s)", exc)


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


def server_label(api):
    """How a server reads in the menu and dialogs: "showstack.io", "localhost:8000"."""
    u = urlparse(api or DEFAULT_API)
    host = (u.hostname or "").lower()
    if host in ALLOWED_API_HOSTS:
        return host
    return "%s:%s" % (host, u.port) if u.port else host


def parse_pairing(text):
    """(token, api) from what was pasted into "Pair with a show…".

    Takes a bare token, a showstack-listen://start link (its api= is the
    server), or Listen Setup's whole terminal command (--token and --api).
    api is "" when the paste doesn't name a server. An https Listen page
    address points at a rack Mac, not at ShowStack, so only its token counts.
    """
    text = (text or "").strip()
    flags = dict(re.findall(r"--(token|api)[\s=]+['\"]?([^\s'\"\\]+)", text))
    if flags.get("token"):
        return flags["token"], flags.get("api", "").rstrip("/")
    if "://" in text:
        params = {k: v[0] for k, v in parse_qs(urlparse(text).query).items()}
        api = params.get("api", "") if text.startswith("showstack-listen:") else ""
        return params.get("token", ""), api.rstrip("/")
    return text, ""


def valid_token(token):
    try:
        uuid.UUID(token)
        return True
    except (TypeError, ValueError):
        return False


def alert(message, ok=None, cancel=None):
    # Menu bar apps aren't frontmost; bring the dialog forward.
    NSApp.activateIgnoringOtherApps_(True)
    return rumps.alert(DISPLAY_NAME, message, ok=ok, cancel=cancel)


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
        super().__init__(DISPLAY_NAME, title=ICON, quit_button=None)
        self.config = load_config()
        self.server = None
        self.state = "stopped"          # stopped | starting | live | lost | error
        self.error = ""
        self._lock = threading.Lock()
        self._device_names = None
        self.simulate = 0
        self.pair_api = DEFAULT_API     # server for pasted tokens; memory only

        self.show_item = rumps.MenuItem("Not paired with a show")
        self.source_item = rumps.MenuItem("")
        self.listeners_item = rumps.MenuItem("")
        self.input_menu = rumps.MenuItem("Audio Input")
        self.phone_item = rumps.MenuItem("Set up a phone…", callback=self.open_phone_setup)
        self.copy_item = rumps.MenuItem("Copy phone Listen address", callback=self.copy_lan_url)
        self.toggle_item = rumps.MenuItem("Start", callback=self.toggle_server)
        self.pair_item = rumps.MenuItem("Pair with a show…", callback=self.pair_by_token)
        self.sim_row = rumps.MenuItem("Test signal warning")   # unique key; hidden until on
        self.sim_item = rumps.MenuItem("Test signal (simulated %d ch)" % SIMULATE_CHANNELS,
                                       callback=self.toggle_simulate)
        self.login_item = rumps.MenuItem("Open at Login", callback=self.toggle_login)
        self.server_item = rumps.MenuItem("Advanced: server…", callback=self.choose_server)
        self.menu = [
            self.show_item, self.source_item, self.listeners_item, None,
            self.input_menu, None,
            self.phone_item, self.copy_item, None,
            self.toggle_item, self.pair_item, self.server_item, self.login_item,
            rumps.MenuItem("Show Log", callback=self.show_log), None,
            rumps.MenuItem("Quit %s" % DISPLAY_NAME, callback=self.quit_app),
        ]
        if BETA:
            self.build_item = rumps.MenuItem("Beta %s · build %s" % (lc.__version__, BUILD or "?"))
            self.menu.insert_before(self.show_item.title, self.build_item)
            self.build_item.set_callback(None)
            self.menu.insert_after(self.build_item.title, self.sim_row)
            self.sim_row.set_callback(None)
            self.menu.insert_after(self.input_menu.title, self.sim_item)
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
                  "🎧 Listen Setup and click “Start on this Mac”, or use "
                  "%s → Pair with a show…" % ICON)
            return
        if not self.config.get("device") and not self.simulate:
            device = self._choose_default_device()
            if device is None:
                self.state, self.error = "error", "Choose an audio input"
                self.refresh(None)
                rumps.notification(DISPLAY_NAME, "Choose an audio input",
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
                simulate=self.simulate,
            )
            try:
                server.start()
            except lc.PairingError as exc:
                self.state, self.error = "error", "Pairing rejected by %s — pair again" \
                    % server_label(cfg["api"])
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
                rumps.notification(DISPLAY_NAME, "Already running",
                                   "Listening for %s" % (self.config.get("show") or "this show"))
            return

        host = server_label(api)
        try:
            # strict: an unreachable server must not look like a good pairing.
            show, _mapping, _sessions = lc.fetch_mapping(api, token, strict=True)
        except lc.PairingError:
            alert("%s rejected this show token.\n\nChecked with %s. If the token "
                  "is from a different server, use %s → Advanced: server…"
                  % (host, api, ICON))
            return
        except lc.MappingUnavailable as exc:
            alert("Couldn't check the token with %s.\n\n%s" % (host, exc))
            return
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

    def pair_by_token(self, _sender):
        """Pair by pasting the show token — the same path as a Start link."""
        NSApp.activateIgnoringOtherApps_(True)
        response = rumps.Window(
            "Checking with %s.\n\nPaste the show token from ShowStack → Mic Tracker → "
            "🎧 Listen Setup → Advanced (the --token value, or the whole command). "
            "For another server, use %s → Advanced: server…"
            % (server_label(self.pair_api), ICON),
            title="%s — pair with a show" % DISPLAY_NAME,
            default_text="", ok="Pair", cancel="Cancel", dimensions=(320, 24),
        ).run()
        if response.clicked != 1 or not (response.text or "").strip():
            return
        token, api = parse_pairing(response.text)
        if not valid_token(token):
            alert("That doesn't look like a show token.")
            return
        # A paste that names its server wins; a bare token goes to the
        # chosen server, which is showstack.io unless changed for this run.
        api = api or self.pair_api
        self.handle_url("showstack-listen://start?" + urlencode({"token": token, "api": api}))

    def choose_server(self, _sender):
        """Advanced: pair with a local ShowStack. Held in memory only, so the
        next launch pairs with showstack.io again."""
        NSApp.activateIgnoringOtherApps_(True)
        response = rumps.Window(
            "Server that “Pair with a show…” checks tokens with. Leave it as "
            "%s for real shows; use e.g. http://127.0.0.1:8000 only for local "
            "ShowStack development. Back to %s on the next launch."
            % (server_label(DEFAULT_API), server_label(DEFAULT_API)),
            title="%s — server" % DISPLAY_NAME,
            default_text=self.pair_api, ok="Use", cancel="Cancel", dimensions=(320, 24),
        ).run()
        if response.clicked != 1:
            return
        api = (response.text or "").strip().rstrip("/") or DEFAULT_API
        if "://" not in api:
            api = "https://" + api
        if not api_allowed(api):
            alert("Only showstack.io or this Mac (localhost / 127.0.0.1) can be used.")
            return
        self.pair_api = api
        log.info("Pairing server: %s", api)
        self.refresh(None)

    def toggle_server(self, _sender):
        if self.server is not None or self.state == "starting":
            self.config["autostart"] = False
            save_config(self.config)
            self.stop_server()
        else:
            self.config["autostart"] = True
            save_config(self.config)
            self.start_server()

    def toggle_simulate(self, _sender):
        self.simulate = 0 if self.simulate else SIMULATE_CHANNELS
        log.info("Test signal %s", "ON (simulated %d ch)" % self.simulate if self.simulate
                 else "off — back to live input")
        self.stop_server()
        self.start_server()

    def choose_device(self, sender):
        name = sender.title
        self.config["device"] = name
        save_config(self.config)
        if self.simulate:               # picking a real input ends the test signal
            self.toggle_simulate(None)
            return
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
            rumps.notification(DISPLAY_NAME, "Copied", status["lan_url"])

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

        self.server_item.title = "Advanced: server…" if self.pair_api == DEFAULT_API \
            else "Advanced: server — %s" % server_label(self.pair_api)
        # Name the server when it isn't showstack.io, so a show paired with a
        # local test server can't pass for the real one.
        saved = self.config.get("api") or DEFAULT_API
        where = "" if server_label(saved) == server_label(DEFAULT_API) \
            else " (%s)" % server_label(saved)
        if self.config.get("show"):
            self.show_item.title = "Show: %s%s" % (self.config["show"], where)
        elif self.config.get("token"):
            self.show_item.title = "Show: (paired)%s" % where
        else:
            self.show_item.title = "Not paired — use “Start on this Mac” in ShowStack"

        if self.state == "live":
            self.title = ICON
            show_row(self.source_item, "Source: %s" % status["source"])
            n = status.get("listeners", 0)
            show_row(self.listeners_item, "Listeners: %d" % n)
        elif self.state == "lost":
            self.title = ICON + "⚠︎"
            show_row(self.source_item, "⚠︎ Waiting for “%s”…" % status.get("device"))
            show_row(self.listeners_item, "Listeners: %d" % status.get("listeners", 0))
        elif self.state == "starting":
            self.title = ICON + "…"
            show_row(self.source_item, "Starting…")
            show_row(self.listeners_item, "")
        elif self.state == "error":
            self.title = ICON + "⚠︎"
            show_row(self.source_item, "⚠︎ %s" % self.error)
            show_row(self.listeners_item, "")
        else:
            self.title = ICON + "○"
            show_row(self.source_item, "Stopped")
            show_row(self.listeners_item, "")

        if self.simulate:
            # Never mistakable for the real show: marked in the menu bar itself.
            self.title = self.title + " TEST"
            show_row(self.sim_row, "⚠︎ TEST SIGNAL — not live audio")
        else:
            show_row(self.sim_row, "")
        self.sim_item.title = ("Back to live input" if self.simulate
                               else "Test signal (simulated %d ch)" % SIMULATE_CHANNELS)

        running = self.server is not None
        self.toggle_item.title = "Stop" if running or self.state == "starting" else "Start"
        self.phone_item.set_callback(self.open_phone_setup if running else None)
        self.copy_item.set_callback(
            self.copy_lan_url if running and status and status.get("lan_url") else None)
        self._rebuild_inputs()


def main():
    setup_logging()
    log.info("%s %s starting%s", DISPLAY_NAME, lc.__version__, (" (build %s)" % BUILD) if BUILD else "")
    backup_settings_before_beta()       # before ListenApp reads or writes config
    ListenApp().run()


if __name__ == "__main__":
    main()
