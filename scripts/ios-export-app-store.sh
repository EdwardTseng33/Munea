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
ARCHIVE_APP_PATH="$ARCHIVE_PATH/Products/Applications/App.app"
AUTH_CONFIG_PATH="$APP_PATH/public/src/auth-config.js"
PRIVACY_MANIFEST_PATH="$APP_PATH/PrivacyInfo.xcprivacy"
PRIVACY_DATA_TYPE_COUNT="$(plutil -extract NSPrivacyCollectedDataTypes raw "$PRIVACY_MANIFEST_PATH" 2>/dev/null || echo 0)"

codesign --verify --deep --strict "$APP_PATH"
ENTITLEMENTS="$(codesign -d --entitlements - "$APP_PATH" 2>&1)"

EXPECTED_VERSION="$(node -p "require('./package.json').version")"
EXPECTED_BUILD="$(plutil -extract CFBundleVersion raw "$ARCHIVE_APP_PATH/Info.plist")"
ACTUAL_VERSION="$(plutil -extract CFBundleShortVersionString raw "$APP_PATH/Info.plist")"
ACTUAL_BUILD="$(plutil -extract CFBundleVersion raw "$APP_PATH/Info.plist")"
ACTUAL_BUNDLE_ID="$(plutil -extract CFBundleIdentifier raw "$APP_PATH/Info.plist")"
CAMERA_USAGE="$(plutil -extract NSCameraUsageDescription raw "$APP_PATH/Info.plist")"
PHOTO_USAGE="$(plutil -extract NSPhotoLibraryUsageDescription raw "$APP_PATH/Info.plist")"
GOOGLE_IOS_CLIENT_ID="$(plutil -extract GIDClientID raw "$APP_PATH/Info.plist" 2>/dev/null || true)"
GOOGLE_SERVER_CLIENT_ID="$(plutil -extract GIDServerClientID raw "$APP_PATH/Info.plist" 2>/dev/null || true)"
GOOGLE_URL_TYPES="$(plutil -extract CFBundleURLTypes xml1 -o - "$APP_PATH/Info.plist" 2>/dev/null || true)"
DEVICE_FAMILIES="$(plutil -extract UIDeviceFamily json -o - "$APP_PATH/Info.plist" 2>/dev/null || true)"

if [ ! -f "$AUTH_CONFIG_PATH" ] \
  || grep -q 'MUNEA_IOS_DEVELOPMENT_PROFILE_START' "$AUTH_CONFIG_PATH" \
  || ! grep -Eq 'enabled:[[:space:]]*false' "$AUTH_CONFIG_PATH" \
  || ! grep -Eq 'autoSignIn:[[:space:]]*false' "$AUTH_CONFIG_PATH" \
  || ! grep -Eq 'seedFixtures:[[:space:]]*false' "$AUTH_CONFIG_PATH" \
  || ! grep -Eq 'bypassCallControl:[[:space:]]*false' "$AUTH_CONFIG_PATH"; then
  echo "FAIL development account or fixtures leaked into the App Store IPA."
  exit 1
fi

if ! cmp -s "$ROOT/web/index.html" "$APP_PATH/public/index.html" \
  || ! cmp -s "$ROOT/web/src/app.js" "$APP_PATH/public/src/app.js" \
  || ! cmp -s "$ROOT/web/src/auth.js" "$APP_PATH/public/src/auth.js" \
  || ! cmp -s "$ROOT/web/src/auth-config.js" "$AUTH_CONFIG_PATH" \
  || ! cmp -s "$ROOT/web/src/styles.css" "$APP_PATH/public/src/styles.css"; then
  echo "FAIL exported IPA does not contain the latest Web design assets."
  exit 1
fi

if ! grep -Fq 'fespbkdwafueyonppzwq' "$AUTH_CONFIG_PATH" \
  || grep -Fq 'uhmpmystjjdqqxlpsthc' "$AUTH_CONFIG_PATH"; then
  echo "FAIL exported IPA auth configuration is not pinned to Tokyo Supabase."
  exit 1
fi

if [ ! -f "$PRIVACY_MANIFEST_PATH" ] \
  || [ "$(plutil -extract NSPrivacyTracking raw "$PRIVACY_MANIFEST_PATH")" != "false" ] \
  || [ "${PRIVACY_DATA_TYPE_COUNT:-0}" -lt 1 ]; then
  echo "FAIL exported IPA is missing a valid PrivacyInfo.xcprivacy manifest."
  exit 1
fi

if [[ ! "$GOOGLE_IOS_CLIENT_ID" =~ ^491603544409-[a-z0-9]+\.apps\.googleusercontent\.com$ ]] \
  || [ "$GOOGLE_SERVER_CLIENT_ID" != "491603544409-u0bl2ij69mh1m4buhmsuato5d2p5rtua.apps.googleusercontent.com" ]; then
  echo "FAIL exported IPA is missing the production Google iOS/server client IDs."
  exit 1
fi

GOOGLE_REVERSED_CLIENT_ID="com.googleusercontent.apps.${GOOGLE_IOS_CLIENT_ID%.apps.googleusercontent.com}"
if ! grep -Fq "$GOOGLE_REVERSED_CLIENT_ID" <<<"$GOOGLE_URL_TYPES"; then
  echo "FAIL exported IPA is missing the Google Sign-In callback URL scheme."
  exit 1
fi

if [ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ] \
  || [ "$ACTUAL_BUILD" != "$EXPECTED_BUILD" ] \
  || [ "$ACTUAL_BUNDLE_ID" != "net.munea.app" ] \
  || [ -z "$CAMERA_USAGE" ] \
  || [ -z "$PHOTO_USAGE" ] \
  || ! grep -q 'com.apple.developer.healthkit' <<<"$ENTITLEMENTS" \
  || ! grep -q 'com.apple.developer.applesignin' <<<"$ENTITLEMENTS"; then
  echo "FAIL exported IPA metadata, privacy usage strings, or entitlements are incorrect."
  exit 1
fi

if [ "$DEVICE_FAMILIES" != '[1]' ]; then
  echo "FAIL exported IPA must support iPhone only; UIDeviceFamily=$DEVICE_FAMILIES"
  exit 1
fi

echo "PASS IPA excludes development fixtures and contains the latest Web and authentication assets."
echo "PASS IPA contains the non-tracking privacy manifest and collected-data declarations."
echo "PASS IPA signature, version/build, bundle id, privacy usage strings, HealthKit, and Apple sign-in entitlement verified."
echo "PASS IPA supports iPhone only."
echo "PASS App Store package exported."
echo "Output: $FINAL_EXPORT_PATH"
