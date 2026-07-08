#!/usr/bin/env bash
# 沐寧 · 4090 開卡後一鍵裝機（骨架版 · D1 現場補完細節）
# 用法：開卡 → 進主機 → bash bootstrap.sh
set -euo pipefail

echo "[1/5] 系統與依賴"
apt-get update -qq && apt-get install -y -qq git ffmpeg coturn > /dev/null

echo "[2/5] 臉引擎（Ditto · Apache-2.0）"
mkdir -p /workspace && cd /workspace
[ -d ditto-talkinghead ] || git clone https://github.com/antgroup/ditto-talkinghead
cd ditto-talkinghead
pip install -q -r requirements.txt
# 權重下載（HuggingFace）＋ TensorRT 引擎建置：依官方 README 當日指示執行（D1 現場補）
# python scripts/download_weights.py && python scripts/build_trt.py  ← 佔位、以官方為準

echo "[3/5] 串流橋（沿用本機驗證資產）"
pip install -q aiortc aiohttp websockets google-genai librosa
# avatar_cloud_server.py：D1 現場落地（對時/羽化/門禁設計自本機版移植）

echo "[4/5] 語音橋（聊聊 Gemini 語音鏈）"
# 從 Munea repo 取 engine/live_voice_server.py 同款、鑰匙走環境變數

echo "[5/5] 門禁與監控"
# 發碼窗口（demo-cloud/api/token.js 同邏輯的 python 版）＋ 成本計時器（BUDGET_USD_CAP 到頂自動關）

echo "裝機骨架完成——D1 現場補完標記處後，此訊息改為『裝機完成』"
