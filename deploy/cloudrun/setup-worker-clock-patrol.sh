#!/usr/bin/env bash
# 沐寧 · 顯卡時鐘巡邏鬧鐘（Cloud Scheduler → Brain /admin/worker-clock-patrol）
# 用法：bash deploy/cloudrun/setup-worker-clock-patrol.sh production|staging [--run-now]
#
# 背景（Edward 2026-08-01 拍板 A 案）：GPU 租賃主機的時鐘由機房控制、容器內無權校時。
# tw-06 從 07-23 起快 257 秒，通話證被誤判過期＝通話全滅；歪了 9 天沒人發現，最後是
# Edward 自己看到打不通才追出來、寫信請廠商校時。
#
# 7/24 其實就寫好了警報（deploy/gateway/monitor.py），但那是一支要有人定時叫起來的巡邏，
# 排程從沒建過——工具是好的，只是沒人按下開始。這支就是把「開始」按下去。
#
# 為什麼不直接跑 monitor.py：那支在 deploy/ 底下，不在大腦的映像裡（Dockerfile 只帶
# engine/ 與 web/）。所以大腦內放了一支只做時鐘這件事的輕量版，複用既有的 Slack 告警線。
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
  production) SVC="munea-brain";         JOB="munea-worker-clock-patrol-production" ;;
  staging)    SVC="munea-brain-staging"; JOB="munea-worker-clock-patrol-staging" ;;
  *) echo "用法：$0 production|staging [--run-now]"; exit 1 ;;
esac
RUN_NOW="${2:-}"

BRAIN_URL="$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)')"
[ -n "$BRAIN_URL" ] || { echo "⛔ 取不到 $SVC 服務網址"; exit 1; }

# ⚠ 兩個保險箱名字很像、別拿錯：
#   munea-admin-token-staging = 管理 API 通行碼（X-Munea-Admin-Token 認這把、兩台大腦同用）
#   munea-admin-password      = 後台帳密登入的密碼（跟這支無關）
ADMIN_TOKEN="$(gcloud_run secrets versions access latest --secret munea-admin-token-staging --project "$PROJECT")"
[ -n "$ADMIN_TOKEN" ] || { echo "⛔ 取不到管理 API 通行碼（Secret munea-admin-token-staging）"; exit 1; }

APP_KEY="${MUNEA_APP_KEY:-}"
if [ -z "$APP_KEY" ] && [ -f deploy/.munea-app-key ]; then
  APP_KEY="$(tr -d '[:space:]' < deploy/.munea-app-key)"
fi
[ -n "$APP_KEY" ] || { echo "⛔ 找不到 MUNEA_APP_KEY 或 deploy/.munea-app-key"; exit 1; }

HEADERS="Content-Type=application/json,X-Munea-Admin-Token=$ADMIN_TOKEN,X-Munea-Key=$APP_KEY"
# 每 15 分鐘巡一次：時鐘是慢慢歪或一次跳掉，不必分秒必爭；但也不能到隔天才知道
# （07-23 那次歪了 9 天）。告警本身有 5 分鐘防洪，不會因為巡太密而洗版。
COMMON_ARGS=(
  --project "$PROJECT" --location "$REGION"
  --schedule "*/15 * * * *" --time-zone "Asia/Taipei"
  --uri "$BRAIN_URL/admin/worker-clock-patrol" --http-method POST
  --message-body '{}'
  --max-retry-attempts 2 --min-backoff 30s --max-backoff 600s
)

if gcloud_run scheduler jobs describe "$JOB" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1; then
  echo "== 鬧鐘已存在、更新設定：$JOB → $BRAIN_URL =="
  # update 的頭參數叫 --update-headers（跟 create 的 --headers 不同名）
  gcloud_run scheduler jobs update http "$JOB" "${COMMON_ARGS[@]}" --update-headers "$HEADERS" 2>&1 | grep -v "$ADMIN_TOKEN" || true
else
  echo "== 建立鬧鐘：$JOB → $BRAIN_URL（每 15 分鐘）=="
  gcloud_run scheduler jobs create http "$JOB" "${COMMON_ARGS[@]}" --headers "$HEADERS" 2>&1 | grep -v "$ADMIN_TOKEN" || true
fi

echo "== 掛載後核對 =="
gcloud_run scheduler jobs describe "$JOB" --project "$PROJECT" --location "$REGION" \
  --format='value(state,schedule,httpTarget.uri)'

if [ "$RUN_NOW" = "--run-now" ]; then
  echo "== 手動觸發一次（驗證端到端）=="
  gcloud_run scheduler jobs run "$JOB" --project "$PROJECT" --location "$REGION"
  sleep 8
  gcloud_run scheduler jobs describe "$JOB" --project "$PROJECT" --location "$REGION" \
    --format='value(state,lastAttemptTime,status.code)'
  echo "（時鐘正常時這支不會發任何訊息——安靜就是好消息。要看巡到什麼，"
  echo "  直接打一次：curl -s -X POST \"$BRAIN_URL/admin/worker-clock-patrol\" -H 'Content-Type: application/json' -H 'X-Munea-Admin-Token: …' -H 'X-Munea-Key: …' -d '{}'）"
fi
