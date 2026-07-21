#!/usr/bin/env bash
set -euo pipefail

ROOT="${MUNEA_DEMO_ROOT:-/workspace/munea-demo}"
TARGET="${1:?target release path required}"
CURRENT="$ROOT/current"
OLD="$(readlink -f "$CURRENT")"
committed=0

[[ "$TARGET" == "$ROOT/releases/"* ]] || { echo "target is outside Demo releases" >&2; exit 1; }
[[ -x "$TARGET/manage-demo.sh" ]] || { echo "target manager is missing" >&2; exit 1; }
[[ -n "$OLD" && -x "$OLD/manage-demo.sh" ]] || { echo "current release is invalid" >&2; exit 1; }

rollback() {
  local code=$?
  if [[ "$committed" -eq 0 ]]; then
    echo "release switch failed; restoring $OLD" >&2
    "$CURRENT/manage-demo.sh" stop || true
    ln -sfn "$OLD" "$CURRENT"
    "$CURRENT/manage-demo.sh" start || true
  fi
  exit "$code"
}
trap rollback ERR INT TERM

"$CURRENT/manage-demo.sh" stop
ln -sfn "$TARGET" "$CURRENT"
"$CURRENT/manage-demo.sh" start
for _ in {1..300}; do
  if "$CURRENT/manage-demo.sh" probe >/dev/null 2>&1; then
    committed=1
    trap - ERR INT TERM
    "$CURRENT/manage-demo.sh" status
    echo "release_switch=ready target=$TARGET"
    exit 0
  fi
  sleep 1
done

echo "target release did not become ready within 300 seconds" >&2
exit 1
