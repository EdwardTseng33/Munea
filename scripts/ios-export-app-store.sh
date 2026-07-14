#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD_ROOT="${MUNEA_XCODE_BUILD_ROOT:-/private/tmp/munea-xcode-$UID}"
ARCHIVE_PATH="$BUILD_ROOT/archives/Munea.xcarchive"
EXPORT_PATH="$BUILD_ROOT/exports/$(date +%Y%m%d-%H%M%S)"
FINAL_EXPORT_PATH="$ROOT/.tools/xcode-exports/app-store"
OPTIONS_PATH="$ROOT/scripts/ios-export-options.plist"
LOG_PATH="/private/tmp/munea-ios-export.log"

if [ ! -d "$ARCHIVE_PATH" ]; then
  echo "FAIL archive does not exist. Run npm run ios:archive first."
  exit 1
fi

mkdir -p "$EXPORT_PATH" "$FINAL_EXPORT_PATH"

echo "== Export App Store package =="
if ! xcodebuild \
  -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_PATH" \
  -exportOptionsPlist "$OPTIONS_PATH" \
  -allowProvisioningUpdates >"$LOG_PATH" 2>&1; then
  echo "FAIL App Store export failed."
  echo "Log: $LOG_PATH"
  grep -E "error:|EXPORT FAILED|No profiles|certificate|provisioning" "$LOG_PATH" | tail -30 || true
  exit 1
fi

find "$EXPORT_PATH" -maxdepth 1 -name '*.ipa' -exec cp -f {} "$FINAL_EXPORT_PATH/" \;

IPA_PATH="$(find "$FINAL_EXPORT_PATH" -maxdepth 1 -name '*.ipa' -print -quit)"
if [ -z "$IPA_PATH" ]; then
  echo "FAIL export completed without an IPA."
  exit 1
fi

VERIFY_DIR="$(mktemp -d /private/tmp/munea-ipa-verify.XXXXXX)"
trap 'rm -rf "$VERIFY_DIR"' EXIT
ditto -x -k "$IPA_PATH" "$VERIFY_DIR"
APP_PATH="$VERIFY_DIR/Payload/App.app"

codesign --verify --deep --strict "$APP_PATH"
ENTITLEMENTS="$(codesign -d --entitlements :- "$APP_PATH" 2>&1)"

EXPECTED_VERSION="$(node -p "require('./package.json').version")"
ACTUAL_VERSION="$(plutil -extract CFBundleShortVersionString raw "$APP_PATH/Info.plist")"
ACTUAL_BUNDLE_ID="$(plutil -extract CFBundleIdentifier raw "$APP_PATH/Info.plist")"

if [ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ] || [ "$ACTUAL_BUNDLE_ID" != "net.munea.app" ] || ! grep -q '<key>com.apple.developer.healthkit</key><true/>' <<<"$ENTITLEMENTS"; then
  echo "FAIL exported IPA metadata or HealthKit entitlement is incorrect."
  exit 1
fi

echo "PASS IPA signature, version, bundle id, and HealthKit entitlement verified."
echo "PASS App Store package exported."
echo "Output: $FINAL_EXPORT_PATH"
