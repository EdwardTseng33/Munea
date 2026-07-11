#!/usr/bin/env bash
set -euo pipefail

PY=/root/miniconda3/envs/workenv/bin/python
APP=/root/flashhead_server.py
LOG=/root/flashhead.log
PATTERN="^${PY} ${APP}$"

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
fi

nohup "$PY" "$APP" >"$LOG" 2>&1 &
echo $! > /root/flashhead.pid
