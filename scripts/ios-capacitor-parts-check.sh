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
  Object.keys(pkg.dependencies || {})
    .filter((name) => name.startsWith('@capacitor/'))
    .map((name) => name.slice('@capacitor/'.length))
    .filter((name) => !nonPlugins.has(name))
    .sort()
    .join(' ')
")"

FAILED=0

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
