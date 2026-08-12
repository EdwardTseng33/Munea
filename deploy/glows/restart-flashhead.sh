#!/usr/bin/env bash
set -euo pipefail

PY=/root/miniconda3/envs/workenv/bin/python
APP=/root/flashhead_server.py
LOG=/root/flashhead.log
ENV_FILE="${MUNEA_FACE_ENV_FILE:-/root/munea-face.env}"
PATTERN="^${PY}( -u)? ${APP}$"

pid="$(pgrep -fo "$PATTERN" || true)"
if [[ -n "$pid" && -r "/proc/$pid/environ" ]]; then
  while IFS= read -r -d '' entry; do
    export "$entry"
  done < "/proc/$pid/environ"
  kill "$pid"
  for _ in {1..30}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid"
  fi
fi

# The previous process is a compatibility fallback, not release authority.
# Apply the persistent deployment file last so a new protocol/commit cannot be
# silently overwritten by the environment of the process being replaced.
if [[ -r "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

nohup "$PY" -u "$APP" >"$LOG" 2>&1 &
echo $! > /root/flashhead.pid
