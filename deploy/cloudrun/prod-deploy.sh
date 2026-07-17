#!/usr/bin/env bash
# 沐寧 · 正式環境部署（2026-07-16 Edward 拍板 B 案後新增）
# 用法：bash deploy/cloudrun/prod-deploy.sh brain|voice
#
# 環境分工（2026-07-16 起）：
#   munea-brain / munea-voice                 ＝ 真正式（正式 App 預設連這裡）
#   munea-brain-staging / munea-voice-staging ＝ 真測試機（開發包、canary 驗證用）
#
# 紀律：這支只准部署「已在測試機 canary 驗證過（真人測過）」的版本。
#   流程＝ canary-deploy.sh（測試機出新版）→ 真人驗證 OK → 這支（正式出新版）→ exact revision promote
#
# ⚠ env-drop 地雷（2026-07-12 踩過、memory: deploy-env-drop-gotcha）：
#   一律 --update-env-vars / --update-secrets（合併語意），絕不用 --set-*（會把其餘 env 全洗掉）。
# ⚠ secrets 沿用 *-staging 命名（單一環境時期的名字、值是真鑰匙）；改名要連動多處、之後有空再清。
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

WHAT="${1:-}"
case "$WHAT" in
  brain) SVC="munea-brain" ;;
  voice) SVC="munea-voice" ;;
  *) echo "用法：bash deploy/cloudrun/prod-deploy.sh brain|voice"; exit 1 ;;
esac

KEY="${MUNEA_APP_KEY:-}"
if [ -z "$KEY" ] && [ -f deploy/.munea-app-key ]; then
  KEY=$(cat deploy/.munea-app-key)
fi
[ -n "$KEY" ] || { echo "⛔ 找不到 MUNEA_APP_KEY 或 deploy/.munea-app-key——薄門沒鑰匙不准部署"; exit 1; }

echo "== 只打包 committed 程式碼（git archive HEAD）=="
TMP=$(mktemp -d)
RELEASE_COMMIT="$(git rev-parse HEAD)"
git archive --format=tar "$RELEASE_COMMIT" | tar -x -C "$TMP"
RELEASE_VERSION=$(node -p "require(process.argv[1]).version" "$TMP/package.json")
[[ "$RELEASE_COMMIT" =~ ^[0-9a-fA-F]{40,64}$ ]] || { echo "invalid release commit"; exit 1; }
[[ "$RELEASE_VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$ ]] || { echo "invalid release version"; exit 1; }
echo "   source: ${RELEASE_COMMIT:0:12} · v${RELEASE_VERSION} · $(git log -1 --format=%s "$RELEASE_COMMIT")"

TAG="prod-$(date +%m%d-%H%M%S)-${RELEASE_COMMIT:0:7}"

if [ "$WHAT" = "brain" ]; then
  echo "== 部署 ${SVC}（正式管家腦・--no-traffic + --tag=${TAG}，不影響目前正式流量）=="
  gcloud_run run deploy "$SVC" --source "$TMP" --clear-base-image --region "$REGION" --project "$PROJECT" \
    --no-traffic --tag "$TAG" \
    --update-secrets "GEMINI_API_KEY=munea-gemini-key-staging:latest,SUPABASE_SERVICE_ROLE_KEY=munea-supabase-service-staging:latest,MUNEA_ADMIN_API_TOKEN=munea-admin-token-staging:latest,MUNEA_ADMIN_PASSWORD=munea-admin-password:latest,MUNEA_VOICE_BRAIN_SECRET=munea-voice-brain-secret:latest" \
    --update-env-vars "^|^MUNEA_APP_KEY=$KEY|MUNEA_DATABASE_PROVIDER=supabase|MUNEA_ENV_NAME=production|MUNEA_RELEASE_VERSION=$RELEASE_VERSION|MUNEA_RELEASE_COMMIT=$RELEASE_COMMIT|MUNEA_REQUIRE_AUTH=1|MUNEA_ENABLE_DEV_AUTH_BYPASS=false|MUNEA_ADMIN_EMAIL=edwardt0303@gmail.com|SUPABASE_URL=https://fespbkdwafueyonppzwq.supabase.co|SUPABASE_PUBLISHABLE_KEY=sb_publishable_fP-PoA531waoIOmxl8tsWg_kCeZQD0e|MUNEA_SUPABASE_ACCOUNT_ID=11111111-1111-4111-8111-111111111111|MUNEA_SUPABASE_PERSON_ID=22222222-2222-4222-8222-222222222222|MUNEA_SUPABASE_FAMILY_GROUP_ID=33333333-3333-4333-8333-333333333333" \
    --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 40 --allow-unauthenticated --quiet
else
  echo "== 部署 ${SVC}（正式語音橋・--no-traffic + --tag=${TAG}，不影響目前正式流量）=="
  gcloud_run run deploy "$SVC" --source "$TMP" --clear-base-image --region "$REGION" --project "$PROJECT" \
    --no-traffic --tag "$TAG" \
    --update-secrets "GEMINI_API_KEY=munea-gemini-key-staging:latest,MUNEA_GATEWAY_ADMIN_KEY=munea-gateway-admin-key:latest,MUNEA_CALL_TOKEN_SECRET=munea-call-token-secret:latest,MUNEA_VOICE_BRAIN_SECRET=munea-voice-brain-secret:latest" \
    --update-env-vars "MUNEA_SERVICE=voice,MUNEA_APP_KEY=$KEY,MUNEA_ENV_NAME=production,MUNEA_RELEASE_VERSION=$RELEASE_VERSION,MUNEA_RELEASE_COMMIT=$RELEASE_COMMIT,MUNEA_CALL_CONTROL_URL=https://munea-call-control-fiu65jd4da-de.a.run.app,MUNEA_CALL_CONTROL_REQUIRED=1,MUNEA_VOICE_SHARD_ID=gemini-live-asia-east1-01,MUNEA_BRAIN_INTERNAL_URL=https://munea-brain-491603544409.asia-east1.run.app" \
    --timeout 3600 --session-affinity --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 20 \
    --allow-unauthenticated --quiet
fi

rm -rf "$TMP"

echo
echo "== 新版測試網址（帶 tag、還沒吃正式流量）=="
DOMAIN=$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format="value(status.url)" | sed 's#https://##')
echo "  https://${TAG}---${DOMAIN}"
echo
bash deploy/cloudrun/canary-verify.sh "$WHAT" "$TAG" production "$RELEASE_VERSION" "$RELEASE_COMMIT"
echo
echo "真人與正式 Gate 都確認 OK 後，只能用這組 exact release 證據切 production 流量："
echo "  bash deploy/cloudrun/promote.sh production $WHAT $TAG $RELEASE_VERSION $RELEASE_COMMIT"
