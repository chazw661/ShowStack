#!/bin/bash
# Build "ShowStack Listen.app" (Issue #74) into companion/dist/.
#
#   cd companion && ./build_app.sh
#
# The app is ad-hoc signed only (no Apple Developer ID yet), so on another Mac
# the first launch is right-click → Open. Built for this Mac's architecture.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-venv/bin/python}"
APP="dist/ShowStack Listen.app"

"$PYTHON" -m pip install -q -r requirements.txt -r requirements-app.txt
rm -rf build dist
"$PYTHON" -m PyInstaller --noconfirm --clean ShowStackListen.spec

# arm64 binaries must be signed to run; ad-hoc until a Developer ID exists.
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

(cd dist && ditto -c -k --keepParent "ShowStack Listen.app" "ShowStack-Listen-mac-$(uname -m).zip")

echo
echo "Built: $(pwd)/$APP"
echo "Zip:   $(pwd)/dist/ShowStack-Listen-mac-$(uname -m).zip"
echo "Install: drag the app to /Applications, then open it once (right-click → Open)."
