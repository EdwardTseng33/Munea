#!/usr/bin/env bash
set -euo pipefail

SERVICE_ROOT="${MUNEA_SERVICE_ROOT:-/workspace/munea-service}"
ENV_FILE="${MUNEA_RUNTIME_ENV_FILE:-$SERVICE_ROOT/runtime.env}"
LOG_FILE="${MUNEA_FLASHHEAD_LOG_FILE:-$SERVICE_ROOT/flashhead.log}"
PID_FILE="${MUNEA_FLASHHEAD_PID_FILE:-$SERVICE_ROOT/flashhead.pid}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing runtime env: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PY="${MUNEA_PYTHON_BIN:-python3}"
APP="$SERVICE_ROOT/flashhead_server.py"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid"
    for _ in {1..30}; do
      kill -0 "$old_pid" 2>/dev/null || break
      sleep 0.2
    done
    kill -0 "$old_pid" 2>/dev/null && kill -9 "$old_pid"
  fi
fi

cd "$SERVICE_ROOT"
nohup "$PY" -u "$APP" >"$LOG_FILE" 2>&1 < /dev/null &
echo $! >"$PID_FILE"
echo "FlashHead started pid=$(cat "$PID_FILE") log=$LOG_FILE"
