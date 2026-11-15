#!/bin/zsh
# Independent AppKit helper; no Python or Qt is needed after the main app exits.
set -euo pipefail
cd "${0:A:h:h}"
OUT="${1:-$PWD/dist.nosync/helpers/Deskmate Uninstaller.app}"
mkdir -p "$OUT/Contents/MacOS"
EXTRA=()
# Test binaries cannot touch real preferences, logs or cache.
if [[ "${2:-}" == "--test" ]]; then EXTRA=(-D UNINSTALL_TESTING); fi
xcrun swiftc -O "${EXTRA[@]}" -target arm64-apple-macos12.0 -module-cache-path "${TMPDIR:-/tmp}/deskmate-swift-cache" \
  packaging/Uninstaller.swift -o "$OUT/Contents/MacOS/DeskmateUninstaller" -framework AppKit
cat > "$OUT/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>com.deskmate.companion.uninstaller</string>
<key>CFBundleName</key><string>DeskMates Uninstaller</string>
<key>CFBundleExecutable</key><string>DeskmateUninstaller</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSUIElement</key><true/>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
/usr/bin/xattr -cr "$OUT"
/usr/bin/codesign --force --sign - "$OUT"
