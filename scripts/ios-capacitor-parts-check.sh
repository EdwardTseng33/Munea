#!/usr/bin/env bash
set -euo pipefail

# Declared Capacitor parts vs actually packaged parts.
#
# Background (2026-07-16, Build 31): the packaging machine skipped npm install,
# node_modules was missing @capacitor/app and @capacitor/browser, and cap sync
# silently removed both native parts from CapApp-SPM/Package.swift. The IPA
# shipped without them and still passed every existing export check.
#
# Stage "pre-sync":  every @capacitor/* package declared in package.json must
#                    exist in node_modules, otherwise cap sync silently drops it.
# Stage "post-sync": every runtime @capacitor/* plugin must keep its package
#                    entry in ios/App/CapApp-SPM/Package.swift after cap sync.
# Default "all" runs both stages.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAGE="${1:-all}"
case "$STAGE" in
  pre-sync|post-sync|all) ;;
  *)
    echo "FAIL unknown stage '$STAGE' (use pre-sync, post-sync, or all)."
    exit 1
    ;;
esac

PACKAGE_SWIFT="ios/App/CapApp-SPM/Package.swift"

# Platform and tooling packages that never appear as path entries in Package.swift.
NON_PLUGIN_PARTS="core cli ios android"

# Android-only plugins (2026-11-20): kept out of iOS on purpose via capacitor.config.json
# ios.includePlugins. iOS keeps its own native NotifyPlugin for local reminders; the official
# local-notifications plugin would compete for the iOS notification delegate.
# Any runtime plugin that is neither here nor in ios.includePlugins fails the check, so a new
# plugin cannot be silently left out of the iOS build by the allowlist.
ANDROID_ONLY_PARTS="local-notifications"

ALL_PARTS="$(node -p "
  const pkg = require('./package.json');
  Object.keys({ ...pkg.dependencies, ...pkg.devDependencies })
    .filter((name) => name.startsWith('@capacitor/'))
    .map((name) => name.slice('@capacitor/'.length))
    .sort()
    .join(' ')
")"

PLUGIN_PARTS="$(node -p "
  const pkg = require('./package.json');
  const nonPlugins = new Set('$NON_PLUGIN_PARTS'.split(' '));
  const androidOnly = new Set('$ANDROID_ONLY_PARTS'.split(' '));
  Object.keys(pkg.dependencies || {})
    .filter((name) => name.startsWith('@capacitor/'))
    .map((name) => name.slice('@capacitor/'.length))
    .filter((name) => !nonPlugins.has(name) && !androidOnly.has(name))
    .sort()
    .join(' ')
")"

# Runtime plugins missing from ios.includePlugins (when the allowlist exists) and not Android-only.
IOS_ALLOWLIST_GAPS="$(node -p "
  const pkg = require('./package.json');
  const config = require('./capacitor.config.json');
  const allow = config.ios && Array.isArray(config.ios.includePlugins) ? new Set(config.ios.includePlugins) : null;
  const nonPlugins = new Set('$NON_PLUGIN_PARTS'.split(' '));
  const androidOnly = new Set('$ANDROID_ONLY_PARTS'.split(' '));
  Object.keys(pkg.dependencies || {})
    .filter((name) => name.startsWith('@capacitor/'))
    .filter((name) => !nonPlugins.has(name.slice('@capacitor/'.length)))
    .filter((name) => allow && !allow.has(name) && !androidOnly.has(name.slice('@capacitor/'.length)))
    .sort()
    .join(' ')
")"

FAILED=0

if [ -n "$IOS_ALLOWLIST_GAPS" ]; then
  echo "FAIL capacitor.config.json ios.includePlugins is missing: $IOS_ALLOWLIST_GAPS. Add it there (or to ANDROID_ONLY_PARTS if it must stay out of iOS)."
  FAILED=1
fi

if [ "$STAGE" = "pre-sync" ] || [ "$STAGE" = "all" ]; then
  for part in $ALL_PARTS; do
    if [ ! -f "node_modules/@capacitor/$part/package.json" ]; then
      echo "FAIL node_modules is missing @capacitor/$part. Run npm install before packaging."
      FAILED=1
    fi
  done
fi

if [ "$STAGE" = "post-sync" ] || [ "$STAGE" = "all" ]; then
  if [ ! -f "$PACKAGE_SWIFT" ]; then
    echo "FAIL $PACKAGE_SWIFT does not exist. Run npx cap sync ios first."
    FAILED=1
  else
    for part in $PLUGIN_PARTS; do
      if ! grep -q "node_modules/@capacitor/$part\"" "$PACKAGE_SWIFT"; then
        echo "FAIL $PACKAGE_SWIFT has no package entry for @capacitor/$part. cap sync dropped it (usually a stale node_modules)."
        FAILED=1
      fi
    done
  fi
fi

if [ "$FAILED" -ne 0 ]; then
  exit 1
fi

echo "PASS Capacitor parts check ($STAGE). Declared: $ALL_PARTS. Native plugins in Package.swift: ${PLUGIN_PARTS:-none}."
