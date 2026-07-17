#!/usr/bin/env bash
# 沐寧 · Cloud Run exact-revision promote（安全閘 2/2）
# 用法：bash deploy/cloudrun/promote.sh staging|production brain|voice <tag> <version> <commit>
#
# 只會把流量切到剛重驗通過的 tag/revision/commit；禁止用 floating latest。
# 切換後若 service URL 的 /version identity 不符，會立刻退回原本 100% serving revision。
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

resolve_python() {
  if command -v python3 >/dev/null 2>&1 && python3 -c "print()" >/dev/null 2>&1; then
    PYTHON=(python3)
  elif [ -x /usr/bin/python3 ]; then
    PYTHON=(/usr/bin/python3)
  elif command -v python >/dev/null 2>&1 && python -c "print()" >/dev/null 2>&1; then
    PYTHON=(python)
  else
    echo "⛔ 找不到 Python；無法安全解析 Cloud Run 流量狀態"
    exit 1
  fi
}

PROFILE="${1:-}"
WHAT="${2:-}"
TAG="${3:-}"
EXPECTED_VERSION="${4:-}"
EXPECTED_COMMIT="${5:-}"
case "$PROFILE:$WHAT" in
  staging:brain) SVC="munea-brain-staging"; EXPECTED_SERVICE="munea-brain" ;;
  staging:voice) SVC="munea-voice-staging"; EXPECTED_SERVICE="munea-voice" ;;
  production:brain) SVC="munea-brain"; EXPECTED_SERVICE="munea-brain" ;;
  production:voice) SVC="munea-voice"; EXPECTED_SERVICE="munea-voice" ;;
  *)
    echo "用法：bash deploy/cloudrun/promote.sh staging|production brain|voice <tag> <version> <commit>"
    exit 1
    ;;
