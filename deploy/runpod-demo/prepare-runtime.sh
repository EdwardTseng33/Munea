#!/usr/bin/env bash
set -euo pipefail

ROOT="${MUNEA_DEMO_ROOT:-/workspace/munea-demo}"
RELEASE="${1:?release path required}"
LEGACY_ENV="${MUNEA_DEMO_LEGACY_ENV:-/workspace/munea-service/runtime-demo-640.env}"

[[ -d "$RELEASE" ]] || { echo "missing release: $RELEASE" >&2; exit 1; }
[[ -f "$RELEASE/runtime.env.example" ]] || { echo "missing runtime template" >&2; exit 1; }
[[ -f "$LEGACY_ENV" ]] || { echo "missing legacy Demo env" >&2; exit 1; }
[[ ! -e "$ROOT/current" || -L "$ROOT/current" ]] || {
  echo "$ROOT/current exists and is not a symlink" >&2
  exit 1
}

set -a
# shellcheck disable=SC1090
source "$LEGACY_ENV"
set +a
[[ -n "${MUNEA_DEMO_PASSWORD_SHA256:-}" ]] || {
  echo "legacy Demo password hash is missing" >&2
  exit 1
}

cp "$RELEASE/runtime.env.example" "$ROOT/runtime.env.next"
printf 'MUNEA_DEMO_PASSWORD_SHA256=%q\n' "$MUNEA_DEMO_PASSWORD_SHA256" >>"$ROOT/runtime.env.next"
chmod 600 "$ROOT/runtime.env.next"
mv "$ROOT/runtime.env.next" "$ROOT/runtime.env"
ln -sfn "$RELEASE" "$ROOT/current"

[[ "$(grep -c '^MUNEA_DEMO_PASSWORD_SHA256=' "$ROOT/runtime.env")" -eq 1 ]]
echo "runtime=ready"
readlink -f "$ROOT/current"
