#!/usr/bin/env bash
# 沐寧 · Promote（安全閘 2/2）—— canary 網址測過 OK，才把 100% 正式流量切過去
# 用法：bash deploy/cloudrun/promote.sh brain|voice
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$LOCALAPPDATA/Google/Cloud SDK/google-cloud-sdk/bin:$PATH"
G="cmd //c gcloud.cmd"
REGION="asia-east1"

WHAT="${1:-}"
case "$WHAT" in
  brain) SVC="munea-brain-staging" ;;
  voice) SVC="munea-voice-staging" ;;
  *) echo "用法：bash deploy/cloudrun/promote.sh brain|voice"; exit 1 ;;
esac

echo "== 目前流量分布 =="
$G run services describe "$SVC" --region "$REGION" --format="value(status.traffic)"
echo

read -p "canary 網址測過、確認 OK、把 100% 正式流量切給 $SVC 最新版？(輸入 yes 繼續) " ok
[ "$ok" = "yes" ] || { echo "未確認、停止。"; exit 1; }

echo "== 切 100% 流量到最新版 =="
$G run services update-traffic "$SVC" --region "$REGION" --to-latest

echo
echo "== 驗證（用 App 那樣的匿名連線戳門，不是拿 gcloud 憑證驗）=="
python tools/door-sentinel.py || echo "⚠ 門衛叫了——切完流量後有異常，看上面訊息，必要時回滾（見下）"

echo
echo "DONE · 記得把本次版本與結果記上白板。"
echo "回滾（切回上一版）：$G run services update-traffic $SVC --region $REGION --to-revisions=<上一個 revision 名>=100"
echo "  （上一個 revision 名字用『$G run revisions list --service $SVC --region $REGION --limit=5』查）"
