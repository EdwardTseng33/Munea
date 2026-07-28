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
BUILD_IDENTITY_PATH="$ROOT/ios/App/App/public/src/build-identity.json"

mkdir -p "$DERIVED_DATA" "$SOURCE_PACKAGES" "$(dirname "$ARCHIVE_PATH")"

if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
  echo "FAIL iOS archive requires a clean committed worktree."
  exit 1
fi
RELEASE_COMMIT="$(git rev-parse HEAD)"
if [[ ! "$RELEASE_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "FAIL iOS archive could not resolve an exact 40-character source commit."
  exit 1
fi

echo "== Check declared Capacitor parts exist in node_modules =="
bash "$ROOT/scripts/ios-capacitor-parts-check.sh" pre-sync

echo "== Sync iOS assets =="
"$ROOT/node_modules/.bin/cap" sync ios

if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
  echo "FAIL cap sync changed tracked source; commit the generated changes before archiving."
  exit 1
fi

echo "== Embed exact App build identity =="
node "$ROOT/scripts/ios-build-identity.js" \
  --write \
  --commit "$RELEASE_COMMIT" \
  --output "$BUILD_IDENTITY_PATH"

echo "== Check native parts survived cap sync =="
bash "$ROOT/scripts/ios-capacitor-parts-check.sh" post-sync

echo "== Remove non-App web tools from the iOS bundle =="
for relative_path in \
  "admin.html" \
  "flashhead-live-test.html" \
  "src/admin.js" \
  "src/admin.css"; do
  rm -f "$ROOT/ios/App/App/public/$relative_path"
done

for relative_path in \
  "admin.html" \
  "flashhead-live-test.html" \
  "src/admin.js" \
  "src/admin.css"; do
  if [ -e "$ROOT/ios/App/App/public/$relative_path" ]; then
    echo "FAIL non-App web tool remained in the iOS bundle: $relative_path"
    exit 1
  fi
done
echo "PASS cloud admin and FlashHead test assets excluded from the iOS bundle."

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
