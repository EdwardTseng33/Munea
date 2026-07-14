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
echo "== Build settings =="
if ! xcodebuild \
  -project ios/App/App.xcodeproj \
  -scheme App \
  -showBuildSettings >"$OUTPUT" 2>"$LOG"; then
  echo "FAIL build settings did not resolve."
  echo "Logs: $OUTPUT and $LOG"
  exit 1
fi

echo "PASS build settings resolved: $OUTPUT"
