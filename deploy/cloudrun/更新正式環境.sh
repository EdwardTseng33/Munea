#!/usr/bin/env bash
# ⛔ 已退役（2026-07-13）—— 這支腳本原本部署的 munea-brain / munea-voice（無 -staging 字尾）
#    兩個舊「正式」服務，已在 2026-07-13 刪除（單人開發收斂成一套環境，見下方說明）。
#
# 現在唯一正式 = munea-brain-staging / munea-voice-staging（名字仍帶 -staging，只是外觀沿用）。
# 要部署新版，請改用：
#   1) bash deploy/cloudrun/canary-deploy.sh brain|voice   ← 先出新版、不吃流量、給測試網址
#   2) bash deploy/cloudrun/promote.sh brain|voice          ← 測過 OK 才切 100% 正式流量
#
# 完整說明：docs/單一正式環境-部署SOP-2026-07-13.md
set -euo pipefail
echo "⛔ 這支腳本已退役——舊的無 -staging 正式服務已刪除。"
echo "   請改用 canary-deploy.sh + promote.sh（見本檔開頭註解 / docs/單一正式環境-部署SOP-2026-07-13.md）"
exit 1
