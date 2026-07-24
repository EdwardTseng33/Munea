#!/usr/bin/env bash
# 沐寧 VocaFrame 640 備援卡開機小抄（2026-07-24 卡西法，8-10人併發容量升級
# 工程包1：備援卡印象檔補齊主卡「合批手術階段2」多程序修復）。
#
# 沿用主卡 GLOWS 4090 已驗收的病灶結論：3 條 thread 共用 1 個 process 的
# GIL 序列化才是「多路變超慢」的真病灶（不是 CUDA sync 屏障）；同一張卡
# 開 N 個獨立 process（各自 1 slot）比 N thread 快 1.6 倍，GPU 才真的吃到
# 100%。細節與部署步驟見 deploy/glows/README.md「2026-07-23 合批手術階段2」。
#
# 跟 GLOWS 版 deploy/runpod-avatar/start-vocaframe.sh 的差異（RunPod 環境
# 特性，兩邊刻意不共用同一支腳本、各自維護）：
#   - GLOWS 版從 $MUNEA_SERVICE_ROOT/runtime.env 讀設定（長駐機器、手動
#     維護的環境檔）；RunPod 走 Docker 映像＋型錄直填環境變數，沒有
#     runtime.env 這個檔案，這裡直接讀容器已存在的環境變數。
#   - 服務根目錄固定 /root/munea-service（Dockerfile COPY 進去的位置），
#     不是 /workspace/munea-service。
#   - 這支腳本額外處理 sshd 啟動與 sync-face-assets.py 條件圖對答案（原本
#     單程序版就有的開機步驟）；GLOWS 版沒有這兩步（機器常駐，由
#     install-flashhead.sh 另外處理一次）。
#
# 機密（MUNEA_APP_KEY / MUNEA_CALL_TOKEN_SECRET / MUNEA_GATEWAY_ADMIN_KEY /
# MUNEA_CALL_CONTROL_URL）由 RunPod 型錄的環境變數帶入、不烤進印象檔。
set -uo pipefail

SERVICE_ROOT="/root/munea-service"

# 工作機編號＝runpod-<pod id>，跟總機登記與通行證綁定一致（controller 同款命名）
export MUNEA_WORKER_ID="${MUNEA_WORKER_ID:-runpod-${RUNPOD_POD_ID:-unknown}}"
export MUNEA_FACE_PORT="${MUNEA_FACE_PORT:-8188}"
export MUNEA_FH_FRAME_SIZE="${MUNEA_FH_FRAME_SIZE:-640}"
export MUNEA_FH_MODEL_ROOT="${MUNEA_FH_MODEL_ROOT:-/models}"
# 2026-07-24：預設從「單程序執行緒多槽（MUNEA_FH_SLOTS=2，受 GIL 序列化
# 拖慢）」升級成「2 個獨立 process（各自 1 slot）」，跟主卡同一套修復、
# 同一個目標值。這個預設值刻意寫死在腳本裡（不是等 ops 去 RunPod 型錄
# 另外加環境變數）：印象檔一旦重新烤進這版腳本，任何用這個模板開出來的
# 新卡自動就是雙程序——因為爆量卡本來就是「用完刪、要用重開」的一次性卡
# （deploy/runpod-avatar/README.md 城堡規矩），開賣新版模板之後不會有
# 「舊卡還活著、新設定推過去」的版本混跑問題。想暫時退回單程序（例如新
# 映像有問題要應急）才需要在 RunPod 型錄手動加 MUNEA_FH_PROCS=1 覆蓋。
N_PROCS="${MUNEA_FH_PROCS:-2}"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" || "${MUNEA_FH_DRY_RUN:-0}" == "1" ]]; then
  DRY_RUN=1
fi

BASE_PORT="$MUNEA_FACE_PORT"
BASE_WORKER_ID="$MUNEA_WORKER_ID"

if [[ "$DRY_RUN" == "1" ]]; then
  # 純印計畫，不碰檔案系統／不需要 /root/munea-service 真的存在——方便
  # 部署前預覽、也方便離開容器單獨跑（見 scripts/test_runpod_vocaframe_image_launcher.py）。
  if [[ "$N_PROCS" -le 1 ]]; then
    echo "PLAN mode=single port=$BASE_PORT worker_id=$BASE_WORKER_ID"
  else
    echo "PLAN mode=multi n_procs=$N_PROCS router_port=$BASE_PORT image_build=${MUNEA_FH_IMAGE_BUILD:-unset}"
    for ((i = 0; i < N_PROCS; i++)); do
      echo "PLAN i=$i port=$((BASE_PORT + 1 + i)) worker_id=${BASE_WORKER_ID}-p${i}"
    done
  fi
  exit 0
fi

cd "$SERVICE_ROOT"

PY="${MUNEA_PYTHON_BIN:-python3}"
APP="$SERVICE_ROOT/flashhead_server.py"
ROUTER_APP="$SERVICE_ROOT/flashhead_router.py"

# 維修門（sshd）：RunPod 對 22/tcp 發公網直連埠；掛了也不影響通話服務
/usr/sbin/sshd 2>/dev/null || echo "[boot] sshd failed to start (non-fatal)" >&2

# 條件圖再對一次正式線答案（立繪若改版、開機就跟上）；對不到網路就用烘焙版
"$PY" sync-face-assets.py || echo "[boot] sync-face-assets failed; using baked condition images" >&2

if [[ "$N_PROCS" -le 1 ]]; then
  echo "[vocaframe] MUNEA_FH_PROCS<=1 -- single-process boot (unchanged behavior)"
  export MUNEA_FH_SLOTS="${MUNEA_FH_SLOTS:-2}"
  exec "$PY" -u "$APP"
fi

if [[ ! -f "$ROUTER_APP" ]]; then
  echo "missing $ROUTER_APP -- flashhead_router.py and flashhead_router_core.py must be baked into the image alongside flashhead_server.py / flashhead_engine_core.py when MUNEA_FH_PROCS>1 (see Dockerfile.vocaframe)" >&2
  exit 1
fi

for ((i = 0; i < N_PROCS; i++)); do
  (
    export MUNEA_FACE_PORT=$((BASE_PORT + 1 + i))
    export MUNEA_FH_SLOTS=1
    export MUNEA_WORKER_ID="${BASE_WORKER_ID}-p${i}"
    nohup "$PY" -u "$APP" >"$SERVICE_ROOT/flashhead-p${i}.log" 2>&1 < /dev/null &
    echo $! >"$SERVICE_ROOT/flashhead-p${i}.pid"
  )
  echo "[vocaframe] process p${i} started pid=$(cat "$SERVICE_ROOT/flashhead-p${i}.pid") port=$((BASE_PORT + 1 + i))"
done

export MUNEA_FH_PROCS="$N_PROCS"
export MUNEA_FACE_PORT="$BASE_PORT"
export MUNEA_WORKER_ID="$BASE_WORKER_ID"
echo "[vocaframe] router starting on 0.0.0.0:$BASE_PORT -> $N_PROCS backend process(es) image_build=${MUNEA_FH_IMAGE_BUILD:-unset}"
exec "$PY" -u "$ROUTER_APP"
