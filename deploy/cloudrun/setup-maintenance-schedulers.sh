#!/usr/bin/env bash
# 沐寧 · 兩支維運鬧鐘掛載小工具（Cloud Scheduler → Brain）
#   ① 企業席次到期自動處理  /admin/enterprise/seats/sweep   每天台灣 03:20
#   ② 60 天閒置帳號清理      /admin/retention/run             每天台灣 03:40
#
# 用法：bash deploy/cloudrun/setup-maintenance-schedulers.sh production|staging [--live] [--run-now]
#   預設兩支都掛「乾跑」（只出報告不動資料）——先看幾天報告，確認判斷正確才加 --live。
#   --live   把 dryRun 改成 false（真的動資料）
#   --run-now 掛完立刻手動觸發一次，驗證端到端通不通
#
# 背景（2026-07-30）：這兩套機制的程式早就寫好，但 Cloud Scheduler 上只有清晨備料兩支鬧鐘，
# 沒有人來打它們＝「設計說有、正式線沒有」。企業席次那支尤其要緊：公司停付款後
# 沒人收回會員資格，那個人的 Pro 會一直留著。
#
# 沿用 setup-daily-briefing-scheduler.sh 的所有做法：冪等（已存在就更新）、
# 管理通行碼從保險箱現取不落地、輸出過濾掉通行碼。
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
  production) SVC="munea-brain";         SUFFIX="production" ;;
  staging)    SVC="munea-brain-staging"; SUFFIX="staging" ;;
  *) echo "用法：$0 production|staging [--live] [--run-now]"; exit 1 ;;
esac
shift || true

DRY_RUN="true"
RUN_NOW=""
for arg in "$@"; do
  case "$arg" in
    --live) DRY_RUN="false" ;;
    --run-now) RUN_NOW="yes" ;;
    *) echo "⛔ 不認識的參數：$arg"; exit 1 ;;
  esac
done

BRAIN_URL="$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format='value(status.url)')"
[ -n "$BRAIN_URL" ] || { echo "⛔ 取不到 $SVC 服務網址"; exit 1; }

# ⚠ 兩個保險箱名字很像、別拿錯（2026-07-24 首掛踩過 403）：
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

echo "== 環境 $ENVIRONMENT · $SVC · dryRun=$DRY_RUN =="

install_job() {
  local job="$1" schedule="$2" path="$3" body="$4" label="$5"
  local args=(
    --project "$PROJECT" --location "$REGION"
    --schedule "$schedule" --time-zone "Asia/Taipei"
    --uri "$BRAIN_URL$path" --http-method POST
    --message-body "$body"
    --max-retry-attempts 3 --min-backoff 30s --max-backoff 3600s
  )
  if gcloud_run scheduler jobs describe "$job" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1; then
    echo "-- 已存在、更新設定：$job（$label）"
    # update 的頭參數叫 --update-headers（跟 create 的 --headers 不同名、2026-07-24 踩過）
    gcloud_run scheduler jobs update http "$job" "${args[@]}" --update-headers "$HEADERS" 2>&1 | grep -v "$ADMIN_TOKEN" || true
  else
    echo "-- 建立鬧鐘：$job（$label · $schedule 台灣時間）"
    gcloud_run scheduler jobs create http "$job" "${args[@]}" --headers "$HEADERS" 2>&1 | grep -v "$ADMIN_TOKEN" || true
  fi
  gcloud_run scheduler jobs describe "$job" --project "$PROJECT" --location "$REGION" \
    --format='value(state,schedule,httpTarget.uri)'
  if [ "$RUN_NOW" = "yes" ]; then
    echo "-- 手動觸發一次驗證"
    gcloud_run scheduler jobs run "$job" --project "$PROJECT" --location "$REGION" >/dev/null
  fi
}

# 席次到期先跑（可能把某些人轉回免費），閒置清理後跑——
# 順序反了的話，剛被轉回免費的帳號在同一輪就被當成閒置對象評估，時序上容易誤判。
install_job "munea-enterprise-seat-sweep-$SUFFIX" "20 3 * * *" \
  "/admin/enterprise/seats/sweep" "{\"dryRun\":$DRY_RUN,\"actor\":\"scheduler\"}" \
  "企業席次到期自動處理"

install_job "munea-account-retention-$SUFFIX" "40 3 * * *" \
  "/admin/retention/run" "{\"dryRun\":$DRY_RUN}" \
  "60 天閒置帳號清理"

echo
if [ "$DRY_RUN" = "true" ]; then
  echo "✅ DONE · 兩支鬧鐘已掛（乾跑模式：只出報告、不動資料）"
  echo "   看幾天報告確認判斷正確後，再跑一次帶 --live 讓它真的執行。"
else
  echo "✅ DONE · 兩支鬧鐘已掛（真的會動資料）"
fi
echo "   查看記錄：gcloud scheduler jobs describe munea-enterprise-seat-sweep-$SUFFIX --location $REGION --project $PROJECT"
