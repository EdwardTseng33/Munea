#!/usr/bin/env bash
# 沐寧 VocaFrame 640 備援卡開機小抄：條件圖對答案 → 開服務。
# 機密（MUNEA_APP_KEY / MUNEA_CALL_TOKEN_SECRET / MUNEA_GATEWAY_ADMIN_KEY /
# MUNEA_CALL_CONTROL_URL）由 RunPod 型錄的環境變數帶入、不烤進印象檔。
set -uo pipefail

# 工作機編號＝runpod-<pod id>，跟總機登記與通行證綁定一致（controller 同款命名）
export MUNEA_WORKER_ID="${MUNEA_WORKER_ID:-runpod-${RUNPOD_POD_ID:-unknown}}"
export MUNEA_FACE_PORT="${MUNEA_FACE_PORT:-8188}"
export MUNEA_FH_FRAME_SIZE="${MUNEA_FH_FRAME_SIZE:-640}"
# 爆量卡走 eager（開機 5 秒內可接客）；渦輪要熱身 2 分鐘、對排隊的人太久
export MUNEA_FH_SLOTS="${MUNEA_FH_SLOTS:-2}"
export MUNEA_FH_MODEL_ROOT="${MUNEA_FH_MODEL_ROOT:-/models}"

cd /root/munea-service

# 維修門（sshd）：RunPod 對 22/tcp 發公網直連埠；掛了也不影響通話服務
/usr/sbin/sshd 2>/dev/null || echo "[boot] sshd failed to start (non-fatal)" >&2

# 條件圖再對一次正式線答案（立繪若改版、開機就跟上）；對不到網路就用烘焙版
python sync-face-assets.py || echo "[boot] sync-face-assets failed; using baked condition images" >&2

exec python -u flashhead_server.py