esac
[[ "$TAG" =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || { echo "⛔ tag 格式不合法：$TAG"; exit 1; }
[[ "$EXPECTED_VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$ ]] || { echo "⛔ version 格式不合法"; exit 1; }
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-fA-F]{40,64}$ ]] || { echo "⛔ commit 必須是完整 release commit"; exit 1; }

resolve_gcloud
resolve_python
command -v curl >/dev/null 2>&1 || { echo "⛔ 找不到 curl"; exit 1; }

echo "== 重驗 0% canary 與 exact release identity =="
VERIFY_OUTPUT="$(bash deploy/cloudrun/canary-verify.sh "$WHAT" "$TAG" "$PROFILE" "$EXPECTED_VERSION" "$EXPECTED_COMMIT")"
printf '%s\n' "$VERIFY_OUTPUT"
VERIFIED_REVISION="$(printf '%s\n' "$VERIFY_OUTPUT" | sed -n 's/^revision=//p' | tail -n 1)"
[ -n "$VERIFIED_REVISION" ] || { echo "⛔ canary verifier 未回傳 exact revision"; exit 1; }

SERVICE_JSON="$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format=json)"
PROMOTION_META="$(printf '%s' "$SERVICE_JSON" | "${PYTHON[@]}" -c '
import json, sys
data = json.load(sys.stdin)
tag = sys.argv[1]
traffic = data.get("status", {}).get("traffic", [])
target = next((item for item in traffic if item.get("tag") == tag), None)
if not target or not target.get("revisionName"):
    raise SystemExit("tag_revision_not_found")
if int(target.get("percent") or 0) != 0:
    raise SystemExit("target_revision_is_not_zero_percent")
serving = [item for item in traffic if int(item.get("percent") or 0) > 0]
if len(serving) != 1 or int(serving[0].get("percent") or 0) != 100 or not serving[0].get("revisionName"):
    raise SystemExit("expected_one_100_percent_serving_revision")
service_url = data.get("status", {}).get("url", "")
if not service_url:
    raise SystemExit("service_url_missing")
print(target["revisionName"])
print(serving[0]["revisionName"])
print(service_url)
' "$TAG")"
unset SERVICE_JSON
TARGET_REVISION="$(printf '%s\n' "$PROMOTION_META" | sed -n '1p')"
PREVIOUS_REVISION="$(printf '%s\n' "$PROMOTION_META" | sed -n '2p')"
SERVICE_URL="$(printf '%s\n' "$PROMOTION_META" | sed -n '3p')"
[ "$TARGET_REVISION" = "$VERIFIED_REVISION" ] || {
  echo "⛔ tag 在驗證後改指其他 revision；verified=$VERIFIED_REVISION current=$TARGET_REVISION"
  exit 1
}

echo "   environment: $PROFILE"
echo "   service:     $SVC"
echo "   target:      $TARGET_REVISION"
echo "   current:     $PREVIOUS_REVISION"
echo "   release:     v$EXPECTED_VERSION @ ${EXPECTED_COMMIT:0:12}"
echo
read -r -p "真人 Gate 已完成，確認把 $SVC 的 100% 流量切到上述 exact revision？(輸入 yes 繼續) " ok
[ "$ok" = "yes" ] || { echo "未確認、停止。"; exit 1; }

CURRENT_SERVICE_JSON="$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format=json)"
CURRENT_TRAFFIC="$(printf '%s' "$CURRENT_SERVICE_JSON" | "${PYTHON[@]}" -c '
import json, sys
data = json.load(sys.stdin)
tag = sys.argv[1]
traffic = data.get("status", {}).get("traffic", [])
target = next((item for item in traffic if item.get("tag") == tag), None)
serving = [item for item in traffic if int(item.get("percent") or 0) > 0]
print((target or {}).get("revisionName", ""))
print(serving[0].get("revisionName", "") if len(serving) == 1 and int(serving[0].get("percent") or 0) == 100 else "")
' "$TAG")"
unset CURRENT_SERVICE_JSON
CURRENT_TARGET_REVISION="$(printf '%s\n' "$CURRENT_TRAFFIC" | sed -n '1p')"
CURRENT_SERVING_REVISION="$(printf '%s\n' "$CURRENT_TRAFFIC" | sed -n '2p')"
[ "$CURRENT_TARGET_REVISION" = "$TARGET_REVISION" ] && [ "$CURRENT_SERVING_REVISION" = "$PREVIOUS_REVISION" ] || {
  echo "⛔ 確認期間 Cloud Run 流量或 tag 已被其他 session 修改；請重新驗證，不切流量。"
  exit 1
}

echo "== 切 100% 流量到 exact revision =="
gcloud_run run services update-traffic "$SVC" --region "$REGION" --project "$PROJECT" \
  --to-revisions "$TARGET_REVISION=100"

echo "== 等待並驗證 service URL 的 serving release identity（最多 60 秒）=="
PROMOTION_OK=0
for ATTEMPT in {1..10}; do
  if curl --connect-timeout 2 --max-time 4 -fsS "$SERVICE_URL/version" | "${PYTHON[@]}" -c '
import json, sys
payload = json.load(sys.stdin)
release = payload.get("release") or {}
expected = {
    "schema": "munea.service-release.v1",
    "service": sys.argv[1],
    "environment": sys.argv[2],
    "revision": sys.argv[3],
    "version": sys.argv[4],
    "commit": sys.argv[5].lower(),
}
errors = [f"{key}={release.get(key)!r}, expected {value!r}" for key, value in expected.items() if release.get(key) != value]
if payload.get("ok") is not True or errors:
    raise SystemExit("serving_release_mismatch: " + "; ".join(errors))
' "$EXPECTED_SERVICE" "$PROFILE" "$TARGET_REVISION" "$EXPECTED_VERSION" "$EXPECTED_COMMIT"; then
    PROMOTION_OK=1
    break
  fi
  if [ "$ATTEMPT" -lt 10 ]; then
    sleep 2
  fi
done

if [ "$PROMOTION_OK" != "1" ]; then
  echo "⛔ 切換後 release identity 不符；立即回滾到 $PREVIOUS_REVISION"
  if ! gcloud_run run services update-traffic "$SVC" --region "$REGION" --project "$PROJECT" \
    --to-revisions "$PREVIOUS_REVISION=100"; then
    echo "🚨 自動回滾命令失敗，必須立即人工處理：$SVC -> $PREVIOUS_REVISION"
    exit 2
  fi

  echo "== 驗證回滾已恢復原 serving revision（最多 60 秒）=="
  ROLLBACK_OK=0
  for ATTEMPT in {1..10}; do
    if curl --connect-timeout 2 --max-time 4 -fsS "$SERVICE_URL/version" | "${PYTHON[@]}" -c '
import json, sys
payload = json.load(sys.stdin)
release = payload.get("release") or {}
if payload.get("ok") is not True or release.get("schema") != "munea.service-release.v1" or release.get("revision") != sys.argv[1]:
    raise SystemExit("rollback_identity_mismatch")
' "$PREVIOUS_REVISION"; then
      ROLLBACK_OK=1
      break
    fi
    if [ "$ATTEMPT" -lt 10 ]; then
      sleep 2
    fi
  done
  if [ "$ROLLBACK_OK" != "1" ]; then
    echo "🚨 自動回滾後仍無法證明 $PREVIOUS_REVISION 已恢復，必須立即人工處理。"
    exit 2
  fi
  ROLLBACK_TRAFFIC_JSON="$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format=json)"
  if ! printf '%s' "$ROLLBACK_TRAFFIC_JSON" | "${PYTHON[@]}" -c '
import json, sys
data = json.load(sys.stdin)
serving = [item for item in data.get("status", {}).get("traffic", []) if int(item.get("percent") or 0) > 0]
if len(serving) != 1 or int(serving[0].get("percent") or 0) != 100 or serving[0].get("revisionName") != sys.argv[1]:
    raise SystemExit("rollback_traffic_not_restored")
' "$PREVIOUS_REVISION"; then
    echo "🚨 回滾 identity 已回復，但控制面未顯示 $PREVIOUS_REVISION=100；必須立即人工處理。"
    exit 2
  fi
  echo "✅ 已確認回滾到 $PREVIOUS_REVISION"
  exit 1
fi

FINAL_TRAFFIC_JSON="$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format=json)"
printf '%s' "$FINAL_TRAFFIC_JSON" | "${PYTHON[@]}" -c '
import json, sys
data = json.load(sys.stdin)
serving = [item for item in data.get("status", {}).get("traffic", []) if int(item.get("percent") or 0) > 0]
if len(serving) != 1 or int(serving[0].get("percent") or 0) != 100 or serving[0].get("revisionName") != sys.argv[1]:
    raise SystemExit("promotion_traffic_not_exact_revision_100")
' "$TARGET_REVISION"

echo "✅ DONE · $SVC 正在服務 $TARGET_REVISION（v$EXPECTED_VERSION @ ${EXPECTED_COMMIT:0:12}）"
echo "回滾：gcloud run services update-traffic $SVC --region $REGION --project $PROJECT --to-revisions $PREVIOUS_REVISION=100"
