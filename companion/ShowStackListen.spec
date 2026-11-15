# PyInstaller spec for "ShowStack Listen.app" (Issue #74). Build with ./build_app.sh.
# -*- mode: python ; coding: utf-8 -*-
#
# LISTEN_BETA=1 builds "ShowStack Listen Beta.app" (io.showstack.listen.beta)
# instead: same code, its own name, and no showstack-listen:// handler, so
# ShowStack's "Start on this Mac" always opens the installed app.

import os

from PyInstaller.utils.hooks import collect_all

import listen_companion

BETA = os.environ.get("LISTEN_BETA") == "1"
NAME = "ShowStack Listen Beta" if BETA else "ShowStack Listen"
BUNDLE_ID = "io.showstack.listen.beta" if BETA else "io.showstack.listen"
# Shown in the beta's menu, so a hotfix can be told from the build it replaces.
BUILD = os.environ.get("LISTEN_BUILD", "")

datas, binaries, hiddenimports = [], [], []
# Packages with native libraries / data PyInstaller can miss on its own.
for package in ("aiortc", "aioice", "av", "pylibsrtp", "sounddevice", "_sounddevice_data",
                "rumps", "qrcode", "cryptography", "google_crc32c", "pyee", "certifi"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ["menubar_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["certs", "listen_companion"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    argv_emulation=False,   # URL events are handled by the app's own Apple Event handler
    codesign_identity=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME)

info_plist = {
    "CFBundleName": NAME,
    "CFBundleDisplayName": NAME,
    "CFBundleShortVersionString": listen_companion.__version__,
    "CFBundleVersion": listen_companion.__version__,
    "LSUIElement": True,                     # menu bar only, no Dock icon
    "LSMinimumSystemVersion": "12.0",
    "NSHighResolutionCapable": True,
    # Without this macOS silently feeds the app silence from every input.
    "NSMicrophoneUsageDescription":
        "ShowStack Listen captures your audio interface (e.g. Dante Virtual Soundcard) "
        "so A2s can monitor beltpacks on their phones.",
}
if BETA:
    info_plist["ShowStackBuild"] = BUILD
else:
    info_plist["CFBundleURLTypes"] = [{
        "CFBundleURLName": "io.showstack.listen",
        "CFBundleURLSchemes": ["showstack-listen"],
    }]

app = BUNDLE(
    coll,
    name=NAME + ".app",
    icon=None,
    bundle_identifier=BUNDLE_ID,
    version=listen_companion.__version__,
    info_plist=info_plist,
)
