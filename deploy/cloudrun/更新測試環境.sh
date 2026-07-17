#!/usr/bin/env bash
# ⛔ 已退役（2026-07-13）—— 這支腳本原本直接部署+立刻 100% 吃流量，沒有安全閘、
#    也曾在此腳本裡漏帶完整 env（--set-env-vars 只帶一個值＝把其餘 env 全洗掉，
#    見 memory：deploy-env-drop-gotcha，2026-07-12 就是這樣弄壞過 staging）。
#
# munea-brain-staging / munea-voice-staging 是 staging。
# 部署一律走有安全閘的兩步，且 promote 必須帶 exact tag/version/commit：
#   1) bash deploy/cloudrun/canary-deploy.sh brain|voice   ← 先出新版、不吃流量、給測試網址
#   2) 使用 canary-deploy.sh 印出的 promote.sh 指令       ← 真人測過才切 staging 預設流量
#
# 完整說明：deploy/cloudrun/SERVICE-TOPOLOGY.md
set -euo pipefail
echo "⛔ 這支腳本已退役——沒有安全閘、且曾在此腳本內踩過 env-drop 地雷。"
echo "   staging 請從 deploy/cloudrun/canary-deploy.sh 開始；見 deploy/cloudrun/SERVICE-TOPOLOGY.md。"
exit 1
