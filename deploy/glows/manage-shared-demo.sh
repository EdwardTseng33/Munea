#!/usr/bin/env bash
set -euo pipefail

# Manages only the B2B Demo process on a shared GLOWS card. The production App
# process, pid file, log and port are deliberately outside this script's scope.
ROOT="${MUNEA_DEMO_ROOT:-/home/glows/munea-demo}"
ENV_FILE="${MUNEA_DEMO_ENV_FILE:-${ROOT}/demo.env}"
PY="${MUNEA_DEMO_PYTHON:-/home/glows/miniconda3/envs/workenv/bin/python}"
APP="${ROOT}/flashhead_server.py"
PID_FILE="${ROOT}/flashhead-demo.pid"
LOG_FILE="${ROOT}/flashhead-demo.log"

read_pid() {
  [[ -f "$PID_FILE" ]] && tr -cd '0-9' < "$PID_FILE" || true
}

is_demo_process() {
  local pid="${1:-}"
  [[ -n "$pid" && -r "/proc/${pid}/cmdline" ]] || return 1
  tr '\0' ' ' < "/proc/${pid}/cmdline" | grep -Fq -- "$APP"
}

status() {
  local pid
  pid="$(read_pid)"
  if is_demo_process "$pid"; then
    echo "demo=running pid=${pid}"
    return 0
  fi
  echo "demo=stopped"
  return 0
}

start() {
  local pid port
  pid="$(read_pid)"
  if is_demo_process "$pid"; then
    echo "demo already running pid=${pid}"
    return 0
  fi
  [[ -x "$PY" ]] || { echo "python not found: $PY" >&2; return 2; }
  [[ -f "$APP" ]] || { echo "server not found: $APP" >&2; return 2; }
  [[ -f "$ENV_FILE" ]] || { echo "env not found: $ENV_FILE" >&2; return 2; }

  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  port="${MUNEA_FACE_PORT:-8188}"
  umask 077
  nohup "$PY" -u "$APP" >"$LOG_FILE" 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"

  for _ in {1..180}; do
    if ! is_demo_process "$pid"; then
      echo "demo failed during startup; see $LOG_FILE" >&2
      tail -n 30 "$LOG_FILE" >&2 || true
      return 3
    fi
    if curl --silent --fail --max-time 2 "http://127.0.0.1:${port}/openapi.json" >/dev/null; then
      echo "demo=ready pid=${pid} port=${port}"
      return 0
    fi
    sleep 1
  done
  echo "demo startup timed out; process remains running for inspection" >&2
  return 4
}

stop() {
  local pid
  pid="$(read_pid)"
  if [[ -z "$pid" ]]; then
    echo "demo already stopped"
    return 0
  fi
  if [[ ! -d "/proc/${pid}" ]]; then
    rm -f -- "$PID_FILE"
    echo "demo already stopped (stale pid file removed)"
    return 0
  fi
  if ! is_demo_process "$pid"; then
    echo "refusing to signal pid ${pid}: it is not the Demo process" >&2
    return 5
  fi
  kill "$pid"
  for _ in {1..50}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "demo did not stop cleanly; leaving it for manual inspection" >&2
    return 6
  fi
  rm -f -- "$PID_FILE"
  echo "demo=stopped"
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  logs) tail -n "${2:-80}" "$LOG_FILE" ;;
  *) echo "usage: $0 start|stop|restart|status|logs [lines]" >&2; exit 2 ;;
esac
