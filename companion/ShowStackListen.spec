# PyInstaller spec for "ShowStack Listen.app" (Issue #74). Build with ./build_app.sh.
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

import listen_companion

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
    name="ShowStack Listen",
    console=False,
    argv_emulation=False,   # URL events are handled by the app's own Apple Event handler
    codesign_identity=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ShowStack Listen")

app = BUNDLE(
    coll,
    name="ShowStack Listen.app",
    icon=None,
    bundle_identifier="io.showstack.listen",
    version=listen_companion.__version__,
    info_plist={
        "CFBundleName": "ShowStack Listen",
        "CFBundleDisplayName": "ShowStack Listen",
        "CFBundleShortVersionString": listen_companion.__version__,
        "CFBundleVersion": listen_companion.__version__,
        "LSUIElement": True,                     # menu bar only, no Dock icon
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        # Without this macOS silently feeds the app silence from every input.
        "NSMicrophoneUsageDescription":
            "ShowStack Listen captures your audio interface (e.g. Dante Virtual Soundcard) "
            "so A2s can monitor beltpacks on their phones.",
        "CFBundleURLTypes": [{
            "CFBundleURLName": "io.showstack.listen",
            "CFBundleURLSchemes": ["showstack-listen"],
        }],
    },
)
