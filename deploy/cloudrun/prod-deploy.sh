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

# ── 不准倒退保險（2026-07-29 立·當晚親踩）：拿「自己的分支」上正式、沒發現主線在
#    自己之外又進了別條線的貨（含 #291 就醫安全鐵則），把已上線的安全功能蓋掉 8 分鐘。
#    機器擋門：抓「正式機此刻在跑的版本」，HEAD 必須包含它（是它的後代）才准部署。
#    真要非線性部署（例如緊急回退鏈）：MUNEA_DEPLOY_ALLOW_NONLINEAR=1 明示跳過、留下記錄。
#
#    2026-07-31 Edward 拍板「改成比內容、不比編號」：squash 合併會換編號——別條線
#    從還沒合併的分支上正式，等它的 PR 合併之後，main 上是**另一個編號**的同一份貨，
#    純血緣比對就會誤擋（當晚誤擋一次、我逐檔核對過內容才放行）。
#    第二關改問 GitHub：那筆現跑的編號屬於哪個 PR、那個 PR 合進 main 了沒、
#    合併後的編號在不在 HEAD 裡。三者都成立＝那份貨真的在，內容沒有倒退。
#    查不到（沒有 gh／沒網／那筆不屬於任何已合併的 PR）就照舊擋——**判不出來一律當作會倒退**。
serving_work_already_merged() {
  local sha="$1" merged=""
  command -v gh >/dev/null 2>&1 || return 1
  sha=$(git rev-parse "$sha" 2>/dev/null) || return 1
  merged=$(gh api "repos/EdwardTseng33/Munea/commits/${sha}/pulls" \
    --jq '[.[] | select(.merged_at != null and .base.ref == "main")] | first | .merge_commit_sha' \
    2>/dev/null) || return 1
  [ -n "$merged" ] && [ "$merged" != "null" ] || return 1
  git cat-file -e "$merged" 2>/dev/null || return 1
  git merge-base --is-ancestor "$merged" HEAD 2>/dev/null || return 1
  printf '%s' "$merged"
}
if [ "${MUNEA_DEPLOY_ALLOW_NONLINEAR:-0}" != "1" ]; then
  # 兩步取「吃流量那版」的版本（spec.template 是最新版模板、可能是還沒切流量的 canary——抓錯會誤判）
  SERVING_REV=$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format=json 2>/dev/null | python -c 'import json,sys; d=json.load(sys.stdin); tr=[t for t in d["status"].get("traffic",[]) if t.get("percent")]; print(tr[0]["revisionName"] if tr else "")' 2>/dev/null || true)
  SERVING_COMMIT=""
  if [ -n "$SERVING_REV" ]; then
    SERVING_COMMIT=$(gcloud_run run revisions describe "$SERVING_REV" --region "$REGION" --project "$PROJECT" --format=json 2>/dev/null | python -c 'import json,sys; d=json.load(sys.stdin); envs=d["spec"]["containers"][0].get("env",[]); print(next((e.get("value","") for e in envs if e.get("name")=="MUNEA_RELEASE_COMMIT"),""))' 2>/dev/null || true)
  fi
  if [ -n "$SERVING_COMMIT" ]; then
    if git cat-file -e "$SERVING_COMMIT" 2>/dev/null && git merge-base --is-ancestor "$SERVING_COMMIT" HEAD 2>/dev/null; then
      echo "✅ 不倒退檢查 PASS：HEAD 包含正式機現跑版本 ${SERVING_COMMIT:0:12}"
    elif MERGED_AS=$(serving_work_already_merged "$SERVING_COMMIT"); then
      echo "✅ 不倒退檢查 PASS：正式機現跑 ${SERVING_COMMIT:0:12} 的編號雖然不在 HEAD 裡，"
      echo "   但那份貨已經以 ${MERGED_AS:0:12} 合併進 main、且 HEAD 含它——內容沒有倒退。"
    else
      echo "⛔ 不倒退檢查 FAIL：正式機現跑 ${SERVING_COMMIT:0:12}，你的 HEAD 不包含它，"
      echo "   也查不到那份貨已經合併進 main——"
      echo "   先 git fetch 並把 origin/main（或現跑版本）合併進來再部署，否則會蓋掉別條線已上線的貨。"
      echo "   （緊急情況明示 MUNEA_DEPLOY_ALLOW_NONLINEAR=1 才可跳過）"
      exit 1
    fi
  else
    echo "⚠ 讀不到正式機現跑版本（首次部署或查詢失敗）——不倒退檢查跳過"
  fi
fi

