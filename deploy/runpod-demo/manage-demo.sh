#!/usr/bin/env bash
set -euo pipefail

ROOT="${MUNEA_DEMO_ROOT:-/workspace/munea-demo}"
CURRENT="${MUNEA_DEMO_CURRENT:-$ROOT/current}"
ENV_FILE="${MUNEA_DEMO_ENV_FILE:-$ROOT/runtime.env}"
PID_FILE="$ROOT/demo.pid"
LOG_FILE="$ROOT/demo.log"

owned_pid() {
  local pid="${1:-}"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  tr '\0' ' ' <"/proc/$pid/cmdline" | grep -Fq "$CURRENT/flashhead_demo.py"
}

status() {
  local pid=""
  [[ -f "$PID_FILE" ]] && pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if owned_pid "$pid"; then
    echo "demo=running pid=$pid root=$CURRENT"
    nvidia-smi --query-gpu=name,memory.used,utilization.gpu --format=csv,noheader 2>/dev/null || true
    return 0
  fi
  echo "demo=stopped root=$CURRENT"
  return 1
}

start() {
  [[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE" >&2; exit 1; }
  [[ -f "$CURRENT/flashhead_demo.py" ]] || { echo "missing Demo release" >&2; exit 1; }
  if status >/dev/null 2>&1; then
    status
    return 0
  fi
  if ss -ltn 2>/dev/null | grep -Eq '[:.]8188[[:space:]]'; then
    echo "port 8188 is already occupied; refusing to touch an unowned process" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  [[ "${MUNEA_FH_LANE:-}" == "demo" ]] || { echo "MUNEA_FH_LANE must be demo" >&2; exit 1; }
  [[ "${MUNEA_FACE_PORT:-}" == "8188" ]] || { echo "Demo port must be 8188" >&2; exit 1; }
  [[ "${MUNEA_FH_SLOTS:-}" == "1" ]] || { echo "Demo slots must be 1" >&2; exit 1; }
  cd "$CURRENT"
  nohup "${MUNEA_PYTHON_BIN:-python3}" -u "$CURRENT/flashhead_demo.py" >"$LOG_FILE" 2>&1 < /dev/null &
  echo $! >"$PID_FILE"
  echo "Demo starting pid=$(cat "$PID_FILE") log=$LOG_FILE"
}

stop() {
  local pid=""
  [[ -f "$PID_FILE" ]] && pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if ! owned_pid "$pid"; then
    echo "Demo is not running; no process changed"
    rm -f "$PID_FILE"
    return 0
  fi
  kill "$pid"
  for _ in {1..60}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "Demo did not stop cleanly; refusing to kill an uncertain process" >&2
    exit 1
  fi
  rm -f "$PID_FILE"
  echo "Demo stopped pid=$pid"
}

probe() {
  status
  curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8188/openapi.json >/dev/null
  echo "demo_http=ready"
}

case "${1:-status}" in
  status) status ;;
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  probe) probe ;;
  *) echo "usage: $0 status|start|stop|restart|probe" >&2; exit 2 ;;
esac
