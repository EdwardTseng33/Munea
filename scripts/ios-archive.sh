#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TEAM_ID="${MUNEA_APPLE_TEAM_ID:-V77L5245MR}"
BUILD_ROOT="${MUNEA_XCODE_BUILD_ROOT:-/private/tmp/munea-xcode-$UID}"
DERIVED_DATA="$BUILD_ROOT/derived-data-release"
SOURCE_PACKAGES="$BUILD_ROOT/source-packages"
ARCHIVE_PATH="$BUILD_ROOT/archives/Munea.xcarchive"
LOG_PATH="/private/tmp/munea-ios-archive.log"

mkdir -p "$DERIVED_DATA" "$SOURCE_PACKAGES" "$(dirname "$ARCHIVE_PATH")"

echo "== Sync iOS assets =="
"$ROOT/node_modules/.bin/cap" sync ios

# Finder and cloud-provider metadata can invalidate Apple code signatures.
xattr -cr "$ROOT/ios/App/App"
rm -rf "$ARCHIVE_PATH"

echo "== Create signed App Store archive =="
if ! xcodebuild \
  -project ios/App/App.xcodeproj \
  -scheme App \
  -configuration Release \
  -destination "generic/platform=iOS" \
  -archivePath "$ARCHIVE_PATH" \
  -derivedDataPath "$DERIVED_DATA" \
  -clonedSourcePackagesDirPath "$SOURCE_PACKAGES" \
  -allowProvisioningUpdates \
  DEVELOPMENT_TEAM="$TEAM_ID" \
  CODE_SIGN_STYLE=Automatic \
  archive >"$LOG_PATH" 2>&1; then
  echo "FAIL iOS archive failed."
  echo "Log: $LOG_PATH"
  grep -E "error:|CodeSign|ARCHIVE FAILED|No profiles|requires a provisioning profile|resource fork" "$LOG_PATH" | tail -30 || true
  exit 1
fi

test -d "$ARCHIVE_PATH"
echo "PASS signed iOS archive created."
echo "Archive: $ARCHIVE_PATH"
