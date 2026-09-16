#!/bin/bash
# Build "ShowStack Listen.app" (Issue #74) into companion/dist/.
#
#   cd companion && ./build_app.sh
#
# Signing:
#   * Default: ad-hoc signed — runs on this Mac; elsewhere needs right-click → Open.
#   * Distribution: set SIGN_IDENTITY (and NOTARY_PROFILE to notarize + staple):
#
#       SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
#       NOTARY_PROFILE=showstack-notary ./build_app.sh
#
#     NOTARY_PROFILE is a keychain profile made once with
#       xcrun notarytool store-credentials showstack-notary --apple-id <id> --team-id <TEAMID>
#
# Built for this Mac's architecture.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-venv/bin/python}"
APP="dist/ShowStack Listen.app"
ZIP="dist/ShowStack-Listen-mac-$(uname -m).zip"
SIGN_IDENTITY="${SIGN_IDENTITY:-}"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"

"$PYTHON" -m pip install -q -r requirements.txt -r requirements-app.txt
rm -rf build dist
"$PYTHON" -m PyInstaller --noconfirm --clean ShowStackListen.spec

if [[ -z "$SIGN_IDENTITY" ]]; then
    # arm64 binaries must be signed to run; ad-hoc until a Developer ID is used.
    codesign --force --deep --sign - "$APP"
else
    echo "Signing with: $SIGN_IDENTITY"
    sign() {
        codesign --force --timestamp --options runtime --sign "$SIGN_IDENTITY" "$@"
    }
    # Inside-out: every nested Mach-O first, then the main executable with the
    # entitlements, then the bundle itself. (--deep is not used for real signing.)
    while IFS= read -r -d '' f; do
        if file -b "$f" | grep -q "Mach-O"; then
            sign "$f"
        fi
    done < <(find "$APP/Contents" -type f ! -path "*/Contents/MacOS/ShowStack Listen" -print0)
    sign --entitlements entitlements.plist "$APP/Contents/MacOS/ShowStack Listen"
    sign --entitlements entitlements.plist "$APP"
fi
codesign --verify --deep --strict --verbose=1 "$APP"

rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"

if [[ -n "$SIGN_IDENTITY" && -n "$NOTARY_PROFILE" ]]; then
    echo "Submitting for notarization (usually a few minutes)…"
    xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$APP"
    xcrun stapler validate "$APP"
    # Re-zip so the download carries the stapled ticket (works offline).
    rm -f "$ZIP"
    ditto -c -k --keepParent "$APP" "$ZIP"
    spctl --assess --type execute --verbose=2 "$APP"
fi

echo
echo "Built: $(pwd)/$APP"
echo "Zip:   $(pwd)/$ZIP"
if [[ -n "$SIGN_IDENTITY" && -n "$NOTARY_PROFILE" ]]; then
    echo "Signed + notarized: opens normally on any Mac ($(uname -m))."
else
    echo "Not notarized: on another Mac, open it the first time with right-click → Open."
fi
