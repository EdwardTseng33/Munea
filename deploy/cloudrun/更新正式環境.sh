#!/usr/bin/env bash
# 沐寧 · 更新【正式環境】⚠ 憲法級規矩：只有 Edward 說「上」之後才准跑；跑完證據貼白板
# 用法：bash deploy/cloudrun/更新正式環境.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$LOCALAPPDATA/Google/Cloud SDK/google-cloud-sdk/bin:$PATH"
G="cmd //c gcloud.cmd"

read -p "Edward 已拍板『上正式』？(輸入 yes 繼續) " ok
[ "$ok" = "yes" ] || { echo "未拍板、停止。"; exit 1; }

# 薄門通行碼（開公眾大門後擋陌生流量的唯一防線）：從本機 deploy/.munea-app-key 帶進雲端
KEY=$(cat deploy/.munea-app-key 2>/dev/null || true)
[ -n "$KEY" ] || { echo "⛔ 找不到 deploy/.munea-app-key——薄門沒鑰匙不准部署正式（會裸奔燒錢）"; exit 1; }

echo "== 更新前快照（可回滾的版本）=="
$G run revisions list --service munea-brain --region asia-east1 --limit=1 --format="value(name)" || true

echo "== 部署 正式環境·管家腦 =="
$G run deploy munea-brain --source . --clear-base-image --region asia-east1 \
  --set-secrets GEMINI_API_KEY=munea-gemini-key-prod:latest,SUPABASE_SERVICE_ROLE_KEY=munea-supabase-service-prod:latest \
  --set-env-vars "MUNEA_APP_KEY=$KEY" \
  --memory 1Gi --min-instances 0 --max-instances 3 --concurrency 40 --no-allow-unauthenticated --quiet

echo "== 部署 正式環境·語音橋 =="
$G run deploy munea-voice --source . --clear-base-image --region asia-east1 \
  --set-secrets GEMINI_API_KEY=munea-gemini-key-prod:latest \
  --set-env-vars "MUNEA_SERVICE=voice,MUNEA_APP_KEY=$KEY" \
  --timeout 3600 --session-affinity --memory 1Gi --min-instances 0 --max-instances 5 --concurrency 40 \
  --no-allow-unauthenticated --quiet

echo "== 冒煙檢查 =="
TOK=$(cmd //c "gcloud.cmd auth print-identity-token" | tr -d '\r')
curl -s -m 20 -o /dev/null -w "正式環境·管家腦 / -> %{http_code}\n" -H "Authorization: Bearer $TOK" "https://munea-brain-491603544409.asia-east1.run.app/"
echo "DONE · 回滾方式：Cloud Run 主控台選上一版、兩下點回"
