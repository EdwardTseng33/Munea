#!/usr/bin/env bash
# ⛔ 已退役——檔名保留供舊連結辨識，不再執行任何部署。
#
# production = munea-brain / munea-voice。
# 正式部署只准用 prod-deploy.sh 建 0% canary，再用它印出的 exact promote 指令切流量。
# 完整說明：deploy/cloudrun/SERVICE-TOPOLOGY.md
set -euo pipefail
echo "⛔ 這支舊入口已退役，未執行任何部署。"
echo "   production 請從 deploy/cloudrun/prod-deploy.sh 開始；見 deploy/cloudrun/SERVICE-TOPOLOGY.md。"
exit 1
