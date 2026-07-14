#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD_ROOT="${MUNEA_XCODE_BUILD_ROOT:-/private/tmp/munea-xcode-$UID}"
DERIVED_DATA="$BUILD_ROOT/derived-data-simulator"
SOURCE_PACKAGES="$BUILD_ROOT/source-packages"
APP_PATH="$DERIVED_DATA/Build/Products/Debug-iphonesimulator/App.app"
LOG_PATH="/private/tmp/munea-ios-simulator-build.log"

mkdir -p "$DERIVED_DATA" "$SOURCE_PACKAGES"

echo "== Sync iOS assets =="
"$ROOT/node_modules/.bin/cap" sync ios

echo "== Build iOS Simulator app =="
if ! xcodebuild \
  -project ios/App/App.xcodeproj \
  -scheme App \
  -configuration Debug \
  -sdk iphonesimulator \
  -destination "generic/platform=iOS Simulator" \
  -derivedDataPath "$DERIVED_DATA" \
  -clonedSourcePackagesDirPath "$SOURCE_PACKAGES" \
  CODE_SIGNING_ALLOWED=NO \
  build >"$LOG_PATH" 2>&1; then
  echo "FAIL iOS Simulator build failed."
  echo "Log: $LOG_PATH"
  tail -80 "$LOG_PATH"
  exit 1
fi

test -d "$APP_PATH"
echo "PASS iOS Simulator build succeeded."
echo "App: $APP_PATH"
