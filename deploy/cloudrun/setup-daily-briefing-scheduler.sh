#!/usr/bin/env bash
# 沐寧 · 清晨備料鬧鐘掛載小工具（Cloud Scheduler → Brain /admin/daily-briefing）
# 用法：bash deploy/cloudrun/setup-daily-briefing-scheduler.sh production|staging [--run-now]
#
# 背景（2026-07-24 架構體檢 90 分路線 #3）：清晨備料（天氣/空品/明日預告/本週話題）
# 生成鏈早就 ready、測試機 06:30 鬧鐘也掛了，但正式機一直沒掛＝「設計說有、正式線沒有」。
# 這支把掛鬧鐘變成有版本的設備：冪等（已存在就更新）、管理通行碼從 Secret Manager 現取不落地。
set -euo pipefail
cd "$(dirname "$0")/../.."
REGION="asia-east1"
PROJECT="${MUNEA_GCP_PROJECT:-gen-lang-client-0229303523}"

resolve_gcloud() {
  if command -v gcloud >/dev/null 2>&1; then
    GCLOUD=(gcloud)
  elif command -v gcloud.cmd >/dev/null 2>&1; then
    GCLOUD=(cmd //c gcloud.cmd)
  else
    echo "⛔ 找不到 gcloud；請先將 Google Cloud SDK 加入 PATH"
    exit 1
  fi
}
gcloud_run() { "${GCLOUD[@]}" "$@"; }
resolve_gcloud

ENVIRONMENT="${1:-}"
case "$ENVIRONMENT" in
  production) SVC="munea-brain";        JOB="munea-daily-briefing-production" ;;
  staging)    SVC="munea-brain-staging"; JOB="munea-daily-briefing-staging" ;;
  *) echo "用法：$0 production|staging [--run-now]"; exit 1 ;;
esac
RUN_NOW="${2:-}"

BRAIN_URL="$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)')"
[ -n "$BRAIN_URL" ] || { echo "⛔ 取不到 $SVC 服務網址"; exit 1; }

ADMIN_TOKEN="$(gcloud_run secrets versions access latest --secret munea-admin-password --project "$PROJECT")"
[ -n "$ADMIN_TOKEN" ] || { echo "⛔ 取不到管理通行碼（Secret munea-admin-password）"; exit 1; }

APP_KEY="${MUNEA_APP_KEY:-}"
if [ -z "$APP_KEY" ] && [ -f deploy/.munea-app-key ]; then
  APP_KEY="$(tr -d '[:space:]' < deploy/.munea-app-key)"
fi
[ -n "$APP_KEY" ] || { echo "⛔ 找不到 MUNEA_APP_KEY 或 deploy/.munea-app-key"; exit 1; }

COMMON_ARGS=(
  --project "$PROJECT" --location "$REGION"
  --schedule "30 6 * * *" --time-zone "Asia/Taipei"
  --uri "$BRAIN_URL/admin/daily-briefing" --http-method POST
  --headers "Content-Type=application/json,X-Munea-Admin-Token=$ADMIN_TOKEN,X-Munea-Key=$APP_KEY"
  --message-body '{"region":"臺北市"}'
  --max-retry-attempts 3 --min-backoff 30s --max-backoff 3600s
)

if gcloud_run scheduler jobs describe "$JOB" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1; then
  echo "== 鬧鐘已存在、更新設定：$JOB → $BRAIN_URL =="
  gcloud_run scheduler jobs update http "$JOB" "${COMMON_ARGS[@]}"
else
  echo "== 建立鬧鐘：$JOB → $BRAIN_URL（每天台灣 06:30）=="
  gcloud_run scheduler jobs create http "$JOB" "${COMMON_ARGS[@]}"
fi

echo "== 掛載後核對 =="
gcloud_run scheduler jobs describe "$JOB" --project "$PROJECT" --location "$REGION" \
  --format='value(state,schedule,httpTarget.uri)'

if [ "$RUN_NOW" = "--run-now" ]; then
  echo "== 手動觸發一次（驗證端到端）=="
  gcloud_run scheduler jobs run "$JOB" --project "$PROJECT" --location "$REGION"
  sleep 8
  gcloud_run scheduler jobs describe "$JOB" --project "$PROJECT" --location "$REGION" \
    --format='value(status.lastAttemptTime,state)'
  echo "（HTTP 結果看 Cloud Scheduler 記錄；備料成功與否也可打 /admin/daily-briefing 回傳確認）"
fi

echo "✅ DONE · $JOB"
