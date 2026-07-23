#!/usr/bin/env bash
# 沐寧 · staging canary 部署（安全閘 1/2）—— 新版先不接 staging 預設流量
# 用法：bash deploy/cloudrun/canary-deploy.sh brain   （或 voice）
#
# 服務角色以 deploy/cloudrun/SERVICE-TOPOLOGY.md 為準：
#   munea-brain-staging / munea-voice-staging = staging（開發包、預演、真人驗證）
#   munea-brain / munea-voice                 = production（App Store 包預設）
set -euo pipefail
cd "$(dirname "$0")/../.."
REGION="asia-east1"
PROJECT="${MUNEA_GCP_PROJECT:-gen-lang-client-0229303523}"
# 2026-07-16 事故夜鐵律（STATUS 102 號⑤）：預設 0＝雙門（有證驗證、沒證走通行碼薄門）。
# 現役 App（含 Edward 開發包）走薄門直連；改回 1（一律要證）的時機＝App 全面走總機
# 領證的包出貨且真人驗過、Edward 拍板後。7/16 18:04 事故＝部署時吃到舊預設 1、薄門被焊死。
VOICE_CALL_CONTROL_REQUIRED="${MUNEA_VOICE_CALL_CONTROL_REQUIRED:-0}"
case "$VOICE_CALL_CONTROL_REQUIRED" in
  0|1) ;;
  *) echo "⛔ MUNEA_VOICE_CALL_CONTROL_REQUIRED 只能是 0 或 1"; exit 1 ;;
esac

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
RELEASE_COMMIT="$(git rev-parse HEAD)"
git archive --format=tar "$RELEASE_COMMIT" | tar -x -C "$TMP"
RELEASE_VERSION=$(node -p "require(process.argv[1]).version" "$TMP/package.json")
[[ "$RELEASE_COMMIT" =~ ^[0-9a-fA-F]{40,64}$ ]] || { echo "⛔ 無效的 release commit"; exit 1; }
[[ "$RELEASE_VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$ ]] || { echo "⛔ 無效的 release version"; exit 1; }
echo "   打包來源：${RELEASE_COMMIT:0:12} · v${RELEASE_VERSION} · $(git log -1 --format=%s "$RELEASE_COMMIT")"

TAG="stg-$(date +%m%d-%H%M%S)-${RELEASE_COMMIT:0:7}"

# ⚠ env-drop 地雷（2026-07-12 踩過、memory: deploy-env-drop-gotcha）：
#   一定要用 --update-env-vars / --update-secrets（合併），不要用 --set-env-vars / --set-secrets
#   （那兩個是「先清空全部、再設」——只帶一兩個值會把其餘 env/secrets 全洗掉，服務會壞）。
if [ "$WHAT" = "brain" ]; then
  echo "== 部署 ${SVC}（管家腦・--no-traffic + --tag=${TAG}，不影響 staging 預設流量）=="
  gcloud_run run deploy "$SVC" --source "$TMP" --clear-base-image --region "$REGION" --project "$PROJECT" \
    --no-traffic --tag "$TAG" \
    --update-secrets "GEMINI_API_KEY=munea-gemini-key-staging:latest,SUPABASE_SERVICE_ROLE_KEY=munea-supabase-service-staging:latest,MUNEA_ADMIN_API_TOKEN=munea-admin-token-staging:latest,MUNEA_ADMIN_PASSWORD=munea-admin-password:latest,MUNEA_VOICE_BRAIN_SECRET=munea-voice-brain-secret:latest,MUNEA_APNS_PRIVATE_KEY=munea-apns-private-key:latest" \
    --update-env-vars "^|^MUNEA_APP_KEY=$KEY|MUNEA_APNS_KEY_ID=59QVAHNMZP|MUNEA_APNS_TEAM_ID=V77L5245MR|MUNEA_DATABASE_PROVIDER=supabase|MUNEA_ENV_NAME=staging|MUNEA_RELEASE_VERSION=$RELEASE_VERSION|MUNEA_RELEASE_COMMIT=$RELEASE_COMMIT|MUNEA_REQUIRE_AUTH=1|MUNEA_ENABLE_DEV_AUTH_BYPASS=false|MUNEA_ADMIN_EMAIL=edwardt0303@gmail.com|SUPABASE_URL=https://fespbkdwafueyonppzwq.supabase.co|SUPABASE_PUBLISHABLE_KEY=sb_publishable_fP-PoA531waoIOmxl8tsWg_kCeZQD0e|MUNEA_SUPABASE_ACCOUNT_ID=11111111-1111-4111-8111-111111111111|MUNEA_SUPABASE_PERSON_ID=22222222-2222-4222-8222-222222222222|MUNEA_SUPABASE_FAMILY_GROUP_ID=33333333-3333-4333-8333-333333333333" \
    --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 40 --allow-unauthenticated --quiet
else
  echo "== 部署 ${SVC}（語音橋・--no-traffic + --tag=${TAG}，不影響 staging 預設流量）=="
  gcloud_run run deploy "$SVC" --source "$TMP" --clear-base-image --region "$REGION" --project "$PROJECT" \
    --no-traffic --tag "$TAG" \
    --update-secrets "GEMINI_API_KEY=munea-gemini-key-staging:latest,MUNEA_GATEWAY_ADMIN_KEY=munea-gateway-admin-key:latest,MUNEA_CALL_TOKEN_SECRET=munea-call-token-secret:latest,MUNEA_VOICE_BRAIN_SECRET=munea-voice-brain-secret:latest" \
    --update-env-vars "MUNEA_SERVICE=voice,MUNEA_APP_KEY=$KEY,MUNEA_ENV_NAME=staging,MUNEA_RELEASE_VERSION=$RELEASE_VERSION,MUNEA_RELEASE_COMMIT=$RELEASE_COMMIT,MUNEA_CALL_CONTROL_URL=https://munea-call-control-fiu65jd4da-de.a.run.app,MUNEA_CALL_CONTROL_REQUIRED=$VOICE_CALL_CONTROL_REQUIRED,MUNEA_VOICE_SHARD_ID=gemini-live-asia-east1-01,MUNEA_BRAIN_INTERNAL_URL=https://munea-brain-staging-fiu65jd4da-de.a.run.app" \
    --timeout 3600 --session-affinity --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 20 \
    --allow-unauthenticated --quiet
fi

rm -rf "$TMP"

echo
echo "== 新版測試網址（帶 tag、不影響 staging 預設流量）=="
gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format="value(status.traffic)"
echo
echo "測試網址（規則：https://<tag>---<服務網域>）："
DOMAIN=$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format="value(status.url)" | sed 's#https://##')
echo "  https://${TAG}---${DOMAIN}"
echo
echo "== 自動驗證 0% canary（不切 staging 預設流量）=="
bash deploy/cloudrun/canary-verify.sh "$WHAT" "$TAG" staging "$RELEASE_VERSION" "$RELEASE_COMMIT"
echo
echo "真人測過 OK 後，只能用這組 exact release 證據切 staging 流量："
echo "  bash deploy/cloudrun/promote.sh staging $WHAT $TAG $RELEASE_VERSION $RELEASE_COMMIT"
echo "不 OK：什麼都不用做——沒 promote 就沒切流量，staging 預設版完全沒被動到。"
