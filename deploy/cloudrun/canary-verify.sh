#!/usr/bin/env bash
# 沐寧 · Cloud Run 0% canary 結構驗證
# 用法：bash deploy/cloudrun/canary-verify.sh brain|voice <canary-tag> staging|production <version> <commit>
#
# 只驗證部署層：tag 指向 Ready revision、該 revision 流量為 0%、HTTP 入口與 release identity 可用。
# Voice 的 Call Token、Gemini 音訊、ASR、插話與真人體感仍須另外跑真機 Gate。
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

resolve_python() {
  # Windows 陷阱：python3 常是微軟商店空殼（叫了靜默失敗）——必須真跑一次 print 驗證可用
  if command -v python3 >/dev/null 2>&1 && python3 -c "print()" >/dev/null 2>&1; then
    PYTHON=(python3)
  elif [ -x /usr/bin/python3 ]; then
    PYTHON=(/usr/bin/python3)
  elif command -v python >/dev/null 2>&1 && python -c "print()" >/dev/null 2>&1; then
    PYTHON=(python)
  else
    echo "⛔ 找不到 Python；無法安全解析 Cloud Run 狀態"
    exit 1
  fi
}

gcloud_run() {
  "${GCLOUD[@]}" "$@"
}

WHAT="${1:-}"
TAG="${2:-}"
PROFILE="${3:-staging}"
EXPECTED_VERSION="${4:-}"
EXPECTED_COMMIT="${5:-}"
case "$WHAT" in
  brain) SVC="munea-brain-staging" ;;
  voice) SVC="munea-voice-staging" ;;
  *) echo "用法：bash deploy/cloudrun/canary-verify.sh brain|voice <canary-tag> staging|production <version> <commit>"; exit 1 ;;
esac
[ -n "$TAG" ] || { echo "⛔ 缺少 canary tag"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "⛔ 找不到 curl"; exit 1; }
case "$PROFILE:$WHAT" in
  staging:brain) EXPECTED_ENV="staging"; EXPECTED_SERVICE="munea-brain" ;;
  staging:voice) EXPECTED_ENV="staging"; EXPECTED_SERVICE="munea-voice" ;;
  production:brain) SVC="munea-brain"; EXPECTED_ENV="production"; EXPECTED_SERVICE="munea-brain" ;;
  production:voice) SVC="munea-voice"; EXPECTED_ENV="production"; EXPECTED_SERVICE="munea-voice" ;;
  *) echo "invalid profile: $PROFILE"; exit 1 ;;
esac
resolve_gcloud
resolve_python

SERVICE_JSON="$(gcloud_run run services describe "$SVC" --region "$REGION" --project "$PROJECT" --format=json)"
CANARY_META="$(printf '%s' "$SERVICE_JSON" | "${PYTHON[@]}" -c '
import json, sys
data = json.load(sys.stdin)
tag = sys.argv[1]
traffic = next((item for item in data.get("status", {}).get("traffic", []) if item.get("tag") == tag), None)
if not traffic:
    raise SystemExit("tag_not_found")
print(traffic.get("revisionName", ""))
print(traffic.get("percent", 0))
print(traffic.get("url", ""))
' "$TAG")"
unset SERVICE_JSON

REVISION="$(printf '%s\n' "$CANARY_META" | sed -n '1p')"
PERCENT="$(printf '%s\n' "$CANARY_META" | sed -n '2p')"
CANARY_URL="$(printf '%s\n' "$CANARY_META" | sed -n '3p')"
[ -n "$REVISION" ] && [ -n "$CANARY_URL" ] || { echo "⛔ canary metadata 不完整"; exit 1; }
[ "$PERCENT" = "0" ] || { echo "⛔ $REVISION 已承接 $PERCENT% 流量，不是安全的 0% canary"; exit 1; }

REVISION_JSON="$(gcloud_run run revisions describe "$REVISION" --region "$REGION" --project "$PROJECT" --format=json)"
READY="$(printf '%s' "$REVISION_JSON" | "${PYTHON[@]}" -c '
import json, sys
data = json.load(sys.stdin)
ready = next((item for item in data.get("status", {}).get("conditions", []) if item.get("type") == "Ready"), None)
print((ready or {}).get("status", ""))
')"
unset REVISION_JSON
[ "$READY" = "True" ] || { echo "⛔ $REVISION 尚未 Ready：$READY"; exit 1; }

ROOT_CODE="$(curl --retry 3 --retry-delay 1 -sS -o /dev/null -w '%{http_code}' "$CANARY_URL/")"
[ "$ROOT_CODE" = "200" ] || { echo "⛔ $CANARY_URL/ 回 $ROOT_CODE"; exit 1; }

VERSION_JSON="$(curl --retry 3 --retry-delay 1 -fsS "$CANARY_URL/version")"
printf '%s' "$VERSION_JSON" | "${PYTHON[@]}" -c '
import json, sys
payload = json.load(sys.stdin)
release = payload.get("release") or {}
expected = {
    "schema": "munea.service-release.v1",
    "service": sys.argv[1],
    "environment": sys.argv[2],
    "revision": sys.argv[3],
}
if sys.argv[4]:
    expected["version"] = sys.argv[4]
if sys.argv[5]:
    expected["commit"] = sys.argv[5].lower()
errors = [f"{key}={release.get(key)!r}, expected {value!r}" for key, value in expected.items() if release.get(key) != value]
if payload.get("ok") is not True or errors:
    raise SystemExit("release_metadata_mismatch: " + "; ".join(errors))
' "$EXPECTED_SERVICE" "$EXPECTED_ENV" "$REVISION" "$EXPECTED_VERSION" "$EXPECTED_COMMIT"
unset VERSION_JSON

if [ "$WHAT" = "brain" ]; then
  NOTIFICATION_CODE="$(curl --retry 2 --retry-delay 1 -sS -o /dev/null -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    -d '{"signedPayload":"not-a-jws"}' \
    "$CANARY_URL/apple/notifications")"
  [ "$NOTIFICATION_CODE" = "400" ] || {
    echo "⛔ Apple notification 無效簽章應回 400，實際為 $NOTIFICATION_CODE"
    exit 1
  }
  echo "✅ Brain canary PASS：$REVISION · 0% · root 200 · invalid Apple JWS 400"
else
  echo "✅ Voice canary 部署層 PASS：$REVISION · 0% · root 200"
  echo "⚠️ 尚未涵蓋：正式 Call Token、Gemini 音訊、ASR、插話、靜音與真人體感。"
fi
echo "revision=$REVISION"
echo "canary_url=$CANARY_URL"
