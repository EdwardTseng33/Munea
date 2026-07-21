#!/usr/bin/env bash
set -euo pipefail

DEMO_ROOT="${MUNEA_DEMO_ROOT:-/workspace/munea-demo}"
MANAGER="$DEMO_ROOT/current/manage-demo.sh"
LEGACY_ROOT="${MUNEA_DEMO_LEGACY_ROOT:-/workspace/munea-service}"
LEGACY_PID_FILE="$LEGACY_ROOT/flashhead.pid"
committed=0

rollback() {
  local code=$?
  if [[ "$committed" -eq 0 ]]; then
    echo "cutover failed; restoring legacy 640 Demo" >&2
    "$MANAGER" stop || true
    MUNEA_SERVICE_ROOT="$LEGACY_ROOT" "$LEGACY_ROOT/post_start.sh" || true
  fi
  exit "$code"
}
trap rollback ERR INT TERM

[[ -x "$MANAGER" ]] || { echo "missing Demo manager" >&2; exit 1; }
[[ -f "$LEGACY_PID_FILE" ]] || { echo "missing legacy PID file" >&2; exit 1; }
legacy_pid="$(cat "$LEGACY_PID_FILE")"
kill -0 "$legacy_pid" 2>/dev/null || { echo "legacy Demo PID is not running" >&2; exit 1; }
legacy_cmd="$(tr '\0' ' ' <"/proc/$legacy_pid/cmdline")"
[[ "$legacy_cmd" == *"$LEGACY_ROOT/flashhead_server.py"* ]] || {
  echo "legacy PID does not belong to the Demo service; refusing cutover" >&2
  exit 1
}

echo "stopping legacy Demo pid=$legacy_pid"
kill "$legacy_pid"
for _ in {1..80}; do
  kill -0 "$legacy_pid" 2>/dev/null || break
  sleep 0.25
done
kill -0 "$legacy_pid" 2>/dev/null && {
  echo "legacy Demo did not stop cleanly" >&2
  exit 1
}

"$MANAGER" start
for _ in {1..300}; do
  if "$MANAGER" probe >/dev/null 2>&1; then
    committed=1
    trap - ERR INT TERM
    "$MANAGER" status
    echo "cutover=ready"
    exit 0
  fi
  sleep 1
done

echo "new Demo did not become ready within 300 seconds" >&2
exit 1
