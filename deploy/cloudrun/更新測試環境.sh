#!/usr/bin/env bash
# 沐寧 · 更新【測試環境】（城堡主控：任何蘇菲/城堡 session 可跑；跑完證據貼白板）
# 用法：bash deploy/cloudrun/更新測試環境.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$LOCALAPPDATA/Google/Cloud SDK/google-cloud-sdk/bin:$PATH"
G="cmd //c gcloud.cmd"

# 薄門通行碼（跟正式同款）：帶進雲端，開門後 App 帶碼才進得來
KEY=$(cat deploy/.munea-app-key 2>/dev/null || true)
[ -n "$KEY" ] || { echo "⛔ 找不到 deploy/.munea-app-key——薄門沒鑰匙不准部署"; exit 1; }

echo "== 更新前快照（可回滾的版本）=="
$G run revisions list --service munea-brain-staging --region asia-east1 --limit=1 --format="value(name)" || true

echo "== 部署 測試環境·管家腦 =="
$G run deploy munea-brain-staging --source . --clear-base-image --region asia-east1 \
  --set-secrets GEMINI_API_KEY=munea-gemini-key-staging:latest,SUPABASE_SERVICE_ROLE_KEY=munea-supabase-service-staging:latest \
  --set-env-vars "MUNEA_APP_KEY=$KEY" \
  --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 40 --no-allow-unauthenticated --quiet

echo "== 部署 測試環境·語音橋 =="
$G run deploy munea-voice-staging --source . --clear-base-image --region asia-east1 \
  --set-secrets GEMINI_API_KEY=munea-gemini-key-staging:latest \
  --set-env-vars "MUNEA_SERVICE=voice,MUNEA_APP_KEY=$KEY" \
  --timeout 3600 --session-affinity --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 20 \
  --no-allow-unauthenticated --quiet

echo "== 冒煙檢查 =="
TOK=$(cmd //c "gcloud.cmd auth print-identity-token" | tr -d '\r')
curl -s -m 20 -o /dev/null -w "測試環境·管家腦 / -> %{http_code}\n" -H "Authorization: Bearer $TOK" "https://munea-brain-staging-491603544409.asia-east1.run.app/"
echo "DONE · 記得把本次版本與結果記上白板"
