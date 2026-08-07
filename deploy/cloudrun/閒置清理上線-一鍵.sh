#!/usr/bin/env bash
# 沐寧 · 免費帳號 60 天未上線自動清理 · 上線一鍵包（2026-07-23 · PR #229+#233 已併主線 225e118）
# 用法：bash deploy/cloudrun/閒置清理上線-一鍵.sh
#
# 會做：測試機出新版→驗證→切流量（要你打 yes）→正式機出新版→驗證→切流量（再打 yes）
#       →掛每日 04:30 定時鬧鐘→兩台各跑一次乾跑報告
# 資料庫：023+024 已於 2026-07-23 套用東京並乾跑驗證（容錯版函式已就位）。
#         乾跑報告應回正常 JSON（scannedFreeAccounts…），不再是 retention_run_failed。
set -euo pipefail

# 乾淨工作區（含 #229 接口＋#233 容錯，2026-07-23 重建；舊 worktree 已作廢）
WORKTREE="E:/Claude/Munea/.worktrees/retention-deploy-20260723"
REGION="asia-east1"
PROJECT="${MUNEA_GCP_PROJECT:-gen-lang-client-0229303523}"

cd "$WORKTREE"
echo "== 部署來源 =="
git log --oneline -1

parse_promote() {
  # 從 canary/prod 部署輸出撈「promote.sh <env> brain TAG VERSION COMMIT」那行
  printf '%s\n' "$1" | grep -o "promote\.sh $2 brain [^ ]* [^ ]* [0-9a-fA-F]*" | tail -1
}

echo
echo "===== ① 測試機出新版（不吃流量、自帶驗證）====="
STG_OUT=$(bash deploy/cloudrun/canary-deploy.sh brain 2>&1 | tee /dev/stderr)
STG_LINE=$(parse_promote "$STG_OUT" staging)
[ -n "$STG_LINE" ] || { echo "⛔ 沒撈到測試機切換指令、停"; exit 1; }
read -r _ _ _ STG_TAG STG_VER STG_COMMIT <<< "$STG_LINE"

echo
echo "===== ② 測試機切流量（輸入 yes）====="
bash deploy/cloudrun/promote.sh staging brain "$STG_TAG" "$STG_VER" "$STG_COMMIT"

echo
echo "===== ③ 正式機出新版（不吃流量、自帶驗證）====="
PROD_OUT=$(bash deploy/cloudrun/prod-deploy.sh brain 2>&1 | tee /dev/stderr)
PROD_LINE=$(parse_promote "$PROD_OUT" production)
[ -n "$PROD_LINE" ] || { echo "⛔ 沒撈到正式機切換指令、停"; exit 1; }
read -r _ _ _ PROD_TAG PROD_VER PROD_COMMIT <<< "$PROD_LINE"

echo
echo "===== ④ 正式機切流量（再輸入 yes）====="
bash deploy/cloudrun/promote.sh production brain "$PROD_TAG" "$PROD_VER" "$PROD_COMMIT"

echo
echo "===== ⑤ 掛每日鬧鐘（台北 04:30、真跑非乾跑；第一週只蓋警示章、首刪在 7 天後）====="
ADMIN_TOKEN=$(gcloud secrets versions access latest --secret=munea-admin-token-staging)
PROD_URL=$(gcloud run services describe munea-brain --region "$REGION" --project "$PROJECT" --format="value(status.url)")
if gcloud scheduler jobs describe munea-retention-daily --location "$REGION" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud scheduler jobs update http munea-retention-daily --location "$REGION" --project "$PROJECT" \
    --schedule="30 4 * * *" --time-zone="Asia/Taipei" \
    --uri="$PROD_URL/admin/retention/run" --http-method=POST \
    --update-headers="Content-Type=application/json,X-Munea-Admin-Token=$ADMIN_TOKEN" \
    --message-body='{"dryRun": false}'
else
  gcloud scheduler jobs create http munea-retention-daily --location "$REGION" --project "$PROJECT" \
    --schedule="30 4 * * *" --time-zone="Asia/Taipei" \
    --uri="$PROD_URL/admin/retention/run" --http-method=POST \
    --headers="Content-Type=application/json,X-Munea-Admin-Token=$ADMIN_TOKEN" \
    --message-body='{"dryRun": false}'
fi
echo "鬧鐘 OK：munea-retention-daily → $PROD_URL/admin/retention/run"

echo
echo "===== ⑥ 乾跑報告（只看、不動資料）====="
STG_URL=$(gcloud run services describe munea-brain-staging --region "$REGION" --project "$PROJECT" --format="value(status.url)")
echo "-- 測試機 --"
curl -s -X POST "$STG_URL/admin/retention/run" -H "Content-Type: application/json" \
  -H "X-Munea-Admin-Token: $ADMIN_TOKEN" -d '{}' || true
echo
echo "-- 正式機 --"
curl -s -X POST "$PROD_URL/admin/retention/run" -H "Content-Type: application/json" \
  -H "X-Munea-Admin-Token: $ADMIN_TOKEN" -d '{}' || true
echo
echo
echo "✅ 一鍵包跑完。若上面乾跑回 retention_run_failed＝資料庫 023/024 還沒貼（貼完再跑一次⑥的網址即可）。"
