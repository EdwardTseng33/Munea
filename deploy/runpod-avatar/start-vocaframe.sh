#!/usr/bin/env bash
set -euo pipefail

# Munea FlashHead 多程序啟動器（2026-07-23 卡西法，合批手術階段 2）。
#
# MUNEA_FH_PROCS 未設或設 1 時：完全委派給既有 start-flashhead.sh，跟改動
# 前一字不差（相容性鐵律）——這支腳本在單程序模式下只是一層薄轉發，不重寫
# 任何既有「怎麼啟動/怎麼殺舊行程」的邏輯，避免兩份邏輯分叉出行為差異。
#
# MUNEA_FH_PROCS > 1 時：在同一張卡上開 N 個 flashhead_server.py process
# （各自 MUNEA_FH_SLOTS=1、各自埠號 MUNEA_FACE_PORT+1..+N、各自
# MUNEA_WORKER_ID 尾碼 -p0/-p1/.../-p(N-1)、各自獨立心跳——這些都是
# flashhead_server.py 既有機制，這支腳本只是把對的環境變數餵給對的
# process，沒有新增任何引擎邏輯），前面再起一個 flashhead_router.py 監聽
# 原本對外的 MUNEA_FACE_PORT，依 call token 裡的 worker_id 把請求轉給
# 對應的 process（見 flashhead_router_core.py 的路由決策表）。
#
# 背景：今晚同卡 A/B 實測證明「3 個獨立 process」（p95 1183ms）比「1 個
# process 內 3 條 thread」（p95 1920ms）快 1.6 倍——GIL 序列化才是 3 路變
# 超慢的真病灶，不是階段 1 猜測的 CUDA sync 屏障（那條路已經量過、無效，
# 見 deploy/flashhead-patches/README.md 的誠實紀錄）。
#
# 跑法（跟 start-flashhead.sh 同一組環境變數約定，讀同一份 runtime.env）：
#   MUNEA_FH_PROCS=3 bash start-vocaframe.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="${MUNEA_SERVICE_ROOT:-/workspace/munea-service}"
ENV_FILE="${MUNEA_RUNTIME_ENV_FILE:-$SERVICE_ROOT/runtime.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing runtime env: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

N_PROCS="${MUNEA_FH_PROCS:-1}"
DRY_RUN=0
if [[ "${1:-}" == "--dry-run" || "${MUNEA_FH_DRY_RUN:-0}" == "1" ]]; then
  DRY_RUN=1
fi

if [[ "$N_PROCS" -le 1 ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "PLAN mode=single port=${MUNEA_FACE_PORT:-8188} worker_id=${MUNEA_WORKER_ID:-}"
    exit 0
  fi
  echo "[vocaframe] MUNEA_FH_PROCS<=1 -- delegating to start-flashhead.sh (single-process, unchanged behavior)"
  exec bash "$SCRIPT_DIR/start-flashhead.sh"
fi

PY="${MUNEA_PYTHON_BIN:-python3}"
APP="$SERVICE_ROOT/flashhead_server.py"
ROUTER_APP="$SERVICE_ROOT/flashhead_router.py"
BASE_PORT="${MUNEA_FACE_PORT:-8188}"
BASE_WORKER_ID="${MUNEA_WORKER_ID:-}"

if [[ -z "$BASE_WORKER_ID" ]]; then
  echo "[vocaframe] WARNING: MUNEA_WORKER_ID is empty -- each process's heartbeat/token-check will use an empty base id, and the router's worker_id routing will never match a real call token (falls back to round robin)." >&2
fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "PLAN mode=multi n_procs=$N_PROCS router_port=$BASE_PORT"
  for ((i = 0; i < N_PROCS; i++)); do
    if [[ -n "$BASE_WORKER_ID" ]]; then
      PLAN_WORKER_ID="${BASE_WORKER_ID}-p${i}"
    else
      PLAN_WORKER_ID=""
    fi
    echo "PLAN i=$i port=$((BASE_PORT + 1 + i)) worker_id=$PLAN_WORKER_ID"
  done
  exit 0
fi

if [[ ! -f "$ROUTER_APP" ]]; then
  echo "missing $ROUTER_APP -- flashhead_router.py and flashhead_router_core.py must be uploaded alongside flashhead_server.py / flashhead_engine_core.py when MUNEA_FH_PROCS>1 (see deploy/glows/README.md multi-process section)" >&2
  exit 1
fi

_kill_pid_file() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local old_pid
    old_pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid"
      for _ in {1..30}; do
        kill -0 "$old_pid" 2>/dev/null || break
        sleep 0.2
      done
      kill -0 "$old_pid" 2>/dev/null && kill -9 "$old_pid"
    fi
  fi
}

cd "$SERVICE_ROOT"

for ((i = 0; i < N_PROCS; i++)); do
  PID_FILE="$SERVICE_ROOT/flashhead-p${i}.pid"
  LOG_FILE="$SERVICE_ROOT/flashhead-p${i}.log"
  _kill_pid_file "$PID_FILE"
  (
    export MUNEA_FACE_PORT=$((BASE_PORT + 1 + i))
    export MUNEA_FH_SLOTS=1
    if [[ -n "$BASE_WORKER_ID" ]]; then
      export MUNEA_WORKER_ID="${BASE_WORKER_ID}-p${i}"
    fi
    nohup "$PY" -u "$APP" >"$LOG_FILE" 2>&1 < /dev/null &
    echo $! >"$PID_FILE"
  )
  echo "[vocaframe] process p${i} started pid=$(cat "$PID_FILE") port=$((BASE_PORT + 1 + i)) log=$LOG_FILE"
done

ROUTER_PID_FILE="$SERVICE_ROOT/flashhead-router.pid"
ROUTER_LOG_FILE="$SERVICE_ROOT/flashhead-router.log"
_kill_pid_file "$ROUTER_PID_FILE"
(
  export MUNEA_FH_PROCS="$N_PROCS"
  export MUNEA_FACE_PORT="$BASE_PORT"
  nohup "$PY" -u "$ROUTER_APP" >"$ROUTER_LOG_FILE" 2>&1 < /dev/null &
  echo $! >"$ROUTER_PID_FILE"
)
echo "[vocaframe] router started pid=$(cat "$ROUTER_PID_FILE") port=$BASE_PORT log=$ROUTER_LOG_FILE"
echo "[vocaframe] $N_PROCS process(es) + router up"
