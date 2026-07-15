#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUTPUT="/private/tmp/munea-xcode-build-settings.txt"
LOG="/private/tmp/munea-xcode-native-check.log"

echo "== Xcode =="
xcodebuild -version
xcode-select -p

echo
echo "== Capacitor iOS project =="
test -d ios/App
test -f ios/App/App.xcodeproj/project.pbxproj
test -f ios/App/App/Info.plist

echo
echo "== Packaged authentication config =="
AUTH_CONFIG="web/src/auth-config.js"
test -f "$AUTH_CONFIG"
grep -q "window.MUNEA_SUPABASE_CONFIG" "$AUTH_CONFIG"
grep -q "https://.*\.supabase\.co" "$AUTH_CONFIG"
grep -q "sb_publishable_" "$AUTH_CONFIG"
if grep -Eqi "service[_-]?role|SUPABASE_SERVICE_ROLE_KEY|YOUR_PROJECT_REF|YOUR_SUPABASE" "$AUTH_CONFIG"; then
  echo "FAIL auth config contains a server-only or placeholder value."
  exit 1
fi
echo "PASS public Supabase auth config is present and contains no service-role key."

echo
echo "== Build settings =="
if ! xcodebuild \
  -project ios/App/App.xcodeproj \
  -scheme App \
  -showBuildSettings >"$OUTPUT" 2>"$LOG"; then
  echo "FAIL build settings did not resolve."
  echo "Logs: $OUTPUT and $LOG"
  exit 1
fi

if ! grep -Eq '^[[:space:]]*TARGETED_DEVICE_FAMILY = 1$' "$OUTPUT"; then
  echo "FAIL Xcode target must support iPhone only (TARGETED_DEVICE_FAMILY = 1)."
  exit 1
fi

echo "PASS build settings resolved: $OUTPUT"
echo "PASS Xcode target supports iPhone only."
