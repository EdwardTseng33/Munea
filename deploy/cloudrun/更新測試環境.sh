#!/usr/bin/env bash
# ⛔ 已退役（2026-07-13）—— 這支腳本原本直接部署+立刻 100% 吃流量，沒有安全閘、
#    也曾在此腳本裡漏帶完整 env（--set-env-vars 只帶一個值＝把其餘 env 全洗掉，
#    見 memory：deploy-env-drop-gotcha，2026-07-12 就是這樣弄壞過 staging）。
#
# munea-brain-staging / munea-voice-staging 現在是「唯一正式」，不再是「測試」身分，
# 部署一律走有安全閘的兩步：
#   1) bash deploy/cloudrun/canary-deploy.sh brain|voice   ← 先出新版、不吃流量、給測試網址
#   2) bash deploy/cloudrun/promote.sh brain|voice          ← 測過 OK 才切 100% 正式流量
#
# 完整說明：docs/單一正式環境-部署SOP-2026-07-13.md
set -euo pipefail
echo "⛔ 這支腳本已退役——沒有安全閘、且曾在此腳本內踩過 env-drop 地雷。"
echo "   請改用 canary-deploy.sh + promote.sh（見本檔開頭註解 / docs/單一正式環境-部署SOP-2026-07-13.md）"
exit 1
