#!/usr/bin/env bash
# 沐寧 · Canary 部署（安全閘 1/2）—— 新版只生出來、不吃流量，測過才切
# 用法：bash deploy/cloudrun/canary-deploy.sh brain   （或 voice）
#
# 2026-07-13 收斂：munea-brain-staging / munea-voice-staging 是「唯一正式」
#   （單人開發不用兩套環境；App 本就打這兩個網址）。名字仍帶 -staging 字樣，
#   只是外觀沿用，不是「測試」身分——改名要重建服務，非上線必要、之後有空再清。
#   舊「正式」（無 -staging 字尾的 munea-brain / munea-voice）已停更、已退役。
#   完整說明見 docs/單一正式環境-部署SOP-2026-07-13.md
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

gcloud_run() {
  "${GCLOUD[@]}" "$@"
}

resolve_gcloud

WHAT="${1:-}"
case "$WHAT" in
  brain) SVC="munea-brain-staging" ;;
  voice) SVC="munea-voice-staging" ;;
  *) echo "用法：bash deploy/cloudrun/canary-deploy.sh brain|voice"; exit 1 ;;
esac

# 薄門通行碼：App 帶這把碼才進得來門
KEY="${MUNEA_APP_KEY:-}"
if [ -z "$KEY" ] && [ -f deploy/.munea-app-key ]; then
  KEY=$(cat deploy/.munea-app-key)
fi
[ -n "$KEY" ] || { echo "⛔ 找不到 MUNEA_APP_KEY 或 deploy/.munea-app-key——薄門沒鑰匙不准部署"; exit 1; }

echo "== 更新前快照（回滾用）=="
gcloud_run run revisions list --service "$SVC" --region "$REGION" --project "$PROJECT" --limit=1 --format="value(name)" || true

echo "== 只打包 committed 程式碼（git archive HEAD）=="
echo "   不用『--source .』——工作目錄裡有別的 agent 正在動的未提交檔（例：web/app.js），"
echo "   直接打包會把半成品一起送上雲、混淆這次要測的東西。"
TMP=$(mktemp -d)
git archive --format=tar HEAD | tar -x -C "$TMP"
echo "   打包來源：$(git rev-parse --short HEAD) · $(git log -1 --format=%s)"

TAG="canary-$(date +%m%d-%H%M)"

# ⚠ env-drop 地雷（2026-07-12 踩過、memory: deploy-env-drop-gotcha）：
#   一定要用 --update-env-vars / --update-secrets（合併），不要用 --set-env-vars / --set-secrets
#   （那兩個是「先清空全部、再設」——只帶一兩個值會把其餘 env/secrets 全洗掉，服務會壞）。
if [ "$WHAT" = "brain" ]; then
  echo "== 部署 ${SVC}（管家腦・--no-traffic + --tag=${TAG}，不影響目前正式流量）=="
  gcloud_run run deploy "$SVC" --source "$TMP" --clear-base-image --region "$REGION" --project "$PROJECT" \
    --no-traffic --tag "$TAG" \
    --update-secrets "GEMINI_API_KEY=munea-gemini-key-staging:latest,SUPABASE_SERVICE_ROLE_KEY=munea-supabase-service-staging:latest,MUNEA_ADMIN_API_TOKEN=munea-admin-token-staging:latest,MUNEA_ADMIN_PASSWORD=munea-admin-password:latest" \
    --update-env-vars "^|^MUNEA_APP_KEY=$KEY|MUNEA_DATABASE_PROVIDER=supabase|MUNEA_ENV_NAME=staging|MUNEA_REQUIRE_AUTH=1|MUNEA_ENABLE_DEV_AUTH_BYPASS=false|MUNEA_ADMIN_EMAIL=edwardt0303@gmail.com|SUPABASE_URL=https://uhmpmystjjdqqxlpsthc.supabase.co|SUPABASE_PUBLISHABLE_KEY=sb_publishable_Ou8sb6J8yFHMgC1Mcz2eyw_sT2CprIZ|MUNEA_SUPABASE_ACCOUNT_ID=11111111-1111-4111-8111-111111111111|MUNEA_SUPABASE_PERSON_ID=22222222-2222-4222-8222-222222222222|MUNEA_SUPABASE_FAMILY_GROUP_ID=33333333-3333-4333-8333-333333333333" \
    --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 40 --allow-unauthenticated --quiet
else
  echo "== 部署 ${SVC}（語音橋・--no-traffic + --tag=${TAG}，不影響目前正式流量）=="
  gcloud_run run deploy "$SVC" --source "$TMP" --clear-base-image --region "$REGION" --project "$PROJECT" \
    --no-traffic --tag "$TAG" \
    --update-secrets "GEMINI_API_KEY=munea-gemini-key-staging:latest" \
    --update-env-vars "MUNEA_SERVICE=voice,MUNEA_APP_KEY=$KEY,MUNEA_ENV_NAME=staging" \
    --timeout 3600 --session-affinity --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 20 \
    --allow-unauthenticated --quiet
fi

rm -rf "$TMP"

echo
echo "== 新版測試網址（帶 tag、不影響目前正式流量）=="
gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format="value(status.traffic)"
echo
echo "測試網址（規則：https://<tag>---<服務網域>）："
DOMAIN=$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format="value(status.url)" | sed 's#https://##')
echo "  https://${TAG}---${DOMAIN}"
echo
echo "測過 OK 後執行：bash deploy/cloudrun/promote.sh $WHAT"
echo "不 OK：什麼都不用做——沒 promote 就沒切流量，現在的正式版完全沒被動到。"
