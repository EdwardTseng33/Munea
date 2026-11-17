#!/usr/bin/env bash
# 沐寧 · Cloud Run 0% canary 結構驗證
# 用法：bash deploy/cloudrun/canary-verify.sh brain|voice <canary-tag> staging|production <version> <commit> [compatibility|strict]
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
EXPECTED_LOCALE_MODE="${6:-}"
case "$WHAT" in
  brain) SVC="munea-brain-staging" ;;
  voice) SVC="munea-voice-staging" ;;
  *) echo "用法：bash deploy/cloudrun/canary-verify.sh brain|voice <canary-tag> staging|production <version> <commit> [compatibility|strict]"; exit 1 ;;
esac
[ -n "$TAG" ] || { echo "⛔ 缺少 canary tag"; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "⛔ 找不到 curl"; exit 1; }
case "$EXPECTED_LOCALE_MODE" in
  ""|compatibility|strict) ;;
  *) echo "⛔ locale mode 必須是 compatibility 或 strict"; exit 1 ;;
esac
if [ "$WHAT" = "brain" ] && [ -n "$EXPECTED_LOCALE_MODE" ]; then
  echo "⛔ Brain canary 不接受 Voice locale mode"
  exit 1
fi
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
[ "$READY" = "True" ] || { echo "⛔ $REVISION 尚未 Ready：$READY"; exit 1; }

LOCALE_MODE=""
if [ "$WHAT" = "voice" ]; then
  VOICE_LOCALE_META="$(printf '%s' "$REVISION_JSON" | "${PYTHON[@]}" -c '
import json, sys
data = json.load(sys.stdin)
containers = data.get("spec", {}).get("containers") or data.get("template", {}).get("containers") or []
envs = (containers[0] if containers else {}).get("env", [])
values = {item.get("name"): item.get("value", "") for item in envs}
print(values.get("MUNEA_VOICE_ALLOW_LEGACY_LOCALE_CONTEXT", ""))
print(values.get("MUNEA_CALL_CONTROL_REQUIRED", ""))
print(values.get("MUNEA_CALL_PROTOCOL_REQUIRED", ""))
print(values.get("MUNEA_VOICE_FACE_DIRECT", ""))
')"
  ALLOW_LEGACY_LOCALE_CONTEXT="$(printf '%s\n' "$VOICE_LOCALE_META" | sed -n '1p')"
  CALL_CONTROL_REQUIRED="$(printf '%s\n' "$VOICE_LOCALE_META" | sed -n '2p')"
  CALL_PROTOCOL_REQUIRED="$(printf '%s\n' "$VOICE_LOCALE_META" | sed -n '3p')"
  VOICE_FACE_DIRECT="$(printf '%s\n' "$VOICE_LOCALE_META" | sed -n '4p')"
  [ "$CALL_PROTOCOL_REQUIRED" = "3" ] || {
    echo "Voice revision is missing MUNEA_CALL_PROTOCOL_REQUIRED=3"
    exit 1
  }
  [ "$VOICE_FACE_DIRECT" = "1" ] || {
    echo "Voice revision is missing MUNEA_VOICE_FACE_DIRECT=1"
    exit 1
  }
  case "$ALLOW_LEGACY_LOCALE_CONTEXT" in
    1) LOCALE_MODE="compatibility" ;;
    0)
      [ "$CALL_CONTROL_REQUIRED" = "1" ] || {
        echo "⛔ strict LocaleContext revision 沒有同時要求 Call Control"
        exit 1
      }
      LOCALE_MODE="strict"
      ;;
    *)
      echo "⛔ Voice revision 未明確設定 MUNEA_VOICE_ALLOW_LEGACY_LOCALE_CONTEXT=0|1"
      exit 1
      ;;
  esac
  if [ -n "$EXPECTED_LOCALE_MODE" ] && [ "$LOCALE_MODE" != "$EXPECTED_LOCALE_MODE" ]; then
    echo "⛔ Voice locale mode=$LOCALE_MODE，expected=$EXPECTED_LOCALE_MODE"
    exit 1
  fi
fi
unset REVISION_JSON

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

# 真的接一次 Google（2026-11-16）：11/8 重建時工具包自動升版、即時語音連線被拒，正式聊聊
# 四天打不通——當時這個關卡只看「主機起來了、版號對」，全綠放行。現在語音版一定要先用
# 自己的鑰匙、自己的模型、整份通話設定真的開一條線、聽到第一包聲音，才算過。
LIVE_SELFTEST=""
if [ "$WHAT" = "voice" ]; then
  if [ "${MUNEA_SKIP_LIVE_SELFTEST:-0}" = "1" ]; then
    echo "⚠️ 跳過「真的接一次 Google」（MUNEA_SKIP_LIVE_SELFTEST=1）——只有重新放行沒有這個檢查的舊版時才該這樣做"
    LIVE_SELFTEST="skipped"
  else
    SELFTEST_KEY="${MUNEA_APP_KEY:-}"
    if [ -z "$SELFTEST_KEY" ] && [ -f deploy/.munea-app-key ]; then
      SELFTEST_KEY="$(tr -d '\r\n' < deploy/.munea-app-key)"
    fi
    [ -n "$SELFTEST_KEY" ] || { echo "⛔ 找不到 MUNEA_APP_KEY 或 deploy/.munea-app-key——沒辦法做「真的接一次 Google」"; exit 1; }
    SELFTEST_OUT="$(curl -sS --max-time 40 -w '\n%{http_code}' -H "X-Munea-Selftest-Key: $SELFTEST_KEY" "$CANARY_URL/selftest/live" || true)"
    unset SELFTEST_KEY
    SELFTEST_CODE="$(printf '%s\n' "$SELFTEST_OUT" | tail -n 1)"
    SELFTEST_BODY="$(printf '%s\n' "$SELFTEST_OUT" | sed '$d')"
    unset SELFTEST_OUT
    if [ "$SELFTEST_CODE" != "200" ]; then
      echo "⛔ 這一版接不上 Google 的即時語音（/selftest/live 回 ${SELFTEST_CODE:-沒有回應}）"
      printf '%s\n' "$SELFTEST_BODY" | head -c 400; echo
      echo "   404＝這一版沒有自我檢查或鑰匙不對；503＝真的接不上（看上面的 error）；沒有回應＝主機卡住。"
      exit 1
    fi
    LIVE_SELFTEST="$(printf '%s' "$SELFTEST_BODY" | "${PYTHON[@]}" -c '
import json, sys
d = json.load(sys.stdin)
if d.get("ok") is not True or d.get("mode") != "full":
    raise SystemExit("live_selftest_unexpected_payload")
print("%s · 首聲 %sms" % (d.get("model"), d.get("first_audio_ms")))
')"
    unset SELFTEST_BODY
  fi
fi

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
  echo "✅ Voice canary PASS：$REVISION · 0% · root 200 · locale=$LOCALE_MODE · 真的接上 Google：$LIVE_SELFTEST"
  echo "⚠️ 尚未涵蓋：正式 Call Token、ASR、插話、靜音與真人體感。"
fi
echo "revision=$REVISION"
echo "canary_url=$CANARY_URL"
if [ "$WHAT" = "voice" ]; then
  echo "locale_mode=$LOCALE_MODE"
fi