echo "== 只打包 committed 程式碼（git archive HEAD）=="
TMP=$(mktemp -d)
RELEASE_COMMIT="$(git rev-parse HEAD)"
git archive --format=tar "$RELEASE_COMMIT" | tar -x -C "$TMP"
RELEASE_VERSION=$(node -p "require(process.argv[1]).version" "$TMP/package.json")
[[ "$RELEASE_COMMIT" =~ ^[0-9a-fA-F]{40,64}$ ]] || { echo "invalid release commit"; exit 1; }
[[ "$RELEASE_VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$ ]] || { echo "invalid release version"; exit 1; }
echo "   source: ${RELEASE_COMMIT:0:12} · v${RELEASE_VERSION} · $(git log -1 --format=%s "$RELEASE_COMMIT")"

TAG="prod-$(date +%m%d-%H%M%S)-${RELEASE_COMMIT:0:7}"
VERIFY_LOCALE_MODE=""

if [ "$WHAT" = "brain" ]; then
  echo "== 部署 ${SVC}（正式管家腦・--no-traffic + --tag=${TAG}，不影響目前正式流量）=="
  gcloud_run run deploy "$SVC" --source "$TMP" --clear-base-image --region "$REGION" --project "$PROJECT" \
    --no-traffic --tag "$TAG" \
    --update-secrets "GEMINI_API_KEY=munea-gemini-key-staging:latest,SUPABASE_SERVICE_ROLE_KEY=munea-supabase-service-staging:latest,MUNEA_ADMIN_API_TOKEN=munea-admin-token-staging:latest,MUNEA_ADMIN_PASSWORD=munea-admin-password:latest,MUNEA_VOICE_BRAIN_SECRET=munea-voice-brain-secret:latest,MUNEA_APNS_PRIVATE_KEY=munea-apns-private-key:latest,MUNEA_GATEWAY_ADMIN_KEY=munea-gateway-admin-key:latest" \
    --update-env-vars "^|^MUNEA_APP_KEY=$KEY|MUNEA_APNS_KEY_ID=59QVAHNMZP|MUNEA_APNS_TEAM_ID=V77L5245MR|MUNEA_DATABASE_PROVIDER=supabase|MUNEA_ENV_NAME=production|MUNEA_RELEASE_VERSION=$RELEASE_VERSION|MUNEA_RELEASE_COMMIT=$RELEASE_COMMIT|MUNEA_REQUIRE_AUTH=1|MUNEA_ENABLE_DEV_AUTH_BYPASS=false|MUNEA_ADMIN_EMAIL=edwardt0303@gmail.com|MUNEA_CALL_CONTROL_URL=https://munea-call-control-fiu65jd4da-de.a.run.app|SUPABASE_URL=https://fespbkdwafueyonppzwq.supabase.co|SUPABASE_PUBLISHABLE_KEY=sb_publishable_fP-PoA531waoIOmxl8tsWg_kCeZQD0e|MUNEA_SUPABASE_ACCOUNT_ID=11111111-1111-4111-8111-111111111111|MUNEA_SUPABASE_PERSON_ID=22222222-2222-4222-8222-222222222222|MUNEA_SUPABASE_FAMILY_GROUP_ID=33333333-3333-4333-8333-333333333333" \
    --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 40 --allow-unauthenticated --quiet
else
  VERIFY_LOCALE_MODE="compatibility"
  echo "== 部署 ${SVC}（正式語音橋・--no-traffic + --tag=${TAG}，不影響目前正式流量）=="
  gcloud_run run deploy "$SVC" --source "$TMP" --clear-base-image --region "$REGION" --project "$PROJECT" \
    --no-traffic --tag "$TAG" \
    --update-secrets "GEMINI_API_KEY=munea-gemini-key-staging:latest,MUNEA_GATEWAY_ADMIN_KEY=munea-gateway-admin-key:latest,MUNEA_CALL_TOKEN_SECRET=munea-call-token-secret:latest,MUNEA_VOICE_BRAIN_SECRET=munea-voice-brain-secret:latest" \
    --remove-env-vars "MUNEA_VOICE_SILENCE_MS" \
    --update-env-vars "MUNEA_SERVICE=voice,MUNEA_APP_KEY=$KEY,MUNEA_ENV_NAME=production,MUNEA_RELEASE_VERSION=$RELEASE_VERSION,MUNEA_RELEASE_COMMIT=$RELEASE_COMMIT,MUNEA_CALL_CONTROL_URL=https://munea-call-control-fiu65jd4da-de.a.run.app,MUNEA_CALL_CONTROL_REQUIRED=1,MUNEA_CALL_PROTOCOL_REQUIRED=3,MUNEA_VOICE_FACE_DIRECT=1,MUNEA_VOICE_ALLOW_LEGACY_LOCALE_CONTEXT=1,MUNEA_VOICE_ENGINE=vertex25,MUNEA_VERTEX_LOCATION=us-central1,MUNEA_VOICE_SHARD_ID=gemini-live-asia-east1-01,MUNEA_BRAIN_INTERNAL_URL=https://munea-brain-491603544409.asia-east1.run.app" \
    --timeout 3600 --session-affinity --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 20 \
    --allow-unauthenticated --quiet
fi

rm -rf "$TMP"

echo
echo "== 新版測試網址（帶 tag、還沒吃正式流量）=="
DOMAIN=$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format="value(status.url)" | sed 's#https://##')
echo "  https://${TAG}---${DOMAIN}"
echo
bash deploy/cloudrun/canary-verify.sh \
  "$WHAT" "$TAG" production "$RELEASE_VERSION" "$RELEASE_COMMIT" \
  "$VERIFY_LOCALE_MODE"
echo
echo "真人與正式 Gate 都確認 OK 後，只能用這組 exact release 證據切 production 流量："
echo "  bash deploy/cloudrun/promote.sh production $WHAT $TAG $RELEASE_VERSION $RELEASE_COMMIT"
