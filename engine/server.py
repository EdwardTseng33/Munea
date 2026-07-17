#!/usr/bin/env python3
"""
沐寧 Munea · 本機 App 伺服器 — 跑真的 App（web/）＋ 接真的角色腦。
  GET  /                     → web/index.html（完整 App）
  GET  /<path>               → web/ 底下的靜態檔（js / css / 圖）
  POST /open  {char}         → 該角色「主動先開口」＋語音
  POST /chat  {history,char} → 該角色帶記憶回話＋語音
  POST /voice-session        → 回傳目前語音 provider 能力；之後接即時語音 session
  POST /companion-profile    → 讀寫陪伴角色 templateId/displayName
用法：GEMINI_API_KEY="..." py server.py  → 瀏覽器開 http://localhost:8200
"""
import os, sys, json, base64, io, wave, time, posixpath, threading, logging, hmac, hashlib, contextvars, calendar
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from env_loader import load_engine_env
load_engine_env()
from service_metadata import build_service_metadata
import chat_engine as eng
import localization
import supabase_adapter
import model_router
import notify
import apple_store
import notification_service
import apns_service
from google.genai import types

if not os.environ.get("GEMINI_API_KEY"):
    sys.exit("需要 GEMINI_API_KEY")

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.normpath(os.path.join(HERE, "..", "web"))
BRAIN_RELEASE_METADATA = build_service_metadata("munea-brain")
DEFAULT_CHAR = "寧寧"
COMPANION_PROFILE_PATH = os.environ.get("MUNEA_COMPANION_PROFILE_PATH") or os.path.join(HERE, "companion_profile.json")
APP_PROFILE_STORE_PATH = os.environ.get("MUNEA_APP_PROFILE_STORE_PATH") or os.path.join(HERE, "app_profile_store.json")
BILLING_STORE_PATH = os.environ.get("MUNEA_BILLING_STORE_PATH") or os.path.join(HERE, "billing_store.json")
CREDITS_STORE_PATH = os.environ.get("MUNEA_CREDITS_STORE_PATH") or os.path.join(HERE, "credits_store.json")
FAMILY_STATE_STORE_PATH = os.environ.get("MUNEA_FAMILY_STATE_STORE_PATH") or os.path.join(HERE, "family_state_store.json")
FAMILY_ACTIVITIES_PATH = os.environ.get("MUNEA_FAMILY_ACTIVITIES_PATH") or os.path.join(HERE, "family_activities.json")
FAMILY_INVITATIONS_PATH = os.environ.get("MUNEA_FAMILY_INVITATIONS_PATH") or os.path.join(HERE, "family_invitations.json")
FAMILY_RELAYS_PATH = os.environ.get("MUNEA_FAMILY_RELAYS_PATH") or os.path.join(HERE, "family_relay_messages.json")
PUSH_DEVICES_PATH = os.environ.get("MUNEA_PUSH_DEVICES_PATH") or os.path.join(HERE, "push_devices.json")
NOTIFICATION_EVENTS_PATH = os.environ.get("MUNEA_NOTIFICATION_EVENTS_PATH") or os.path.join(HERE, "notification_events.json")
NOTIFICATION_DELIVERIES_PATH = os.environ.get("MUNEA_NOTIFICATION_DELIVERIES_PATH") or os.path.join(HERE, "notification_deliveries.json")
CONSENT_RECORDS_PATH = os.environ.get("MUNEA_CONSENT_RECORDS_PATH") or os.path.join(HERE, "consent_records.json")
PRIVACY_REQUESTS_PATH = os.environ.get("MUNEA_PRIVACY_REQUESTS_PATH") or os.path.join(HERE, "privacy_requests.json")
PRODUCT_EVENTS_PATH = os.environ.get("MUNEA_PRODUCT_EVENTS_PATH") or os.path.join(HERE, "product_events.json")
AUDIT_EVENTS_STORE_PATH = os.environ.get("MUNEA_AUDIT_EVENTS_STORE_PATH") or os.path.join(HERE, "audit_events_store.json")
MEMORY_ITEMS_PATH = os.environ.get("MUNEA_MEMORY_ITEMS_PATH") or os.path.join(HERE, "memory_items.json")
CONVERSATION_SUMMARIES_PATH = os.environ.get("MUNEA_CONVERSATION_SUMMARIES_PATH") or os.path.join(HERE, "conversation_summaries.json")
PERCEPTION_SNAPSHOTS_PATH = os.environ.get("MUNEA_PERCEPTION_SNAPSHOTS_PATH") or os.path.join(HERE, "perception_snapshots.json")
RELATIONSHIP_STATES_PATH = os.environ.get("MUNEA_RELATIONSHIP_STATES_PATH") or os.path.join(HERE, "companion_relationship_states.json")
NOTIFICATION_SETTINGS_PATH = os.environ.get("MUNEA_NOTIFICATION_SETTINGS_PATH") or os.path.join(HERE, "notification_settings.json")
# 主要照護對象編號：雲端模式用資料櫃的正式編號（環境變數）、本機示範照舊（7/9 hotfix：帶錯編號會讓資料櫃拒收）
PRIMARY_CARE_RECIPIENT_ID = os.environ.get("MUNEA_SUPABASE_PERSON_ID") or "local-person-self"
MAX_JSON_BODY_BYTES = 1_000_000
MAX_AUDIO_NOTE_BYTES = 12_000_000

# 邀請碼防爆破（P0-3）：同來源猜錯太多次就暫時擋。記憶體、只計失敗、成功不算。
_INVITE_ATTEMPTS = {}
_INVITE_ATTEMPTS_LOCK = threading.Lock()
INVITE_MAX_FAILS = 10          # 視窗內最多猜錯次數
INVITE_FAIL_WINDOW = 600       # 視窗秒數（10 分鐘）

def invite_rate_limited(client_ip):
    if not client_ip:
        return False
    now = time.time()
    with _INVITE_ATTEMPTS_LOCK:
        fails = [t for t in _INVITE_ATTEMPTS.get(client_ip, []) if now - t < INVITE_FAIL_WINDOW]
        _INVITE_ATTEMPTS[client_ip] = fails
        return len(fails) >= INVITE_MAX_FAILS

def record_invite_failure(client_ip):
    if not client_ip:
        return
    now = time.time()
    with _INVITE_ATTEMPTS_LOCK:
        fails = [t for t in _INVITE_ATTEMPTS.get(client_ip, []) if now - t < INVITE_FAIL_WINDOW]
        fails.append(now)
        _INVITE_ATTEMPTS[client_ip] = fails

# 後台登入防爆破：帳密輸錯太多次就暫時擋（跟邀請碼同一套邏輯、獨立計數）。
_LOGIN_ATTEMPTS = {}
_LOGIN_ATTEMPTS_LOCK = threading.Lock()
LOGIN_MAX_FAILS = 8            # 視窗內最多錯幾次
LOGIN_FAIL_WINDOW = 600       # 視窗秒數（10 分鐘）

def login_rate_limited(client_ip):
    if not client_ip:
        return False
    now = time.time()
    with _LOGIN_ATTEMPTS_LOCK:
        fails = [t for t in _LOGIN_ATTEMPTS.get(client_ip, []) if now - t < LOGIN_FAIL_WINDOW]
        _LOGIN_ATTEMPTS[client_ip] = fails
        return len(fails) >= LOGIN_MAX_FAILS

def record_login_failure(client_ip):
    if not client_ip:
        return
    now = time.time()
    with _LOGIN_ATTEMPTS_LOCK:
        fails = [t for t in _LOGIN_ATTEMPTS.get(client_ip, []) if now - t < LOGIN_FAIL_WINDOW]
        fails.append(now)
        _LOGIN_ATTEMPTS[client_ip] = fails

# AI 端點限流（上線護欄 · 7/16）：聊天/語音/記憶/感知這些每一下都燒 AI 費用的入口，
# 加「同一個人對同一條端點、每分鐘上限」。App key 是全 App 共用的一把鑰匙、CORS 擋不住
# 非瀏覽器客戶端——沒有這道閘＝拿到鑰匙的人可以無限灌爆 LLM 帳單。
# 已驗證用戶以 authUserId 計、未驗證（本機/示範模式）退回來源 IP 計。
AI_RATE_LIMITED_PATHS = {
    "/open",
    "/chat",
    "/voice-note",
    "/persona/context",
    "/memory/extract",
    "/memory/retrieve",
    "/conversation-summary",
    "/butler/post-turn",
    "/guardian/evaluate",
    "/perception/topic-plan",
    "/perception/snapshot",
    "/proactive/opening",
}
AI_RATE_WINDOW = 60            # 滑動視窗秒數
AI_RATE_DEFAULT_LIMIT = 60     # 視窗內同一 actor 對同一端點的次數上限
_AI_RATE_HITS = {}
_AI_RATE_LOCK = threading.Lock()
_AI_RATE_PRUNE_THRESHOLD = 5000


def ai_rate_limit_enabled():
    return str(os.environ.get("MUNEA_AI_RATE_LIMIT_ENABLED", "1")).strip().lower() not in {"0", "false", "no", "off"}


def ai_rate_limit_per_minute():
    raw = os.environ.get("MUNEA_AI_RATE_LIMIT_PER_MINUTE", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = AI_RATE_DEFAULT_LIMIT
    return max(1, value) if value else AI_RATE_DEFAULT_LIMIT


def ai_rate_limited(actor_key, path, now=None):
    """視窗內超額回 (True, 建議等待秒數)，否則記一筆並回 (False, 0)。"""
    if not ai_rate_limit_enabled() or not actor_key:
        return False, 0
    now = time.time() if now is None else now
    limit = ai_rate_limit_per_minute()
    bucket = f"{actor_key}|{path}"
    with _AI_RATE_LOCK:
        if len(_AI_RATE_HITS) > _AI_RATE_PRUNE_THRESHOLD:
            for key in [k for k, hits in _AI_RATE_HITS.items() if not hits or now - hits[-1] >= AI_RATE_WINDOW]:
                _AI_RATE_HITS.pop(key, None)
        hits = [t for t in _AI_RATE_HITS.get(bucket, []) if now - t < AI_RATE_WINDOW]
        if len(hits) >= limit:
            _AI_RATE_HITS[bucket] = hits
            return True, max(1, int(AI_RATE_WINDOW - (now - hits[0])) + 1)
        hits.append(now)
        _AI_RATE_HITS[bucket] = hits
        return False, 0

ALLOWED_AUDIO_MIMES = {"audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}
AVATAR_ENGINE_MODES = {"static-css", "2d-viseme", "ditto", "liveavatar"}
PREMIUM_AVATAR_MODES = {"ditto", "liveavatar"}
MEANINGFUL_EVENT_NAMES = {
    "routine_reminder_completed",
    "family_interaction_sent",
    "family_message_sent",
    "family_message_viewed",
    "family_dashboard_viewed",
    "activity_created",
    "avatar_session_completed",
    "companion_summary_created",
}
AVATAR_MODE_ALIASES = {
    "static": "static-css",
    "css": "static-css",
    "2d": "2d-viseme",
    "viseme": "2d-viseme",
    "live": "liveavatar",
    "live-avatar": "liveavatar",
}
COMPANION_TEMPLATES = {
    "nening-real-female": {"defaultName": "寧寧", "backendChar": "寧寧"},
    "companion-real-male": {"defaultName": "阿宏", "backendChar": "阿宏"},
    "munea-2d-xiaoyun": {"defaultName": "小昀", "backendChar": "小昀"},
    "munea-2d-ayuan": {"defaultName": "阿原", "backendChar": "阿原"},
    "munea-2d-mimi": {"defaultName": "咪咪", "backendChar": "咪咪"},
    "munea-2d-wangcai": {"defaultName": "旺財", "backendChar": "旺財"},
}
COMPANION_ALIASES = {
    "real-f": "nening-real-female",
    "real-m": "companion-real-male",
    "toon-f": "munea-2d-xiaoyun",
    "toon-m": "munea-2d-ayuan",
    "cat": "munea-2d-mimi",
    "dog": "munea-2d-wangcai",
}
JSON_STORE_LOCK = threading.RLock()
LOGGER = logging.getLogger("munea.server")


def log_fallback_exception(context, exc):
    LOGGER.warning(
        "%s failed; using prototype fallback: %s",
        context,
        exc,
        exc_info=os.environ.get("MUNEA_DEBUG_TRACEBACK") == "1",
    )


def normalize_template_id(template_id):
    template_id = COMPANION_ALIASES.get(template_id, template_id)
    return template_id if template_id in COMPANION_TEMPLATES else "nening-real-female"


def normalize_companion_profile(data=None):
    data = data or {}
    template_id = normalize_template_id(data.get("templateId") or data.get("template_id"))
    default_name = COMPANION_TEMPLATES[template_id]["defaultName"]
    display_name = (data.get("displayName") or data.get("display_name") or default_name).strip()[:12] or default_name
    return {
        "templateId": template_id,
        "displayName": display_name,
        "nameTouched": bool(data.get("nameTouched") or data.get("name_touched")),
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def request_id():
    return "req_" + str(int(time.time() * 1000))


def is_uuid_like(value):
    try:
        uuid.UUID(str(value or ""))
        return True
    except Exception:
        return False


def public_supabase_key():
    return (
        os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("MUNEA_SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("MUNEA_SUPABASE_ANON_KEY")
        or ""
    )


def extract_bearer_token(headers=None):
    headers = headers or {}
    raw = headers.get("Authorization") or headers.get("authorization") or ""
    parts = raw.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def verify_dev_auth_token(token):
    if os.environ.get("MUNEA_ENABLE_DEV_AUTH_BYPASS") != "true":
        return None
    if not token or not token.startswith("dev-local-token-"):
        return None
    auth_user_id = token.replace("dev-local-token-", "", 1).strip()
    if not auth_user_id:
        return None
    return {
        "ok": True,
        "provider": "dev-bypass",
        "developerMode": True,
        "authUserId": auth_user_id,
        "email": "developer@munea.local",
    }


def verify_supabase_access_token(token):
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = public_supabase_key()
    if not url or not key:
        return {"ok": False, "code": "auth_not_configured"}
    req = urllib.request.Request(
        url + "/auth/v1/user",
        headers={
            "apikey": key,
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "code": "invalid_auth_token", "status": e.code}
    except Exception as e:
        log_fallback_exception("supabase auth token verification", e)
        return {"ok": False, "code": "auth_verification_unavailable"}
    auth_user_id = payload.get("id") or payload.get("sub")
    if not is_uuid_like(auth_user_id):
        return {"ok": False, "code": "invalid_auth_user"}
    return {
        "ok": True,
        "provider": payload.get("app_metadata", {}).get("provider") or "supabase",
        "developerMode": False,
        "authUserId": auth_user_id,
        "email": payload.get("email"),
        "user": payload,
    }


def verify_auth_context(headers=None):
    token = extract_bearer_token(headers)
    if not token:
        return {"ok": False, "code": "auth_token_missing"}
    dev = verify_dev_auth_token(token)
    if dev:
        return dev
    return verify_supabase_access_token(token)


PUBLIC_POST_PATHS = {"/auth-status", "/account-bootstrap", "/apple/notifications"}
ADMIN_POST_PATHS = {
    "/admin/accounts",
    "/admin/north-star",
    "/admin/usage",
    "/admin/credits",
    "/admin/subscription-metrics",
    "/admin/conversation-summaries",
    "/admin/privacy-requests",
    "/admin/feedback",
    "/admin/safety-events",
    "/admin/audit-events",
    "/admin/voice-diagnostics",
    "/admin/notifications/drain",
    "/admin/login",
    # 維護入口（2026-07-17 補）：晨料備製與記憶整理是定時鬧鐘（Cloud Scheduler）用
    # 管理鑰匙呼叫的，沒有用戶登入證可帶——漏列在這裡＝鬧鐘永遠被會員門擋下。
    # 三個入口的處理端本來就各自再驗一次管理鑰匙（admin_authorized），不是開放門。
    "/admin/daily-briefing",
    "/admin/memory-consolidate",
    "/admin/memory-living-profile",
}
PRIVILEGED_BILLING_POST_PATHS = {"/subscription-event", "/credits/grant", "/credits/consume"}


def auth_required_mode():
    return str(os.environ.get("MUNEA_REQUIRE_AUTH") or "").strip().lower() in {"1", "true", "yes", "on"}


def auth_required_for_path(path):
    return auth_required_mode() and path not in PUBLIC_POST_PATHS and path not in ADMIN_POST_PATHS


def auth_required_for_request(path, data=None):
    data = data or {}
    if not auth_required_for_path(path):
        return False
    if path in PRIVILEGED_BILLING_POST_PATHS:
        return False
    if path == "/entitlements" and (data.get("action") or "load").lower() in ("save", "replace"):
        return False
    return True


def require_verified_auth(headers=None, path="", data=None):
    if not auth_required_for_request(path, data):
        return {"ok": True, "required": False}
    auth_context = verify_auth_context(headers)
    if not auth_context.get("ok"):
        return {
            "ok": False,
            "required": True,
            "code": auth_context.get("code") or "auth_required",
            "auth": public_auth_context(auth_context),
        }
    return {"ok": True, "required": True, "auth": public_auth_context(auth_context)}


def public_auth_context(auth_context):
    return {
        "verified": bool(auth_context.get("ok")),
        "provider": auth_context.get("provider"),
        "developerMode": bool(auth_context.get("developerMode")),
        "authUserId": auth_context.get("authUserId"),
        "email": auth_context.get("email"),
        "errorCode": None if auth_context.get("ok") else auth_context.get("code"),
    }


def auth_status_response(headers=None):
    auth_context = verify_auth_context(headers)
    return {
        "ok": bool(auth_context.get("ok")),
        "auth": public_auth_context(auth_context),
        "error": None if auth_context.get("ok") else {
            "code": auth_context.get("code") or "auth_invalid",
            "requestId": request_id(),
        },
    }


def read_json_file(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback
    except Exception as e:
        log_fallback_exception(f"read_json_file({os.path.basename(path)})", e)
        return fallback


def write_json_file(path, data):
    with JSON_STORE_LOCK:
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}.{int(time.time() * 1000)}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError as e:
                    log_fallback_exception(f"remove temp json file {os.path.basename(tmp_path)}", e)


REQUEST_DATA_IDENTITY = contextvars.ContextVar("munea_request_data_identity", default=None)


def data_backend():
    return supabase_adapter.make_adapter(identity=REQUEST_DATA_IDENTITY.get())


def bind_request_data_identity(auth_gate, allow_missing=False):
    if not auth_gate.get("required"):
        return None
    auth_user_id = (auth_gate.get("auth") or {}).get("authUserId")
    base_backend = supabase_adapter.make_adapter()
    if not base_backend.configured():
        return None
    identity = base_backend.resolve_auth_identity(auth_user_id)
    if not identity:
        if allow_missing:
            return None
        raise PermissionError("account_scope_missing")
    return REQUEST_DATA_IDENTITY.set(identity)


SCOPE_EXEMPT_PATHS = PUBLIC_POST_PATHS | ADMIN_POST_PATHS | PRIVILEGED_BILLING_POST_PATHS | {"/family/invitations", "/family-relays"}
ACCOUNT_SCOPE_KEYS = {"accountid"}
FAMILY_SCOPE_KEYS = {"familygroupid"}
PERSON_SCOPE_KEYS = {
    "personid",
    "primarycarerecipientid",
    "ownerpersonid",
    "inviterpersonid",
    "inviteepersonid",
    "grantedbypersonid",
    "updatedbypersonid",
}


def _request_scope_values(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).replace("_", "").lower()
            if normalized_key in ACCOUNT_SCOPE_KEYS | FAMILY_SCOPE_KEYS | PERSON_SCOPE_KEYS:
                if child not in (None, ""):
                    yield normalized_key, str(child)
            elif isinstance(child, (dict, list)):
                yield from _request_scope_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _request_scope_values(child)


def authorize_request_data_scope(path, data, auth_gate):
    path = str(path or "").split("?", 1)[0]
    if not auth_gate.get("required") or path in SCOPE_EXEMPT_PATHS:
        return
    backend = data_backend()
    if not backend.enabled():
        return

    checked = set()
    for key, value in _request_scope_values(data or {}):
        pair = (key, value)
        if pair in checked:
            continue
        checked.add(pair)
        if key in ACCOUNT_SCOPE_KEYS:
            allowed = backend.owns_account_id(value)
        elif key in FAMILY_SCOPE_KEYS:
            allowed = backend.owns_family_group_id(value)
        else:
            allowed = backend.owns_person_id(value)
        if not allowed:
            raise PermissionError("request_scope_forbidden")


def data_backend_status():
    status = data_backend().status()
    status["fallback"] = "json"
    return status


def load_memory_items(limit=200):
    try:
        remote_items = data_backend().load_memory_items(limit=limit)
        if remote_items is not None:
            return remote_items
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load memory items from Supabase", e)
    items = read_json_file(MEMORY_ITEMS_PATH, [])
    if not isinstance(items, list):
        items = []
    return items[-limit:]


def save_memory_items(items):
    write_json_file(MEMORY_ITEMS_PATH, list(items)[-1000:])
    return items


def append_memory_items(items):
    items = items or []
    try:
        remote_items = data_backend().save_memory_items(items)
        if remote_items is not None:
            return remote_items
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("append memory items to Supabase", e)
    existing = load_memory_items(limit=1000)
    save_memory_items(existing + items)
    return items


def _string_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def normalize_conversation_summary(item=None):
    item = item or {}
    summary = item.get("summary") or item.get("text") or ""
    created_at = item.get("createdAt") or item.get("created_at") or utc_now()
    return {
        "id": item.get("id") or ("local-conversation-summary-" + uuid.uuid4().hex[:10]),
        "accountId": item.get("accountId") or item.get("account_id") or "local-account",
        "personId": item.get("personId") or item.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "voiceSessionId": item.get("voiceSessionId") or item.get("voice_session_id"),
        "summary": str(summary).strip(),
        "memoryTags": _string_list(item.get("memoryTags") or item.get("memory_tags") or item.get("tags")),
        "safetyRelevant": bool(item.get("safetyRelevant") or item.get("safety_relevant")),
        "createdAt": created_at,
        "deletedAt": item.get("deletedAt") or item.get("deleted_at"),
        "privacy": {
            "storesRawTranscriptByDefault": False,
            "retainedRecord": "summary_only",
        },
    }


def load_conversation_summaries(person_id=None, limit=100, include_deleted=False):
    try:
        remote_items = data_backend().load_conversation_summaries(
            {"personId": person_id, "includeDeleted": include_deleted},
            limit=limit,
        )
        if remote_items is not None:
            return remote_items
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load conversation summaries from Supabase", e)
    items = read_json_file(CONVERSATION_SUMMARIES_PATH, [])
    if not isinstance(items, list):
        items = []
    normalized = [normalize_conversation_summary(item) for item in items]
    if person_id:
        normalized = [item for item in normalized if item.get("personId") == person_id]
    if not include_deleted:
        normalized = [item for item in normalized if not item.get("deletedAt")]
    return normalized[-limit:]


def save_conversation_summaries(items):
    write_json_file(CONVERSATION_SUMMARIES_PATH, list(items)[-1000:])
    return items


def append_conversation_summary(item):
    item = normalize_conversation_summary(item)
    if not item["summary"]:
        return None
    try:
        remote_item = data_backend().save_conversation_summary(item)
        if remote_item is not None:
            return remote_item
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("append conversation summary to Supabase", e)
    existing = load_conversation_summaries(limit=1000, include_deleted=True)
    existing = [row for row in existing if row.get("id") != item["id"]]
    existing.append(item)
    save_conversation_summaries(existing)
    return item


def archive_conversation_summary(summary_id):
    if not summary_id:
        return None
    deleted_at = utc_now()
    try:
        remote_item = data_backend().soft_delete_conversation_summary(summary_id, deleted_at)
        if remote_item is not None:
            return remote_item
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("archive conversation summary in Supabase", e)
    items = load_conversation_summaries(limit=1000, include_deleted=True)
    archived = None
    for item in items:
        if item.get("id") == summary_id:
            item["deletedAt"] = deleted_at
            archived = item
            break
    if archived:
        save_conversation_summaries(items)
    return archived


LIVING_PROFILE_PATH = os.environ.get("MUNEA_LIVING_PROFILE_PATH") or os.path.join(HERE, "living_profile.json")


def load_living_profile(person_id=None):
    """「這位長輩現在是誰」的側寫——只能給本人看。

    這支原本沒有「是誰的」概念：一個檔、全站共用、每一輪都塞進她腦裡。
    而檔案裡躺的是示範假資料（一位 72 歲、有高血壓和膝蓋痛的奶奶）——
    等於誰來聊天，她都把那個人的病史當成對方的講回去。第二個用戶一進來就是真的外洩。

    改成蓋章制：側寫存的時候要蓋「這是誰的」；沒蓋章、或蓋的是別人，一律不給。
    寧可她說「我還不夠認識你」，也不能拿別人的高血壓當成他的。
    """
    prof = read_json_file(LIVING_PROFILE_PATH, {})
    if not isinstance(prof, dict) or not prof:
        return {}
    person_id = person_id or _current_person_id()
    if not person_id:
        return {}                      # 認不出是誰 → 不給任何人的側寫
    if prof.get("personId") != person_id:
        return {}                      # 沒蓋章 or 是別人的 → 不給
    return prof


def save_living_profile(profile):
    write_json_file(LIVING_PROFILE_PATH, profile or {})
    return profile


def refresh_living_profile(person_id=None):
    """活的側寫：重讀全部記憶 → 合成一張「這位長輩現在是誰」→ 存起來供聊天/主動開口取用。
    設計為『每週』由背景重跑一次（頻率旋鈕待 Edward 拍板）。"""
    items = load_memory_items(limit=1000)
    try:
        import memory_engine
        profile = memory_engine.build_living_profile(items)
    except Exception as e:
        log_fallback_exception("build living profile", e)
        profile = {}
    if profile:
        profile["updatedAt"] = utc_now()
        # 蓋章「這張側寫是誰的」——沒蓋章的側寫不會被端到任何人面前（見 load_living_profile）
        profile["personId"] = person_id or _current_person_id() or ""
        save_living_profile(profile)
    return {"ok": bool(profile), "brain": "butler", "action": "living_profile",
            "profile": profile, "basedOnMemories": len(items)}


# 她看不到身體數據時的圍籬——寫死一份在這，給「連 health_context 都掛了」時當保險。
# 為什麼要有備份：這道圍籬是唯一擋著她憑空編「你今天血壓有點高喔」的東西，
# 不能因為某支程式壞掉就消失。失敗只能往「她不知道」倒。
HEALTH_FENCE_WHEN_BLIND = (
    "（他的身體狀況：**你現在什麼都看不到**——他的血壓、心跳、血氧、睡眠、吃藥紀錄"
    "都沒有傳到你這裡。所以**絕對不要講任何他的健康數字、不要說「你今天血壓有點高」"
    "「你最近睡不好喔」這種你根本不知道的話**（講了就是捏造，長輩會當真、傷害信任）。"
    "他自己告訴你的、或你們聊過的，才可以接話。想知道就問他。）"
)


def _current_person_id():
    """現在在跟誰講話——只認已驗證的身分，不認外面傳進來的欄位（那可以偽造）。"""
    return (REQUEST_DATA_IDENTITY.get() or {}).get("personId") or None


def _current_family_group_id():
    return (REQUEST_DATA_IDENTITY.get() or {}).get("familyGroupId") or None


def load_health_context(person_id=None, family_group_id=None):
    """這個人自己的身體狀況 → 她心裡知道的事實（檔位 2「知道但不多嘴」）。

    資料其實早就在了：手機把 Apple 健康的血壓/心跳/血氧/睡眠/步數同步進家庭帳本、
    用藥有自己的紀錄、心情趨勢也算好了。問題是這些全都是「存起來給家人看」的——
    水管是「長輩 → 雲端 → 家人畫面」，AI 站在水管外面。這支就是把她接上去。

    兩條原則：
    - 認不出是誰就回空。寧可她說「我不知道」，也不能把別人的血壓當成他的。
    - 哪一段撈不到就當那段沒有。上游圍籬會據此告訴她「這塊你不知道、不准編」。
    """
    person_id = person_id or _current_person_id()
    if not person_id:
        return {"facts": [], "notable": [], "hasData": False}
    family_group_id = family_group_id or _current_family_group_id()

    try:
        import perception_engine
        today = (perception_engine.now_context() or {}).get("date") or ""
    except Exception:
        today = ""

    vitals_entry, doses, trend = None, None, None
    try:
        state = family_state_response({"action": "load", "familyGroupId": family_group_id or "shared"})
        vitals = (state.get("state") or {}).get("vitals") or {}
        if isinstance(vitals, dict):
            vitals_entry = vitals.get(person_id)
    except Exception as e:
        log_fallback_exception("load vitals for health context", e)
    try:
        doses = load_medication_doses(person_id=person_id, start_date=today, end_date=today, limit=50)
    except Exception as e:
        log_fallback_exception("load medication doses for health context", e)
    try:
        trend = wellbeing_trend_response({"personId": person_id, "days": 7})
    except Exception as e:
        log_fallback_exception("load wellbeing trend for health context", e)

    try:
        import health_context
        return health_context.build(vitals_entry=vitals_entry, doses=doses, mood_trend=trend, today=today)
    except Exception as e:
        log_fallback_exception("build health context", e)
        return {"facts": [], "notable": [], "hasData": False}


def _invalidate_memory_items(ids):
    """把被取代的舊記憶下架：Supabase 用軟刪除（deleted_at，可還原），本機 JSON 直接移除。
    下架後就不再被召回，寧寧回話用當下版本、不吐過時事實。"""
    ids = [i for i in (ids or []) if i]
    if not ids:
        return
    backend = data_backend()
    if backend.enabled():
        try:
            backend.soft_delete_memory_items(ids, utc_now())
            return
        except Exception as e:
            if backend.enabled():
                raise e
            log_fallback_exception("invalidate superseded memory (supabase)", e)
    remove = set(ids)
    kept = [it for it in load_memory_items(limit=1000) if it.get("id") not in remove]
    save_memory_items(kept)


WELLBEING_PATH = os.environ.get("MUNEA_WELLBEING_PATH") or os.path.join(HERE, "wellbeing_signals.json")
CARE_SCHEDULE_PATH = os.environ.get("MUNEA_CARE_SCHEDULE_PATH") or os.path.join(HERE, "care_schedule.json")
MEDICATION_DOSES_PATH = os.environ.get("MUNEA_MEDICATION_DOSES_PATH") or os.path.join(HERE, "medication_doses.json")


def append_wellbeing_signal(signal):
    """存一筆「心情觀察」訊號（統一格式 WellbeingSignal：V2 影像/動作將來也吐同格式）。"""
    try:
        remote_signal = data_backend().append_wellbeing_signal(signal)
        if remote_signal is not None:
            return remote_signal
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("append wellbeing signal to Supabase", e)
    signals = read_json_file(WELLBEING_PATH, [])
    if not isinstance(signals, list):
        signals = []
    signals.append(signal)
    write_json_file(WELLBEING_PATH, signals[-2000:])
    return signal


def load_wellbeing_signals(person_id=None, limit=200):
    try:
        remote_signals = data_backend().load_wellbeing_signals(person_id=person_id, limit=limit)
        if remote_signals is not None:
            return remote_signals
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load wellbeing signals from Supabase", e)
    signals = read_json_file(WELLBEING_PATH, [])
    if not isinstance(signals, list):
        signals = []
    if person_id:
        signals = [s for s in signals if s.get("personId") == person_id]
    return signals[-limit:]


FAMILY_STATE_KEYS = {"activities", "familyFeed", "meds", "visit", "visits", "routine", "wallet", "circle", "vitals"}

FAMILY_STATE_SUPABASE_KEYS = {"circle", "activities", "familyFeed", "meds", "visit", "routine", "wallet", "vitals"}  # 雲端桌子收的鑰匙（vitals 需 008 遷移；沒上桌前自動退引擎本子）

def _looks_like_uuid(v):
    try:
        uuid.UUID(str(v))
        return True
    except Exception:
        return False

def _family_state_json_all():
    """引擎本子：分家記帳 {家庭編號: {key: {value, updatedAt}}}；老格式（扁平）自動搬進 'shared' 這一家。"""
    try:
        state = read_json_file(FAMILY_STATE_STORE_PATH) or {}
    except Exception:
        state = {}
    if state and any(k in FAMILY_STATE_KEYS for k in state.keys()):
        state = {"shared": state}
    return state

def family_state_response(data):
    """家庭共享狀態：每家一本帳（familyGroupId 分家）。正式編號（UUID）走雲端桌子；
    試營運的裝置編號走引擎本子——真帳號上線後自動回到雲端桌子、格式不變。"""
    data = data or {}
    action = data.get("action") or "load"
    group = str(data.get("familyGroupId") or data.get("family_group_id") or "shared")
    group_uuid = group if _looks_like_uuid(group) else None
    use_supabase = bool(group_uuid) or group == "shared"
    # A former subscriber must never retain read access merely because an
    # asynchronous membership cleanup has not run yet.  Their own free circle
    # remains usable; only a cross-account circle is denied.
    if group_uuid:
        try:
            backend = data_backend()
            if backend.enabled():
                family_account_id = backend.family_group_account_id(group_uuid)
                billing = load_billing_store()
                if family_account_id and family_account_id != backend.account_id and billing.get("activePlan") == "free":
                    return {"ok": False, "error": "family_access_expired"}
        except Exception as e:
            log_fallback_exception("check expired cross-family access", e)
    if action == "save":
        key = data.get("key")
        if key not in FAMILY_STATE_KEYS:
            return {"ok": False, "error": "key_not_allowed"}
        value_to_store = data.get("value")
        if key == "vitals":
            # 健康數據＝每人一份（7/9 Edward「數據真同步」）：跟既有帳「按人合併」、
            # 絕不整包覆蓋——否則兩支手機互相蓋掉對方的數據。進來的格式 {personId: {..當天摘要..}}。
            incoming = value_to_store if isinstance(value_to_store, dict) else {}
            current = {}
            if use_supabase:
                try:
                    remote_state = data_backend().load_family_state_store(family_group_id=group_uuid)
                    ent = (remote_state or {}).get("vitals")
                    if isinstance(ent, dict) and isinstance(ent.get("value"), dict):
                        current = dict(ent["value"])
                except Exception as e:
                    log_fallback_exception("load vitals for merge", e)
            if not current:
                ent = (_family_state_json_all().get(group) or {}).get("vitals") or {}
                if isinstance(ent.get("value"), dict):
                    current = dict(ent["value"])
            current.update(incoming)
            value_to_store = current
        if use_supabase and key in FAMILY_STATE_SUPABASE_KEYS:
            try:
                backend = data_backend()
                remote_entry = backend.save_family_state_entry(
                    key,
                    value_to_store,
                    family_group_id=group_uuid,
                    updated_by_person_id=data.get("personId") or data.get("person_id"),
                )
                if remote_entry is not None:
                    return {"ok": True, "key": key, "backend": "supabase"}
            except Exception as e:
                # 23514＝雲端桌子還不認這把鑰匙（vitals 待 008 遷移）→ 安靜退引擎本子、不炸用戶
                if data_backend().enabled() and not is_missing_table_error(e) and "22P02" not in str(e) and "23514" not in str(e):
                    raise e
                log_fallback_exception("save family state to Supabase", e)
        allstate = _family_state_json_all()
        g = allstate.setdefault(group, {})
        g[key] = {"value": value_to_store, "updatedAt": now_iso() if "now_iso" in globals() else time.strftime("%Y-%m-%dT%H:%M:%S")}
        write_json_file(FAMILY_STATE_STORE_PATH, allstate)
        return {"ok": True, "key": key, "backend": "json"}
    merged = {}
    backend_name = "json"
    if use_supabase:
        try:
            remote_state = data_backend().load_family_state_store(family_group_id=group_uuid)
            if remote_state is not None:
                backend_name = "supabase"
                merged.update({k: v.get("value") for k, v in remote_state.items() if isinstance(v, dict)})
        except Exception as e:
            if data_backend().enabled() and not is_missing_table_error(e) and "22P02" not in str(e):
                raise e
            log_fallback_exception("load family state from Supabase", e)
    allstate = _family_state_json_all()
    for k, v in (allstate.get(group) or {}).items():
        if isinstance(v, dict):
            merged[k] = v.get("value")
    return {"ok": True, "state": merged, "backend": backend_name}

FAMILY_INVITATION_STATUSES = {"pending", "applied", "accepted", "rejected", "revoked", "expired"}

def normalize_family_invitation(invitation):
    invitation = invitation or {}
    status = invitation.get("status") or "pending"
    created_at = invitation.get("createdAt") or invitation.get("created_at") or utc_now()
    expires_at = invitation.get("expiresAt") or invitation.get("expires_at")
    if not expires_at:
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
    short_code = str(invitation.get("shortCode") or invitation.get("short_code") or "").strip()
    if not (len(short_code) == 6 and short_code.isdigit()):
        short_code = str(uuid.uuid4().int % 1_000_000).zfill(6)
    share_token = invitation.get("shareToken") or invitation.get("share_token") or invitation.get("token")
    token_hash = invitation.get("tokenHash") or invitation.get("token_hash")
    return {
        "id": str(invitation.get("id") or ("fam_inv_" + uuid.uuid4().hex[:10])),
        "accountId": invitation.get("accountId") or invitation.get("account_id") or "local-demo-account",
        "familyGroupId": invitation.get("familyGroupId") or invitation.get("family_group_id") or "local-demo-family",
        "inviterPersonId": invitation.get("inviterPersonId") or invitation.get("inviter_person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "inviteePersonId": invitation.get("inviteePersonId") or invitation.get("invitee_person_id"),
        "shortCode": short_code,
        "shareToken": share_token,
        "tokenHash": token_hash or ("local-" + uuid.uuid4().hex),
        "deliveryHint": invitation.get("deliveryHint") or invitation.get("delivery_hint"),
        "elderAssisted": bool(invitation.get("elderAssisted") or invitation.get("elder_assisted") or False),
        "status": status if status in FAMILY_INVITATION_STATUSES else "pending",
        "expiresAt": expires_at,
        "acceptedAt": invitation.get("acceptedAt") or invitation.get("accepted_at"),
        "revokedAt": invitation.get("revokedAt") or invitation.get("revoked_at"),
        "metadata": invitation.get("metadata") or {},
        "createdAt": created_at,
        "updatedAt": invitation.get("updatedAt") or invitation.get("updated_at") or created_at,
    }


def public_family_invitation(invitation, include_share_token=False):
    invitation = normalize_family_invitation(invitation)
    public = {k: v for k, v in invitation.items() if k not in {"tokenHash", "shareToken"}}
    if include_share_token and invitation.get("shareToken"):
        public["shareToken"] = invitation.get("shareToken")
    return public


def load_family_invitations(family_group_id=None, status=None, limit=100):
    try:
        remote_invitations = data_backend().load_family_invitations(family_group_id=family_group_id, status=status, limit=limit)
        if remote_invitations is not None:
            return [public_family_invitation(inv) for inv in remote_invitations]
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e) and "22P02" not in str(e):
            raise e
        log_fallback_exception("load family invitations from Supabase", e)
    invitations = read_json_file(FAMILY_INVITATIONS_PATH, [])
    if not isinstance(invitations, list):
        invitations = []
    invitations = [normalize_family_invitation(inv) for inv in invitations]
    if family_group_id:
        invitations = [inv for inv in invitations if inv.get("familyGroupId") == family_group_id]
    if status:
        invitations = [inv for inv in invitations if inv.get("status") == status]
    return [public_family_invitation(inv) for inv in invitations[-limit:]]


def create_family_invitation(invitation):
    invitation = invitation or {}
    share_token = invitation.get("shareToken") or invitation.get("share_token") or ("munea_" + uuid.uuid4().hex)
    invitation = normalize_family_invitation({**(invitation or {}), "shareToken": share_token, "status": "pending", "updatedAt": utc_now()})
    try:
        remote_invitation = data_backend().create_family_invitation(invitation)
        if remote_invitation is not None:
            return public_family_invitation({**remote_invitation, "shareToken": share_token}, include_share_token=True), "supabase"
    except Exception as e:
        # 22P02＝雲端桌子要正式編號（真帳號上線前給的是裝置編號）→ 退引擎本子記帳、功能照常
        if data_backend().enabled() and not is_missing_table_error(e) and "22P02" not in str(e):
            raise e
        log_fallback_exception("create family invitation in Supabase", e)
    invitations = read_json_file(FAMILY_INVITATIONS_PATH, [])
    if not isinstance(invitations, list):
        invitations = []
    invitations.append(invitation)
    write_json_file(FAMILY_INVITATIONS_PATH, invitations[-1000:])
    return public_family_invitation(invitation, include_share_token=True), "json"


def update_family_invitation(invitation_id, patch):
    patch = patch or {}
    status = patch.get("status")
    if status and status not in FAMILY_INVITATION_STATUSES:
        return None, "invalid_status"
    try:
        remote_invitation = data_backend().update_family_invitation(invitation_id, patch)
        if remote_invitation is not None:
            return public_family_invitation(remote_invitation), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e) and "22P02" not in str(e):
            raise e
        log_fallback_exception("update family invitation in Supabase", e)
    invitations = read_json_file(FAMILY_INVITATIONS_PATH, [])
    if not isinstance(invitations, list):
        invitations = []
    next_invitations = []
    updated = None
    for invitation in invitations:
        current = normalize_family_invitation(invitation)
        if current.get("id") == invitation_id:
            now = utc_now()
            current = normalize_family_invitation({**current, **patch, "updatedAt": now})
            if current.get("status") == "accepted" and not current.get("acceptedAt"):
                current["acceptedAt"] = now
            if current.get("status") == "revoked" and not current.get("revokedAt"):
                current["revokedAt"] = now
            updated = current
        next_invitations.append(current)
    write_json_file(FAMILY_INVITATIONS_PATH, next_invitations[-1000:])
    return (public_family_invitation(updated), "json") if updated else (None, "not_found")


FAMILY_CIRCLE_LIMITS = {"plus": 4, "pro": 12}


def family_actor_backend(actor):
    """Return the authenticated actor's scoped backend, or a safe error code.

    Family-circle membership is sensitive health-adjacent data.  Unlike the
    prototype's UI-only guard, all membership mutations require a verified
    account which has already been bootstrapped into Supabase.
    """
    auth_user_id = str((actor or {}).get("authUserId") or "")
    backend = data_backend()
    if not auth_user_id:
        return None, "auth_required"
    if not backend.enabled() or not backend.request_scoped:
        return None, "family_cloud_identity_required"
    if backend.auth_user_id != auth_user_id:
        return None, "family_identity_mismatch"
    return backend, None


def family_plan_entitlement(backend):
    """Get a server-verified plan and member limit; never trust client plan data."""
    try:
        billing = normalize_billing_store(backend.load_billing_store() or {})
    except Exception as e:
        log_fallback_exception("load family entitlement", e)
        return None, "family_entitlement_unavailable"
    plan = str(billing.get("activePlan") or "free").lower()
    subscription = billing.get("subscription") or {}
    if plan not in FAMILY_CIRCLE_LIMITS or subscription.get("status") != "active" or billing.get("serverVerificationRequired", True):
        return None, "family_plan_required"
    return {"plan": plan, "maxMembers": FAMILY_CIRCLE_LIMITS[plan]}, None


def find_pending_family_invitation_by_code(short_code):
    """Locate an exact one-time code without exposing another family's list."""
    try:
        remote = supabase_adapter.make_adapter().find_pending_family_invitation_by_short_code(short_code)
        if remote is not None:
            return public_family_invitation(remote), "supabase"
    except Exception as e:
        log_fallback_exception("find family invitation by code", e)
    invitations = read_json_file(FAMILY_INVITATIONS_PATH, [])
    matches = [normalize_family_invitation(inv) for inv in invitations if isinstance(inv, dict)
               and str(inv.get("shortCode") or "") == short_code
               and str(inv.get("status") or "pending") == "pending"]
    return (public_family_invitation(matches[0]), "json") if len(matches) == 1 else (None, "not_found")


def update_family_invitation_after_code_exchange(invitation_id, patch):
    """Server-side update paired with the exact-code lookup above."""
    try:
        remote = supabase_adapter.make_adapter().update_family_invitation_by_id_unscoped(invitation_id, patch)
        if remote is not None:
            return public_family_invitation(remote), "supabase"
    except Exception as e:
        log_fallback_exception("complete family invitation exchange", e)
    # JSON is only the development fallback. Production reaches the scoped
    # Supabase update above after verified authentication.
    invitations = read_json_file(FAMILY_INVITATIONS_PATH, [])
    next_invitations, updated = [], None
    for invitation in invitations if isinstance(invitations, list) else []:
        current = normalize_family_invitation(invitation)
        if current.get("id") == invitation_id:
            current = normalize_family_invitation({**current, **(patch or {}), "updatedAt": utc_now()})
            updated = current
        next_invitations.append(current)
    if updated is not None:
        write_json_file(FAMILY_INVITATIONS_PATH, next_invitations[-1000:])
        return public_family_invitation(updated), "json"
    return None, "not_found"


def family_circle_member_count(family_group_id):
    try:
        remote_count = supabase_adapter.make_adapter().count_family_members_unscoped(family_group_id)
        if remote_count is not None:
            return remote_count
    except Exception as e:
        log_fallback_exception("load family circle for capacity check", e)
    state = _family_state_json_all().get(family_group_id) or {}
    circle = (state.get("circle") or {}).get("value")
    return len(circle) if isinstance(circle, list) else 0


def add_family_member_after_invitation(family_group_id, person_id):
    try:
        member = supabase_adapter.make_adapter().add_family_member_after_invitation_unscoped(family_group_id, person_id)
        if member is not None:
            return member, None
    except Exception as e:
        log_fallback_exception("add accepted family member", e)
    return None, "family_membership_provision_failed"


def _mask_email(email):
    email = str(email or "").strip()
    if "@" not in email:
        return None
    name, dom = email.split("@", 1)
    return ((name[0] + "***") if name else "***") + "@" + dom


def family_invitations_response(data, client_ip=None, actor=None):
    data = data or {}
    action = str(data.get("action") or "list").lower()
    backend, actor_error = family_actor_backend(actor)
    if actor_error:
        return {"ok": False, "error": actor_error}
    if action == "create":
        if not backend.is_account_owner():
            return {"ok": False, "error": "family_owner_required"}
        entitlement, entitlement_error = family_plan_entitlement(backend)
        if entitlement_error:
            return {"ok": False, "error": entitlement_error}
        # Derive all authority-bearing fields server-side.  In particular, a
        # browser cannot forge a larger limit, another family id, or another
        # person's identity by editing the request body.
        invitation, storage_backend = create_family_invitation({
            "familyGroupId": backend.family_group_id,
            "inviterPersonId": backend.person_id,
            "metadata": {
                "plan": entitlement["plan"],
                "maxMembers": entitlement["maxMembers"],
                "ownerAuthUserId": backend.auth_user_id,
                "ownerPersonId": backend.person_id,
            },
        })
        return {"ok": True, "invitation": invitation, "backend": storage_backend}
    if action in ("accept", "apply"):
        # 審核制（2026-07-11 Edward）：輸入邀請碼 → 變「申請中」、不直接進圈；要 owner 按通過才加入。
        # 防爆破（P0-3）：同來源猜錯太多次就暫時擋。
        if invite_rate_limited(client_ip):
            return {"ok": False, "error": "too_many_attempts"}
        raw_code = str(data.get("shortCode") or data.get("short_code") or data.get("code") or "")
        short_code = "".join(ch for ch in raw_code if ch.isdigit())[-6:]
        if len(short_code) != 6:
            record_invite_failure(client_ip)
            return {"ok": False, "error": "short_code_required"}
        match, _match_backend = find_pending_family_invitation_by_code(short_code)
        if not match:
            record_invite_failure(client_ip)
            return {"ok": False, "error": "invitation_not_found"}
        try:
            exp = str(match.get("expiresAt") or "").replace("Z", "+00:00")
            if exp and datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                return {"ok": False, "error": "invitation_expired"}
        except Exception as e:
            log_fallback_exception("parse family invitation expiry", e)
        entitlement, entitlement_error = family_plan_entitlement(backend)
        if entitlement_error:
            return {"ok": False, "error": entitlement_error}
        # 跟舊版相容：現行 App 送 accept ＝ 舊行為（直接進圈），新審核 UI 送 apply ＝ 申請制。
        # 兩者可並存，等 App 審核 UI 上線後，accept 再切成也走申請制。
        if action == "accept":
            try:
                max_members = int(((match.get("metadata") or {}).get("maxMembers")) or 0)
                if max_members and family_circle_member_count(match.get("familyGroupId")) >= max_members:
                    return {"ok": False, "error": "circle_full"}
            except Exception as e:
                log_fallback_exception("check family invitation member limit", e)
            member, member_error = add_family_member_after_invitation(match.get("familyGroupId"), backend.person_id)
            if member_error:
                return {"ok": False, "error": member_error}
            invitation, storage_backend = update_family_invitation_after_code_exchange(match.get("id"), {
                "status": "accepted",
                "acceptedAt": utc_now(),
                "inviteePersonId": backend.person_id,
                "metadata": {**(match.get("metadata") or {}),
                             "inviteeName": str(data.get("inviteeName") or data.get("invitee_name") or "")[:24],
                             "inviteeAuthUserId": backend.auth_user_id,
                             "inviteePlan": entitlement["plan"]},
            })
            if invitation is None:
                return {"ok": False, "error": storage_backend}
            return {"ok": True, "invitation": invitation, "backend": storage_backend}
        # action == "apply"：新審核制——存申請人資訊、標「申請中」等 owner 審。不回 familyGroupId＝進不了圈。
        applicant = {
            "inviteeName": str(data.get("inviteeName") or data.get("invitee_name") or "")[:24],
            "applicantPersonId": backend.person_id,
            "applicantAuthUserId": backend.auth_user_id,
            "applicantLoginProvider": data.get("loginProvider") or data.get("login_provider"),
            "applicantEmailMasked": _mask_email(data.get("email") or data.get("applicantEmail")),
            "appliedAt": utc_now(),
        }
        invitation, storage_backend = update_family_invitation_after_code_exchange(match.get("id"), {
            "status": "applied",
            "inviteePersonId": backend.person_id,
            "metadata": {**(match.get("metadata") or {}), **applicant},
        })
        if invitation is None:
            return {"ok": False, "error": storage_backend}
        return {"ok": True, "status": "applied", "pendingApproval": True,
                "invitationId": invitation.get("id"),
                "message": "已送出申請，等對方確認後就會加入。"}
    if action in ("list_pending", "list-pending"):
        # owner 看有誰在申請：回這個圈 status=applied 的邀請＋申請人資訊（最小揭露）
        family_group_id = data.get("familyGroupId") or data.get("family_group_id")
        if not backend.is_account_owner() or family_group_id != backend.family_group_id:
            return {"ok": False, "error": "family_owner_required"}
        pending = load_family_invitations(family_group_id=family_group_id, status="applied", limit=100)
        applicants = [{
            "invitationId": inv.get("id"),
            "name": (inv.get("metadata") or {}).get("inviteeName") or "（未填名字）",
            "loginProvider": (inv.get("metadata") or {}).get("applicantLoginProvider"),
            "emailMasked": (inv.get("metadata") or {}).get("applicantEmailMasked"),
            "appliedAt": (inv.get("metadata") or {}).get("appliedAt"),
        } for inv in pending]
        return {"ok": True, "applicants": applicants, "count": len(applicants)}
    if action == "approve":
        # owner 按通過：再驗人數上限 → 標 accepted ＋ 記歸屬（auth↔person↔family，解 BOLA 地基）→ 回 familyGroupId 讓成員進圈
        invitation_id = data.get("id") or data.get("invitationId") or data.get("invitation_id")
        if not invitation_id:
            return {"ok": False, "error": "invitation_id_required"}
        target = None
        for inv in load_family_invitations(limit=500):
            if inv.get("id") == invitation_id:
                target = inv
        if not target or target.get("status") != "applied":
            return {"ok": False, "error": "application_not_found"}
        if not backend.is_account_owner() or (target.get("metadata") or {}).get("ownerAuthUserId") != backend.auth_user_id:
            return {"ok": False, "error": "family_owner_required"}
        try:
            max_members = int(((target.get("metadata") or {}).get("maxMembers")) or 0)
            if max_members:
                if max_members and family_circle_member_count(target.get("familyGroupId")) >= max_members:
                    return {"ok": False, "error": "circle_full"}
        except Exception as e:
            log_fallback_exception("check circle limit on approve", e)
        md = target.get("metadata") or {}
        invitation, backend = update_family_invitation(invitation_id, {
            "status": "accepted",
            "acceptedAt": utc_now(),
            "metadata": {**md, "approvedAt": utc_now(),
                         "membership": {"authUserId": md.get("applicantAuthUserId"),
                                        "personId": target.get("inviteePersonId"),
                                        "familyGroupId": target.get("familyGroupId")}},
        })
        if invitation is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "invitation": invitation, "familyGroupId": target.get("familyGroupId"),
                "member": {"name": md.get("inviteeName"), "personId": target.get("inviteePersonId")}, "backend": backend}
    if action == "reject":
        # owner 按不通過：刪這筆申請（碼作廢）
        invitation_id = data.get("id") or data.get("invitationId") or data.get("invitation_id")
        if not invitation_id:
            return {"ok": False, "error": "invitation_id_required"}
        target = next((inv for inv in load_family_invitations(limit=500) if inv.get("id") == invitation_id), None)
        if not target or not backend.is_account_owner() or (target.get("metadata") or {}).get("ownerAuthUserId") != backend.auth_user_id:
            return {"ok": False, "error": "family_owner_required"}
        invitation, backend = update_family_invitation(invitation_id, {"status": "rejected", "revokedAt": utc_now()})
        if invitation is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "status": "rejected", "invitation": invitation, "backend": backend}
    if action in ("application_status", "application-status"):
        # 申請人用自己的申請單編號查「被核准了嗎」；只有 accepted 才給 familyGroupId（入圈鑰匙）
        invitation_id = data.get("id") or data.get("invitationId") or data.get("invitation_id")
        if not invitation_id:
            return {"ok": False, "error": "invitation_id_required"}
        found = None
        for inv in load_family_invitations(limit=500):
            if inv.get("id") == invitation_id:
                found = inv
        if not found:
            return {"ok": True, "status": "not_found"}
        if (found.get("metadata") or {}).get("applicantAuthUserId") != backend.auth_user_id:
            return {"ok": False, "error": "application_forbidden"}
        st = found.get("status")
        out = {"ok": True, "status": st}
        if st == "accepted":
            out["familyGroupId"] = found.get("familyGroupId")
        return out
    return {"ok": False, "error": "family_invitation_action_not_allowed"}

CONSENT_RECORD_STATUSES = {"granted", "revoked", "expired"}

def normalize_consent_record(record):
    record = record or {}
    status = record.get("status") or "granted"
    consent_type = record.get("consentType") or record.get("consent_type") or "ai_provider_processing"
    granted_at = record.get("grantedAt") or record.get("granted_at") or record.get("createdAt") or record.get("created_at") or utc_now()
    return {
        "id": str(record.get("id") or ("consent_" + uuid.uuid4().hex[:10])),
        "accountId": record.get("accountId") or record.get("account_id") or "local-demo-account",
        "personId": record.get("personId") or record.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "familyGroupId": record.get("familyGroupId") or record.get("family_group_id"),
        "consentType": str(consent_type),
        "consentVersion": record.get("consentVersion") or record.get("consent_version") or "v1",
        "status": status if status in CONSENT_RECORD_STATUSES else "granted",
        "grantedByPersonId": record.get("grantedByPersonId") or record.get("granted_by_person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "source": record.get("source") or "munea-api",
        "scope": record.get("scope") or {},
        "evidence": record.get("evidence") or {},
        "grantedAt": granted_at,
        "revokedAt": record.get("revokedAt") or record.get("revoked_at"),
        "expiresAt": record.get("expiresAt") or record.get("expires_at"),
        "createdAt": record.get("createdAt") or record.get("created_at") or granted_at,
    }


def load_consent_records(person_id=None, consent_type=None, status=None, limit=100):
    try:
        remote_records = data_backend().load_consent_records(person_id=person_id, consent_type=consent_type, status=status, limit=limit)
        if remote_records is not None:
            return [normalize_consent_record(r) for r in remote_records]
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load consent records from Supabase", e)
    records = read_json_file(CONSENT_RECORDS_PATH, [])
    if not isinstance(records, list):
        records = []
    records = [normalize_consent_record(r) for r in records]
    if person_id:
        records = [r for r in records if r.get("personId") == person_id]
    if consent_type:
        records = [r for r in records if r.get("consentType") == consent_type]
    if status:
        records = [r for r in records if r.get("status") == status]
    return records[-limit:]


def grant_consent_record(record):
    record = normalize_consent_record({**(record or {}), "status": "granted", "grantedAt": utc_now()})
    try:
        remote_record = data_backend().append_consent_record(record)
        if remote_record is not None:
            return normalize_consent_record(remote_record), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("grant consent record in Supabase", e)
    records = read_json_file(CONSENT_RECORDS_PATH, [])
    if not isinstance(records, list):
        records = []
    records.append(record)
    write_json_file(CONSENT_RECORDS_PATH, records[-2000:])
    return record, "json"


def revoke_consent_record(record_id=None, person_id=None, consent_type=None, revoked_by_person_id=None):
    patch = {
        "status": "revoked",
        "revokedAt": utc_now(),
        "revokedByPersonId": revoked_by_person_id or PRIMARY_CARE_RECIPIENT_ID,
    }
    try:
        remote_record = data_backend().revoke_consent_record(record_id, person_id=person_id, consent_type=consent_type, patch=patch)
        if remote_record is not None:
            return normalize_consent_record(remote_record), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("revoke consent record in Supabase", e)
    records = read_json_file(CONSENT_RECORDS_PATH, [])
    if not isinstance(records, list):
        records = []
    next_records = []
    updated = None
    for record in records:
        current = normalize_consent_record(record)
        matches_id = bool(record_id and current.get("id") == record_id)
        matches_type = bool((not record_id) and person_id and consent_type and current.get("personId") == person_id and current.get("consentType") == consent_type and current.get("status") == "granted")
        if matches_id or matches_type:
            current = normalize_consent_record({
                **current,
                "status": "revoked",
                "revokedAt": patch["revokedAt"],
                "evidence": {**(current.get("evidence") or {}), "revokedByPersonId": patch["revokedByPersonId"]},
            })
            updated = current
        next_records.append(current)
    write_json_file(CONSENT_RECORDS_PATH, next_records[-2000:])
    return (updated, "json") if updated else (None, "not_found")


def consent_records_response(data):
    data = data or {}
    action = data.get("action") or "list"
    if action in ("grant", "create"):
        record, backend = grant_consent_record(data.get("record") or data)
        return {"ok": True, "record": record, "backend": backend}
    if action == "revoke":
        record_id = data.get("id") or data.get("recordId") or data.get("record_id")
        person_id = data.get("personId") or data.get("person_id")
        consent_type = data.get("consentType") or data.get("consent_type")
        if not record_id and not (person_id and consent_type):
            return {"ok": False, "error": "consent_record_or_type_required"}
        record, backend = revoke_consent_record(
            record_id=record_id,
            person_id=person_id,
            consent_type=consent_type,
            revoked_by_person_id=data.get("revokedByPersonId") or data.get("revoked_by_person_id"),
        )
        if record is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "record": record, "backend": backend}
    person_id = data.get("personId") or data.get("person_id")
    consent_type = data.get("consentType") or data.get("consent_type")
    status = data.get("status")
    limit = int(data.get("limit") or 100)
    return {"ok": True, "records": load_consent_records(person_id=person_id, consent_type=consent_type, status=status, limit=limit)}

FAMILY_ACTIVITY_TYPES = {"walk", "quiz", "event", "vote", "draw", "custom"}
FAMILY_ACTIVITY_STATUSES = {"draft", "active", "completed", "archived", "cancelled"}
FAMILY_PARTICIPANT_STATUSES = {"invited", "accepted", "declined", "completed"}

def normalize_family_activity(activity):
    activity = activity or {}
    activity_id = str(activity.get("id") or ("fam_act_" + uuid.uuid4().hex[:10]))
    activity_type = activity.get("type") or activity.get("activityType") or activity.get("activity_type") or "custom"
    status = activity.get("status") or "active"
    participants = activity.get("participants") if isinstance(activity.get("participants"), list) else []
    return {
        "id": activity_id,
        "familyGroupId": activity.get("familyGroupId") or activity.get("family_group_id") or "local-demo-family",
        "ownerPersonId": activity.get("ownerPersonId") or activity.get("owner_person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "type": activity_type if activity_type in FAMILY_ACTIVITY_TYPES else "custom",
        "title": str(activity.get("title") or "Family activity"),
        "status": status if status in FAMILY_ACTIVITY_STATUSES else "active",
        "startsAt": activity.get("startsAt") or activity.get("starts_at"),
        "endsAt": activity.get("endsAt") or activity.get("ends_at"),
        "payload": activity.get("payload") or {},
        "result": activity.get("result") or {},
        "participants": [normalize_family_activity_participant(p) for p in participants],
        "createdAt": activity.get("createdAt") or activity.get("created_at") or utc_now(),
        "updatedAt": activity.get("updatedAt") or activity.get("updated_at") or utc_now(),
        "archivedAt": activity.get("archivedAt") or activity.get("archived_at"),
    }


def normalize_family_activity_participant(participant):
    participant = participant or {}
    status = participant.get("status") or "invited"
    return {
        "id": participant.get("id") or "",
        "activityId": participant.get("activityId") or participant.get("family_activity_id"),
        "personId": participant.get("personId") or participant.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "role": participant.get("role") or "participant",
        "status": status if status in FAMILY_PARTICIPANT_STATUSES else "invited",
        "contribution": participant.get("contribution") or {},
        "response": participant.get("response") or {},
        "createdAt": participant.get("createdAt") or participant.get("created_at"),
        "updatedAt": participant.get("updatedAt") or participant.get("updated_at") or utc_now(),
    }


def load_family_activities(family_group_id=None, status=None, limit=100):
    try:
        remote_activities = data_backend().load_family_activities(family_group_id=family_group_id, status=status, limit=limit)
        if remote_activities is not None:
            return [normalize_family_activity(a) for a in remote_activities]
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load family activities from Supabase", e)
    activities = read_json_file(FAMILY_ACTIVITIES_PATH, [])
    if not isinstance(activities, list):
        activities = []
    activities = [normalize_family_activity(a) for a in activities]
    if family_group_id:
        activities = [a for a in activities if a.get("familyGroupId") == family_group_id]
    if status:
        activities = [a for a in activities if a.get("status") == status]
    return activities[-limit:]


def save_family_activity(activity):
    activity = normalize_family_activity({**(activity or {}), "updatedAt": utc_now()})
    try:
        remote_activity = data_backend().save_family_activity(activity)
        if remote_activity is not None:
            return normalize_family_activity(remote_activity), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("save family activity to Supabase", e)
    activities = load_family_activities(limit=1000)
    next_activities = [a for a in activities if a.get("id") != activity.get("id")]
    next_activities.append(activity)
    write_json_file(FAMILY_ACTIVITIES_PATH, next_activities[-1000:])
    return activity, "json"


def save_family_activity_participant(activity_id, participant):
    participant = normalize_family_activity_participant({**(participant or {}), "activityId": activity_id, "updatedAt": utc_now()})
    try:
        remote_participant = data_backend().save_family_activity_participant(activity_id, participant)
        if remote_participant is not None:
            return normalize_family_activity_participant(remote_participant), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("save family activity participant to Supabase", e)
    activities = load_family_activities(limit=1000)
    next_activities = []
    for activity in activities:
        if activity.get("id") == activity_id:
            participants = [p for p in activity.get("participants", []) if p.get("personId") != participant.get("personId")]
            participants.append(participant)
            activity = {**activity, "participants": participants, "updatedAt": utc_now()}
        next_activities.append(activity)
    write_json_file(FAMILY_ACTIVITIES_PATH, next_activities[-1000:])
    return participant, "json"


def family_activity_response(data):
    data = data or {}
    action = data.get("action") or "list"
    if action == "save":
        activity, backend = save_family_activity(data.get("activity") or data)
        return {"ok": True, "activity": activity, "backend": backend}
    if action == "participant":
        activity_id = data.get("activityId") or data.get("activity_id")
        if not activity_id:
            return {"ok": False, "error": "activity_id_required"}
        participant, backend = save_family_activity_participant(activity_id, data.get("participant") or data)
        return {"ok": True, "participant": participant, "backend": backend}
    family_group_id = data.get("familyGroupId") or data.get("family_group_id")
    status = data.get("status")
    limit = int(data.get("limit") or 100)
    activities = load_family_activities(family_group_id=family_group_id, status=status, limit=limit)
    return {"ok": True, "activities": activities}


def wellbeing_log_response(data):
    """情緒球手動打卡：寫一筆『自我回報』心情訊號，與聊聊觀察同一本帳（wellbeing_signals）。"""
    data = data or {}
    person_id = data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID
    mood = data.get("mood") or "平靜"
    try:
        import perception_engine
        d = perception_engine.now_context()["date"]
    except Exception:
        d = time.strftime("%Y-%m-%d")
    signal = {
        "id": "wb_" + uuid.uuid4().hex[:10],
        "personId": person_id,
        "date": d,
        "modality": "manual",
        "signalType": "mood",
        "source": "self-report",
        "mood": mood,
        "moodKey": data.get("moodKey"),
        "moodColor": data.get("moodColor") or {},
        "level": data.get("level") if data.get("level") is not None else 3,
        "levelLabel": mood,
        "confidence": 1.0,
        "isMedicalInference": False,
        "createdAt": utc_now(),
    }
    signal = append_wellbeing_signal(signal)
    # 追蹤：心情打卡記一筆 product event（後台「心情」面板未來的真資料源；失敗不影響打卡）
    try:
        append_product_event({
            "eventName": "mood_logged",
            "personId": person_id,
            "source": "munea-api",
            "properties": {"mood": mood, "moodKey": data.get("moodKey"), "level": signal.get("level")},
        })
    except Exception as e:
        log_fallback_exception("emit mood_logged product event", e)
    return {"ok": True, "signal": signal}


def wellbeing_recent_response(data):
    """情緒球讀取：近期原始心情訊號（含時間），前端用來算當前色與當天主色。"""
    data = data or {}
    person_id = data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID
    limit = int(data.get("limit") or 400)
    signals = load_wellbeing_signals(person_id, limit=limit)
    out = []
    for sig in signals:
        if sig.get("signalType") and sig.get("signalType") != "mood":
            continue
        out.append({
            "mood": sig.get("mood"),
            "moodKey": sig.get("moodKey"),
            "moodColor": sig.get("moodColor"),
            "level": sig.get("level"),
            "source": sig.get("source") or ("self-report" if sig.get("modality") == "manual" else "observation"),
            "date": sig.get("date"),
            "createdAt": sig.get("createdAt"),
        })
    return {"ok": True, "signals": out}


def wellbeing_trend_response(data):
    """心情趨勢（餵 App 心情天氣卡）：近 N 天每日聚合＋個人基準線＋溫柔提示判斷。
    鐵律：給的是觀察與天氣等級，絕無 0-100 分數、絕無臨床字眼。"""
    data = data or {}
    person_id = data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID
    days = int(data.get("days") or 7)
    signals = load_wellbeing_signals(person_id, limit=500)
    by_date = {}
    for s in signals:
        d = s.get("date")
        if d:
            by_date.setdefault(d, []).append(s)
    dates = sorted(by_date.keys())
    daily = []
    for d in dates[-days:]:
        rows = by_date[d]
        avg = sum(r.get("level", 3) for r in rows) / len(rows)
        latest = rows[-1]
        moods = [r.get("mood") for r in rows if r.get("mood")]
        dominant = latest.get("mood") or "平穩"  # 日總結＝最近一次為主
        daily.append({
            "date": d,
            "mood": dominant,
            "moodColor": latest.get("moodColor"),
            "mixed": len(set(moods)) > 1,          # 當天不只一種心情 → 顯示層加小點
            "chats": len(rows),
            "level": round(avg, 1),
            "levelLabel": dominant,
            "voiceObs": latest.get("voiceObs"),
            "chatObs": latest.get("chatObs"),
            "topics": latest.get("topics") or [],
            "signals": [{                          # 點該日展開：每次聊天各自的心情＋一句觀察
                "mood": r.get("mood"),
                "oneLine": r.get("wordObs") or r.get("chatObs") or "",
                "createdAt": r.get("createdAt"),
            } for r in rows],
        })
    # 個人基準線＝再往前 14 天的平均（跟自己比、不跟量表比）
    base_dates = dates[:-3] if len(dates) > 3 else []
    base_rows = [r for d in base_dates[-14:] for r in by_date[d]]
    baseline = round(sum(r.get("level", 3) for r in base_rows) / len(base_rows), 2) if base_rows else None
    recent_rows = [r for d in dates[-3:] for r in by_date[d]]
    recent = round(sum(r.get("level", 3) for r in recent_rows) / len(recent_rows), 2) if recent_rows else None
    concern = bool(baseline and recent and len(recent_rows) >= 2 and recent <= baseline - 0.8)
    gentle_note = ""
    if concern:
        gentle_note = "這幾天聊天比平常安靜一些。不一定有什麼事——但也許是打通電話回家的好時機。"
    import perception_engine
    return {"ok": True, "personId": person_id, "daily": daily,
            "baseline": baseline, "recent": recent,
            "gentleConcern": concern, "gentleNote": gentle_note,
            "display": {"moodMap": perception_engine.MOOD_CATEGORIES,   # 六類心情圖譜（App 直接取色）
                        "selfView": "today_only",                        # 自己只看今天；週/月在圖表頁
                        "rule": "觀察不是判定；絕無分數、絕無臨床字眼"}}


def load_care_schedule(person_id=None):
    remote_items = load_routine_reminders(person_id=person_id, status="active", limit=500)
    if remote_items:
        return [routine_reminder_to_care_item(item) for item in remote_items]
    items = read_json_file(CARE_SCHEDULE_PATH, [])
    if not isinstance(items, list):
        items = []
    if person_id:
        items = [i for i in items if i.get("personId") in (None, person_id)]
    return items


def today_care_items(person_id=None):
    """今天的照護行事曆（回診/用藥日/重要日子）：date 精確比對或 weekday 每週重複。"""
    import perception_engine
    ctx = perception_engine.now_context()
    out = []
    for it in load_care_schedule(person_id):
        if it.get("date") == ctx["date"] or (it.get("weekday") and it.get("weekday") == ctx["weekday"]):
            if it.get("label"):
                out.append(it["label"])
    return out


def care_schedule_response(data):
    data = data or {}
    action = data.get("action") or "list"
    person_id = data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID
    if action == "add":
        reminder = {
            "personId": person_id,
            "title": (data.get("label") or data.get("title") or "").strip()[:80],
            "type": data.get("type") or data.get("reminderType") or data.get("reminder_type") or "routine",
            "schedule": {"date": data.get("date"), "weekday": data.get("weekday"), **(data.get("schedule") or {})},
            "status": "active",
        }
        item, backend = save_routine_reminder(reminder)
        return {"ok": True, "action": "add", "item": routine_reminder_to_care_item(item), "backend": backend}
    if action == "remove":
        rid = data.get("id")
        item, backend = update_routine_reminder(rid, {"status": "archived"})
        return {"ok": True, "action": "remove", "id": rid, "backend": backend, "item": item}
    return {"ok": True, "action": "list", "items": load_care_schedule(person_id),
            "today": today_care_items(person_id)}

ROUTINE_REMINDER_TYPES = {"medication", "routine", "check_in", "custom"}
ROUTINE_REMINDER_STATUSES = {"active", "paused", "archived"}

def normalize_routine_reminder(item):
    item = item or {}
    reminder_type = item.get("type") or item.get("reminderType") or item.get("reminder_type") or "routine"
    status = item.get("status") or "active"
    title = item.get("title") or item.get("label") or "Routine reminder"
    schedule = dict(item.get("schedule") or {})
    # 用藥照片只留使用者裝置本機、不進雲端（隱私政策對外承諾）。
    # 伺服器端強制剝除，因為已安裝的舊版 App 仍會在 schedule 夾帶 base64 照片。
    schedule.pop("photo", None)
    for key in ("date", "weekday", "time", "times", "dosage", "note", "repeat"):
        if key in item and item.get(key) is not None:
            schedule.setdefault(key, item.get(key))
    return {
        "id": str(item.get("id") or ("rr_" + uuid.uuid4().hex[:10])),
        "accountId": item.get("accountId") or item.get("account_id") or "local-demo-account",
        "personId": item.get("personId") or item.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "title": str(title).strip()[:120] or "Routine reminder",
        "type": reminder_type if reminder_type in ROUTINE_REMINDER_TYPES else "custom",
        "status": status if status in ROUTINE_REMINDER_STATUSES else "active",
        "schedule": schedule,
        "createdAt": item.get("createdAt") or item.get("created_at") or utc_now(),
        "updatedAt": item.get("updatedAt") or item.get("updated_at") or utc_now(),
        "deletedAt": item.get("deletedAt") or item.get("deleted_at"),
    }


def routine_reminder_to_care_item(item):
    reminder = normalize_routine_reminder(item)
    schedule = reminder.get("schedule") or {}
    return {
        "id": reminder.get("id"),
        "personId": reminder.get("personId"),
        "label": reminder.get("title"),
        "date": schedule.get("date"),
        "weekday": schedule.get("weekday"),
        "type": reminder.get("type"),
        "status": reminder.get("status"),
        "schedule": schedule,
        "createdAt": reminder.get("createdAt"),
        "updatedAt": reminder.get("updatedAt"),
    }


def load_routine_reminders(person_id=None, status=None, limit=100):
    try:
        remote_items = data_backend().load_routine_reminders(person_id=person_id, status=status, limit=limit)
        if remote_items is not None:
            return [normalize_routine_reminder(item) for item in remote_items]
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load routine reminders from Supabase", e)
    items = read_json_file(CARE_SCHEDULE_PATH, [])
    if not isinstance(items, list):
        items = []
    items = [normalize_routine_reminder(item) for item in items]
    if person_id:
        items = [item for item in items if item.get("personId") in (None, person_id)]
    if status:
        items = [item for item in items if item.get("status") == status]
    return items[-limit:]


def save_routine_reminder(item):
    reminder = normalize_routine_reminder({**(item or {}), "updatedAt": utc_now()})
    try:
        remote_item = data_backend().save_routine_reminder(reminder)
        if remote_item is not None:
            return normalize_routine_reminder(remote_item), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("save routine reminder to Supabase", e)
    items = load_routine_reminders(limit=1000)
    next_items = [item for item in items if item.get("id") != reminder.get("id")]
    next_items.append(reminder)
    write_json_file(CARE_SCHEDULE_PATH, next_items[-1000:])
    return reminder, "json"


def update_routine_reminder(reminder_id, patch):
    if not reminder_id:
        return None, "reminder_id_required"
    patch = patch or {}
    try:
        remote_item = data_backend().update_routine_reminder(reminder_id, patch)
        if remote_item is not None:
            return normalize_routine_reminder(remote_item), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("update routine reminder in Supabase", e)
    items = load_routine_reminders(limit=1000)
    updated = None
    next_items = []
    for item in items:
        if item.get("id") == reminder_id:
            merged_schedule = {**(item.get("schedule") or {}), **(patch.get("schedule") or {})}
            item = normalize_routine_reminder({**item, **patch, "schedule": merged_schedule, "updatedAt": utc_now()})
            updated = item
        next_items.append(item)
    write_json_file(CARE_SCHEDULE_PATH, next_items[-1000:])
    return (updated, "json") if updated else (None, "not_found")


def routine_reminders_response(data):
    data = data or {}
    action = data.get("action") or "list"
    if action in ("save", "create", "add"):
        item, backend = save_routine_reminder(data.get("reminder") or data.get("item") or data)
        return {"ok": True, "reminder": item, "backend": backend}
    if action in ("update", "patch", "archive", "pause", "activate"):
        reminder_id = data.get("id") or data.get("reminderId") or data.get("reminder_id")
        patch = data.get("patch") or data
        if action == "archive":
            patch = {**patch, "status": "archived"}
        elif action == "pause":
            patch = {**patch, "status": "paused"}
        elif action == "activate":
            patch = {**patch, "status": "active"}
        item, backend = update_routine_reminder(reminder_id, patch)
        if item is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "reminder": item, "backend": backend}
    person_id = data.get("personId") or data.get("person_id")
    status = data.get("status")
    limit = int(data.get("limit") or 100)
    return {"ok": True, "reminders": load_routine_reminders(person_id=person_id, status=status, limit=limit)}


MEDICATION_DOSE_STATUSES = {"scheduled", "taken", "snoozed", "skipped", "missed"}


def normalize_medication_dose(item):
    item = item or {}
    status = item.get("status") or "scheduled"
    scheduled_date = str(item.get("scheduledDate") or item.get("scheduled_date") or utc_now()[:10])[:10]
    try:
        datetime.strptime(scheduled_date, "%Y-%m-%d")
    except (TypeError, ValueError):
        scheduled_date = utc_now()[:10]
    try:
        expected_count = int(item.get("expectedCount") or item.get("expected_count") or 0)
    except (TypeError, ValueError):
        expected_count = 0
    dose_key = str(item.get("doseKey") or item.get("dose_key") or "").strip()[:240]
    return {
        "id": str(item.get("id") or ("md_" + uuid.uuid4().hex[:16])),
        "accountId": item.get("accountId") or item.get("account_id") or "local-demo-account",
        "personId": item.get("personId") or item.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "reminderId": item.get("reminderId") or item.get("reminder_id"),
        "doseKey": dose_key,
        "medicationName": str(item.get("medicationName") or item.get("medication_name") or "用藥")[:160],
        "slot": str(item.get("slot") or item.get("slotLabel") or item.get("slot_label") or "")[:80],
        "scheduledDate": scheduled_date,
        "scheduledAt": item.get("scheduledAt") or item.get("scheduled_at"),
        "expectedCount": max(0, min(100, expected_count)),
        "status": status if status in MEDICATION_DOSE_STATUSES else "scheduled",
        "takenAt": item.get("takenAt") or item.get("taken_at") if status == "taken" else None,
        "source": str(item.get("source") or "munea-app")[:80],
        "timezone": str(item.get("timezone") or "Asia/Taipei")[:80],
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        "createdAt": item.get("createdAt") or item.get("created_at") or utc_now(),
        "updatedAt": item.get("updatedAt") or item.get("updated_at") or utc_now(),
    }


def load_medication_doses(person_id=None, start_date=None, end_date=None, limit=1000):
    limit = max(1, min(5000, int(limit or 1000)))
    try:
        remote_items = data_backend().load_medication_doses(
            person_id=person_id, start_date=start_date, end_date=end_date, limit=limit
        )
        if remote_items is not None:
            return [normalize_medication_dose(item) for item in remote_items]
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load medication doses from Supabase", e)
    items = read_json_file(MEDICATION_DOSES_PATH, [])
    if not isinstance(items, list):
        items = []
    items = [normalize_medication_dose(item) for item in items]
    if person_id:
        items = [item for item in items if item.get("personId") == person_id]
    if start_date:
        items = [item for item in items if item.get("scheduledDate", "") >= str(start_date)[:10]]
    if end_date:
        items = [item for item in items if item.get("scheduledDate", "") <= str(end_date)[:10]]
    items.sort(key=lambda item: (item.get("scheduledDate") or "", item.get("updatedAt") or ""), reverse=True)
    return items[:limit]


def save_medication_dose(item):
    dose = normalize_medication_dose({**(item or {}), "updatedAt": utc_now()})
    if not dose.get("doseKey"):
        return None, "dose_key_required"
    try:
        remote_item = data_backend().save_medication_dose(dose)
        if remote_item is not None:
            return normalize_medication_dose(remote_item), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("save medication dose to Supabase", e)
    items = load_medication_doses(limit=5000)
    identity = (dose.get("personId"), dose.get("doseKey"))
    next_items = [item for item in items if (item.get("personId"), item.get("doseKey")) != identity]
    next_items.append(dose)
    write_json_file(MEDICATION_DOSES_PATH, next_items[-10000:])
    return dose, "json"


def medication_doses_response(data):
    data = data or {}
    action = (data.get("action") or "list").lower()
    if action in ("save", "upsert", "record"):
        dose, backend = save_medication_dose(data.get("dose") or data.get("item") or data)
        if dose is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "dose": dose, "backend": backend}
    return {
        "ok": True,
        "doses": load_medication_doses(
            person_id=data.get("personId") or data.get("person_id"),
            start_date=data.get("startDate") or data.get("start_date"),
            end_date=data.get("endDate") or data.get("end_date"),
            limit=data.get("limit") or 1000,
        ),
    }


def _notification_identity():
    identity = REQUEST_DATA_IDENTITY.get() or {}
    return {
        "accountId": identity.get("accountId") or identity.get("account_id"),
        "personId": identity.get("personId") or identity.get("person_id"),
        "authUserId": identity.get("authUserId") or identity.get("auth_user_id"),
    }


def load_notification_settings(person_id=None):
    """通知中心設定（總開關＋分類）。沒存過＝預設值（推播關、分類全開）。"""
    identity = _notification_identity()
    person = person_id or identity.get("personId") or PRIMARY_CARE_RECIPIENT_ID
    backend = data_backend()
    if backend.enabled():
        try:
            row = backend.load_notification_settings(person)
            if row is not None:
                return notification_service.normalize_notification_settings(row)
        except Exception as e:
            if not is_missing_table_error(e):
                raise
            log_fallback_exception("load notification settings", e)
    items = read_json_file(NOTIFICATION_SETTINGS_PATH, {})
    row = items.get(person) if isinstance(items, dict) else None
    settings = notification_service.normalize_notification_settings(row or {})
    settings["personId"] = person
    return settings


def save_notification_settings(patch, person_id=None):
    """只收 pushEnabled 與四個分類；其他欄位一律忽略。冪等。"""
    current = load_notification_settings(person_id)
    merged = dict(current)
    if isinstance(patch, dict):
        if "pushEnabled" in patch:
            merged["pushEnabled"] = bool(patch["pushEnabled"])
        cats = patch.get("categories")
        if isinstance(cats, dict):
            merged["categories"] = {
                **current["categories"],
                **{k: bool(v) for k, v in cats.items()
                   if k in notification_service.NOTIFICATION_CATEGORIES},
            }
    merged["updatedAt"] = utc_now()
    backend = data_backend()
    if backend.enabled():
        try:
            saved = backend.save_notification_settings(merged)
            if saved is not None:
                return notification_service.normalize_notification_settings(saved)
        except Exception as e:
            if not is_missing_table_error(e):
                raise
            log_fallback_exception("save notification settings", e)
    items = read_json_file(NOTIFICATION_SETTINGS_PATH, {})
    if not isinstance(items, dict):
        items = {}
    items[merged["personId"]] = merged
    write_json_file(NOTIFICATION_SETTINGS_PATH, items)
    return merged


def notification_settings_response(data):
    data = data or {}
    if str(data.get("action") or "get") == "set":
        settings = save_notification_settings(data)
    else:
        settings = load_notification_settings()
    return {"ok": True, "settings": settings}


def load_push_devices(include_invalid=False, limit=20):
    backend = data_backend()
    if backend.enabled():
        items = backend.load_push_devices(include_invalid=include_invalid, limit=limit)
        return [notification_service.public_device(item) for item in items or []], "supabase"
    identity = _notification_identity()
    items = read_json_file(PUSH_DEVICES_PATH, [])
    if not isinstance(items, list):
        items = []
    items = [notification_service.normalize_device(item) for item in items]
    if identity.get("accountId"):
        items = [item for item in items if item.get("accountId") == identity.get("accountId")]
    if identity.get("personId"):
        items = [item for item in items if item.get("personId") == identity.get("personId")]
    if not include_invalid:
        items = [item for item in items if not item.get("invalidatedAt")]
    items.sort(key=lambda item: item.get("lastSeenAt") or "", reverse=True)
    return [notification_service.public_device(item) for item in items[:max(1, min(int(limit or 20), 100))]], "json"


def save_push_device(item):
    identity = _notification_identity()
    device = notification_service.normalize_device(item, identity=identity)
    error = notification_service.validate_device(device)
    if error:
        return None, error
    backend = data_backend()
    if backend.enabled():
        saved = backend.upsert_push_device(device)
        return notification_service.public_device(saved), "supabase"
    items = read_json_file(PUSH_DEVICES_PATH, [])
    if not isinstance(items, list):
        items = []
    existing = None
    next_items = []
    for raw in items:
        current = notification_service.normalize_device(raw)
        same_token = (
            current.get("tokenHash") == device.get("tokenHash")
            and current.get("environment") == device.get("environment")
            and current.get("bundleId") == device.get("bundleId")
        )
        if same_token:
            existing = current
            continue
        next_items.append(current)
    device["id"] = (existing or {}).get("id") or str(uuid.uuid4())
    device["createdAt"] = (existing or {}).get("createdAt") or notification_service.utc_now()
    device["updatedAt"] = notification_service.utc_now()
    device["invalidatedAt"] = None
    next_items.append(device)
    write_json_file(PUSH_DEVICES_PATH, next_items[-100:])
    return notification_service.public_device(device), "json"


def disable_push_device(device_id=None, token_hash=None):
    backend = data_backend()
    if backend.enabled():
        item = backend.disable_push_device(device_id=device_id, token_hash=token_hash)
        return (notification_service.public_device(item), "supabase") if item else (None, "push_device_not_found")
    identity = _notification_identity()
    items = read_json_file(PUSH_DEVICES_PATH, [])
    updated = None
    next_items = []
    for raw in items if isinstance(items, list) else []:
        item = notification_service.normalize_device(raw)
        owns = (
            (not identity.get("accountId") or item.get("accountId") == identity.get("accountId"))
            and (not identity.get("personId") or item.get("personId") == identity.get("personId"))
        )
        matches = item.get("id") == device_id or (token_hash and item.get("tokenHash") == token_hash)
        if owns and matches:
            item["notificationsEnabled"] = False
            item["invalidatedAt"] = notification_service.utc_now()
            item["updatedAt"] = notification_service.utc_now()
            updated = item
        next_items.append(item)
    write_json_file(PUSH_DEVICES_PATH, next_items[-100:])
    return (notification_service.public_device(updated), "json") if updated else (None, "push_device_not_found")


def push_devices_response(data):
    data = data or {}
    action = str(data.get("action") or "list").lower()
    if action in ("register", "save", "update_permission"):
        device, backend = save_push_device(data.get("device") or data)
        if device is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "device": device, "backend": backend}
    if action in ("unregister", "disable"):
        item, backend = disable_push_device(
            device_id=data.get("id") or data.get("deviceId") or data.get("device_id"),
            token_hash=data.get("tokenHash") or data.get("token_hash"),
        )
        if item is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "device": item, "backend": backend}
    devices, backend = load_push_devices(
        include_invalid=bool(data.get("includeInvalid") or data.get("include_invalid")),
        limit=data.get("limit") or 20,
    )
    return {"ok": True, "devices": devices, "backend": backend}


def enqueue_notification_event(item, recipient_person_id=None, actor_person_id=None):
    raw_event_type = str((item or {}).get("eventType") or (item or {}).get("event_type") or "").strip()
    if raw_event_type not in notification_service.EVENT_TYPES:
        return None, "notification_event_type_invalid"
    event = notification_service.normalize_event(
        item, recipient_person_id=recipient_person_id, actor_person_id=actor_person_id
    )
    error = notification_service.validate_event(event)
    if error:
        return None, error
    backend = data_backend()
    if backend.enabled():
        saved = backend.enqueue_notification_event(event)
        return notification_service.normalize_event(saved), "supabase"
    events = read_json_file(NOTIFICATION_EVENTS_PATH, [])
    if not isinstance(events, list):
        events = []
    if event.get("dedupeKey"):
        existing = next((candidate for candidate in events
                         if candidate.get("recipientPersonId") == event.get("recipientPersonId")
                         and candidate.get("dedupeKey") == event.get("dedupeKey")), None)
        if existing:
            return notification_service.normalize_event(existing), "json"
    events.append(event)
    write_json_file(NOTIFICATION_EVENTS_PATH, events[-10000:])

    devices = read_json_file(PUSH_DEVICES_PATH, [])
    deliveries = read_json_file(NOTIFICATION_DELIVERIES_PATH, [])
    deliveries = deliveries if isinstance(deliveries, list) else []
    # 通知中心設定：收件人關掉的類別只寫事件、不建推播投遞
    recipient_settings = load_notification_settings(event.get("recipientPersonId"))
    if not notification_service.push_allowed(recipient_settings, event.get("eventType")):
        devices = []
    for raw in devices if isinstance(devices, list) else []:
        device = notification_service.normalize_device(raw)
        if (device.get("personId") == event.get("recipientPersonId")
                and device.get("notificationsEnabled")
                and not device.get("invalidatedAt")
                and device.get("permissionStatus") in ("authorized", "provisional")):
            delivery_key = f"{event['id']}:{device['id']}:apns"
            if any(candidate.get("deliveryKey") == delivery_key for candidate in deliveries):
                continue
            deliveries.append({
                "id": str(uuid.uuid4()),
                "deliveryKey": delivery_key,
                "eventId": event["id"],
                "deviceId": device["id"],
                "channel": "apns",
                "status": "queued",
                "attemptCount": 0,
                "nextAttemptAt": notification_service.utc_now(),
                "createdAt": notification_service.utc_now(),
            })
    write_json_file(NOTIFICATION_DELIVERIES_PATH, deliveries[-20000:])
    return event, "json"


def load_notification_events(unread_only=False, include_archived=False, event_type=None, limit=100):
    backend = data_backend()
    if backend.enabled():
        items = backend.load_notification_events(
            unread_only=unread_only, include_archived=include_archived,
            event_type=event_type, limit=limit,
        )
        return [notification_service.normalize_event(item) for item in items or []], "supabase"
    identity = _notification_identity()
    items = read_json_file(NOTIFICATION_EVENTS_PATH, [])
    if not isinstance(items, list):
        items = []
    items = [notification_service.normalize_event(item) for item in items]
    if identity.get("personId"):
        items = [item for item in items if item.get("recipientPersonId") == identity.get("personId")]
    if unread_only:
        items = [item for item in items if not item.get("readAt")]
    if not include_archived:
        items = [item for item in items if not item.get("archivedAt")]
    if event_type:
        items = [item for item in items if item.get("eventType") == event_type]
    items.sort(key=lambda item: item.get("createdAt") or "", reverse=True)
    return items[:max(1, min(int(limit or 100), 500))], "json"


def update_notification_event(event_id, action):
    backend = data_backend()
    if backend.enabled():
        item = backend.mark_notification_event(event_id, action)
        return (notification_service.normalize_event(item), "supabase") if item else (None, "notification_not_found")
    identity = _notification_identity()
    items = read_json_file(NOTIFICATION_EVENTS_PATH, [])
    updated = None
    next_items = []
    for raw in items if isinstance(items, list) else []:
        item = notification_service.normalize_event(raw)
        if item.get("id") == event_id and (
            not identity.get("personId") or item.get("recipientPersonId") == identity.get("personId")
        ):
            item = notification_service.mark_event(item, action)
            updated = item
        next_items.append(item)
    write_json_file(NOTIFICATION_EVENTS_PATH, next_items[-10000:])
    return (updated, "json") if updated else (None, "notification_not_found")


def notification_events_response(data):
    data = data or {}
    action = str(data.get("action") or "list").lower()
    if action in ("read", "archive", "opened", "actioned"):
        event_id = data.get("id") or data.get("eventId") or data.get("event_id")
        if not event_id:
            return {"ok": False, "error": "notification_id_required"}
        try:
            item, backend = update_notification_event(event_id, action)
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        if item is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "notification": item, "backend": backend}
    items, backend = load_notification_events(
        unread_only=bool(data.get("unreadOnly") or data.get("unread_only")),
        include_archived=bool(data.get("includeArchived") or data.get("include_archived")),
        event_type=data.get("eventType") or data.get("event_type"),
        limit=data.get("limit") or 100,
    )
    return {
        "ok": True,
        "notifications": items,
        "unreadCount": sum(1 for item in items if not item.get("readAt")),
        "backend": backend,
    }


def apns_status():
    try:
        return apns_service.APNSConfig.from_env().status()
    except (OSError, ValueError) as error:
        return {
            "enabled": False,
            "missing": ["valid MUNEA_APNS_PRIVATE_KEY_PATH"],
            "error": type(error).__name__,
        }


def drain_notification_outbox_response(data=None):
    data = data or {}
    try:
        config = apns_service.APNSConfig.from_env()
    except OSError:
        return {"ok": False, "error": "apns_private_key_unreadable", "apns": apns_status()}
    if not config.configured():
        return {"ok": False, "error": "apns_not_configured", "apns": config.status()}
    backend = data_backend()
    if not backend.enabled():
        return {"ok": False, "error": "notification_backend_not_configured"}
    return apns_service.drain_outbox(
        backend,
        sender=apns_service.APNSSender(config=config),
        limit=max(1, min(int(data.get("limit") or 50), 200)),
        # 發送前照收件人的通知中心設定過濾；查不到收件人 fail-open（見 drain_outbox）
        push_allowed_fn=lambda d: notification_service.push_allowed(
            load_notification_settings(
                d.get("recipient_person_id") or d.get("recipientPersonId")),
            d.get("event_type") or d.get("eventType"),
        ) if (d.get("recipient_person_id") or d.get("recipientPersonId")) else True,
    )


def proactive_opening_response(data):
    """主動開口引擎（感知層的靈魂 · 借 ElliQ「先算了才開口」）：
    分數 = 時段合適度 × 今天已開口次數退頻 × 心情調節 × 今日關懷素材加成。夠高才開口、低分就安靜。"""
    import perception_engine
    data = data or {}
    person_id = data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID
    ctx = perception_engine.now_context()
    reasons = []
    period_fit = {"清晨": 0.55, "早上": 0.85, "中午": 0.45, "下午": 0.75,
                  "傍晚": 0.8, "晚上": 0.65, "深夜": 0.05}.get(ctx["period"], 0.5)
    score = period_fit
    reasons.append(f"時段 {ctx['period']}（合適度 {period_fit}）")
    opened = int(data.get("openedToday") or 0)  # 今天已主動幾次 → 指數退頻（預設一天 1 次為主）
    if opened:
        score *= 0.35 ** opened
        reasons.append(f"今天已主動 {opened} 次 → 大幅退頻")
    style = "warm"
    signals = load_wellbeing_signals(person_id, limit=10)
    last = signals[-1] if signals else None
    if last and last.get("level") is not None:
        if last["level"] <= 2:
            style = "gentle"
            score += 0.1
            reasons.append("最近聽起來有點悶 → 更該溫柔關心（語氣放輕）")
        elif last["level"] >= 4:
            reasons.append("最近心情不錯")
    brief = _latest_daily_briefing(person_id)
    if brief.get("careHints"):
        score += 0.08
        reasons.append("今天有關懷素材（天氣/空品提醒）")
    if today_care_items(person_id):
        score += 0.12
        reasons.append("今天有重要日子（回診/紀念日）")
    score = round(max(0.0, min(1.0, score)), 2)
    should = score >= 0.5
    opener = ""
    if should and data.get("withText", True):
        try:
            today_line = brief.get("briefingLine") or ""
            if style == "gentle":
                today_line += "（她昨天聽起來有點悶——開場要更輕更慢，先陪伴、不要話題轟炸。）"
            opener = eng.open_chat(data.get("char") or DEFAULT_CHAR, today=today_line)
        except Exception as e:
            log_fallback_exception("generate proactive opener", e)
    return {"ok": True, "brain": "butler", "action": "proactive_opening",
            "shouldOpen": should, "score": score, "style": style,
            "period": ctx["period"], "reasons": reasons, "opener": opener}


def refresh_daily_briefing(region=None, person_id=None):
    """每日簡報功課：抓真天氣＋真空品＋明天預告＋本週話題（多則）＋今天回診 → 一句人話 → 存感知抽屜（帶當天到期）。
    設計為清晨定時跑（預設 06:30、掛 Cloud Scheduler）；也可由管理端手動觸發 POST /admin/daily-briefing。
    可靠性：每一塊獨立 try/except，任何一塊抓失敗都不崩、不瞎編——部分成功也存（天氣有、話題沒，也存天氣那份）。
    per-region（上線接法）：region＝這次要備的縣市；目前試營運單一長輩（PRIMARY_CARE_RECIPIENT_ID/MUNEA_REGION）。
    真帳號多人上線時＝外層加一個迴圈，查全部長輩清單、對每個長輩各自呼叫
    refresh_daily_briefing(該長輩的縣市, 該長輩 personId)——本函式簽章已支援、不用改；
    Cloud Scheduler 打的入口也不用改，只要把 /admin/daily-briefing 的 handler 改成呼叫那層迴圈即可。"""
    import perception_engine
    person_id = person_id or PRIMARY_CARE_RECIPIENT_ID
    try:
        briefing = perception_engine.build_briefing(region)  # 天氣＋空品＋明天預告（內部已零例外、都失敗回 None 不瞎編）
    except Exception as e:
        log_fallback_exception("build daily briefing", e)
        return {"ok": False, "brain": "butler", "action": "daily_briefing", "error": "briefing_failed"}
    try:
        briefing["scheduleToday"] = today_care_items(person_id)  # 今天的回診/重要日子
    except Exception as e:
        log_fallback_exception("load today care items for briefing", e)
        briefing["scheduleToday"] = []
    try:
        topics = perception_engine.fetch_weekly_topics(count=3)  # 本週話題（暖新聞＋生活健康＋懷舊，有護欄、找不到寧可少給）
    except Exception as e:
        log_fallback_exception("fetch weekly topics for briefing", e)
        topics = []
    briefing["topics"] = topics
    briefing["newsLine"] = topics[0]["line"] if topics else ""  # 相容舊欄位（單則、給還沒升級的讀取端）
    expires = briefing["date"] + "T23:59:59+08:00"  # 當天有效、隔天自然過期
    try:
        append_perception_snapshots([{
            "personId": person_id,
            "snapshotType": "daily_briefing",
            "expiresAt": expires,
            "facts": briefing,
            "source": "perception_engine",
        }])
    except Exception as e:
        # 存檔失敗不讓整支 cron 帶著未捕捉例外爆掉（run_daily_briefing.py 才接得到乾淨的 ok:False 訊息）。
        # ⚠ 已知一個會讓這裡必定失敗的成因：Supabase perception_snapshots.snapshot_type 的 CHECK
        # constraint 清單裡沒有 'daily_briefing'（見 supabase/sql/009_perception_snapshot_daily_briefing.sql）
        # ——這正是「23514 check_violation」的根因，要等這支 migration 跑過才會真的存得進去。
        log_fallback_exception("save daily briefing snapshot", e)
        return {"ok": False, "brain": "butler", "action": "daily_briefing",
                "error": "snapshot_save_failed", "briefing": briefing, "expiresAt": expires}
    return {"ok": True, "brain": "butler", "action": "daily_briefing",
            "briefing": briefing, "expiresAt": expires}


def _latest_daily_briefing(person_id=None):
    """讀最新、未過期的今日簡報（通話中只讀這裡、絕不臨時對外查）。"""
    person_id = person_id or PRIMARY_CARE_RECIPIENT_ID
    snaps = load_perception_snapshots({"snapshotType": "daily_briefing", "personId": person_id}, limit=10)
    now = datetime.now(timezone.utc)
    for snap in reversed(snaps or []):
        exp = snap.get("expiresAt")
        try:
            if exp and datetime.fromisoformat(str(exp).replace("Z", "+00:00")) < now:
                continue
        except ValueError as e:
            log_fallback_exception("parse daily briefing expiration", e)
        facts = snap.get("facts") or {}
        if facts.get("briefingLine") or facts.get("careHints"):
            return facts
    return {}


def normalize_perception_snapshot(data):
    data = data or {}
    return {
        "id": data.get("id") or "ps_" + uuid.uuid4().hex[:12],
        "personId": data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "snapshotType": data.get("snapshotType") or data.get("snapshot_type") or data.get("type") or "current_topic",
        "observedAt": data.get("observedAt") or data.get("observed_at") or utc_now(),
        "expiresAt": data.get("expiresAt") or data.get("expires_at"),
        "facts": data.get("facts") or {},
        "source": data.get("source") or "munea",
        "createdAt": data.get("createdAt") or data.get("created_at") or utc_now(),
    }


def load_perception_snapshots(query=None, limit=100):
    query = query or {}
    try:
        remote_snapshots = data_backend().load_perception_snapshots(query=query, limit=limit)
        if remote_snapshots is not None:
            return remote_snapshots
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e) and "22P02" not in str(e):
            raise e
        log_fallback_exception("load perception snapshots from Supabase", e)
    snapshots = read_json_file(PERCEPTION_SNAPSHOTS_PATH, [])
    if not isinstance(snapshots, list):
        snapshots = []
    snapshot_type = query.get("snapshotType") or query.get("snapshot_type") or query.get("type")
    person_id = query.get("personId") or query.get("person_id")
    if snapshot_type:
        snapshots = [s for s in snapshots if s.get("snapshotType") == snapshot_type]
    if person_id:
        snapshots = [s for s in snapshots if s.get("personId") == person_id]
    return snapshots[-limit:]


def save_perception_snapshots(snapshots):
    write_json_file(PERCEPTION_SNAPSHOTS_PATH, list(snapshots)[-1000:])
    return snapshots


def append_perception_snapshots(snapshots):
    snapshots = [normalize_perception_snapshot(snapshot) for snapshot in (snapshots or [])]
    try:
        remote_snapshots = data_backend().save_perception_snapshots(snapshots)
        if remote_snapshots is not None:
            return remote_snapshots
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e) and "22P02" not in str(e):
            raise e
        log_fallback_exception("append perception snapshots to Supabase", e)
    existing = load_perception_snapshots(limit=1000)
    save_perception_snapshots(existing + snapshots)
    return snapshots


def normalize_relationship_state(data):
    data = data or {}
    template_id = normalize_template_id(
        data.get("personaTemplateId")
        or data.get("persona_template_id")
        or data.get("templateId")
        or "nening-real-female"
    )
    rapport = data.get("rapportLevel") or data.get("rapport_level") or "new"
    if rapport not in {"new", "familiar", "trusted", "close"}:
        rapport = "new"
    return {
        "id": data.get("id") or f"rel_{uuid.uuid4().hex[:12]}",
        "accountId": data.get("accountId") or data.get("account_id") or "local-account-demo",
        "personId": data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "companionProfileId": data.get("companionProfileId") or data.get("companion_profile_id"),
        "personaTemplateId": template_id,
        "rapportLevel": rapport,
        "preferredAddress": data.get("preferredAddress") or data.get("preferred_address"),
        "toneOverrides": data.get("toneOverrides") or data.get("tone_overrides") or {},
        "userBoundaries": data.get("userBoundaries") or data.get("user_boundaries") or {},
        "relationshipMemory": data.get("relationshipMemory") or data.get("relationship_memory") or {},
        "updatedByBrainRunId": data.get("updatedByBrainRunId") or data.get("updated_by_brain_run_id"),
        "createdAt": data.get("createdAt") or data.get("created_at") or utc_now(),
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or utc_now(),
        "deletedAt": data.get("deletedAt") or data.get("deleted_at"),
    }


def is_missing_table_error(e):
    # 「雲端不可用、可安全退回本地備份」的判斷：缺表(PGRST205) 或 連線層失敗(逾時/連不上/斷路器開)
    # 連線失敗也走本地備份，才不會在雲端掛掉時噴 500（配合 supabase_adapter 斷路器）
    msg = str(e)
    return (
        "PGRST205" in msg
        or "Could not find the table" in msg
        or "circuit open" in msg
        or "unreachable" in msg
    )


def load_relationship_states(query=None, limit=100):
    query = query or {}
    try:
        remote_states = data_backend().load_relationship_states(query=query, limit=limit)
        if remote_states is not None:
            return remote_states
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load relationship states from Supabase", e)
    store = read_json_file(RELATIONSHIP_STATES_PATH, {"states": []})
    states = store.get("states") if isinstance(store, dict) else store
    states = [normalize_relationship_state(state) for state in (states or [])]
    person_id = query.get("personId") or query.get("person_id")
    template_id = query.get("personaTemplateId") or query.get("persona_template_id") or query.get("templateId")
    companion_profile_id = query.get("companionProfileId") or query.get("companion_profile_id")
    if person_id:
        states = [state for state in states if state.get("personId") == person_id]
    if template_id:
        template_id = normalize_template_id(template_id)
        states = [state for state in states if state.get("personaTemplateId") == template_id]
    if companion_profile_id:
        states = [state for state in states if state.get("companionProfileId") == companion_profile_id]
    states.sort(key=lambda state: state.get("updatedAt") or "", reverse=True)
    return states[:limit]


def save_relationship_states(states):
    states = [normalize_relationship_state(state) for state in (states or [])]
    write_json_file(RELATIONSHIP_STATES_PATH, {"states": states})
    return states


def upsert_relationship_state(state):
    state = normalize_relationship_state({**(state or {}), "updatedAt": utc_now()})
    try:
        remote_state = data_backend().save_relationship_state(state)
        if remote_state is not None:
            return normalize_relationship_state(remote_state)
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("upsert relationship state to Supabase", e)
    states = load_relationship_states(limit=1000)
    updated = False
    next_states = []
    for existing in states:
        if (
            existing.get("personId") == state.get("personId")
            and existing.get("personaTemplateId") == state.get("personaTemplateId")
            and existing.get("companionProfileId") == state.get("companionProfileId")
        ):
            state["id"] = existing.get("id") or state["id"]
            state["createdAt"] = existing.get("createdAt") or state["createdAt"]
            next_states.append(state)
            updated = True
        else:
            next_states.append(existing)
    if not updated:
        next_states.append(state)
    save_relationship_states(next_states)
    return state


def relationship_state_for_context(data, profile):
    data = data or {}
    profile = profile or {}
    explicit_state = data.get("relationshipState") or data.get("relationship_state")
    if explicit_state:
        return normalize_relationship_state(explicit_state)
    store = load_app_profile_store()
    person_id = data.get("personId") or data.get("person_id") or store.get("primaryCareRecipientId") or PRIMARY_CARE_RECIPIENT_ID
    template_id = normalize_template_id(
        data.get("templateId")
        or data.get("template_id")
        or profile.get("templateId")
        or profile.get("template_id")
    )
    companion_profile_id = (
        data.get("companionProfileId")
        or data.get("companion_profile_id")
        or profile.get("id")
        or profile.get("companionProfileId")
        or profile.get("companion_profile_id")
    )
    query = {"personId": person_id, "personaTemplateId": template_id}
    states = load_relationship_states(query=query, limit=10)
    if companion_profile_id:
        for state in states:
            if state.get("companionProfileId") == companion_profile_id:
                return state
    return states[0] if states else None


def memory_extract_response(data):
    data = data or {}
    response = model_router.memory_extract_response(data)
    if (data.get("action") or "preview") == "store":
        person_id = data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID
        new_items = [model_router.normalize_memory_item(c, person_id) for c in response["candidates"]]
        stored_items = append_memory_items(new_items)
        response["stored"] = len(stored_items)
        response["memoryItems"] = stored_items
    else:
        response["stored"] = 0
    return response


def memory_retrieve_response(data):
    data = data or {}
    items = load_memory_items()
    query = data.get("query") or data.get("text") or ""
    if query and items:
        try:
            import memory_engine
            sem = memory_engine.retrieve(query, items, limit=int(data.get("limit") or 5))
        except Exception:
            sem = []
        if sem:
            return {"ok": True, "brain": "butler", "query": query,
                    "memories": sem, "retriever": "semantic_local", "count": len(sem)}
    return model_router.memory_retrieve_response(data, items)


def conversation_summary_response(data):
    data = data or {}
    action = (data.get("action") or "list").lower()
    if action in ("save", "store", "create"):
        payload = data.get("conversationSummary") or data.get("summaryRecord") or data
        if isinstance(payload, str):
            payload = {"summary": payload}
        payload = {**(payload or {})}
        payload.setdefault("personId", data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID)
        payload.setdefault("voiceSessionId", data.get("voiceSessionId") or data.get("voice_session_id"))
        payload.setdefault("summary", data.get("summary"))
        if not str(payload.get("summary") or "").strip():
            return {
                "ok": False,
                "error": "summary_required",
                "message": "Store a concise conversation summary, not raw transcript history.",
            }
        summary = append_conversation_summary(payload)
        if not summary:
            return {"ok": False, "error": "summary_required"}
        append_product_event({
            "eventName": "companion_summary_created",
            "personId": summary.get("personId"),
            "properties": {
                "memoryTags": summary.get("memoryTags") or [],
                "safetyRelevant": summary.get("safetyRelevant") is True,
                "rawTranscriptStored": False,
            },
        })
        return {
            "ok": True,
            "action": "save",
            "summary": summary,
            "privacy": summary.get("privacy") or {"storesRawTranscriptByDefault": False},
            "backend": data_backend_status(),
        }
    if action in ("archive", "delete"):
        summary_id = data.get("id") or data.get("summaryId") or data.get("summary_id")
        if not summary_id:
            return {"ok": False, "error": "summary_id_required"}
        summary = archive_conversation_summary(summary_id)
        if not summary:
            return {"ok": False, "error": "summary_not_found"}
        return {"ok": True, "action": "archive", "summary": summary, "backend": data_backend_status()}
    person_id = data.get("personId") or data.get("person_id")
    summaries = load_conversation_summaries(
        person_id=person_id,
        limit=int(data.get("limit") or 100),
        include_deleted=bool(data.get("includeDeleted") or data.get("include_deleted")),
    )
    return {"ok": True, "action": "list", "summaries": summaries, "count": len(summaries), "backend": data_backend_status()}


def _compact_text(value, max_chars=120):
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def _summary_tags_from_context(context, text=""):
    context = context or {}
    tags = []
    for item in (context.get("perception") or {}).get("domains", []):
        domain = item.get("domain")
        if domain and domain not in tags:
            tags.append(domain)
    risk = (context.get("guardian") or {}).get("risk") or {}
    for category in risk.get("categories") or []:
        if category and category not in tags:
            tags.append(category)
    lower = str(text or "").lower()
    keyword_tags = [
        ("family", ["daughter", "son", "family", "mom", "dad", "女兒", "兒子", "家人"]),
        ("routine", ["medicine", "medication", "reminder", "walk", "藥", "提醒", "散步"]),
        ("emotion", ["lonely", "sad", "worry", "anxious", "孤單", "難過", "擔心", "焦慮"]),
        ("video_entertainment", ["drama", "netflix", "movie", "韓劇", "電影"]),
    ]
    for tag, keywords in keyword_tags:
        if tag not in tags and any(keyword.lower() in lower for keyword in keywords):
            tags.append(tag)
    return tags[:8]


def build_post_turn_conversation_summary(data, context):
    data = data or {}
    history = data.get("history") or []
    text = conversation_text(history)
    if not text.strip():
        return None
    user_turn_count = len([h for h in history if isinstance(h, dict) and (h.get("role") or "user") == "user"])
    tags = _summary_tags_from_context(context, text)
    risk = (context.get("guardian") or {}).get("risk") or {}
    risk_level = risk.get("level") or "none"
    safety_relevant = risk_level in {"medium", "high", "critical"} or bool(risk.get("requiresHumanEscalation"))
    topics = ", ".join(tags[:4]) if tags else "general companionship"
    summary = f"Post-turn companion review covered {topics}; user turns: {user_turn_count}; Guardian risk: {risk_level}."
    if safety_relevant:
        summary += " Safety-relevant content was detected for audit-aware follow-up."
    return normalize_conversation_summary({
        "personId": data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "voiceSessionId": data.get("voiceSessionId") or data.get("voice_session_id"),
        "summary": _compact_text(summary, 280),
        "memoryTags": tags,
        "safetyRelevant": safety_relevant,
    })


def guardian_evaluate_response(data):
    result = model_router.guardian_evaluate_response(data or {})
    if result["risk"]["requiresAuditEvent"]:
        append_product_event({
            "eventName": "guardian_risk_evaluated",
            "properties": {
                "riskLevel": result["risk"]["level"],
                "categories": result["risk"]["categories"],
                "analyticsExcluded": True,
            },
        })
    return result


def persona_context_response(data):
    data = data or {}
    if not data.get("companionProfile") and not data.get("companion_profile") and not data.get("templateId"):
        data = {**data, "companionProfile": load_companion_profile()}
    profile = data.get("companionProfile") or data.get("companion_profile") or load_companion_profile()
    relationship_state = relationship_state_for_context(data, profile)
    response = model_router.persona_context_response({
        **data,
        "companionProfile": profile,
        "relationshipState": relationship_state,
    })
    if relationship_state:
        response["relationshipState"] = {
            **(response.get("relationshipState") or {}),
            "id": relationship_state.get("id"),
            "personId": relationship_state.get("personId"),
            "personaTemplateId": relationship_state.get("personaTemplateId"),
            "companionProfileId": relationship_state.get("companionProfileId"),
        }
    return response


def topic_perception_plan_response(data):
    return model_router.topic_perception_plan_response(data or {})


def perception_snapshot_response(data):
    data = data or {}
    action = (data.get("action") or "list").lower()
    if action == "store":
        snapshots = data.get("snapshots") if isinstance(data.get("snapshots"), list) else [data]
        stored = append_perception_snapshots(snapshots)
        return {
            "ok": True,
            "action": "store",
            "stored": len(stored),
            "snapshots": stored,
            "backend": data_backend_status(),
        }
    query = {
        "personId": data.get("personId") or data.get("person_id"),
        "snapshotType": data.get("snapshotType") or data.get("snapshot_type") or data.get("type"),
    }
    snapshots = load_perception_snapshots(query=query, limit=int(data.get("limit") or 100))
    return {
        "ok": True,
        "action": "list",
        "count": len(snapshots),
        "snapshots": snapshots,
        "backend": data_backend_status(),
    }


def template_id_for_backend_char(char):
    for template_id, template in COMPANION_TEMPLATES.items():
        if template.get("backendChar") == char:
            return template_id
    return "nening-real-female"


def conversation_text(history):
    parts = []
    for item in history or []:
        if isinstance(item, dict):
            role = item.get("role") or "user"
            text = item.get("text") or item.get("content") or ""
            if text:
                parts.append(f"{role}: {text}")
    return "\n".join(parts)


# 簡報背景補救的去抖狀態：防止每通新電話都開一條執行緒（高併發下一堆線搶 GIL、拖垮語音主線程 · 2026-07-12 卡西法壓測抓到 10 人斷崖根因）
_briefing_refresh_state = {"running": False, "last": 0.0}


def _maybe_refresh_briefing_bg():
    """沒有當日簡報時背景補做，但同時只允許一條、且失敗後 5 分鐘內不再狂試——避免每通電話都堆一條註定失敗的執行緒。"""
    st = _briefing_refresh_state
    now = time.time()
    if st["running"] or (now - st["last"] < 300):
        return
    st["running"] = True
    st["last"] = now

    def _run():
        try:
            refresh_daily_briefing()
        except Exception as e:
            log_fallback_exception("refresh daily briefing in background", e)
        finally:
            st["running"] = False

    threading.Thread(target=_run, daemon=True).start()


def build_reply_context(history, char=DEFAULT_CHAR, data=None):
    data = data or {}
    locale = localization.normalize_locale(data.get("locale"))
    text = conversation_text(history)
    user_mood = (data or {}).get("userMood") or ""   # 情緒球：使用者當下記錄的心情
    interests = [str(t).strip() for t in (data.get("interests") or []) if str(t).strip()][:8]  # 用戶挑的興趣話題
    active_profile = load_companion_profile()
    template_id = data.get("templateId") or active_profile.get("templateId")
    if not template_id or COMPANION_TEMPLATES.get(template_id, {}).get("backendChar") != char:
        template_id = template_id_for_backend_char(char)
    profile = {
        **active_profile,
        "templateId": template_id,
        "displayName": data.get("displayName") or active_profile.get("displayName") or COMPANION_TEMPLATES[template_id]["defaultName"],
    }
    persona = persona_context_response({
        "companionProfile": profile,
        "char": char,
        "text": text,
    })
    guardian = guardian_evaluate_response({"text": text, "effort": "quick"})
    memories = memory_retrieve_response({"query": text, "limit": 5}).get("memories", [])
    perception = topic_perception_plan_response({"query": text})
    try:
        import perception_engine
        now_ctx = perception_engine.now_context()
    except Exception:
        now_ctx = {}
    briefing = _latest_daily_briefing()
    if not briefing:
        # 簡報保鮮：沒有今天的就背景補做（去抖：同時只一條、失敗後 5 分鐘不狂試——高併發下不再拖垮語音）
        _maybe_refresh_briefing_bg()
    return {
        "persona": persona,
        "guardian": guardian,
        "memories": memories,
        "perception": perception,
        "livingProfile": load_living_profile(),
        # 他自己的身體數據（檔位 2）。語音那條路的 Voice 程式沒有雲端鑰匙、也認不出來電者，
        # 所以它會先向 Brain 要好、從 data 餵進來（跟「上次聊天」同一個模子）。
        # 餵不進來（Brain 不通、認不出人）就自己撈；撈不到就是空的——圍籬會告訴她「你看不到」。
        "healthContext": data.get("healthContext") or load_health_context(person_id=data.get("personId")),
        "now": now_ctx,                                # 真時間（台灣、時段、語氣提示）
        "dailyBriefing": briefing,                     # 今日簡報（清晨備好的真天氣/空品/行程/暖聞）
        "userMood": user_mood,                          # 情緒球：使用者當下心情（拿來自然關心）
        "interests": interests,                         # 用戶挑的興趣話題（開場方向＋接話素材）
        "location": str(data.get("location") or "").strip()[:24],  # 所在地（可到區）→ 在地推薦定位
        "locale": locale,
    }


def reply_context_instruction(context):
    persona = context.get("persona") or {}
    guardian = context.get("guardian") or {}
    perception = context.get("perception") or {}
    memories = context.get("memories") or []
    persona_body = persona.get("persona") or {}
    relationship_state = persona.get("relationshipState") or context.get("relationshipState") or {}
    relationship_memory = relationship_state.get("relationshipMemory") or {}
    tone_overrides = relationship_state.get("toneOverrides") or {}
    relationship_line = (
        f"[Relationship state] rapport={relationship_state.get('rapportLevel') or 'new'}; "
        f"preferredAddress={relationship_state.get('preferredAddress') or ''}; "
        f"toneOverrides={json.dumps(tone_overrides, ensure_ascii=False)}; "
        f"relationshipMemory={json.dumps(relationship_memory, ensure_ascii=False)}."
    )
    now_ctx = context.get("now") or {}
    time_line = ""
    if now_ctx.get("time"):
        time_line = (f"（現在時間：{now_ctx.get('date')}（{now_ctx.get('weekday')}）{now_ctx.get('period')} {now_ctx.get('time')}。"
                     + (f"時段語氣：{now_ctx.get('toneHint')}。" if now_ctx.get("toneHint") else "") + "）")
    brief = context.get("dailyBriefing") or {}
    brief_line = ""
    _brief_topics = [t for t in (brief.get("topics") or []) if isinstance(t, dict) and t.get("line")]
    if not _brief_topics and brief.get("newsLine"):  # 相容舊 snapshot（升級前存的、只有單則 newsLine）
        _brief_topics = [{"line": brief["newsLine"]}]
    if (brief.get("briefingLine") or brief.get("tomorrowLine") or brief.get("careHints")
            or brief.get("scheduleToday") or _brief_topics):
        seg = "（今日簡報（已核實的真實資料，可自然帶進關心、不要照唸）："
        if brief.get("briefingLine"):
            seg += brief["briefingLine"] + "。"
        if brief.get("tomorrowLine"):
            seg += "明天預告：" + brief["tomorrowLine"] + "。"
        if brief.get("careHints"):
            seg += "關心提示：" + "；".join(brief["careHints"]) + "。"
        if brief.get("scheduleToday"):
            seg += "今天的重要日子：" + "、".join(brief["scheduleToday"]) + "（要記得溫柔提醒）。"
        if _brief_topics:
            seg += "這週可以聊的話題（挑一兩則自然帶入、別一次唸完）：" + "、".join(t["line"] for t in _brief_topics)
        brief_line = seg + "）"
    living = context.get("livingProfile") or {}
    living_parts = []
    if living.get("who"):
        living_parts.append(f"是誰：{living['who']}")
    if living.get("recent"):
        living_parts.append(f"近況：{living['recent']}")
    if living.get("moodTrend"):
        living_parts.append(f"心情走向：{living['moodTrend']}")
    if living.get("caresAbout"):
        living_parts.append("最在乎：" + "、".join(living["caresAbout"]))
    if living.get("intoLately"):
        living_parts.append("最近迷：" + "、".join(living["intoLately"]))
    living_line = (
        "（這位長輩現在是誰（活的側寫，拿來自然關心、別照唸出來）：\n"
        + "\n".join(f"- {p}" for p in living_parts) + "\n）"
    ) if living_parts else ""
    try:
        import health_context as _hc
        health_line = _hc.instruction_block(context.get("healthContext") or {})
    except Exception as e:
        # 這裡壞掉就退回「你什麼都看不到」那道圍籬——寫死在這、不依賴剛剛壞掉的那支。
        # 失敗方向只能往「她不知道」倒，絕不能往「她以為自己看得到」倒。
        log_fallback_exception("render health context block", e)
        health_line = HEALTH_FENCE_WHEN_BLIND
    memory_lines = [
        f"- {item.get('type')}: {item.get('content')}"
        for item in memories[:5]
        if item.get("content")
    ]
    domain_lines = [
        f"- {item.get('domain')} needs {', '.join(item.get('requiredSources') or [])}"
        for item in perception.get("domains", [])
    ]
    _um = context.get("userMood") or ""
    mood_recorded_line = (
        f"（使用者剛在情緒球親手記錄的心情是「{_um}」——把它當這輪陪伴的重要參考，自然貼著這個心情關心、調整語氣；"
        "低落/焦慮/煩躁/生氣先接住情緒、放慢；開心/愉悅就一起有精神。別生硬地把『你現在心情是X』唸出來。）"
    ) if _um else ""
    _ints = context.get("interests") or []
    interests_line = (
        "（他勾選過想聊的話題：" + "、".join(_ints) + "。"
        "開場或冷場時可以從這幾個方向自然起頭（搭今日簡報或最近的真時事更好）；"
        "聊到相關話題時多帶點料、多分享一個真實的亮點或小知識。"
        "但這是參考不是劇本——他想聊別的就跟著他走，別硬拉回來、別一次全部聊完。）"
    ) if _ints else ""
    _loc = context.get("location") or ""
    _now_period = (context.get("now") or {}).get("period") or ""
    location_line = (
        f"（他住在「{_loc}」。聊到吃飯、附近哪裡好玩、在地活動時，用即時查詢找「{_loc}」真實存在的店家/景點再推薦——"
        "會考慮現在的時段（例如快到晚餐就推現在還有營業、去得到的；早上就別推只開晚上的），"
        "講真店名、真特色，不確定就先查、查不到就老實說，絕對不編地址或營業時間。）"
        + (f"（現在是{_now_period}，推薦餐廳就挑這個時段吃得到的。）" if _now_period else "")
    ) if _loc else ""
    culture_line = (
        "（聊到影劇/戲劇/歌曲/新聞這類會隨時間變的話題：用即時查詢找「最近這一兩週真的在紅、評價不錯」的，"
        "講得出劇名/歌名與一句為什麼好看好聽；不要憑印象講可能過時或不存在的，不確定就查、查不到就老實說。）"
    )
    return "\n".join([
        "",
        relationship_line,
        "（Munea AI 服務組裝規則：回應 = 角色人格 + 使用者記憶 + 即時感知 + 當下對話 + 安全規則 + 語音表達限制。）",
        f"（目前角色顯示名：{persona.get('displayName') or ''}；人格型：{persona_body.get('personaArchetype') or ''}；關係框架：{persona_body.get('relationshipFrame') or ''}。）",
        f"（語氣：{', '.join(persona_body.get('toneProfile') or [])}。）",
        f"（對話風格：{', '.join(persona_body.get('conversationStyle') or [])}。）",
        f"（安全風險：{(guardian.get('risk') or {}).get('level', 'none')}；動作：{(guardian.get('risk') or {}).get('action', 'allow')}。）",
        time_line,
        brief_line,
        "（聽出對方的語氣與心情、跟著調整：聽起來累或低落→放柔放慢、不催、多陪；開心→跟著亮起來。這是關心、不是診斷，絕不評斷對方的心理狀態。）",
        mood_recorded_line,
        interests_line,
        location_line,
        culture_line,
        "（智慧鏡頭：可溫柔用台灣諺語、生活智慧、簡單的反思提問陪伴；對方有信仰才順著其信仰語彙。絕不捏造經文、不強加宗教、不說教；危機時安全規則優先於一切。）",
        living_line,
        health_line,
        "（相關記憶：\n" + ("\n".join(memory_lines) if memory_lines else "- 沒有足夠相關記憶，不要假裝記得。") + "\n）",
        "（即時感知需求：\n" + ("\n".join(domain_lines) if domain_lines else "- 此輪不需要外部即時事實。") + "\n）",
        "（醫療紅線，最高優先：不診斷、不開藥、不建議劑量或顆數、不說停藥換藥、不說不用看醫生。被問到藥怎麼吃、吃幾顆、能不能吃、要不要停，一律溫柔回：這要請醫生或藥師決定，並主動提議幫忙記下來回診時問。身體急症徵兆一律提醒聯絡 119。不主動顯示逐字稿；沒有資料來源就說不能確認、不編造。）",
    ])


def ai_context_summary(context):
    context = context or {}
    persona = context.get("persona") or {}
    guardian = context.get("guardian") or {}
    perception = context.get("perception") or {}
    return {
        "personaLayer": {
            "templateId": persona.get("templateId"),
            "displayName": persona.get("displayName"),
            "personaArchetype": (persona.get("persona") or {}).get("personaArchetype"),
        },
        "relationship": {
            "rapportLevel": (persona.get("relationshipState") or {}).get("rapportLevel") or "new",
            "hasRelationshipMemory": bool((persona.get("relationshipState") or {}).get("relationshipMemory")),
            "toneOverrideKeys": sorted(((persona.get("relationshipState") or {}).get("toneOverrides") or {}).keys()),
        },
        "guardian": {
            "riskLevel": (guardian.get("risk") or {}).get("level"),
            "action": (guardian.get("risk") or {}).get("action"),
        },
        "perception": {
            "domains": [item.get("domain") for item in perception.get("domains", [])],
            "needsCurrentFacts": perception.get("needsCurrentFacts"),
        },
        "memory": {
            "count": len(context.get("memories") or []),
        },
    }


def load_legacy_companion_profile():
    return normalize_companion_profile(read_json_file(COMPANION_PROFILE_PATH, {}))


def default_app_profile_store(companion_profile=None):
    companion_profile = normalize_companion_profile(companion_profile)
    return {
        "schemaVersion": 1,
        "account": {
            "id": "local-demo-account",
            "locale": "zh-TW",
            "preferredLanguages": ["zh-TW", "en"],
            "createdAt": "2026-06-29T00:00:00Z",
        },
        "familyGroup": {
            "id": "local-demo-family",
            "name": "Munea Care Circle",
            "members": [
                {
                    "id": PRIMARY_CARE_RECIPIENT_ID,
                    "role": "primary_user",
                    "displayName": "Primary user",
                    "relationship": "self",
                },
                {
                    "id": "local-family-contact",
                    "role": "family_contact",
                    "displayName": "Family contact",
                    "relationship": "family",
                },
            ],
        },
        "primaryCareRecipientId": PRIMARY_CARE_RECIPIENT_ID,
        "companionProfiles": {
            PRIMARY_CARE_RECIPIENT_ID: companion_profile,
        },
        "updatedAt": companion_profile.get("updatedAt") or utc_now(),
    }


FAMILY_MEMBER_ROLES = {"primary_user", "family_contact", "caregiver", "viewer"}

def normalize_family_member(member):
    member = member or {}
    role = str(member.get("role") or "family_contact")
    member_id = str(member.get("id") or (PRIMARY_CARE_RECIPIENT_ID if role == "primary_user" else ("local-family-member-" + uuid.uuid4().hex[:10])))
    permissions = member.get("permissions") or {}
    if not isinstance(permissions, dict):
        permissions = {}
    return {
        "id": member_id,
        "role": role if role in FAMILY_MEMBER_ROLES else "family_contact",
        "displayName": str(member.get("displayName") or member.get("display_name") or "Member").strip()[:40] or "Member",
        "relationship": str(member.get("relationship") or "family"),
        "permissions": permissions,
        "createdAt": member.get("createdAt") or member.get("created_at"),
        "updatedAt": member.get("updatedAt") or member.get("updated_at") or utc_now(),
    }


def normalize_app_profile_store(data=None):
    data = data or {}
    primary_id = str(data.get("primaryCareRecipientId") or data.get("primary_care_recipient_id") or PRIMARY_CARE_RECIPIENT_ID)
    raw_profiles = data.get("companionProfiles") or data.get("companion_profiles") or {}
    if data.get("companionProfile") and primary_id not in raw_profiles:
        raw_profiles = {**raw_profiles, primary_id: data.get("companionProfile")}
    companion_profiles = {
        str(person_id): normalize_companion_profile(profile)
        for person_id, profile in raw_profiles.items()
    }
    companion_profiles.setdefault(primary_id, load_legacy_companion_profile())

    family_group = data.get("familyGroup") or data.get("family_group") or {}
    members = [normalize_family_member(m) for m in family_group.get("members", [])]
    if not any(m["id"] == primary_id for m in members):
        members.insert(0, normalize_family_member({
            "id": primary_id,
            "role": "primary_user",
            "displayName": "Primary user",
            "relationship": "self",
        }))

    account = data.get("account") or {}
    return {
        "schemaVersion": int(data.get("schemaVersion") or data.get("schema_version") or 1),
        "account": {
            "id": str(account.get("id") or "local-demo-account"),
            "locale": str(account.get("locale") or "zh-TW"),
            "preferredLanguages": account.get("preferredLanguages") or account.get("preferred_languages") or ["zh-TW", "en"],
            "createdAt": account.get("createdAt") or account.get("created_at") or "2026-06-29T00:00:00Z",
        },
        "familyGroup": {
            "id": str(family_group.get("id") or "local-demo-family"),
            "name": str(family_group.get("name") or "Munea Care Circle"),
            "members": members,
        },
        "primaryCareRecipientId": primary_id,
        "companionProfiles": companion_profiles,
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or utc_now(),
    }


def load_json_app_profile_store():
    raw = read_json_file(APP_PROFILE_STORE_PATH)
    if raw is None:
        return default_app_profile_store(load_legacy_companion_profile())
    return normalize_app_profile_store(raw)


# 帳號側寫短期快取：normalize_product_event 等熱路徑會在單一請求內反覆讀取，
# 每次雲端往返 ~1.7s、77 筆事件就滾成兩分鐘。5 秒 TTL 把同批呼叫收斂成一次。
_APP_PROFILE_CACHE = {"store": None, "ts": 0.0}
_APP_PROFILE_TTL = 5.0


def load_app_profile_store():
    now = time.time()
    cached = _APP_PROFILE_CACHE["store"]
    if cached is not None and (now - _APP_PROFILE_CACHE["ts"]) < _APP_PROFILE_TTL:
        return cached
    try:
        remote_store = data_backend().load_app_profile_store()
        if remote_store:
            store = normalize_app_profile_store(remote_store)
            _APP_PROFILE_CACHE["store"] = store
            _APP_PROFILE_CACHE["ts"] = now
            return store
    except Exception as e:
        log_fallback_exception("load app profile from Supabase", e)
    store = load_json_app_profile_store()
    _APP_PROFILE_CACHE["store"] = store
    _APP_PROFILE_CACHE["ts"] = now
    return store


def save_app_profile_store(data):
    store = normalize_app_profile_store({**data, "updatedAt": utc_now()})
    try:
        remote_store = data_backend().save_app_profile_store(store)
        if remote_store:
            store = normalize_app_profile_store(remote_store)
    except Exception as e:
        log_fallback_exception("save app profile to Supabase", e)
    write_json_file(APP_PROFILE_STORE_PATH, store)
    _APP_PROFILE_CACHE["store"] = store  # 存檔後即時更新快取，避免讀到舊值
    _APP_PROFILE_CACHE["ts"] = time.time()
    return store


def load_family_members(family_group_id=None, limit=100):
    try:
        remote_members = data_backend().load_family_members(family_group_id=family_group_id, limit=limit)
        if remote_members is not None:
            return [normalize_family_member(member) for member in remote_members]
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("load family members from Supabase", e)
    store = load_app_profile_store()
    members = store.get("familyGroup", {}).get("members") or []
    return [normalize_family_member(member) for member in members][-limit:]


def save_family_member(member, family_group_id=None):
    member = normalize_family_member(member)
    try:
        remote_member = data_backend().save_family_member(member, family_group_id=family_group_id)
        if remote_member is not None:
            return normalize_family_member(remote_member), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("save family member to Supabase", e)
    store = load_app_profile_store()
    family_group = store.setdefault("familyGroup", {"id": family_group_id or "local-demo-family", "name": "Munea Care Circle", "members": []})
    members = [normalize_family_member(m) for m in family_group.get("members", [])]
    next_members = [m for m in members if m.get("id") != member.get("id")]
    next_members.append(member)
    family_group["members"] = next_members[-100:]
    save_app_profile_store(store)
    return member, "json"


def update_family_member(member_id, patch, family_group_id=None):
    if not member_id:
        return None, "member_id_required"
    patch = patch or {}
    if patch.get("action") in ("remove", "archive") or patch.get("status") in ("removed", "archived"):
        try:
            remote_member = data_backend().remove_family_member(member_id, family_group_id=family_group_id)
            if remote_member is not None:
                return normalize_family_member(remote_member), "supabase"
        except Exception as e:
            if data_backend().enabled() and not is_missing_table_error(e):
                raise e
            log_fallback_exception("remove family member from Supabase", e)
        store = load_app_profile_store()
        family_group = store.setdefault("familyGroup", {"id": family_group_id or "local-demo-family", "name": "Munea Care Circle", "members": []})
        members = [normalize_family_member(m) for m in family_group.get("members", [])]
        removed = next((m for m in members if m.get("id") == member_id), None)
        family_group["members"] = [m for m in members if m.get("id") != member_id]
        save_app_profile_store(store)
        return (removed, "json") if removed else (None, "not_found")
    try:
        remote_member = data_backend().update_family_member(member_id, patch, family_group_id=family_group_id)
        if remote_member is not None:
            return normalize_family_member(remote_member), "supabase"
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("update family member in Supabase", e)
    store = load_app_profile_store()
    family_group = store.setdefault("familyGroup", {"id": family_group_id or "local-demo-family", "name": "Munea Care Circle", "members": []})
    members = [normalize_family_member(m) for m in family_group.get("members", [])]
    updated = None
    next_members = []
    for member in members:
        if member.get("id") == member_id:
            member = normalize_family_member({
                **member,
                **patch,
                "permissions": {**(member.get("permissions") or {}), **(patch.get("permissions") or {})},
                "updatedAt": utc_now(),
            })
            updated = member
        next_members.append(member)
    family_group["members"] = next_members
    save_app_profile_store(store)
    return (updated, "json") if updated else (None, "not_found")


def family_members_response(data):
    data = data or {}
    action = data.get("action") or "list"
    family_group_id = data.get("familyGroupId") or data.get("family_group_id")
    if action in ("save", "create", "add", "invite"):
        member, backend = save_family_member(data.get("member") or data.get("item") or data, family_group_id=family_group_id)
        return {"ok": True, "member": member, "backend": backend}
    if action in ("update", "patch", "role", "permissions", "remove", "archive"):
        member_id = data.get("id") or data.get("memberId") or data.get("member_id") or data.get("personId") or data.get("person_id")
        patch = data.get("patch") or data
        if action in ("remove", "archive"):
            patch = {**patch, "action": action}
        member, backend = update_family_member(member_id, patch, family_group_id=family_group_id)
        if member is None:
            return {"ok": False, "error": backend}
        return {"ok": True, "member": member, "backend": backend}
    return {"ok": True, "members": load_family_members(family_group_id=family_group_id, limit=int(data.get("limit") or 100))}


FAMILY_RELAY_STATUSES = {"pending", "claimed", "delivered", "cancelled", "reported", "expired"}


def normalize_family_relay(item):
    item = item or {}
    status = item.get("status") or "pending"
    return {
        "id": str(item.get("id") or uuid.uuid4()),
        "accountId": item.get("accountId") or item.get("account_id"),
        "familyGroupId": item.get("familyGroupId") or item.get("family_group_id") or "local-family",
        "senderPersonId": item.get("senderPersonId") or item.get("sender_person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "recipientPersonId": item.get("recipientPersonId") or item.get("recipient_person_id"),
        "senderLabel": str(item.get("senderLabel") or item.get("sender_label") or "家人").strip()[:40] or "家人",
        "recipientLabel": str(item.get("recipientLabel") or item.get("recipient_label") or "家人").strip()[:40] or "家人",
        "content": str(item.get("content") or "").strip()[:240],
        "status": status if status in FAMILY_RELAY_STATUSES else "pending",
        "source": str(item.get("source") or "voice-ai")[:40],
        "claimToken": item.get("claimToken") or item.get("claim_token"),
        "relayProof": item.get("relayProof") or item.get("relay_proof"),
        "claimedAt": item.get("claimedAt") or item.get("claimed_at"),
        "deliveredAt": item.get("deliveredAt") or item.get("delivered_at"),
        "cancelledAt": item.get("cancelledAt") or item.get("cancelled_at"),
        "expiresAt": item.get("expiresAt") or item.get("expires_at") or (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        "createdAt": item.get("createdAt") or item.get("created_at") or utc_now(),
        "updatedAt": item.get("updatedAt") or item.get("updated_at") or utc_now(),
    }


def family_relay_voice_proof(relay):
    secret = os.environ.get("MUNEA_FAMILY_RELAY_SIGNING_SECRET", "").strip()
    if not secret and not auth_required_mode():
        secret = "munea-local-family-relay"
    if not secret:
        return None
    material = "\n".join(str(relay.get(key) or "") for key in (
        "id", "recipientPersonId", "senderLabel", "content", "claimToken",
    ))
    return hmac.new(secret.encode("utf-8"), material.encode("utf-8"), hashlib.sha256).hexdigest()


def family_relay_for_voice(relay):
    if not relay:
        return None
    relay = normalize_family_relay(relay)
    proof = family_relay_voice_proof(relay)
    return {**relay, "relayProof": proof} if proof else None


def _relay_json_store():
    items = read_json_file(FAMILY_RELAYS_PATH, [])
    return [normalize_family_relay(item) for item in items] if isinstance(items, list) else []


def family_relays_response(data):
    data = data or {}
    action = str(data.get("action") or "list").lower()
    backend = data_backend()
    actor_person_id = backend.person_id or PRIMARY_CARE_RECIPIENT_ID

    if action in ("create", "send"):
        raw = data.get("relay") or data.get("item") or data
        relay = normalize_family_relay({
            **raw,
            "senderPersonId": actor_person_id,
            "familyGroupId": backend.family_group_id or raw.get("familyGroupId") or raw.get("family_group_id"),
            "status": "pending",
        })
        if len(relay["content"]) < 2:
            return {"ok": False, "error": "family_relay_content_required"}
        if not relay.get("recipientPersonId"):
            return {"ok": False, "error": "family_relay_recipient_required"}
        if relay.get("recipientPersonId") == actor_person_id:
            return {"ok": False, "error": "family_relay_recipient_self"}
        try:
            remote = backend.create_family_relay(relay)
            if remote is not None:
                return {"ok": True, "relay": normalize_family_relay(remote), "backend": "supabase"}
        except Exception as e:
            if backend.enabled() and not is_missing_table_error(e):
                raise
            log_fallback_exception("create family relay in Supabase", e)
        with JSON_STORE_LOCK:
            items = _relay_json_store()
            items.append(relay)
            write_json_file(FAMILY_RELAYS_PATH, items[-1000:])
        notification, notification_backend = enqueue_notification_event({
            "eventType": "family_relay",
            "recipientPersonId": relay.get("recipientPersonId"),
            "actorPersonId": relay.get("senderPersonId"),
            "familyGroupId": relay.get("familyGroupId"),
            "resourceType": "family_relay_message",
            "resourceId": relay.get("id"),
            "title": f"{relay.get('senderLabel') or '家人'}捎來一則話",
            "body": relay.get("content"),
            "publicTitle": "沐寧提醒",
            "publicBody": "家人捎來一則訊息，解鎖後收聽。",
            "sensitivity": "private",
            "deepLink": f"munea://relay/{relay.get('id')}",
            "dedupeKey": f"family-relay:{relay.get('id')}",
            "expiresAt": relay.get("expiresAt"),
            "metadata": {"source": relay.get("source")},
        })
        return {
            "ok": True, "relay": relay, "backend": "json",
            "notificationQueued": bool(notification), "notificationBackend": notification_backend,
        }

    if action == "claim":
        try:
            remote = backend.claim_next_family_relay()
            if backend.enabled():
                if not remote:
                    return {"ok": True, "relay": None, "backend": "supabase"}
                signed = family_relay_for_voice(remote)
                if not signed:
                    backend.update_family_relay_status(remote.get("id"), "release", claim_token=remote.get("claimToken"))
                    return {"ok": False, "error": "family_relay_signing_not_configured"}
                return {"ok": True, "relay": signed, "backend": "supabase"}
        except Exception as e:
            if backend.enabled() and not is_missing_table_error(e):
                raise
            log_fallback_exception("claim family relay in Supabase", e)
        now = datetime.now(timezone.utc)
        with JSON_STORE_LOCK:
            items = _relay_json_store()
            target = None
            for relay in sorted(items, key=lambda item: item.get("createdAt") or ""):
                if relay.get("recipientPersonId") == actor_person_id and relay.get("status") == "claimed":
                    try:
                        claimed_at = datetime.fromisoformat(str(relay.get("claimedAt") or "").replace("Z", "+00:00"))
                    except ValueError:
                        claimed_at = now - timedelta(minutes=11)
                    if claimed_at < now - timedelta(minutes=10):
                        relay.update({"status": "pending", "claimToken": None, "claimedAt": None, "updatedAt": utc_now()})
                try:
                    expires = datetime.fromisoformat(str(relay.get("expiresAt") or "").replace("Z", "+00:00"))
                except ValueError:
                    expires = now + timedelta(days=1)
                if relay.get("recipientPersonId") == actor_person_id and relay.get("status") == "pending" and expires > now:
                    relay.update({"status": "claimed", "claimToken": str(uuid.uuid4()), "claimedAt": utc_now(), "updatedAt": utc_now()})
                    target = relay
                    break
            write_json_file(FAMILY_RELAYS_PATH, items)
        signed = family_relay_for_voice(target)
        if target and not signed:
            with JSON_STORE_LOCK:
                items = _relay_json_store()
                for item in items:
                    if item.get("id") == target.get("id") and item.get("claimToken") == target.get("claimToken"):
                        item.update({"status": "pending", "claimToken": None, "claimedAt": None, "updatedAt": utc_now()})
                write_json_file(FAMILY_RELAYS_PATH, items)
            return {"ok": False, "error": "family_relay_signing_not_configured"}
        return {"ok": True, "relay": signed, "backend": "json"}

    if action in ("ack", "release", "cancel", "report"):
        relay_id = str(data.get("id") or data.get("relayId") or "")
        claim_token = data.get("claimToken") or data.get("claim_token")
        try:
            remote = backend.update_family_relay_status(relay_id, action, claim_token=claim_token)
            if remote is not None:
                return {"ok": True, "relay": normalize_family_relay(remote), "backend": "supabase"}
            if backend.enabled():
                return {"ok": False, "error": "family_relay_not_found"}
        except Exception as e:
            if backend.enabled() and not is_missing_table_error(e):
                raise
            log_fallback_exception("update family relay in Supabase", e)
        with JSON_STORE_LOCK:
            items = _relay_json_store()
            target = next((item for item in items if item.get("id") == relay_id), None)
            if not target:
                return {"ok": False, "error": "family_relay_not_found"}
            if action in ("ack", "release"):
                if target.get("recipientPersonId") != actor_person_id or target.get("status") != "claimed" or target.get("claimToken") != claim_token:
                    return {"ok": False, "error": "family_relay_claim_forbidden"}
                target.update({"status": "delivered", "deliveredAt": utc_now()} if action == "ack" else {"status": "pending", "claimToken": None, "claimedAt": None})
            elif action == "cancel":
                if target.get("senderPersonId") != actor_person_id or target.get("status") not in ("pending", "claimed"):
                    return {"ok": False, "error": "family_relay_cancel_forbidden"}
                target.update({"status": "cancelled", "cancelledAt": utc_now()})
            elif action == "report":
                if target.get("recipientPersonId") != actor_person_id:
                    return {"ok": False, "error": "family_relay_report_forbidden"}
                target["status"] = "reported"
            target["updatedAt"] = utc_now()
            write_json_file(FAMILY_RELAYS_PATH, items)
        return {"ok": True, "relay": target, "backend": "json"}

    direction = "sent" if data.get("direction") == "sent" else "received"
    status = data.get("status")
    limit = max(1, min(100, int(data.get("limit") or 50)))
    try:
        remote = backend.load_family_relays(direction=direction, status=status, limit=limit)
        if remote is not None:
            return {"ok": True, "relays": [normalize_family_relay(item) for item in remote], "backend": "supabase"}
    except Exception as e:
        if backend.enabled() and not is_missing_table_error(e):
            raise
        log_fallback_exception("load family relays from Supabase", e)
    items = _relay_json_store()
    key = "senderPersonId" if direction == "sent" else "recipientPersonId"
    items = [item for item in items if item.get(key) == actor_person_id and (not status or item.get("status") == status)]
    return {"ok": True, "relays": list(reversed(items[-limit:])), "backend": "json"}


def bootstrap_account_response(data, headers=None):
    data = data or {}
    data = {**data, "locale": localization.normalize_locale(data.get("locale"))}
    action = (data.get("action") or "create").lower()
    backend = data_backend()
    auth_context = verify_auth_context(headers)
    verified_auth_user_id = auth_context.get("authUserId") if auth_context.get("ok") else None
    if action != "preview" and backend.enabled() and not is_uuid_like(verified_auth_user_id):
        return {
            "ok": False,
            "error": {
                "code": "auth_user_required",
                "message": "Account bootstrap requires a verified Supabase Auth bearer token.",
                "requestId": request_id(),
            },
            "requiresAuth": True,
            "auth": public_auth_context(auth_context),
            "backend": data_backend_status(),
        }
    try:
        bootstrap_payload = {**data}
        if verified_auth_user_id:
            bootstrap_payload.update({
                "authUserId": verified_auth_user_id,
                "authProvider": auth_context.get("provider"),
                "authEmail": auth_context.get("email"),
            })
        remote_store = None if action == "preview" else backend.bootstrap_account(bootstrap_payload)
        if remote_store:
            store = normalize_app_profile_store(remote_store)
            account_id = store.get("account", {}).get("id") or verified_auth_user_id
            bootstrap_identity = {
                "accountId": account_id,
                "personId": store.get("primaryCareRecipientId"),
                "familyGroupId": (store.get("familyGroup") or {}).get("id") or "",
                "authUserId": verified_auth_user_id,
            }
            bootstrap_scope_token = REQUEST_DATA_IDENTITY.set(bootstrap_identity)
            try:
                free_trial = ensure_free_signup_trial(account_id)
                append_product_event({"eventName": "account_bootstrapped", "properties": {"backend": "supabase"}})
                return {
                    "ok": True,
                    "store": store,
                    "activeCompanionProfile": active_companion_profile(store),
                    "freeTrial": free_trial,
                    "auth": public_auth_context(auth_context),
                    "backend": data_backend_status(),
                }
            finally:
                REQUEST_DATA_IDENTITY.reset(bootstrap_scope_token)
    except Exception as e:
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("bootstrap account through Supabase", e)

    if action in ("update", "patch"):
        store = load_app_profile_store()
        account = store.setdefault("account", {})
        account["locale"] = localization.normalize_locale(data.get("locale") or account.get("locale"))
        account["preferredLanguages"] = data.get("preferredLanguages") or data.get("preferred_languages") or account.get("preferredLanguages") or [account["locale"]]
        save_app_profile_store(store)
        return {"ok": True, "store": store, "activeCompanionProfile": active_companion_profile(store), "auth": public_auth_context(auth_context), "backend": data_backend_status()}

    display_name = (data.get("displayName") or data.get("display_name") or "Munea user").strip()[:80] or "Munea user"
    account_id = data.get("accountId") or data.get("account_id") or f"local-account-{uuid.uuid4()}"
    person_id = data.get("personId") or data.get("person_id") or f"local-person-{uuid.uuid4()}"
    family_group_id = data.get("familyGroupId") or data.get("family_group_id") or f"local-family-{uuid.uuid4()}"
    companion_profile = normalize_companion_profile(data.get("companionProfile") or data.get("companion_profile") or {
        "templateId": "nening-real-female",
        "displayName": "Munea",
        "nameTouched": True,
    })
    store = normalize_app_profile_store({
        "schemaVersion": 1,
        "account": {
            "id": account_id,
            "locale": data.get("locale") or "zh-TW",
            "preferredLanguages": data.get("preferredLanguages") or data.get("preferred_languages") or ["zh-TW", "en"],
            "createdAt": utc_now(),
        },
        "familyGroup": {
            "id": family_group_id,
            "name": data.get("familyGroupName") or data.get("family_group_name") or "Munea Care Circle",
            "members": [{
                "id": person_id,
                "role": "primary_user",
                "displayName": display_name,
                "relationship": data.get("relationship") or "self",
            }],
        },
        "primaryCareRecipientId": person_id,
        "companionProfiles": {person_id: companion_profile},
        "updatedAt": utc_now(),
    })
    if action != "preview":
        save_app_profile_store(store)
        append_product_event({"eventName": "account_bootstrapped", "properties": {"backend": "json"}})
    free_trial = ensure_free_signup_trial(account_id) if action != "preview" else None
    return {
        "ok": True,
        "store": store,
        "activeCompanionProfile": active_companion_profile(store),
        "freeTrial": free_trial,
        "auth": public_auth_context(auth_context),
        "backend": data_backend_status(),
    }


def active_companion_profile(store=None):
    store = store or load_app_profile_store()
    primary_id = store["primaryCareRecipientId"]
    return normalize_companion_profile(store["companionProfiles"].get(primary_id))


def load_companion_profile():
    try:
        remote_profile = data_backend().load_companion_profile()
        if remote_profile:
            return normalize_companion_profile(remote_profile)
    except Exception as e:
        log_fallback_exception("load companion profile from Supabase", e)
    return active_companion_profile(load_app_profile_store())


def save_companion_profile(data):
    profile = normalize_companion_profile({**data, "updatedAt": utc_now()})
    try:
        remote_profile = data_backend().save_companion_profile(profile)
        if remote_profile:
            profile = normalize_companion_profile(remote_profile)
    except Exception as e:
        log_fallback_exception("save companion profile to Supabase", e)
    store = load_app_profile_store()
    store["companionProfiles"][store["primaryCareRecipientId"]] = profile
    save_app_profile_store(store)
    write_json_file(COMPANION_PROFILE_PATH, profile)
    return profile


def companion_profile_response(data):
    action = (data.get("action") or "load").lower()
    if action == "save":
        profile = save_companion_profile(data.get("profile") or data)
    else:
        profile = load_companion_profile()
    template = COMPANION_TEMPLATES[profile["templateId"]]
    return {"ok": True, "profile": profile, "backendChar": template["backendChar"], "backend": data_backend_status()}


def app_profile_response(data):
    action = (data.get("action") or "load").lower()
    if action in ("save", "replace"):
        store = save_app_profile_store(data.get("store") or data.get("profileStore") or data)
    elif action in ("save-companion", "save_companion"):
        save_companion_profile(data.get("profile") or data.get("companionProfile") or data)
        store = load_app_profile_store()
    else:
        store = load_app_profile_store()
    return {"ok": True, "store": store, "activeCompanionProfile": active_companion_profile(store), "backend": data_backend_status()}


def parse_iso_datetime(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def parse_optional_iso_datetime(value):
    """Parse persisted billing timestamps without turning bad data into 'now'."""
    if isinstance(value, datetime):
        parsed = value
    elif not value:
        return None
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_product_event(data=None):
    data = data or {}
    store = load_app_profile_store()
    account_id = data.get("accountId") or data.get("account_id") or store.get("account", {}).get("id") or "local-demo-account"
    person_id = data.get("personId") or data.get("person_id") or store.get("primaryCareRecipientId")
    family_group_id = data.get("familyGroupId") or data.get("family_group_id") or store.get("familyGroup", {}).get("id")
    event_time = parse_iso_datetime(data.get("eventTime") or data.get("event_time"))
    event_name = str(data.get("eventName") or data.get("event_name") or "unknown_event").strip()[:80] or "unknown_event"
    properties = data.get("properties") if isinstance(data.get("properties"), dict) else {}
    return {
        "id": data.get("id") or request_id(),
        "accountId": str(account_id),
        "personId": str(person_id) if person_id else None,
        "familyGroupId": str(family_group_id) if family_group_id else None,
        "eventName": event_name,
        "eventTime": event_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(data.get("source") or "munea-api")[:60],
        "sessionId": data.get("sessionId") or data.get("session_id"),
        "properties": properties,
        "createdAt": data.get("createdAt") or data.get("created_at") or utc_now(),
    }


def default_product_events_store():
    return {"schemaVersion": 1, "events": [], "updatedAt": utc_now()}


def normalize_product_events_store(data=None):
    data = data or {}
    events = [normalize_product_event(e) for e in data.get("events", [])]
    events.sort(key=lambda e: e["eventTime"], reverse=True)
    return {
        "schemaVersion": int(data.get("schemaVersion") or data.get("schema_version") or 1),
        "events": events[:1000],
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or utc_now(),
    }


def load_product_events(since_iso=None, limit=500):
    try:
        remote_events = data_backend().load_product_events(since_iso=since_iso, limit=limit)
        if remote_events is not None:
            return [normalize_product_event(e) for e in remote_events]
    except Exception as e:
        log_fallback_exception("load product events from Supabase", e)
    store = normalize_product_events_store(read_json_file(PRODUCT_EVENTS_PATH, default_product_events_store()))
    events = store["events"]
    if since_iso:
        since = parse_iso_datetime(since_iso)
        events = [e for e in events if parse_iso_datetime(e.get("eventTime")) >= since]
    return events[:limit]


def truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def env_set(name):
    raw = os.environ.get(name) or ""
    return {item.strip() for item in raw.split(",") if item.strip()}


def is_analytics_excluded_event(event):
    props = event.get("properties") or {}
    for key in ("analyticsExcluded", "excludeAnalytics", "developerMode", "isDeveloperActivity", "operationalAccount"):
        if truthy(props.get(key)):
            return True
    account_type = str(props.get("accountType") or props.get("actorType") or props.get("environment") or "").strip().lower()
    if account_type in {"developer", "dev", "internal", "test", "qa", "ops", "operational"}:
        return True
    excluded_ids = set()
    excluded_ids.update(env_set("MUNEA_ANALYTICS_EXCLUDED_ACCOUNT_IDS"))
    excluded_ids.update(env_set("MUNEA_ANALYTICS_EXCLUDED_PERSON_IDS"))
    excluded_ids.update(env_set("MUNEA_ANALYTICS_EXCLUDED_SESSION_IDS"))
    if event.get("accountId") in excluded_ids or event.get("personId") in excluded_ids or event.get("sessionId") in excluded_ids:
        return True
    return False


def append_product_event(data=None):
    event = normalize_product_event(data)
    try:
        remote_event = data_backend().append_product_event(event)
        if remote_event:
            return normalize_product_event(remote_event)
    except Exception as e:
        log_fallback_exception("append product event to Supabase", e)
    store = normalize_product_events_store(read_json_file(PRODUCT_EVENTS_PATH, default_product_events_store()))
    store["events"].insert(0, event)
    store["events"] = store["events"][:1000]
    store["updatedAt"] = utc_now()
    write_json_file(PRODUCT_EVENTS_PATH, store)
    return event


def is_meaningful_product_event(event):
    if is_analytics_excluded_event(event):
        return False
    name = event.get("eventName")
    props = event.get("properties") or {}
    if name in MEANINGFUL_EVENT_NAMES:
        return True
    if name == "voice_session_completed":
        return int(props.get("durationMs") or props.get("duration_ms") or 0) >= 60000 or int(props.get("turnCount") or props.get("turn_count") or 0) >= 3
    return bool(props.get("meaningful"))


def north_star_summary(data=None):
    data = data or {}
    days = max(1, min(30, int(data.get("days") or 7)))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days - 1)
    since_day = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    all_events = load_product_events(since_iso=since_day.strftime("%Y-%m-%dT%H:%M:%SZ"), limit=1000)
    events = [event for event in all_events if not is_analytics_excluded_event(event)]
    excluded_events = len(all_events) - len(events)
    meaningful_days = set()
    active_people = set()
    voice_started = 0
    voice_completed = 0
    avatar_completed = 0
    family_interactions = 0
    routine_completions = 0
    for event in events:
        event_time = parse_iso_datetime(event.get("eventTime"))
        event_day = event_time.strftime("%Y-%m-%d")
        person_id = event.get("personId") or "unknown-person"
        active_people.add(person_id)
        name = event.get("eventName")
        if is_meaningful_product_event(event):
            meaningful_days.add((person_id, event_day))
        if name == "voice_session_started":
            voice_started += 1
        elif name == "voice_session_completed":
            voice_completed += 1
        elif name == "avatar_session_completed":
            avatar_completed += 1
        elif name in ("family_interaction_sent", "family_message_sent", "family_message_viewed", "family_dashboard_viewed", "activity_created"):
            family_interactions += 1
        elif name == "routine_reminder_completed":
            routine_completions += 1
    return {
        "ok": True,
        "metric": "Weekly Meaningful Companion Days",
        "windowDays": days,
        "since": since_day.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "meaningfulCompanionDays": len(meaningful_days),
        "activePeople": len(active_people),
        "voiceSessionSuccessRate": round(voice_completed / voice_started, 4) if voice_started else None,
        "voiceSessionsStarted": voice_started,
        "voiceSessionsCompleted": voice_completed,
        "avatarSessionsCompleted": avatar_completed,
        "routineCompletions": routine_completions,
        "familyInteractions": family_interactions,
        "eventCount": len(events),
        "excludedEventCount": excluded_events,
        "backend": data_backend_status(),
    }


def safe_number(value, fallback=0):
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def admin_usage_summary(data=None):
    data = data or {}
    days = max(1, min(90, int(data.get("days") or 30)))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days - 1)
    since_day = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    all_events = load_product_events(since_iso=since_day.strftime("%Y-%m-%dT%H:%M:%SZ"), limit=2000)
    events = [event for event in all_events if not is_analytics_excluded_event(event)]
    event_counts = {}
    daily = {}
    voice_minutes = 0.0
    avatar_minutes = 0.0
    voice_started = 0
    voice_completed = 0
    for event in events:
        name = event.get("eventName") or "unknown_event"
        props = event.get("properties") or {}
        event_counts[name] = event_counts.get(name, 0) + 1
        event_day = parse_iso_datetime(event.get("eventTime")).strftime("%Y-%m-%d")
        bucket = daily.setdefault(event_day, {"events": 0, "meaningfulEvents": 0, "voiceMinutes": 0, "avatarMinutes": 0})
        bucket["events"] += 1
        if is_meaningful_product_event(event):
            bucket["meaningfulEvents"] += 1
        if name == "voice_session_started":
            voice_started += 1
        elif name == "voice_session_completed":
            voice_completed += 1
            minutes = safe_number(props.get("durationMinutes") or props.get("duration_minutes"))
            if not minutes:
                minutes = safe_number(props.get("durationMs") or props.get("duration_ms")) / 60000
            voice_minutes += minutes
            bucket["voiceMinutes"] = round(bucket["voiceMinutes"] + minutes, 2)
        elif name == "avatar_session_completed":
            minutes = safe_number(props.get("durationMinutes") or props.get("duration_minutes"))
            if not minutes:
                minutes = safe_number(props.get("durationMs") or props.get("duration_ms")) / 60000
            avatar_minutes += minutes
            bucket["avatarMinutes"] = round(bucket["avatarMinutes"] + minutes, 2)
    return {
        "ok": True,
        "windowDays": days,
        "since": since_day.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "northStar": north_star_summary({"days": min(days, 30)}),
        "totals": {
            "events": len(events),
            "excludedEvents": len(all_events) - len(events),
            "voiceMinutes": round(voice_minutes, 2),
            "avatarMinutes": round(avatar_minutes, 2),
            "voiceSessionSuccessRate": round(voice_completed / voice_started, 4) if voice_started else None,
        },
        "eventCounts": dict(sorted(event_counts.items())),
        "daily": [{"date": date, **daily[date]} for date in sorted(daily.keys())],
        "backend": data_backend_status(),
    }


def normalize_admin_account_summary(item=None):
    item = item or {}
    family_group = item.get("familyGroup") or item.get("family_group") or {}
    primary_person = item.get("primaryPerson") or item.get("primary_person") or {}
    companion = item.get("companion") or {}
    family_members = item.get("familyMembers") or item.get("family_members") or {}
    roles = family_members.get("byRole") or family_members.get("by_role") or {}
    return {
        "accountId": str(item.get("accountId") or item.get("account_id") or ""),
        "accountName": str(item.get("accountName") or item.get("account_name") or ""),
        "locale": str(item.get("locale") or "zh-TW"),
        "preferredLanguages": item.get("preferredLanguages") or item.get("preferred_languages") or ["zh-TW", "en"],
        "createdAt": item.get("createdAt") or item.get("created_at"),
        "updatedAt": item.get("updatedAt") or item.get("updated_at"),
        "familyGroup": {
            "id": str(family_group.get("id") or ""),
            "name": str(family_group.get("name") or "Munea Care Circle"),
        },
        "primaryPerson": {
            "id": str(primary_person.get("id") or ""),
            "displayName": str(primary_person.get("displayName") or primary_person.get("display_name") or ""),
            "relationship": str(primary_person.get("relationship") or "self"),
            "locale": str(primary_person.get("locale") or item.get("locale") or "zh-TW"),
            "timezone": str(primary_person.get("timezone") or "Asia/Taipei"),
        },
        "companion": {
            "templateId": str(companion.get("templateId") or companion.get("template_id") or "nening-real-female"),
            "displayName": str(companion.get("displayName") or companion.get("display_name") or "Munea"),
            "nameTouched": bool(companion.get("nameTouched") or companion.get("name_touched")),
        },
        "familyMembers": {
            "count": int(family_members.get("count") or 0),
            "byRole": dict(sorted(roles.items())),
        },
    }


def local_admin_account_summary():
    store = load_app_profile_store()
    account = store.get("account") or {}
    family_group = store.get("familyGroup") or {}
    primary_id = store.get("primaryCareRecipientId") or PRIMARY_CARE_RECIPIENT_ID
    members = [normalize_family_member(member) for member in family_group.get("members", [])]
    primary_member = next((member for member in members if member.get("id") == primary_id), None) or {}
    roles = {}
    for member in members:
        role = member.get("role") or "unknown"
        roles[role] = roles.get(role, 0) + 1
    companion = (store.get("companionProfiles") or {}).get(primary_id) or active_companion_profile(store)
    return normalize_admin_account_summary({
        "accountId": account.get("id"),
        "accountName": account.get("name") or account.get("id") or "local-demo-account",
        "locale": account.get("locale"),
        "preferredLanguages": account.get("preferredLanguages"),
        "createdAt": account.get("createdAt"),
        "updatedAt": store.get("updatedAt"),
        "familyGroup": {
            "id": family_group.get("id"),
            "name": family_group.get("name"),
        },
        "primaryPerson": {
            "id": primary_id,
            "displayName": primary_member.get("displayName") or "Primary user",
            "relationship": primary_member.get("relationship") or "self",
            "locale": account.get("locale") or "zh-TW",
            "timezone": "Asia/Taipei",
        },
        "companion": companion,
        "familyMembers": {
            "count": len(members),
            "byRole": roles,
        },
    })


def load_admin_accounts(query=None, limit=50):
    try:
        remote_accounts = data_backend().load_admin_accounts(query=query, limit=limit)
        if remote_accounts is not None:
            return [normalize_admin_account_summary(account) for account in remote_accounts]
    except Exception as e:
        log_fallback_exception("load admin accounts from Supabase", e)
    return [local_admin_account_summary()]


def _normalize_account_plan(raw):
    """訂閱事件的方案字串 → 'pro' / 'plus' / 'free'（真資料·認不出當免費）。"""
    s = str(raw or "").lower()
    if "pro" in s:
        return "pro"
    if "plus" in s or "premium" in s:
        return "plus"
    return "free"


def _account_activity_index(days=30):
    """按帳號彙總真實活動：通話+視訊分鐘、最後活躍、事件數、方案。
    事件沒帶 accountId 的歸到 unattributed；單帳號 scoped 時由呼叫端併回唯一帳號。"""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=max(1, min(90, int(days))) - 1)
    since_day = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    all_events = load_product_events(since_iso=since_day.strftime("%Y-%m-%dT%H:%M:%SZ"), limit=5000)
    events = [e for e in all_events if not is_analytics_excluded_event(e)]
    index = {}
    unattributed = {"voiceMinutes": 0.0, "avatarMinutes": 0.0, "eventCount": 0,
                    "lastActiveAt": None, "plan": None, "planAt": None}

    def bucket(aid):
        if not aid:
            return unattributed
        return index.setdefault(aid, {"voiceMinutes": 0.0, "avatarMinutes": 0.0, "eventCount": 0,
                                      "lastActiveAt": None, "plan": None, "planAt": None})

    for e in events:
        b = bucket(e.get("accountId") or "")
        b["eventCount"] += 1
        et = e.get("eventTime")
        if et and (b["lastActiveAt"] is None or et > b["lastActiveAt"]):
            b["lastActiveAt"] = et
        name = e.get("eventName") or ""
        props = e.get("properties") or {}
        if name in ("voice_session_completed", "avatar_session_completed"):
            minutes = safe_number(props.get("durationMinutes") or props.get("duration_minutes"))
            if not minutes:
                minutes = safe_number(props.get("durationMs") or props.get("duration_ms")) / 60000
            key = "voiceMinutes" if name == "voice_session_completed" else "avatarMinutes"
            b[key] += minutes
        elif name == "subscription_purchased":
            plan = props.get("plan") or props.get("productId") or props.get("tier")
            if plan and (b["planAt"] is None or (et and et > b["planAt"])):
                b["plan"] = plan
                b["planAt"] = et
    return index, unattributed


def _derive_account_status(last_active_iso, event_count):
    """由真實最後活躍時間推活躍狀態：on 活躍中 / idle 低度使用 / off 離線。"""
    if not last_active_iso or not event_count:
        return "off"
    try:
        last = parse_iso_datetime(last_active_iso)
        gap_days = (datetime.now(timezone.utc) - last).total_seconds() / 86400
    except Exception:
        return "off"
    if gap_days <= 3:
        return "on"
    if gap_days <= 13:
        return "idle"
    return "off"


def _account_points_map(accounts):
    """每帳號的持有點數（真實錢包餘額）。試營運鎖單戶時用 scoped 錢包餘額；
    多帳號時各查各的（沒有就 0）。失敗一律回 0、不編。"""
    points = {}
    try:
        store = load_credits_store()
        total = credit_wallet_summary(store).get("total") or 0
        store_account = store.get("accountId")
        single = len(accounts) == 1
        for acct in accounts:
            aid = acct.get("accountId") or ""
            if single or (store_account and aid == store_account):
                points[aid] = round(float(total), 0)
            else:
                points[aid] = 0
    except Exception as e:
        log_fallback_exception("load per-account points", e)
    return points


def _enrich_accounts_with_activity(accounts, days=30):
    """幫每個帳號補真資料：plan / usage（分鐘·最後活躍·事件數）/ status / points（持有點數）。
    單帳號 scoped（試營運鎖一戶）時把未歸戶事件併給唯一帳號、誠實不亂攤。"""
    index, unattributed = _account_activity_index(days=days)
    points_map = _account_points_map(accounts)
    single = len(accounts) == 1
    for acct in accounts:
        aid = acct.get("accountId") or ""
        agg = dict(index.get(aid) or {"voiceMinutes": 0.0, "avatarMinutes": 0.0,
                                      "eventCount": 0, "lastActiveAt": None, "plan": None, "planAt": None})
        if single:
            agg["voiceMinutes"] += unattributed["voiceMinutes"]
            agg["avatarMinutes"] += unattributed["avatarMinutes"]
            agg["eventCount"] += unattributed["eventCount"]
            if unattributed["lastActiveAt"] and (not agg["lastActiveAt"] or unattributed["lastActiveAt"] > agg["lastActiveAt"]):
                agg["lastActiveAt"] = unattributed["lastActiveAt"]
            if unattributed["plan"] and not agg["plan"]:
                agg["plan"] = unattributed["plan"]
        voice = round(agg["voiceMinutes"], 1)
        avatar = round(agg["avatarMinutes"], 1)
        acct["plan"] = _normalize_account_plan(agg["plan"])
        acct["usage"] = {
            "totalMinutes": round(voice + avatar, 1),
            "voiceMinutes": voice,
            "avatarMinutes": avatar,
            "eventCount": int(agg["eventCount"]),
            "lastActiveAt": agg["lastActiveAt"],
        }
        acct["status"] = _derive_account_status(agg["lastActiveAt"], agg["eventCount"])
        acct["points"] = int(points_map.get(acct.get("accountId") or "", 0) or 0)
    return accounts


def admin_accounts_summary(data=None):
    data = data or {}
    limit = max(1, min(200, int(data.get("limit") or 50)))
    query = str(data.get("query") or "").strip()
    account_id = data.get("accountId") or data.get("account_id")
    family_group_id = data.get("familyGroupId") or data.get("family_group_id")
    person_id = data.get("personId") or data.get("person_id")
    accounts = load_admin_accounts(query=query, limit=limit)
    if account_id:
        accounts = [account for account in accounts if account.get("accountId") == account_id]
    if family_group_id:
        accounts = [account for account in accounts if (account.get("familyGroup") or {}).get("id") == family_group_id]
    if person_id:
        accounts = [account for account in accounts if (account.get("primaryPerson") or {}).get("id") == person_id]
    if query:
        q = query.lower()
        accounts = [
            account for account in accounts
            if q in (account.get("accountId") or "").lower()
            or q in (account.get("accountName") or "").lower()
            or q in ((account.get("familyGroup") or {}).get("name") or "").lower()
            or q in ((account.get("primaryPerson") or {}).get("displayName") or "").lower()
        ]
    accounts = _enrich_accounts_with_activity(accounts[:limit], days=int(data.get("days") or 30))
    return {
        "ok": True,
        "count": len(accounts),
        "filters": {
            "query": query,
            "accountId": account_id,
            "familyGroupId": family_group_id,
            "personId": person_id,
            "limit": limit,
        },
        "accounts": accounts,
        "privacy": {
            "surface": "admin_account_lookup",
            "rawTranscriptRecords": 0,
        },
        "backend": data_backend_status(),
    }


def admin_credits_summary(data=None):
    data = data or {}
    limit = max(1, min(100, int(data.get("limit") or 25)))
    billing = load_billing_store()
    credits = load_credits_store()
    return {
        "ok": True,
        "accountId": billing.get("accountId") or credits.get("accountId"),
        "activePlan": billing.get("activePlan"),
        "subscription": billing.get("subscription"),
        "entitlements": billing.get("entitlements"),
        "usageLedger": billing.get("usageLedger"),
        "walletSummary": credit_wallet_summary(credits),
        "wallets": credits.get("wallets", []),
        "recentTransactions": credits.get("transactions", [])[:limit],
        "recentLedger": credits.get("ledger", [])[:limit],
        "serverVerificationRequired": bool(billing.get("serverVerificationRequired", True)),
        "backend": data_backend_status(),
    }


def admin_subscription_metrics(data=None):
    """訂閱營運聚合：從 product_events 算能算的真數字（新增訂閱/點數/註冊/轉換率）；
    MRR 與流失率需要『目前有效訂閱聚合』與『取消事件』，尚未具備時誠實回 None + 原因。"""
    data = data or {}
    days = max(1, min(90, int(data.get("days") or 30)))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days - 1)
    since_day = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    all_events = load_product_events(since_iso=since_day.strftime("%Y-%m-%dT%H:%M:%SZ"), limit=2000)
    events = [event for event in all_events if not is_analytics_excluded_event(event)]
    new_subs = 0
    subs_by_plan = {}
    points_purchases = 0
    points_total = 0.0
    registrations = 0
    for event in events:
        name = event.get("eventName")
        props = event.get("properties") or {}
        if name == "subscription_purchased":
            new_subs += 1
            plan = str(props.get("plan") or props.get("productId") or "unknown")
            subs_by_plan[plan] = subs_by_plan.get(plan, 0) + 1
        elif name == "points_purchased":
            points_purchases += 1
            points_total += safe_number(props.get("points"))
        elif name == "onboarding_completed":
            registrations += 1
    conversion = round(new_subs / registrations, 4) if registrations else None
    return {
        "ok": True,
        "windowDays": days,
        "since": since_day.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "newSubscriptions": new_subs,
        "newSubscriptionsByPlan": dict(sorted(subs_by_plan.items())),
        "pointsPurchases": points_purchases,
        "pointsTotal": round(points_total),
        "registrations": registrations,
        "freeToPaidConversion": conversion,
        "mrr": None,
        "activeSubscribersByPlan": None,
        "churnRate": None,
        "pending": {
            "mrr": "需要跨帳號『目前有效訂閱』聚合（訂閱事件只記新購、不記目前狀態）",
            "churnRate": "需要 subscription_cancelled / subscription_downgraded 事件（目前只記進、不記出）",
        },
        "backend": data_backend_status(),
    }


def admin_conversation_summaries(data=None):
    data = data or {}
    limit = max(1, min(200, int(data.get("limit") or 50)))
    include_deleted = bool(data.get("includeDeleted") or data.get("include_deleted"))
    person_id = data.get("personId") or data.get("person_id")
    summaries = load_conversation_summaries(
        person_id=person_id,
        limit=limit,
        include_deleted=include_deleted,
    )
    tag_counts = {}
    safety_relevant = 0
    deleted = 0
    for summary in summaries:
        if summary.get("safetyRelevant"):
            safety_relevant += 1
        if summary.get("deletedAt"):
            deleted += 1
        for tag in summary.get("memoryTags") or []:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    top_tags = [
        {"tag": tag, "count": count}
        for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    recent = [
        {
            "id": summary.get("id"),
            "personId": summary.get("personId"),
            "createdAt": summary.get("createdAt"),
            "deletedAt": summary.get("deletedAt"),
            "memoryTags": summary.get("memoryTags") or [],
            "safetyRelevant": summary.get("safetyRelevant") is True,
            "summary": summary.get("summary") or "",
            "privacy": summary.get("privacy") or {"storesRawTranscriptByDefault": False},
        }
        for summary in summaries[:limit]
    ]
    return {
        "ok": True,
        "count": len(summaries),
        "filters": {
            "personId": person_id,
            "limit": limit,
            "includeDeleted": include_deleted,
        },
        "totals": {
            "safetyRelevant": safety_relevant,
            "deleted": deleted,
            "rawTranscriptRecords": 0,
        },
        "topTags": top_tags,
        "recent": recent,
        "privacy": {
            "storesRawTranscriptByDefault": False,
            "surface": "admin_summary_only",
        },
        "backend": data_backend_status(),
    }


def admin_privacy_requests_summary(data=None):
    data = data or {}
    limit = max(1, min(200, int(data.get("limit") or 50)))
    request_type = data.get("type") or data.get("requestType") or data.get("request_type")
    status_filter = data.get("status")
    account_id = data.get("accountId") or data.get("account_id")
    store = load_privacy_requests_store()
    requests = store.get("requests") or []
    if request_type:
        requests = [req for req in requests if req.get("type") == request_type]
    if status_filter:
        requests = [req for req in requests if req.get("status") == status_filter]
    if account_id:
        requests = [req for req in requests if req.get("accountId") == account_id]
    requests = sorted(requests, key=lambda req: req.get("requestedAt") or "", reverse=True)
    type_counts = {}
    status_counts = {}
    reauth_required = 0
    subscription_notice_required = 0
    for req in requests:
        req_type = req.get("type") or "unknown"
        req_status = req.get("status") or "unknown"
        type_counts[req_type] = type_counts.get(req_type, 0) + 1
        status_counts[req_status] = status_counts.get(req_status, 0) + 1
        if req.get("requiresReauth"):
            reauth_required += 1
        if req.get("subscriptionNoticeRequired"):
            subscription_notice_required += 1
    recent = [
        {
            "id": req.get("id"),
            "type": req.get("type"),
            "status": req.get("status"),
            "accountId": req.get("accountId"),
            "requestedAt": req.get("requestedAt"),
            "completedAt": req.get("completedAt"),
            "reason": req.get("reason") or "",
            "requiresReauth": req.get("requiresReauth") is True,
            "subscriptionNoticeRequired": req.get("subscriptionNoticeRequired") is True,
        }
        for req in requests[:limit]
    ]
    return {
        "ok": True,
        "count": len(requests),
        "filters": {
            "accountId": account_id,
            "type": request_type,
            "status": status_filter,
            "limit": limit,
        },
        "totals": {
            "byType": dict(sorted(type_counts.items())),
            "byStatus": dict(sorted(status_counts.items())),
            "reauthRequired": reauth_required,
            "subscriptionNoticeRequired": subscription_notice_required,
        },
        "recent": recent,
        "retentionPolicy": store.get("retentionPolicy") or {},
        "privacy": {
            "surface": "admin_privacy_request_review",
            "rawTranscriptRecords": 0,
        },
        "backend": data_backend_status(),
    }


def admin_safety_events_summary(data=None):
    data = data or {}
    limit = max(1, min(200, int(data.get("limit") or 50)))
    days = max(1, min(365, int(data.get("days") or 30)))
    level_filter = data.get("level") or data.get("riskLevel") or data.get("risk_level")
    category_filter = data.get("category")
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days - 1)
    since_day = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    events = load_product_events(since_iso=since_day.strftime("%Y-%m-%dT%H:%M:%SZ"), limit=2000)
    safety_events = []
    for event in events:
        if event.get("eventName") != "guardian_risk_evaluated":
            continue
        props = event.get("properties") or {}
        categories = props.get("categories") or []
        if isinstance(categories, str):
            categories = [categories]
        risk_level = props.get("riskLevel") or props.get("risk_level") or "unknown"
        if level_filter and risk_level != level_filter:
            continue
        if category_filter and category_filter not in categories:
            continue
        safety_events.append({
            "id": event.get("id"),
            "source": "guardian",
            "riskLevel": risk_level,
            "categories": categories,
            "personId": event.get("personId"),
            "familyGroupId": event.get("familyGroupId"),
            "eventTime": event.get("eventTime") or event.get("createdAt"),
            "requiresHumanEscalation": risk_level in {"high", "crisis"},
            "analyticsExcluded": bool(props.get("analyticsExcluded")),
        })
    summaries = load_conversation_summaries(limit=500, include_deleted=False)
    for summary in summaries:
        if not summary.get("safetyRelevant"):
            continue
        tags = summary.get("memoryTags") or []
        if category_filter and category_filter not in tags:
            continue
        safety_events.append({
            "id": summary.get("id"),
            "source": "conversation_summary",
            "riskLevel": "review",
            "categories": tags,
            "personId": summary.get("personId"),
            "familyGroupId": summary.get("familyGroupId"),
            "eventTime": summary.get("createdAt"),
            "requiresHumanEscalation": False,
            "analyticsExcluded": False,
        })
    if level_filter:
        safety_events = [event for event in safety_events if event.get("riskLevel") == level_filter]
    safety_events = sorted(safety_events, key=lambda event: event.get("eventTime") or "", reverse=True)
    level_counts = {}
    category_counts = {}
    escalation_count = 0
    for event in safety_events:
        level = event.get("riskLevel") or "unknown"
        level_counts[level] = level_counts.get(level, 0) + 1
        if event.get("requiresHumanEscalation"):
            escalation_count += 1
        for category in event.get("categories") or []:
            category_counts[category] = category_counts.get(category, 0) + 1
    top_categories = [
        {"category": category, "count": count}
        for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]
    return {
        "ok": True,
        "count": len(safety_events),
        "filters": {
            "days": days,
            "since": since_day.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": level_filter,
            "category": category_filter,
            "limit": limit,
        },
        "totals": {
            "byRiskLevel": dict(sorted(level_counts.items())),
            "requiresHumanEscalation": escalation_count,
            "summaryReviewRecords": sum(1 for event in safety_events if event.get("source") == "conversation_summary"),
            "rawTranscriptRecords": 0,
        },
        "topCategories": top_categories,
        "recent": safety_events[:limit],
        "privacy": {
            "surface": "admin_safety_event_review",
            "storesRawTranscriptByDefault": False,
        },
        "backend": data_backend_status(),
    }


FEEDBACK_PATH = os.environ.get("MUNEA_FEEDBACK_PATH") or os.path.join(HERE, "feedback_store.json")

def feedback_response(data):
    """意見與建議收件箱：type=bug|idea|praise|nps ＋ 分類/內容/分數＋自動情境（版本/方案），供後台篩選整理。"""
    data = data or {}
    ftype = str(data.get("type") or "").strip()
    if ftype not in ("bug", "idea", "praise", "nps", "survey"):
        return {"ok": False, "error": {"code": "bad_type", "message": "unknown feedback type"}}
    item = {
        "id": f"fb_{int(time.time()*1000)}",
        "type": ftype,
        "category": str(data.get("category") or "")[:24],       # 聊聊/提醒/家人圈/付費/其他…
        "text": str(data.get("text") or "")[:2000],
        "score": (int(data.get("score")) if str(data.get("score") or "").strip().lstrip("-").isdigit() else None),  # NPS 0-10
        "appVersion": str(data.get("appVersion") or "")[:16],
        "plan": str(data.get("plan") or "")[:12],
        "createdAt": utc_now(),
    }
    # 選擇性附圖（7/9 Edward：文字說不清時附截圖）：用戶端已壓成小圖 data URL；伺服器把關格式與大小
    img = data.get("image")
    if isinstance(img, str) and img.startswith("data:image/") and len(img) <= 700000:  # ~700KB 上限（壓過的小圖綽綽有餘）
        item["image"] = img
    items = read_json_file(FEEDBACK_PATH, [])
    if not isinstance(items, list):
        items = []
    items.append(item)
    write_json_file(FEEDBACK_PATH, items[-5000:])
    try:
        label = {"bug": "🐞問題", "idea": "💡建議", "praise": "❤️稱讚", "nps": "📊NPS", "survey": "📋問卷"}.get(ftype, ftype)
        summary = (item["category"] + " · " if item["category"] else "") + (f"{item['score']} 分" if item["score"] is not None else (item["text"][:60] or ""))
        notify.ops("feedback_received", f"{label} {summary}")
    except Exception as notify_error:
        log_fallback_exception("send feedback notification", notify_error)
    return {"ok": True, "id": item["id"]}

def admin_feedback_summary(data=None):
    """後台整理：按類型/分類統計＋最新清單＋NPS 計算（推薦者9-10/中立7-8/批評者0-6）。"""
    data = data or {}
    items = read_json_file(FEEDBACK_PATH, [])
    if not isinstance(items, list):
        items = []
    by_type, by_cat = {}, {}
    nps_scores = []
    for it in items:
        by_type[it.get("type") or "?"] = by_type.get(it.get("type") or "?", 0) + 1
        if it.get("category"):
            by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1
        if it.get("type") == "nps" and isinstance(it.get("score"), int):
            nps_scores.append(it["score"])
    nps = None
    if nps_scores:
        promoters = sum(1 for x in nps_scores if x >= 9)
        detractors = sum(1 for x in nps_scores if x <= 6)
        nps = round((promoters - detractors) / len(nps_scores) * 100)
    limit = max(1, min(200, int(data.get("limit") or 50)))
    ftype = data.get("type")
    latest = [it for it in reversed(items) if not ftype or it.get("type") == ftype][:limit]
    return {"ok": True, "totals": by_type, "byCategory": by_cat, "nps": nps, "npsCount": len(nps_scores), "latest": latest}


def product_event_response(data):
    event = append_product_event(data)
    try:
        name = (event or {}).get("eventName") or ""
        if name in ("subscription_purchased", "points_purchased", "onboarding_completed", "health_connected")            and not is_analytics_excluded_event(event):
            props = (event or {}).get("properties") or {}
            summary = props.get("plan") or (str(props.get("points")) + " 點" if props.get("points") else "")
            notify.ops(name, summary)
    except Exception as e:
        log_fallback_exception("send product event ops notification", e)
    return {"ok": True, "event": event, "northStar": north_star_summary({"days": 7})}


def safe_diagnostic_duration_ms(value):
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


def safe_diagnostic_endpoint(value):
    raw = str(value or "").strip()[:512]
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlsplit(raw)
        if not parsed.scheme or not parsed.hostname:
            return raw.split("?", 1)[0].split("#", 1)[0][:160]
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))[:160]
    except (TypeError, ValueError):
        return raw.split("?", 1)[0].split("#", 1)[0].split("@", 1)[-1][:160]


def admin_voice_diagnostics_summary(data=None):
    """Summarize call traces without exposing audio, captions, tokens, or SDP."""
    data = data or {}
    days = max(1, min(30, int(data.get("days") or 7)))
    limit = max(1, min(200, int(data.get("limit") or 50)))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    events = load_product_events(since_iso=since.strftime("%Y-%m-%dT%H:%M:%SZ"), limit=5000)
    traces = []
    by_outcome = {}
    by_failed_stage = {}
    by_last_success = {}
    total_ms = []
    for event in events:
        if event.get("eventName") != "voice_call_diagnostic":
            continue
        props = event.get("properties") if isinstance(event.get("properties"), dict) else {}
        outcome = str(props.get("outcome") or "unknown")[:40]
        failed_stage = str(props.get("firstFailedStage") or "")[:80]
        last_success = str(props.get("lastSuccessfulStage") or "")[:80]
        duration_ms = safe_diagnostic_duration_ms(props.get("totalMs"))
        context = props.get("context") if isinstance(props.get("context"), dict) else {}
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        if failed_stage:
            by_failed_stage[failed_stage] = by_failed_stage.get(failed_stage, 0) + 1
        if last_success:
            by_last_success[last_success] = by_last_success.get(last_success, 0) + 1
        total_ms.append(duration_ms)
        traces.append({
            "callId": str(props.get("callId") or event.get("sessionId") or "")[:96],
            "eventTime": event.get("eventTime") or event.get("createdAt"),
            "outcome": outcome,
            "reason": str(props.get("reason") or "")[:96],
            "firstFailedStage": failed_stage,
            "lastSuccessfulStage": last_success,
            "totalMs": duration_ms,
            "appVersion": str(context.get("appVersion") or "")[:24],
            "routeMode": str(context.get("routeMode") or "")[:40],
            "voiceEndpoint": safe_diagnostic_endpoint(context.get("voiceEndpoint")),
            "avatarEndpoint": safe_diagnostic_endpoint(context.get("avatarEndpoint")),
        })
    traces.sort(key=lambda item: item.get("eventTime") or "", reverse=True)
    successful = sum(by_outcome.get(name, 0) for name in ("connected", "completed"))
    return {
        "ok": True,
        "windowDays": days,
        "count": len(traces),
        "successRate": round(successful / len(traces), 4) if traces else None,
        "totals": {
            "byOutcome": dict(sorted(by_outcome.items())),
            "byFailedStage": dict(sorted(by_failed_stage.items(), key=lambda item: (-item[1], item[0]))),
            "byLastSuccessfulStage": dict(sorted(by_last_success.items(), key=lambda item: (-item[1], item[0]))),
            "averageTotalMs": round(sum(total_ms) / len(total_ms)) if total_ms else None,
        },
        "recent": traces[:limit],
        "privacy": {
            "rawAudioStored": False,
            "rawTranscriptStored": False,
            "credentialsStored": False,
        },
        "backend": data_backend_status(),
    }


def admin_authorized(headers):
    token = os.environ.get("MUNEA_ADMIN_API_TOKEN") or ""
    if not token:
        return False, "admin_token_not_configured"
    supplied = headers.get("X-Munea-Admin-Token") or headers.get("x-munea-admin-token") or ""
    if not hmac.compare_digest(str(supplied), str(token)):
        return False, "invalid_admin_token"
    return True, None


def admin_login_response(data=None, client_ip=None):
    """後台帳密登入門：帳號(email)+密碼對了，才發後台通行碼。
    密碼存在 Secret Manager（MUNEA_ADMIN_PASSWORD）、不寫在程式裡。
    比對用 compare_digest 防側錄；同來源錯太多次先擋（防猜）。"""
    data = data or {}
    if login_rate_limited(client_ip):
        return {"ok": False, "error": "too_many_attempts"}
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    want_email = str(os.environ.get("MUNEA_ADMIN_EMAIL") or "").strip().lower()
    want_password = str(os.environ.get("MUNEA_ADMIN_PASSWORD") or "")
    admin_token = str(os.environ.get("MUNEA_ADMIN_API_TOKEN") or "")
    if not want_email or not want_password or not admin_token:
        return {"ok": False, "error": "login_not_configured"}
    email_ok = hmac.compare_digest(email, want_email)
    password_ok = hmac.compare_digest(password, want_password)
    if not (email_ok and password_ok):
        record_login_failure(client_ip)
        return {"ok": False, "error": "invalid_credentials"}
    return {"ok": True, "token": admin_token}


def provider_webhook_authorized(headers):
    token = os.environ.get("MUNEA_PROVIDER_WEBHOOK_TOKEN") or ""
    if not token:
        return False, "provider_token_not_configured"
    supplied = headers.get("X-Munea-Provider-Token") or headers.get("x-munea-provider-token") or ""
    if not hmac.compare_digest(str(supplied), str(token)):
        return False, "invalid_provider_token"
    return True, None


def privileged_billing_write_authorized(headers, allow_provider=False):
    if not auth_required_mode():
        return True, None
    ok, code = admin_authorized(headers)
    if ok:
        return True, None
    if allow_provider:
        provider_ok, provider_code = provider_webhook_authorized(headers)
        if provider_ok:
            return True, None
        if code == "admin_token_not_configured":
            return False, provider_code
    return False, code


def privileged_actor_context(headers=None, allow_provider=False):
    headers = headers or {}
    admin_ok, _ = admin_authorized(headers)
    if admin_ok:
        return {"actorType": "admin", "auth": "admin-token"}
    if allow_provider:
        provider_ok, _ = provider_webhook_authorized(headers)
        if provider_ok:
            return {"actorType": "provider", "auth": "provider-webhook"}
    if not auth_required_mode():
        return {"actorType": "local-prototype", "auth": "none"}
    return {"actorType": "unknown", "auth": "unverified"}


def default_audit_events_store():
    return {"schemaVersion": 1, "events": [], "updatedAt": utc_now()}


def load_audit_events(limit=100):
    limit = max(1, min(500, int(limit or 100)))
    try:
        remote_events = data_backend().load_audit_events(limit=limit)
        if remote_events is not None:
            return [normalize_audit_event(event) for event in remote_events][:limit]
    except Exception as e:
        log_fallback_exception("load audit events from Supabase", e)
    store = read_json_file(AUDIT_EVENTS_STORE_PATH, default_audit_events_store())
    events = [normalize_audit_event(event) for event in store.get("events", [])]
    return events[:limit]


def normalize_audit_event(event=None):
    event = event or {}
    return {
        "id": event.get("id") or f"audit_{int(time.time() * 1000)}",
        "accountId": event.get("accountId") or event.get("account_id") or "local-demo-account",
        "actorUserId": event.get("actorUserId") or event.get("actor_user_id"),
        "eventType": str(event.get("eventType") or event.get("event_type") or "unknown_event")[:80],
        "targetTable": event.get("targetTable") or event.get("target_table"),
        "targetId": event.get("targetId") or event.get("target_id"),
        "details": event.get("details") or {},
        "createdAt": event.get("createdAt") or event.get("created_at") or utc_now(),
    }


def append_audit_event(event=None):
    normalized = normalize_audit_event(event)
    try:
        remote_event = data_backend().append_audit_event(normalized)
        if remote_event:
            return normalize_audit_event(remote_event)
    except Exception as e:
        log_fallback_exception("append audit event to Supabase", e)
    store = read_json_file(AUDIT_EVENTS_STORE_PATH, default_audit_events_store())
    events = [normalize_audit_event(e) for e in store.get("events", [])]
    events.insert(0, normalized)
    store = {"schemaVersion": 1, "events": events[:1000], "updatedAt": utc_now()}
    write_json_file(AUDIT_EVENTS_STORE_PATH, store)
    return normalized


def admin_audit_events_summary(data=None):
    data = data or {}
    limit = max(1, min(200, int(data.get("limit") or 50)))
    event_type = data.get("eventType") or data.get("event_type")
    actor_type = data.get("actorType") or data.get("actor_type")
    target_table = data.get("targetTable") or data.get("target_table")
    events = load_audit_events(limit=500)
    if event_type:
        events = [event for event in events if event.get("eventType") == event_type]
    if target_table:
        events = [event for event in events if event.get("targetTable") == target_table]
    if actor_type:
        events = [
            event for event in events
            if (event.get("details") or {}).get("actorType") == actor_type
        ]
    events = sorted(events, key=lambda event: event.get("createdAt") or "", reverse=True)
    type_counts = {}
    actor_counts = {}
    target_counts = {}
    for event in events:
        event_name = event.get("eventType") or "unknown_event"
        actor_name = (event.get("details") or {}).get("actorType") or "unknown"
        target_name = event.get("targetTable") or "unknown"
        type_counts[event_name] = type_counts.get(event_name, 0) + 1
        actor_counts[actor_name] = actor_counts.get(actor_name, 0) + 1
        target_counts[target_name] = target_counts.get(target_name, 0) + 1
    recent = [
        {
            "id": event.get("id"),
            "accountId": event.get("accountId"),
            "actorUserId": event.get("actorUserId"),
            "eventType": event.get("eventType"),
            "targetTable": event.get("targetTable"),
            "targetId": event.get("targetId"),
            "details": event.get("details") or {},
            "createdAt": event.get("createdAt"),
        }
        for event in events[:limit]
    ]
    return {
        "ok": True,
        "count": len(events),
        "filters": {
            "eventType": event_type,
            "actorType": actor_type,
            "targetTable": target_table,
            "limit": limit,
        },
        "totals": {
            "byEventType": dict(sorted(type_counts.items())),
            "byActorType": dict(sorted(actor_counts.items())),
            "byTargetTable": dict(sorted(target_counts.items())),
        },
        "recent": recent,
        "privacy": {
            "surface": "admin_audit_event_review",
            "rawTranscriptRecords": 0,
        },
        "backend": data_backend_status(),
    }


def default_billing_store():
    return {
        "schemaVersion": 1,
        "accountId": "local-demo-account",
        "platform": "ios",
        "provider": "storekit2-or-revenuecat",
        "activePlan": "free",
        "subscription": {
            "status": "inactive",
            "productId": None,
            "originalTransactionId": None,
            "expiresAt": None,
            "willRenew": False,
            "lastVerifiedAt": None,
        },
        "entitlements": {
            "voiceCompanion": True,
            "familyDashboard": True,
            "routineReminders": True,
            "realtimeAvatar": True,
            "signupTrialCredits": 5,
            "creditMinutes": 1,
            "premiumAvatarMinutesMonthly": 0,
            "familyMembersMax": 1,
            "familyCircleInvite": False,
            "familyCircleJoin": False,
        },
        "usageLedger": {
            "period": time.strftime("%Y-%m"),
            "voiceMinutesUsed": 0,
            "avatarMinutesUsed": 0,
        },
        "serverVerificationRequired": True,
        "updatedAt": utc_now(),
    }


def default_credits_store():
    return {
        "schemaVersion": 1,
        "accountId": "local-demo-account",
        "personId": PRIMARY_CARE_RECIPIENT_ID,
        "currencyCode": "MUNEA_CREDIT",
        "wallets": [
            {
                "id": "wallet_included_monthly",
                "type": "included_monthly",
                "period": time.strftime("%Y-%m"),
                "balance": 0,
                "expiresAt": None,
                "status": "active",
            },
            {
                "id": "wallet_purchased",
                "type": "purchased",
                "period": None,
                "balance": 0,
                "expiresAt": None,
                "status": "active",
            },
        ],
        "transactions": [],
        "ledger": [],
        "updatedAt": utc_now(),
    }


def normalize_credit_amount(value):
    try:
        amount = round(float(value or 0), 4)
    except Exception:
        amount = 0
    return max(0, min(amount, 1_000_000))


def add_calendar_months(value, months):
    """Move an aware datetime by calendar months without drifting off month-end."""
    month_index = value.year * 12 + value.month - 1 + int(months)
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def credit_period_window(anchor, now=None, subscription_expires_at=None):
    """Return the current monthly billing window anchored to the purchase date."""
    now = now or datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    if now < anchor:
        start = anchor
        end = add_calendar_months(anchor, 1)
    else:
        offset = (now.year - anchor.year) * 12 + now.month - anchor.month
        start = add_calendar_months(anchor, offset)
        if start > now:
            offset -= 1
            start = add_calendar_months(anchor, offset)
        end = add_calendar_months(anchor, offset + 1)
    if subscription_expires_at and subscription_expires_at < end:
        end = subscription_expires_at
    return start, end


def credit_wallet_is_available(wallet, now=None):
    if wallet.get("status") != "active" or float(wallet.get("balance") or 0) <= 0:
        return False
    expires_at = wallet.get("expiresAt") or wallet.get("expires_at")
    if not expires_at:
        return True
    expires = parse_optional_iso_datetime(expires_at)
    return bool(expires and expires > (now or datetime.now(timezone.utc)))


def normalize_credit_wallet(data=None, wallet_type="purchased", period=None):
    data = data or {}
    wallet_type = data.get("type") or data.get("walletType") or data.get("wallet_type") or wallet_type
    wallet_type = wallet_type if wallet_type in ("included_monthly", "purchased") else "purchased"
    if wallet_type == "included_monthly":
        period = data.get("period") or period or time.strftime("%Y-%m")
    else:
        period = data.get("period")
    wallet_id = data.get("id") or f"wallet_{wallet_type}" + (f"_{period}" if period else "")
    return {
        "id": str(wallet_id)[:80],
        "type": wallet_type,
        "period": period,
        "balance": normalize_credit_amount(data.get("balance")),
        "expiresAt": data.get("expiresAt") or data.get("expires_at"),
        "status": str(data.get("status") or "active"),
    }


def normalize_credits_store(data=None):
    base = default_credits_store()
    data = data or {}
    wallets = [normalize_credit_wallet(w) for w in data.get("wallets", []) if isinstance(w, dict)]
    wallet_keys = {(w["type"], w.get("period")) for w in wallets}
    for wallet in base["wallets"]:
        key = (wallet["type"], wallet.get("period"))
        if key not in wallet_keys and wallet["type"] not in {w["type"] for w in wallets if w["type"] == "purchased"}:
            wallets.append(wallet)
    if not any(w["type"] == "included_monthly" for w in wallets):
        wallets.append(base["wallets"][0])
    if not any(w["type"] == "purchased" for w in wallets):
        wallets.append(base["wallets"][1])
    return {
        "schemaVersion": int(data.get("schemaVersion") or data.get("schema_version") or 1),
        "accountId": str(data.get("accountId") or data.get("account_id") or base["accountId"]),
        "personId": str(data.get("personId") or data.get("person_id") or base["personId"]),
        "currencyCode": str(data.get("currencyCode") or data.get("currency_code") or base["currencyCode"]),
        "wallets": wallets,
        "transactions": list(data.get("transactions") or [])[-500:],
        "ledger": list(data.get("ledger") or [])[-500:],
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or utc_now(),
    }


def load_credits_store():
    try:
        remote_store = data_backend().load_credits_store()
        if remote_store:
            return normalize_credits_store(remote_store)
    except Exception as e:
        log_fallback_exception("load credits store from Supabase", e)
    return normalize_credits_store(read_json_file(CREDITS_STORE_PATH, {}))


def save_credits_store(data):
    store = normalize_credits_store({**(data or {}), "updatedAt": utc_now()})
    try:
        remote_store = data_backend().save_credits_store(store)
        if remote_store:
            store = normalize_credits_store(remote_store)
    except Exception as e:
        log_fallback_exception("save credits store to Supabase", e)
    write_json_file(CREDITS_STORE_PATH, store)
    return store


def credit_wallet_summary(store):
    wallets = store.get("wallets") or []
    included = sum(float(w.get("balance") or 0) for w in wallets if w.get("type") == "included_monthly" and credit_wallet_is_available(w))
    purchased = sum(float(w.get("balance") or 0) for w in wallets if w.get("type") == "purchased" and credit_wallet_is_available(w))
    return {
        "includedMonthly": round(included, 4),
        "purchased": round(purchased, 4),
        "total": round(included + purchased, 4),
        "currencyCode": store.get("currencyCode") or "MUNEA_CREDIT",
    }


def find_credit_wallet(store, wallet_type, period=None):
    wallets = store.setdefault("wallets", [])
    for wallet in wallets:
        if wallet.get("type") == wallet_type and wallet.get("status") == "active" and (wallet_type != "included_monthly" or wallet.get("period") == period):
            return wallet
    wallet = normalize_credit_wallet({"type": wallet_type, "period": period}, wallet_type=wallet_type, period=period)
    wallets.append(wallet)
    return wallet


def close_included_credit_wallets(store, *, except_period=None, reason="monthly_allowance_expired"):
    """Expire unused subscription allowance while preserving purchased credits."""
    changed = False
    for wallet in store.get("wallets") or []:
        if wallet.get("type") != "included_monthly" or wallet.get("status") != "active" or wallet.get("period") == except_period:
            continue
        remaining = float(wallet.get("balance") or 0)
        wallet["balance"] = 0
        wallet["status"] = "closed"
        changed = True
        if remaining > 0:
            append_credit_transaction(
                store,
                transaction_type="expire",
                wallet=wallet,
                amount=-remaining,
                source="system",
                reason=reason,
                idempotency_key=f"expire:{wallet.get('id')}:{wallet.get('period') or 'none'}",
            )
    return changed


def monthly_allowance_details(billing, now=None):
    """Derive the current monthly allowance for both monthly and annual plans."""
    billing = normalize_billing_store(billing)
    if subscription_expiry_reason(billing, now=now) or billing.get("activePlan") in (None, "", "free"):
        return None
    subscription = billing.get("subscription") or {}
    entitlements = billing.get("entitlements") or {}
    product_id = str(subscription.get("productId") or "")
    product = apple_store.PRODUCTS.get(product_id) or {}
    amount = normalize_credit_amount(entitlements.get("monthlyCredits") or product.get("monthlyPoints"))
    if amount <= 0:
        return None
    expires = parse_optional_iso_datetime(subscription.get("expiresAt"))
    if subscription.get("expiresAt") and expires is None:
        return None
    anchor_value = entitlements.get("monthlyCreditAnchorAt") or subscription.get("originalPurchaseDate") or subscription.get("purchaseDate")
    anchor = parse_optional_iso_datetime(anchor_value)
    if anchor is None and expires:
        anchor = add_calendar_months(expires, -12 if product_id.endswith(".yearly") else -1)
    if anchor is None:
        anchor = parse_optional_iso_datetime(subscription.get("lastVerifiedAt"))
        if anchor is None:
            return None
    start, end = credit_period_window(anchor, now=now, subscription_expires_at=expires)
    if end <= (now or datetime.now(timezone.utc)):
        return None
    return {
        "amount": amount,
        "period": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ") + "/" + end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "startsAt": start.isoformat().replace("+00:00", "Z"),
        "expiresAt": end.isoformat().replace("+00:00", "Z"),
        "originalTransactionId": subscription.get("originalTransactionId") or "subscription",
    }


def ensure_current_monthly_allowance(now=None):
    billing = load_billing_store()
    details = monthly_allowance_details(billing, now=now)
    if not details:
        return None
    return credits_grant_response({
        "amount": details["amount"],
        "walletType": "included_monthly",
        "period": details["period"],
        "expiresAt": details["expiresAt"],
        "source": "included_monthly",
        "reason": "subscription_monthly_allowance",
        "provider": "apple_storekit2",
        "providerTransactionId": details["originalTransactionId"],
        "idempotencyKey": f"subscription-allowance:{details['originalTransactionId']}:{details['period']}",
    })


def credit_idempotency_response(store, key):
    if not key:
        return None
    matches = [
        tx for tx in store.get("transactions", [])
        if tx.get("idempotencyKey") == key or str(tx.get("idempotencyKey") or "").startswith(key + ":")
    ]
    if matches:
            return {
                "ok": True,
                "idempotentReplay": True,
                "transactions": matches,
                "transaction": matches[0],
                "walletSummary": credit_wallet_summary(store),
                "credits": store,
            }
    return None


def append_credit_transaction(store, *, transaction_type, wallet, amount, source, reason, idempotency_key, feature=None, provider=None, provider_transaction_id=None):
    tx = {
        "id": f"credit_tx_{int(time.time() * 1000)}_{len(store.get('transactions', [])) + 1}",
        "type": transaction_type,
        "walletId": wallet.get("id"),
        "walletType": wallet.get("type"),
        "amount": round(float(amount or 0), 4),
        "balanceAfter": round(float(wallet.get("balance") or 0), 4),
        "source": str(source or "system")[:40],
        "reason": str(reason or transaction_type)[:120],
        "feature": str(feature or "")[:80] or None,
        "provider": str(provider or "")[:40] or None,
        "providerTransactionId": str(provider_transaction_id or "")[:120] or None,
        "idempotencyKey": str(idempotency_key or tx_fallback_idempotency_key(transaction_type, wallet, amount))[:160],
        "createdAt": utc_now(),
    }
    store.setdefault("transactions", []).append(tx)
    store.setdefault("ledger", []).append({
        "id": f"credit_ledger_{int(time.time() * 1000)}_{len(store.get('ledger', [])) + 1}",
        "eventType": f"credits_{transaction_type}",
        "walletId": wallet.get("id"),
        "amount": tx["amount"],
        "balanceAfter": tx["balanceAfter"],
        "feature": tx["feature"],
        "sourceRef": tx["id"],
        "createdAt": tx["createdAt"],
    })
    return tx


def tx_fallback_idempotency_key(transaction_type, wallet, amount):
    return f"local-{transaction_type}-{wallet.get('id')}-{amount}-{int(time.time() * 1000)}"


def credits_balance_response(data=None):
    ensure_current_monthly_allowance()
    store = load_credits_store()
    return {
        "ok": True,
        "walletSummary": credit_wallet_summary(store),
        "wallets": store.get("wallets", []),
        "recentTransactions": list(store.get("transactions", []))[-20:],
        "backend": data_backend_status(),
    }


def credits_grant_response(data):
    store = load_credits_store()
    amount = normalize_credit_amount(data.get("amount") or data.get("credits"))
    if amount <= 0:
        return {"ok": False, "error": {"code": "invalid_credit_amount"}}
    wallet_type = data.get("walletType") or data.get("wallet_type") or ("included_monthly" if data.get("source") == "included_monthly" else "purchased")
    wallet_type = wallet_type if wallet_type in ("included_monthly", "purchased") else "purchased"
    source = data.get("source") or ("included_monthly" if wallet_type == "included_monthly" else "promo")
    idempotency_key = data.get("idempotencyKey") or data.get("idempotency_key")
    replay = credit_idempotency_response(store, idempotency_key)
    if replay:
        return replay
    period = data.get("period") if wallet_type == "included_monthly" else None
    if wallet_type == "included_monthly":
        period = period or time.strftime("%Y-%m")
        close_included_credit_wallets(store, except_period=period)
    wallet = find_credit_wallet(store, wallet_type, period=period)
    if wallet_type == "included_monthly":
        wallet["balance"] = amount
        wallet["expiresAt"] = data.get("expiresAt") or data.get("expires_at") or add_calendar_months(datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0), 1).isoformat().replace("+00:00", "Z")
        wallet["status"] = "active"
    else:
        wallet["balance"] = round(float(wallet.get("balance") or 0) + amount, 4)
    tx = append_credit_transaction(
        store,
        transaction_type="grant",
        wallet=wallet,
        amount=amount,
        source=source,
        reason=data.get("reason") or "credit_grant",
        idempotency_key=idempotency_key,
        provider=data.get("provider"),
        provider_transaction_id=data.get("providerTransactionId") or data.get("provider_transaction_id"),
    )
    store = save_credits_store(store)
    return {"ok": True, "transaction": tx, "walletSummary": credit_wallet_summary(store), "credits": store}


def credits_refund_response(data):
    """Idempotently claw back an Apple point-pack grant without going negative."""
    store = load_credits_store()
    provider_transaction_id = str(data.get("providerTransactionId") or data.get("provider_transaction_id") or "")
    idempotency_key = str(data.get("idempotencyKey") or data.get("idempotency_key") or f"apple-refund:{provider_transaction_id}")
    replay = credit_idempotency_response(store, idempotency_key)
    if replay:
        return replay
    original = next((
        tx for tx in store.get("transactions", [])
        if tx.get("providerTransactionId") == provider_transaction_id and tx.get("type") == "grant"
    ), None)
    requested = normalize_credit_amount(data.get("amount") or (original or {}).get("amount"))
    if not provider_transaction_id or not original:
        return {
            "ok": True,
            "matchedOriginalGrant": False,
            "refunded": 0,
            "refundDeficit": requested,
            "walletSummary": credit_wallet_summary(store),
            "credits": store,
        }
    if requested <= 0:
        return {
            "ok": True,
            "matchedOriginalGrant": False,
            "refunded": 0,
            "refundDeficit": 0,
            "walletSummary": credit_wallet_summary(store),
        }
    remaining = requested
    transactions = []
    wallets = [wallet for wallet in store.get("wallets", []) if wallet.get("type") == "purchased" and wallet.get("status") == "active"]
    if original:
        wallets.sort(key=lambda wallet: 0 if wallet.get("id") == original.get("walletId") else 1)
    for index, wallet in enumerate(wallets):
        available = max(0, float(wallet.get("balance") or 0))
        take = min(available, remaining)
        if take <= 0:
            continue
        wallet["balance"] = round(available - take, 4)
        remaining = round(remaining - take, 4)
        transactions.append(append_credit_transaction(
            store,
            transaction_type="refund",
            wallet=wallet,
            amount=-take,
            source="apple_storekit2",
            reason=data.get("reason") or "apple_purchase_refunded",
            idempotency_key=f"{idempotency_key}:{index}",
            provider="apple_storekit2",
            provider_transaction_id=provider_transaction_id,
        ))
        if remaining <= 0:
            break
    store = save_credits_store(store)
    return {
        "ok": True,
        "matchedOriginalGrant": bool(original),
        "refunded": round(requested - remaining, 4),
        "refundDeficit": round(remaining, 4),
        "transactions": transactions,
        "walletSummary": credit_wallet_summary(store),
        "credits": store,
    }


def credits_refund_reversal_response(data):
    """Restore only credits that this Apple transaction previously clawed back."""
    store = load_credits_store()
    provider_transaction_id = str(data.get("providerTransactionId") or data.get("provider_transaction_id") or "")
    idempotency_key = str(data.get("idempotencyKey") or data.get("idempotency_key") or f"apple-refund-reversed:{provider_transaction_id}")
    replay = credit_idempotency_response(store, idempotency_key)
    if replay:
        return replay
    prior_refunds = [
        tx for tx in store.get("transactions", [])
        if tx.get("providerTransactionId") == provider_transaction_id and tx.get("type") == "refund"
    ]
    refundable = round(sum(abs(float(tx.get("amount") or 0)) for tx in prior_refunds), 4)
    requested = normalize_credit_amount(data.get("amount") or refundable)
    restored = min(requested, refundable)
    if not provider_transaction_id or restored <= 0:
        return {
            "ok": True,
            "matchedPriorRefund": False,
            "restored": 0,
            "walletSummary": credit_wallet_summary(store),
            "credits": store,
        }
    wallet = find_credit_wallet(store, "purchased")
    wallet["balance"] = round(float(wallet.get("balance") or 0) + restored, 4)
    transaction = append_credit_transaction(
        store,
        transaction_type="refund_reversal",
        wallet=wallet,
        amount=restored,
        source="apple_storekit2",
        reason=data.get("reason") or "apple_refund_reversed",
        idempotency_key=idempotency_key,
        provider="apple_storekit2",
        provider_transaction_id=provider_transaction_id,
    )
    store = save_credits_store(store)
    return {
        "ok": True,
        "matchedPriorRefund": True,
        "restored": restored,
        "transaction": transaction,
        "walletSummary": credit_wallet_summary(store),
        "credits": store,
    }


def ensure_free_signup_trial(account_id):
    """Grant one account-bound Voice+Avatar trial: 5 credits = about 5 minutes.

    The account id is part of the idempotency key, so bootstrap retries, a new
    phone, or reinstalling the App cannot mint the trial a second time.
    """
    account_id = str(account_id or "").strip()
    if not account_id:
        return {"ok": False, "error": {"code": "account_id_required"}}
    backend = data_backend()
    if backend.enabled():
        result = backend.grant_free_signup_trial()
        return {
            "ok": bool(result.get("ok")),
            "credits": int(result.get("credits") or 5),
            "minutesApprox": 5,
            "idempotentReplay": bool(result.get("idempotentReplay")),
            "walletSummary": {"total": float(result.get("balance") or 0)},
        }
    result = credits_grant_response({
        "amount": 5,
        "walletType": "purchased",
        "source": "promo",
        "reason": "free_signup_voice_avatar_trial",
        "provider": "munea_signup",
        "idempotencyKey": f"free-signup-trial:{account_id}",
    })
    return {
        "ok": bool(result.get("ok")),
        "credits": 5,
        "minutesApprox": 5,
        "idempotentReplay": bool(result.get("idempotentReplay")),
        "walletSummary": result.get("walletSummary"),
    }


def credits_consume_response(data):
    ensure_current_monthly_allowance()
    store = load_credits_store()
    amount = normalize_credit_amount(data.get("amount") or data.get("credits"))
    if amount <= 0:
        return {"ok": False, "error": {"code": "invalid_credit_amount"}}
    idempotency_key = data.get("idempotencyKey") or data.get("idempotency_key")
    replay = credit_idempotency_response(store, idempotency_key)
    if replay:
        return replay
    summary = credit_wallet_summary(store)
    if summary["total"] < amount:
        return {
            "ok": False,
            "error": {"code": "insufficient_credits"},
            "walletSummary": summary,
            "shortfall": round(amount - summary["total"], 4),
            "fallbackMode": data.get("fallbackMode") or "2d-viseme",
        }
    remaining = amount
    consumed = []
    available_wallets = [w for w in store.get("wallets") or [] if credit_wallet_is_available(w)]
    available_wallets.sort(key=lambda w: (0 if w.get("type") == "included_monthly" else 1, w.get("expiresAt") or "9999", w.get("id") or ""))
    for wallet in available_wallets:
        available = float(wallet.get("balance") or 0)
        if available <= 0:
            continue
        take = min(available, remaining)
        wallet["balance"] = round(available - take, 4)
        remaining = round(remaining - take, 4)
        consumed.append((wallet, take))
        if remaining <= 0:
            break
    transactions = [
        append_credit_transaction(
            store,
            transaction_type="consume",
            wallet=wallet,
            amount=take,
            source=data.get("source") or "system",
            reason=data.get("reason") or "credit_consume",
            idempotency_key=(idempotency_key + f":{idx}") if idempotency_key else None,
            feature=data.get("feature"),
        )
        for idx, (wallet, take) in enumerate(consumed)
    ]
    store = save_credits_store(store)
    return {"ok": True, "transactions": transactions, "walletSummary": credit_wallet_summary(store), "credits": store}


def normalize_billing_store(data=None):
    base = default_billing_store()
    data = data or {}
    subscription = {**base["subscription"], **(data.get("subscription") or {})}
    entitlements = {**base["entitlements"], **(data.get("entitlements") or {})}
    usage = {**base["usageLedger"], **(data.get("usageLedger") or data.get("usage_ledger") or {})}
    return {
        "schemaVersion": int(data.get("schemaVersion") or data.get("schema_version") or 1),
        "accountId": str(data.get("accountId") or data.get("account_id") or base["accountId"]),
        "platform": str(data.get("platform") or base["platform"]),
        "provider": str(data.get("provider") or base["provider"]),
        "activePlan": str(data.get("activePlan") or data.get("active_plan") or base["activePlan"]),
        "subscription": subscription,
        "entitlements": entitlements,
        "usageLedger": usage,
        "serverVerificationRequired": bool(data.get("serverVerificationRequired", base["serverVerificationRequired"])),
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or utc_now(),
    }


def subscription_expiry_reason(store, now=None):
    """Return a terminal entitlement reason using the server clock."""
    store = normalize_billing_store(store)
    subscription = store.get("subscription") or {}
    status = str(subscription.get("status") or "inactive").lower()
    plan = str(store.get("activePlan") or "free").lower()
    if plan in ("", "free"):
        return None
    if status in {"expired", "revoked", "inactive"}:
        return status
    expires_at = subscription.get("expiresAt")
    if not expires_at:
        return None
    try:
        expires = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if expires <= (now or datetime.now(timezone.utc)):
            return "expired"
    except (TypeError, ValueError):
        return None
    return None


def expire_billing_store(store, reason):
    store = normalize_billing_store(store)
    free = default_billing_store()
    return normalize_billing_store({
        **store,
        "activePlan": "free",
        "subscription": {**(store.get("subscription") or {}), "status": "revoked" if reason == "revoked" else "expired", "willRenew": False},
        "entitlements": {**free["entitlements"], "familyDashboard": True},
        "serverVerificationRequired": False,
        "expiryReason": reason,
    })


def reconcile_billing_expiry(store):
    """Fail closed at expiry and revoke paid-only cross-family access."""
    reason = subscription_expiry_reason(store)
    if not reason:
        return store
    saved = save_billing_store(expire_billing_store(store, reason), reconcile=False)
    credits = load_credits_store()
    if close_included_credit_wallets(credits, reason=f"subscription_{reason}"):
        save_credits_store(credits)
    removed = 0
    try:
        removed = supabase_adapter.make_adapter().remove_external_family_memberships_for_account_unscoped(saved.get("accountId"))
    except Exception as e:
        log_fallback_exception("remove expired external family memberships", e)
    append_audit_event({"eventType": "subscription_expired_access_revoked", "targetTable": "subscription_ledger",
                        "details": {"reason": reason, "externalFamilyMembershipsRemoved": removed}})
    return saved


def load_billing_store():
    try:
        remote_store = data_backend().load_billing_store()
        if remote_store:
            return reconcile_billing_expiry(normalize_billing_store(remote_store))
    except Exception as e:
        log_fallback_exception("load billing store from Supabase", e)
    return reconcile_billing_expiry(normalize_billing_store(read_json_file(BILLING_STORE_PATH, {})))


def save_billing_store(data, reconcile=True):
    store = normalize_billing_store({**data, "updatedAt": utc_now()})
    try:
        remote_store = data_backend().save_billing_store(store)
        if remote_store:
            store = normalize_billing_store(remote_store)
    except Exception as e:
        log_fallback_exception("save billing store to Supabase", e)
    write_json_file(BILLING_STORE_PATH, store)
    return reconcile_billing_expiry(store) if reconcile else store


def entitlements_response(data):
    action = (data.get("action") or "load").lower()
    if action in ("save", "replace"):
        store = save_billing_store(data.get("store") or data.get("billingStore") or data)
    else:
        store = load_billing_store()
    return {
        "ok": True,
        "billing": store,
        "entitlements": store["entitlements"],
        "subscription": store["subscription"],
    }


def subscription_event_response(data):
    event = data.get("event") or {}
    if not isinstance(event, dict):
        return {"ok": False, "error": {"code": "invalid_subscription_event"}}
    store = load_billing_store()
    store["lastSubscriptionEvent"] = {
        "receivedAt": utc_now(),
        "provider": data.get("provider") or "apple-app-store-server-notifications-v2",
        "eventType": event.get("type") or event.get("notificationType") or "unknown",
        "requiresJwsVerification": True,
    }
    save_billing_store(store)
    return {
        "ok": True,
        "accepted": True,
        "serverVerificationRequired": True,
        "note": "Legacy provider event accepted. Apple production events use /apple/notifications with JWS verification.",
    }


APPLE_ACTIVE_NOTIFICATION_TYPES = {
    "SUBSCRIBED", "DID_RENEW", "OFFER_REDEEMED", "RENEWAL_EXTENDED", "REFUND_REVERSED",
}
APPLE_TERMINAL_NOTIFICATION_TYPES = {"EXPIRED", "GRACE_PERIOD_EXPIRED", "REFUND", "REVOKE"}


def _apple_notification_identity(app_account_token):
    base = supabase_adapter.make_adapter()
    if not base.configured():
        return None
    return base.resolve_auth_identity(app_account_token)


def _activate_apple_subscription(verified):
    billing = load_billing_store()
    billing.update({
        "platform": "ios",
        "provider": "apple_storekit2",
        "activePlan": verified.plan,
        "serverVerificationRequired": False,
        "rawEventRef": verified.notificationUUID,
    })
    billing["subscription"] = {
        **(billing.get("subscription") or {}),
        "status": "active",
        "productId": verified.productId,
        "originalTransactionId": verified.originalTransactionId,
        "expiresAt": verified.expiresDate,
        "purchaseDate": verified.purchaseDate,
        "originalPurchaseDate": verified.originalPurchaseDate,
        "willRenew": bool(verified.willRenew) if verified.willRenew is not None else True,
        "lastVerifiedAt": utc_now(),
    }
    billing["entitlements"] = {
        **(billing.get("entitlements") or {}),
        "voiceCompanion": True,
        "familyDashboard": True,
        "routineReminders": True,
        "realtimeAvatar": True,
        "familyMembersMax": 4 if verified.plan == "plus" else 12,
        "familyCircleInvite": True,
        "familyCircleJoin": True,
        "monthlyCredits": verified.points,
        "monthlyCreditAnchorAt": verified.originalPurchaseDate or verified.purchaseDate,
    }
    billing = save_billing_store(billing)
    allowance = monthly_allowance_details(billing)
    grant = None
    if allowance:
        grant = credits_grant_response({
            "amount": allowance["amount"],
            "walletType": "included_monthly",
            "period": allowance["period"],
            "expiresAt": allowance["expiresAt"],
            "source": "included_monthly",
            "reason": "app_store_server_notification_allowance",
            "provider": "apple_storekit2",
            "providerTransactionId": verified.transactionId or verified.originalTransactionId,
            "idempotencyKey": f"apple-subscription:{verified.transactionId or verified.originalTransactionId}:{allowance['period']}",
        })
    return billing, grant


def apply_verified_apple_notification(verified):
    if verified.notificationType == "TEST":
        return {"ok": True, "accepted": True, "test": True, "notificationUUID": verified.notificationUUID}
    if not verified.appAccountToken:
        return {"ok": False, "retryable": True, "error": {"code": "apple_notification_account_token_missing"}}
    try:
        identity = _apple_notification_identity(verified.appAccountToken)
    except Exception as exc:
        log_fallback_exception("resolve Apple notification account", exc)
        return {"ok": False, "retryable": True, "error": {"code": "apple_notification_account_resolution_failed"}}
    if not identity:
        return {"ok": False, "retryable": True, "error": {"code": "apple_notification_account_unresolved"}}

    token = REQUEST_DATA_IDENTITY.set(identity)
    try:
        billing = None
        credit_result = None
        event_type = verified.notificationType
        if verified.kind == "points":
            if event_type in {"REFUND", "REVOKE"}:
                credit_result = credits_refund_response({
                    "amount": verified.points,
                    "providerTransactionId": verified.transactionId,
                    "idempotencyKey": f"apple-refund:{verified.notificationUUID or verified.transactionId}",
                })
            elif event_type == "REFUND_REVERSED":
                credit_result = credits_refund_reversal_response({
                    "amount": verified.points,
                    "providerTransactionId": verified.transactionId,
                    "idempotencyKey": f"apple-refund-reversed:{verified.notificationUUID or verified.transactionId}",
                })
        elif verified.kind == "subscription":
            if event_type in APPLE_ACTIVE_NOTIFICATION_TYPES:
                billing, credit_result = _activate_apple_subscription(verified)
            elif event_type == "DID_CHANGE_RENEWAL_STATUS":
                billing = load_billing_store()
                billing["rawEventRef"] = verified.notificationUUID
                billing["subscription"] = {
                    **(billing.get("subscription") or {}),
                    "willRenew": bool(verified.willRenew),
                    "lastVerifiedAt": utc_now(),
                }
                billing = save_billing_store(billing)
            elif event_type == "DID_FAIL_TO_RENEW" and verified.gracePeriodExpiresDate:
                billing = load_billing_store()
                billing["rawEventRef"] = verified.notificationUUID
                billing["subscription"] = {
                    **(billing.get("subscription") or {}),
                    "status": "grace_period",
                    "expiresAt": verified.gracePeriodExpiresDate,
                    "willRenew": True,
                    "lastVerifiedAt": utc_now(),
                }
                billing = save_billing_store(billing)
            elif event_type == "DID_FAIL_TO_RENEW" and verified.expiresDate and (
                parse_optional_iso_datetime(verified.expiresDate) or datetime.min.replace(tzinfo=timezone.utc)
            ) > datetime.now(timezone.utc):
                billing = load_billing_store()
                billing["rawEventRef"] = verified.notificationUUID
                billing["subscription"] = {
                    **(billing.get("subscription") or {}),
                    "status": "active",
                    "expiresAt": verified.expiresDate,
                    "willRenew": False,
                    "lastVerifiedAt": utc_now(),
                }
                billing = save_billing_store(billing)
            elif event_type in APPLE_TERMINAL_NOTIFICATION_TYPES or event_type == "DID_FAIL_TO_RENEW":
                reason = "revoked" if event_type in {"REFUND", "REVOKE"} else "expired"
                billing = load_billing_store()
                billing["rawEventRef"] = verified.notificationUUID
                billing = save_billing_store(expire_billing_store(billing, reason), reconcile=False)
                credits = load_credits_store()
                if close_included_credit_wallets(credits, reason=f"apple_{event_type.lower()}"):
                    save_credits_store(credits)
                try:
                    supabase_adapter.make_adapter().remove_external_family_memberships_for_account_unscoped(billing.get("accountId"))
                except Exception as exc:
                    log_fallback_exception("remove Apple-expired external family memberships", exc)

        append_audit_event({
            "eventType": "apple_server_notification_applied",
            "targetTable": "subscription_ledger" if verified.kind == "subscription" else "credit_transactions",
            "details": {
                "actorType": "apple_app_store_server",
                "notificationUUID": verified.notificationUUID,
                "notificationType": verified.notificationType,
                "subtype": verified.subtype,
                "transactionId": verified.transactionId,
                "productId": verified.productId,
                "environment": verified.environment,
            },
        })
        return {
            "ok": True,
            "accepted": True,
            "notificationUUID": verified.notificationUUID,
            "notificationType": verified.notificationType,
            "billing": billing,
            "walletSummary": (credit_result or {}).get("walletSummary"),
            "idempotentReplay": bool((credit_result or {}).get("idempotentReplay")),
        }
    finally:
        REQUEST_DATA_IDENTITY.reset(token)


def apple_notification_response(data):
    try:
        verified = apple_store.verify_notification(data.get("signedPayload") or data.get("signed_payload"))
    except apple_store.AppleStoreVerificationError as exc:
        append_audit_event({
            "eventType": "apple_server_notification_rejected",
            "targetTable": "subscription_ledger",
            "details": {"reason": str(exc), "actorType": "apple_app_store_server"},
        })
        return {"ok": False, "retryable": False, "error": {"code": str(exc)}}
    return apply_verified_apple_notification(verified)


def apple_transaction_response(data, auth_gate=None):
    auth_user_id = ((auth_gate or {}).get("auth") or {}).get("authUserId")
    try:
        verified = apple_store.verify_transaction(
            data.get("signedTransaction") or data.get("signed_transaction"),
            auth_user_id,
        )
    except apple_store.AppleStoreVerificationError as exc:
        append_audit_event({
            "eventType": "apple_transaction_rejected",
            "targetTable": "credit_transactions",
            "details": {"reason": str(exc), "actorType": "authenticated_user"},
        })
        return {"ok": False, "verified": False, "error": {"code": str(exc)}}

    claimed_transaction_id = str(data.get("transactionId") or data.get("transaction_id") or "")
    if claimed_transaction_id and claimed_transaction_id != verified.transactionId:
        return {"ok": False, "verified": False, "error": {"code": "apple_transaction_id_mismatch"}}

    grant = None
    billing = None
    if verified.kind == "points":
        grant = credits_grant_response({
            "amount": verified.points,
            "walletType": "purchased",
            "source": "apple_iap",
            "reason": "verified_storekit_purchase",
            "provider": "apple_storekit2",
            "providerTransactionId": verified.transactionId,
            "idempotencyKey": f"apple:{verified.transactionId}",
        })
    elif verified.kind == "subscription":
        billing = load_billing_store()
        billing.update({
            "platform": "ios",
            "provider": "apple_storekit2",
            "activePlan": verified.plan,
            "serverVerificationRequired": False,
        })
        billing["subscription"] = {
            **(billing.get("subscription") or {}),
            "status": "active",
            "productId": verified.productId,
            "originalTransactionId": verified.originalTransactionId,
            "expiresAt": verified.expiresDate,
            "lastVerifiedAt": utc_now(),
        }
        billing["entitlements"] = {
            **(billing.get("entitlements") or {}),
            "voiceCompanion": True,
            "familyDashboard": True,
            "routineReminders": True,
            "realtimeAvatar": True,
            "familyMembersMax": 4 if verified.plan == "plus" else 12,
            "familyCircleInvite": True,
            "familyCircleJoin": True,
            "monthlyCredits": verified.points,
            "monthlyCreditAnchorAt": verified.originalPurchaseDate or verified.purchaseDate,
        }
        billing = save_billing_store(billing)
        allowance = monthly_allowance_details(billing)
        grant = credits_grant_response({
            "amount": verified.points,
            "walletType": "included_monthly",
            "period": (allowance or {}).get("period"),
            "expiresAt": (allowance or {}).get("expiresAt") or verified.expiresDate,
            "source": "included_monthly",
            "reason": "verified_storekit_subscription_allowance",
            "provider": "apple_storekit2",
            "providerTransactionId": verified.transactionId,
            "idempotencyKey": f"apple-subscription:{verified.transactionId}",
        })

    append_audit_event({
        "eventType": "apple_transaction_verified",
        "targetTable": "credit_transactions" if verified.kind == "points" else "subscription_ledger",
        "details": {
            "actorType": "authenticated_user",
            "transactionId": verified.transactionId,
            "productId": verified.productId,
            "environment": verified.environment,
            "idempotentReplay": bool((grant or {}).get("idempotentReplay")),
        },
    })
    return {
        "ok": bool((grant or {}).get("ok")),
        "verified": True,
        "productId": verified.productId,
        "transactionId": verified.transactionId,
        "originalTransactionId": verified.originalTransactionId,
        "environment": verified.environment,
        "idempotentReplay": bool((grant or {}).get("idempotentReplay")),
        "walletSummary": (grant or {}).get("walletSummary"),
        "billing": billing,
    }


def normalize_avatar_mode(mode):
    mode = str(mode or "2d-viseme").strip().lower()
    mode = AVATAR_MODE_ALIASES.get(mode, mode)
    return mode if mode in AVATAR_ENGINE_MODES else "2d-viseme"


def avatar_minutes_from_duration(duration_ms):
    try:
        duration_ms = int(duration_ms or 0)
    except Exception:
        duration_ms = 0
    duration_ms = max(0, min(duration_ms, 3_600_000))
    return round(duration_ms / 60000, 2)


def avatar_session_response(data):
    action = (data.get("action") or "start").lower()
    requested_mode = normalize_avatar_mode(data.get("mode") or data.get("requestedMode") or data.get("engineMode"))
    duration_minutes = avatar_minutes_from_duration(data.get("durationMs") or data.get("estimatedDurationMs"))
    billing = load_billing_store()
    entitlements = billing["entitlements"]
    usage = billing["usageLedger"]
    premium_grant = float(entitlements.get("premiumAvatarMinutesMonthly") or 0)
    premium_used = float(usage.get("avatarMinutesUsed") or 0)
    premium_allowed = bool(entitlements.get("realtimeAvatar"))
    included_remaining = max(0, round(premium_grant - premium_used, 4))
    credits_required = 0
    credits_consumed = None
    selected_mode = requested_mode
    fallback_reason = None

    if requested_mode in PREMIUM_AVATAR_MODES:
        if not premium_allowed:
            selected_mode = "2d-viseme"
            fallback_reason = "premium_avatar_not_entitled"
        elif duration_minutes > 0:
            credits_required = max(0, round(duration_minutes - included_remaining, 4))
            if credits_required > 0:
                credit_summary = credit_wallet_summary(load_credits_store())
                if credit_summary["total"] < credits_required:
                    selected_mode = "2d-viseme"
                    fallback_reason = "premium_avatar_minutes_and_credits_exhausted"

    usage_committed = False
    if action in ("complete", "record-usage", "record_usage") and selected_mode in PREMIUM_AVATAR_MODES and duration_minutes > 0:
        if credits_required > 0:
            credits_consumed = credits_consume_response({
                "amount": credits_required,
                "feature": "premium_avatar",
                "reason": "premium_avatar_overage",
                "fallbackMode": "2d-viseme",
                "idempotencyKey": data.get("creditIdempotencyKey") or data.get("idempotencyKey") or data.get("sessionId"),
            })
            if not credits_consumed.get("ok"):
                selected_mode = "2d-viseme"
                fallback_reason = "premium_avatar_credit_consume_failed"
        if selected_mode not in PREMIUM_AVATAR_MODES:
            duration_minutes = 0
        else:
            usage["avatarMinutesUsed"] = round(premium_used + duration_minutes, 2)
            billing["usageLedger"] = usage
            billing = save_billing_store(billing)
            usage = billing["usageLedger"]
            usage_committed = True

    provider = "local-browser"
    if selected_mode == "ditto":
        provider = "runpod-ditto-reserved"
    elif selected_mode == "liveavatar":
        provider = "runpod-liveavatar-reserved"

    return {
        "ok": True,
        "session": {
            "id": "avatar_" + str(int(time.time() * 1000)),
            "action": action,
            "requestedMode": requested_mode,
            "selectedMode": selected_mode,
            "provider": provider,
            "fallbackReason": fallback_reason,
            "estimatedMinutes": duration_minutes,
            "usageCommitted": usage_committed,
            "includedMinutesRemainingBeforeSession": included_remaining,
            "creditsRequired": credits_required if selected_mode in PREMIUM_AVATAR_MODES else 0,
            "creditsConsumed": credits_consumed,
            "startedAt": utc_now(),
        },
        "entitlements": entitlements,
        "usageLedger": usage,
        "backend": data_backend_status(),
    }


def default_privacy_requests_store():
    return {
        "schemaVersion": 1,
        "accountId": "local-demo-account",
        "requests": [],
        "retentionPolicy": {
            "conversationRawTranscriptDefault": "not_retained_as_primary_record",
            "conversationSummary": "retained_until_user_deletion_or_policy_expiry",
            "safetyEvents": "retained_for_safety_audit_until_deletion_or_legal_hold",
            "billingRecords": "retained_as_required_for_tax_refund_and_platform_audit",
        },
        "updatedAt": "2026-06-29T00:00:00Z",
    }


def normalize_privacy_request(data=None):
    data = data or {}
    req_type = data.get("type") or data.get("requestType") or data.get("request_type") or "export"
    if req_type not in ("export", "account_deletion"):
        req_type = "export"
    return {
        "id": str(data.get("id") or f"{req_type}_{int(time.time() * 1000)}"),
        "type": req_type,
        "status": str(data.get("status") or "requested"),
        "accountId": str(data.get("accountId") or data.get("account_id") or "local-demo-account"),
        "requestedAt": data.get("requestedAt") or data.get("requested_at") or utc_now(),
        "completedAt": data.get("completedAt") or data.get("completed_at"),
        "reason": str(data.get("reason") or "")[:120],
        "requiresReauth": bool(data.get("requiresReauth", True)),
        "subscriptionNoticeRequired": bool(data.get("subscriptionNoticeRequired", req_type == "account_deletion")),
    }


def normalize_privacy_requests_store(data=None):
    base = default_privacy_requests_store()
    data = data or {}
    requests = [normalize_privacy_request(r) for r in data.get("requests", [])]
    retention = {**base["retentionPolicy"], **(data.get("retentionPolicy") or data.get("retention_policy") or {})}
    return {
        "schemaVersion": int(data.get("schemaVersion") or data.get("schema_version") or 1),
        "accountId": str(data.get("accountId") or data.get("account_id") or base["accountId"]),
        "requests": requests,
        "retentionPolicy": retention,
        "updatedAt": data.get("updatedAt") or data.get("updated_at") or utc_now(),
    }


def load_privacy_requests_store():
    try:
        remote_store = data_backend().load_privacy_requests_store()
        if remote_store:
            return normalize_privacy_requests_store(remote_store)
    except Exception as e:
        log_fallback_exception("load privacy requests from Supabase", e)
    return normalize_privacy_requests_store(read_json_file(PRIVACY_REQUESTS_PATH, {}))


def save_privacy_requests_store(data):
    store = normalize_privacy_requests_store({**data, "updatedAt": utc_now()})
    write_json_file(PRIVACY_REQUESTS_PATH, store)
    return store


def append_privacy_request(req_type, data=None):
    data = data or {}
    try:
        remote_request = data_backend().append_privacy_request(req_type, data)
        if remote_request:
            return normalize_privacy_request(remote_request)
    except Exception as e:
        log_fallback_exception("append privacy request to Supabase", e)
    store = load_privacy_requests_store()
    req = normalize_privacy_request({**data, "type": req_type, "requestedAt": utc_now()})
    store["requests"].append(req)
    save_privacy_requests_store(store)
    return req


def privacy_export_response(data):
    action = (data.get("action") or "preview").lower()
    if action not in ("request", "create", "download"):
        return {
            "ok": True,
            "status": "available",
            "requiresReauth": False,
            "message": "登入後可立即建立只屬於你的 JSON 資料副本。",
        }
    backend = data_backend()
    if not backend.enabled() or not backend.request_scoped:
        return {
            "ok": False,
            "status": "unavailable",
            "error": {"code": "privacy_export_account_scope_required"},
            "requiresReauth": True,
        }
    try:
        package = backend.export_scoped_personal_data()
    except PermissionError as exc:
        return {"ok": False, "status": "rejected", "error": {"code": str(exc)}, "requiresReauth": True}
    generated_at = utc_now()
    package = {
        "exportedAt": generated_at,
        "format": "Munea Personal Data Export v1",
        **package,
    }
    export_request = append_privacy_request("export", {
        **data,
        "status": "completed",
        "completedAt": generated_at,
        "requiresReauth": False,
        "metadata": {
            "format": "json",
            "scope": package.get("scope"),
            "schemaVersion": package.get("schemaVersion"),
        },
    })
    filename_date = generated_at[:10].replace("-", "")
    return {
        "ok": True,
        "request": export_request,
        "status": "completed",
        "requiresReauth": False,
        "filename": f"munea-personal-data-{filename_date}.json",
        "mediaType": "application/json",
        "exportPackage": package,
        "message": "你的資料副本已建立完成。",
    }


def account_deletion_response(data, auth_gate=None):
    action = (data.get("action") or "status").lower()
    store = load_privacy_requests_store()
    deletion_requests = [r for r in store["requests"] if r["type"] == "account_deletion"]
    if action in ("request", "create"):
        backend = data_backend()
        auth_user_id = ((auth_gate or {}).get("auth") or {}).get("authUserId")
        if backend.enabled():
            try:
                result = backend.delete_scoped_account(auth_user_id)
            except PermissionError as exc:
                return {
                    "ok": False,
                    "status": "rejected",
                    "error": {"code": str(exc), "requestId": request_id()},
                    "requiresReauth": True,
                }
            if result.get("cleanupRequired"):
                notify.alert("privacy", "account-deletion", "Personal data deleted; Supabase Auth cleanup required")
            return {
                "ok": True,
                "status": "completed" if not result.get("cleanupRequired") else "data_deleted_auth_cleanup_required",
                "accountDeleted": bool(result.get("accountDeleted")),
                "authUserDeleted": bool(result.get("authUserDeleted")),
                "cleanupRequired": bool(result.get("cleanupRequired")),
                "receipt": result.get("receiptHash"),
                "requiresReauth": False,
                "subscriptionNoticeRequired": True,
            }
        deletion = append_privacy_request("account_deletion", data)
        deletion_requests.append(deletion)
    latest = deletion_requests[-1] if deletion_requests else None
    return {
        "ok": True,
        "latestRequest": latest,
        "status": latest["status"] if latest else "not_requested",
        "requiresReauth": True,
        "subscriptionNoticeRequired": True,
        "productionSteps": [
            "reauthenticate account owner",
            "show active subscription cancellation guidance",
            "queue account deletion",
            "soft-delete user-scoped data",
            "retain billing/audit records only as legally required",
            "confirm completion to user",
        ],
    }


def _sys_for(char):
    """組這個角色的系統人格：人格 + 醫療界線 +（真人才帶）記憶側寫。"""
    c = eng.CHARS.get(char, eng.CHARS[DEFAULT_CHAR])
    base = eng.CORE + c["persona"] + eng.RED  # 記憶單一來源＝memory_items（由 reply_context_instruction 注入），不再疊舊 user_profile 側寫
    return base, c


def reply_conv(history, char=DEFAULT_CHAR, data=None, context=None):
    """帶完整對話脈絡，用該角色的腦＋記憶回話。"""
    base, _ = _sys_for(char)
    context = context or build_reply_context(history, char, data)
    base = base + reply_context_instruction(context) + localization.reply_language_instruction(context.get("locale"))
    # 欄位相容：text 或 content 皆可（跟 conversation_text 一致），缺角色預設 user；空句略過。
    contents = []
    for h in (history or []):
        if not isinstance(h, dict):
            continue
        txt = (h.get("text") or h.get("content") or "").strip()
        if not txt:
            continue
        contents.append(types.Content(role=(h.get("role") or "user"), parts=[types.Part(text=txt)]))
    # 空對話：不白燒 12 次 Gemini 呼叫，直接回開場引導
    if not contents:
        return localization.opening_message(context.get("locale"))
    for _ in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = eng.client.models.generate_content(
                    model=m, contents=contents,
                    config=types.GenerateContentConfig(system_instruction=base, temperature=0.85))
                return r.text.strip()
            except Exception as e:
                log_fallback_exception(f"generate chat reply with {m}", e)
        time.sleep(2)
    return localization.retry_message(context.get("locale"))


def chat_response(data, char=DEFAULT_CHAR):
    history = data.get("history", [])
    context = build_reply_context(history, char, data)
    t = localization.assistant_output_text(
        reply_conv(history, char, data, context),
        context.get("locale"),
    )
    return {
        "reply": t,
        "audio": tts_b64(t, char, data.get("locale")),
        "aiContext": ai_context_summary(context),
    }


def relationship_state_from_turn(data, context, stored_memories):
    data = data or {}
    context = context or {}
    persona = context.get("persona") or {}
    history = data.get("history") or []
    text = conversation_text(history)
    previous = persona.get("relationshipState") or {}
    previous_memory = previous.get("relationshipMemory") or {}
    topic_domains = [
        item.get("domain")
        for item in (context.get("perception") or {}).get("domains", [])
        if item.get("domain")
    ]
    user_turns = [
        str(h.get("text") or h.get("content") or "").strip()
        for h in history
        if h.get("role") == "user" and str(h.get("text") or h.get("content") or "").strip()
    ]
    turn_count = len(user_turns)
    meaningful_turn_count = len([turn for turn in user_turns if len(turn) >= 4])
    sensitive_count = len([m for m in stored_memories if m.get("sensitivity") in {"sensitive", "restricted"}])
    has_emotional_memory = any(m.get("type") == "emotion" for m in stored_memories)

    effective_interactions = int(previous_memory.get("effectiveInteractionCount") or 0)
    if meaningful_turn_count:
        effective_interactions += 1
    cumulative_turns = int(previous_memory.get("meaningfulTurnCount") or 0) + meaningful_turn_count
    cumulative_memories = int(previous_memory.get("storedMemoryCount") or 0) + len(stored_memories)
    shared_depth = int(previous_memory.get("sharedDepthScore") or 0)
    if has_emotional_memory or sensitive_count:
        shared_depth += 1
    if any(len(turn) >= 80 for turn in user_turns):
        shared_depth += 1

    candidate_rapport = "new"
    if effective_interactions >= 3 or cumulative_turns >= 8 or cumulative_memories >= 3:
        candidate_rapport = "familiar"
    if effective_interactions >= 8 and (shared_depth >= 2 or cumulative_memories >= 8):
        candidate_rapport = "trusted"
    if effective_interactions >= 20 and shared_depth >= 5 and cumulative_memories >= 15:
        candidate_rapport = "close"
    rapport_order = {"new": 0, "familiar": 1, "trusted": 2, "close": 3}
    previous_rapport = previous.get("rapportLevel") or "new"
    rapport = max((previous_rapport, candidate_rapport), key=lambda item: rapport_order.get(item, 0))
    previous_boundaries = previous.get("userBoundaries") or {}
    previous_tone = previous.get("toneOverrides") or {}

    return normalize_relationship_state({
        "accountId": previous.get("accountId"),
        "personId": data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "personaTemplateId": persona.get("templateId") or "nening-real-female",
        "companionProfileId": previous.get("companionProfileId"),
        "preferredAddress": data.get("preferredAddress") or data.get("preferred_address") or previous.get("preferredAddress"),
        "rapportLevel": rapport,
        "toneOverrides": {
            **previous_tone,
            "reduceHumor": sensitive_count > 0 or has_emotional_memory,
            "preferShortResponses": len(text) > 1200,
            "speechFirst": True,
        },
        "userBoundaries": {
            **previous_boundaries,
            "noRawTranscriptRetention": True,
            "medicalAdviceBoundary": True,
        },
        "relationshipMemory": {
            **previous_memory,
            "lastTopicDomains": topic_domains[:5],
            "lastMeaningfulTurnCount": turn_count,
            "meaningfulTurnCount": cumulative_turns,
            "effectiveInteractionCount": effective_interactions,
            "sharedDepthScore": shared_depth,
            "storedMemoryCount": cumulative_memories,
            "lastSafetyLevel": ((context.get("guardian") or {}).get("risk") or {}).get("level", "none"),
            "updatedFrom": "butler_post_turn",
        },
    })


def _post_turn_extract(history, person_id, store=True, source_summary_id=None):
    """聊完萃取記憶：真萃取（memory_engine，只存長輩事實）優先，失敗退回關鍵字版。
    回傳 dict 相容原本 butler 用法。保留四層 tier。"""
    candidates, extractor = [], "keyword_fallback"
    try:
        import memory_engine
        candidates = memory_engine.extract(history)
        if candidates:
            extractor = "memory_engine"
    except Exception:
        candidates = []
    if not candidates:
        candidates = (model_router.memory_extract_response({"history": history}) or {}).get("candidates") or []
    stored_items = []
    superseded = 0
    if store and candidates:
        # 寫入即對帳：新事實跟既有記憶比對 → 新增 / 已知不動 / 取代過時的（不再無腦堆）
        existing = load_memory_items(limit=1000)
        try:
            plan = memory_engine.reconcile(candidates, existing)
        except Exception:
            plan = {"add": list(candidates), "supersede": [], "noop": []}

        def _norm(cand):
            item = model_router.normalize_memory_item(cand, person_id)
            if cand.get("tier"):
                item["tier"] = cand["tier"]
            if source_summary_id:
                item["sourceConversationSummaryId"] = source_summary_id
            return item

        to_store, superseded_ids = [], []
        for cand in plan.get("add", []):
            to_store.append(_norm(cand))
        for pair in plan.get("supersede", []):
            item = _norm(pair["new"])
            item["supersedesMemoryId"] = pair["oldId"]  # 新的指向它取代的舊記憶
            to_store.append(item)
            superseded_ids.append(pair["oldId"])
        if to_store:
            stored_items = append_memory_items(to_store)
        if superseded_ids:
            _invalidate_memory_items(superseded_ids)  # 舊的下架、不再被召回（保住『不抱過時的你』）
            superseded = len(superseded_ids)
    return {
        "candidates": candidates,
        "memoryItems": stored_items,
        "stored": len(stored_items),
        "superseded": superseded,
        "extractor": extractor,
        "storagePolicy": {
            "storeRawTranscriptByDefault": False,
            "requiresConsentForSensitive": True,
            "supportsUpdateAndSupersede": True,
        },
    }


def consolidate_memory(person_id=None):
    """整理員：載入全部記憶 → 合併重複／剪低價值 → 存回（Supabase 用軟刪除、本機 JSON 重寫）。
    設計為由背景／管理端『定期』呼叫（頻率旋鈕待 Edward 拍板：每天/每週）。"""
    items = load_memory_items(limit=1000)
    if not items:
        return {"ok": True, "brain": "butler", "action": "consolidate",
                "report": {"before": 0, "after": 0, "prunedLowValue": 0, "mergedDuplicates": 0},
                "removed": 0, "persisted": "none"}
    try:
        import memory_engine
        kept, report = memory_engine.consolidate(items)
    except Exception as e:
        log_fallback_exception("consolidate memory", e)
        return {"ok": False, "brain": "butler", "action": "consolidate", "error": "consolidate_failed"}
    kept_ids = {it.get("id") for it in kept if it.get("id")}
    removed_ids = [it.get("id") for it in items if it.get("id") and it.get("id") not in kept_ids]
    persisted = "none"
    backend = data_backend()
    if backend.enabled():
        if removed_ids:
            try:
                backend.soft_delete_memory_items(removed_ids, utc_now())
                persisted = "supabase_soft_delete"
            except Exception as e:
                log_fallback_exception("soft delete consolidated memory", e)
                persisted = "error"
    else:
        save_memory_items(kept)
        persisted = "json_rewrite"
    return {"ok": True, "brain": "butler", "action": "consolidate",
            "report": report, "removed": len(removed_ids), "persisted": persisted}


def butler_post_turn_response(data):
    data = data or {}
    history = data.get("history") or []
    char = data.get("char") or DEFAULT_CHAR
    context = build_reply_context(history, char, data)
    person_id = data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID
    conversation_summary = None
    if data.get("storeSummary") is not False:
        summary_record = build_post_turn_conversation_summary(data, context)
        if summary_record:
            conversation_summary = append_conversation_summary(summary_record)
            if conversation_summary:
                append_product_event({
                    "eventName": "companion_summary_created",
                    "personId": conversation_summary.get("personId"),
                    "properties": {
                        "memoryTags": conversation_summary.get("memoryTags") or [],
                        "safetyRelevant": conversation_summary.get("safetyRelevant") is True,
                        "rawTranscriptStored": False,
                        "source": "butler_post_turn",
                        "analyticsExcluded": bool(data.get("analyticsExcluded")),
                    },
                })
    extract = _post_turn_extract(
        history,
        person_id,
        store=(data.get("storeMemory") is not False),
        source_summary_id=(conversation_summary or {}).get("id"),
    )
    stored_memories = extract.get("memoryItems") or []
    mood = None
    if data.get("analyzeMood") is not False:
        try:
            import perception_engine
            mood = perception_engine.analyze_conversation_mood(history)
        except Exception as e:
            log_fallback_exception("analyze conversation mood", e)
        if mood:
            append_wellbeing_signal({
                "id": "wb_" + uuid.uuid4().hex[:10],
                "personId": person_id,
                "date": perception_engine.now_context()["date"],
                "modality": "text",            # V2 之後：voice(語調) / face / motion 吐同一格式
                "signalType": "mood",
                **mood,
                "isMedicalInference": False,   # 硬閘：觀察、絕非診斷
                "createdAt": utc_now(),
            })
    relationship_state = relationship_state_from_turn(data, context, stored_memories)
    saved_state = upsert_relationship_state(relationship_state)
    append_product_event({
        "eventName": "butler_post_turn_completed",
        "properties": {
            "storedMemoryCount": len(stored_memories),
            "rapportLevel": saved_state.get("rapportLevel"),
            "analyticsExcluded": bool(data.get("analyticsExcluded")),
        },
    })
    return {
        "ok": True,
        "brain": "butler",
        "action": "post_turn_review",
        "aiContext": ai_context_summary(context),
        "memory": {
            "stored": extract.get("stored", 0),
            "candidateCount": len(extract.get("candidates") or []),
            "extractor": extract.get("extractor"),
            "storagePolicy": extract.get("storagePolicy"),
            "sourceConversationSummaryId": (conversation_summary or {}).get("id"),
        },
        "conversationSummary": {
            "created": bool(conversation_summary),
            "summary": conversation_summary,
            "privacy": (conversation_summary or {}).get("privacy") or {"storesRawTranscriptByDefault": False},
        },
        "wellbeing": mood,
        "relationshipState": saved_state,
        "privacy": {
            "storesRawTranscriptByDefault": False,
            "storesStructuredMemory": True,
            "relationshipStateIsUserScoped": True,
        },
        "backend": data_backend_status(),
    }


# 語音通話「上一通接得上」視窗：超過就當成新的一天/新的話頭，不再提上一通。
VOICE_CALL_RECAP_WINDOW_HOURS = 12


def _voice_call_memory_enabled():
    """通話記憶回寫＋開場接續的總開關，預設關（跟多鑰匙/N 槽同一守則：預設不影響現役）。
    為什麼不能預設開：現行 Voice 的 Cloud Run 部署沒有 Supabase 環境變數，
    data_backend 會落到「容器本機 JSON」——所有來電者共用一份、容器回收即蒸發、
    跟 brain 正式記憶庫不相通。單人測試（Edward 現階段）可以開；
    多用戶正式開放前必須先把儲存接到 brain/Supabase 並用 call token 身分隔離。"""
    return os.environ.get("MUNEA_VOICE_CALL_MEMORY", "").strip().lower() in ("1", "true", "yes", "on")


def persist_voice_call_turns(turns, char=None, voice_session_id=None, person_id=None):
    """語音通話收線後，把整通的字幕逐字稿交給既有的聊後管線
    （對話摘要＋記憶萃取對帳＋心情訊號），跟文字聊天走同一套腦。
    turns: [{"role": "user"|"assistant", "content": str}, ...]
    person_id：有 call token 就帶 "voice-<user_id>" 做人別隔離；沒有（開發包直連）
    落回主要照護對象。對方整通沒說話（或 ASR 全空）就不存，避免累積空摘要；
    收線路徑不能炸，所有失敗都吞下並記 fallback log。"""
    if not _voice_call_memory_enabled():
        return None
    return _persist_voice_call_turns_core(turns, char, voice_session_id, person_id)


def _persist_voice_call_turns_core(turns, char=None, voice_session_id=None, person_id=None):
    """persist 的核心（不含總開關）：給 Voice→Brain 內部端點用——
    內部密語（MUNEA_VOICE_BRAIN_SECRET）設了就代表刻意啟用，不再疊第二道旗標。"""
    history = []
    for turn in turns or []:
        if not isinstance(turn, dict):
            continue
        content = str(turn.get("content") or turn.get("text") or "").strip()
        if not content:
            continue
        role = "assistant" if turn.get("role") == "assistant" else "user"
        # text 與 content 都給：真萃取（memory_engine）與心情分析讀 text、
        # 摘要（conversation_text）兩者皆可，缺一邊就會有管線看到空對話。
        history.append({"role": role, "text": content[:600], "content": content[:600]})
    if not any(item["role"] == "user" for item in history):
        return None
    try:
        return butler_post_turn_response({
            "history": history[-120:],
            "char": char or DEFAULT_CHAR,
            # 與 recent_call_recap_line 讀取同一 scope：Gateway 正式路徑的 call token
            # 帶 user_id → "voice-<user_id>" 人別隔離；開發包直連沒 token 才落回
            # 主要照護對象。（Supabase 模式 adapter 會把非 uuid person 壓回 env person，
            # 所以多用戶上 Supabase 前仍須完成正式身分接線——看板紅線。）
            "personId": person_id or PRIMARY_CARE_RECIPIENT_ID,
            # 語音線的 cid 是整數流水號、不是 voice_sessions 的 uuid：
            # 一律轉字串，Supabase 端 conversation_summary_to_row 對非 uuid 會自動落 None，
            # 本機 JSON 保留字串方便對 log。整數直接丟進去會在 UUID_RE.match 炸 TypeError。
            "voiceSessionId": (None if voice_session_id is None else str(voice_session_id)),
            "source": "live_voice",
        })
    except Exception as e:
        log_fallback_exception("persist voice call turns", e)
        return None


def recent_call_recap_line(now=None, person_id=None):
    """上次聊天若還在視窗內，回一段開場接續指令（只講距今多久），
    讓下一通不再重問剛答過的日常問題。沒有近況或超過視窗回空字串。
    注意：①person_id 必須跟 persist_voice_call_turns 同一 scope（token 的
    "voice-<user_id>" 或主要照護對象），否則 A 的上次聊天會講給 B 聽；
    ②不注入 memoryTags——那是內部英文 slug、可能含守護腦風險分類，不能進 prompt。"""
    if not _voice_call_memory_enabled():
        return ""
    return _recent_call_recap_line_core(now, person_id)


def _recent_call_recap_line_core(now=None, person_id=None):
    """recap 的核心（不含總開關）：給 Voice→Brain 內部端點用。"""
    try:
        items = load_conversation_summaries(
            person_id=person_id or PRIMARY_CARE_RECIPIENT_ID, limit=10)
    except Exception as e:
        log_fallback_exception("load recent call recap", e)
        return ""
    latest = None
    latest_ts = None
    for item in items or []:
        if not item.get("summary") or item.get("deletedAt"):
            continue
        try:
            ts = calendar.timegm(time.strptime(
                str(item.get("createdAt") or "")[:19], "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, TypeError):
            continue
        if latest_ts is None or ts > latest_ts:
            latest, latest_ts = item, ts
    if latest is None:
        return ""
    now_ts = now if now is not None else time.time()
    minutes = max(0, int((now_ts - latest_ts) // 60))
    if minutes > VOICE_CALL_RECAP_WINDOW_HOURS * 60:
        return ""
    ago = f"{minutes} 分鐘" if minutes < 60 else f"{minutes // 60} 小時"
    # 三道閘（2026-07-16 Edward 抓到「再撥還在講上一通＋幻覺」後改）：
    # 這行只知道「多久前聊過」、不知道聊了什麼——舊措辭叫 AI「自然接續」＝邀請它
    # 編造「我們剛聊到…」的具體內容。閘門：①不虛構內容 ②不主動宣稱記得 ③不確定當新通話。
    return (
        f"（你們上次聊天大約 {ago} 前結束，但你【不知道】上次聊了什麼內容。"
        "三條鐵律：①絕對不要編造或猜測上次聊過的具體內容，不准說「我們剛聊到…」"
        "「你上次說…」這類話，除非對方自己先提起；②不要主動宣稱你記得上一通，"
        "也不要一直圍繞「剛剛聊過」打轉——就把這通當一次普通的來電，輕鬆打招呼開始；"
        "③唯一可以用到這個資訊的地方：剛問過的日常寒暄（吃飯了沒、睡得好不好）"
        "不要當開場再問一次。）"
    )


def _voice_identity_scope(user_id):
    """Voice→Brain 內部端點：把 call token 的已驗證 user_id 解析成帳號範圍身分。
    回 (contextvar token, personId)；本機 json 模式或查無帳號回 (None, None) → 走預設人。
    綁進 REQUEST_DATA_IDENTITY 後，資料櫃的所有讀寫都落在該用戶自己的範圍——
    這就是「員工A代存、順便認人」的正式身分接線。"""
    if not user_id:
        return None, None
    try:
        identity = supabase_adapter.make_adapter(identity=None).resolve_auth_identity(user_id)
    except Exception as e:
        log_fallback_exception("resolve voice call identity", e)
        return None, None
    if not identity:
        return None, None
    token = REQUEST_DATA_IDENTITY.set(identity)
    return token, identity.get("personId")


def voice_call_memory_response(data):
    """POST /voice/call-memory（內部密語驗證後才會進來）：
    Voice 掛斷時把整通字幕交給 Brain 代存——Brain 有 Supabase 鑰匙、認得用戶，
    資料落東京正式庫而不是 Voice 容器的便條紙。"""
    data = data or {}
    scope_token, person = _voice_identity_scope(str(data.get("userId") or "").strip())
    try:
        result = _persist_voice_call_turns_core(
            data.get("turns"), char=data.get("char"),
            voice_session_id=data.get("voiceSessionId"), person_id=person)
        return {"ok": True, "stored": bool(result),
                "identityResolved": bool(person)}
    finally:
        if scope_token is not None:
            REQUEST_DATA_IDENTITY.reset(scope_token)


def voice_call_recap_response(data):
    """POST /voice/call-recap（內部密語驗證後才會進來）：
    Voice 開場前向 Brain 要「上次聊天重點」，讀的是該用戶自己的正式紀錄。"""
    data = data or {}
    scope_token, person = _voice_identity_scope(str(data.get("userId") or "").strip())
    try:
        return {"ok": True,
                "recapLine": _recent_call_recap_line_core(person_id=person),
                "identityResolved": bool(person)}
    finally:
        if scope_token is not None:
            REQUEST_DATA_IDENTITY.reset(scope_token)


def voice_health_context_response(data):
    """POST /voice/health-context（內部密語驗證後才會進來）：
    Voice 開場前向 Brain 要「這位來電者自己的身體狀況」。

    為什麼要繞這一圈：Voice 那台沒有雲端鑰匙、也認不出電話那頭是誰
    （所有來電者共用一個預設身分）。健康資料是最不能認錯人的東西——
    把 A 的血壓講給 B 聽，比不講嚴重得多。所以一律由 Brain 認人、Brain 撈、
    Voice 只拿結果，跟「上次聊天」「收線回寫記憶」走同一個模子。

    認不出人就回空：Voice 收到空的 → 圍籬告訴她「你什麼都看不到、不准編」。
    """
    data = data or {}
    scope_token, person = _voice_identity_scope(str(data.get("userId") or "").strip())
    try:
        ctx = load_health_context() if person else {"facts": [], "notable": [], "hasData": False}
        return {"ok": True, "healthContext": ctx, "identityResolved": bool(person)}
    finally:
        if scope_token is not None:
            REQUEST_DATA_IDENTITY.reset(scope_token)


def tts_b64(text, char=DEFAULT_CHAR, locale=None):
    """用該角色的聲音（＋動物的演技開場白）把文字唸成語音，回 base64 wav。"""
    c = eng.CHARS.get(char, eng.CHARS[DEFAULT_CHAR])
    content = (c["style"] or "") + localization.speech_text(text, locale)
    for m in ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"):
        try:
            r = eng.client.models.generate_content(
                model=m, contents=content,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(language_code=localization.speech_language_code(locale), voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=c["voice"])))))
            pcm = r.candidates[0].content.parts[0].inline_data.data
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            log_fallback_exception(f"generate TTS audio with {m}", e)
    return ""


def decode_voice_note(data):
    raw = data.get("audio") or ""
    if "," in raw:
        raw = raw.split(",", 1)[1]
    audio_bytes = base64.b64decode(raw) if raw else b""
    mime = data.get("mime") or "audio/webm"
    if mime not in ALLOWED_AUDIO_MIMES:
        raise ValueError("unsupported_audio_mime")
    if len(audio_bytes) > MAX_AUDIO_NOTE_BYTES:
        raise ValueError("audio_note_too_large")
    char = data.get("char") or DEFAULT_CHAR
    context = build_reply_context([], char, data)
    return {
        "ok": bool(audio_bytes),
        "bytes": len(audio_bytes),
        "mime": mime,
        "durationMs": max(0, min(int(data.get("durationMs") or 0), 180000)),
        "reply": "我收到你的語音了。下一步會把這段接到即時語音理解。",
        "aiContext": ai_context_summary(context),
    }


def voice_session(data):
    """回傳前端語音層能力；未來 Gemini Live / Interactions token 從這裡核發。"""
    char = data.get("char") or DEFAULT_CHAR
    context = build_reply_context([], char, data)
    return {
        "ok": True,
        "provider": "stt-chat-tts",
        "fallback": "typed-chat",
        "locale": localization.normalize_locale(data.get("locale")),
        "char": char,
        "aiContext": ai_context_summary(context),
        "sessionContext": {
            "personaContextEndpoint": "/persona/context",
            "replyComposition": "persona + memory + perception + current conversation + safety + voice/avatar limits",
            "visibleTranscriptDefault": False,
        },
        "capabilities": {
            "textChat": True,
            "recordedVoiceNote": True,
            "serverTts": True,
            "realtimeAudio": False,
            "interrupt": False,
            "visemeTiming": False,
        },
    }


EXT = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
       ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
       ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
       ".svg": "image/svg+xml", ".ico": "image/x-icon", ".webp": "image/webp", ".wav": "audio/wav"}

DEFAULT_CORS_ORIGINS = {
    "capacitor://localhost",
    "ionic://localhost",
    "http://localhost",
    "https://localhost",
    "https://app.munea.net",
    "https://munea.net",
    "https://www.munea.net",
}


def cors_origins():
    configured = os.environ.get("MUNEA_CORS_ORIGINS", "").strip()
    if not configured:
        return DEFAULT_CORS_ORIGINS
    return {origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()}


ADMIN_CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "object-src 'none'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self' https://*.run.app https://*.a.run.app",
    )
)


def admin_security_headers(path, content_type=""):
    clean_path = str(path or "").split("?", 1)[0].split("#", 1)[0]
    is_admin_surface = (
        clean_path in {"/admin", "/admin.html", "/src/admin.js", "/src/admin.css", "/src/version.js"}
        or clean_path.startswith("/admin/")
    )
    if not is_admin_surface:
        return {}

    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
    if clean_path in {"/admin", "/admin.html"} or "text/html" in str(content_type).lower():
        headers["Content-Security-Policy"] = ADMIN_CONTENT_SECURITY_POLICY
    return headers


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        response_headers = dict(extra_headers or {})
        response_headers.update(admin_security_headers(getattr(self, "path", ""), ctype))
        for name, value in response_headers.items():
            self.send_header(name, str(value))
        origin = (self.headers.get("Origin") or "").strip().rstrip("/")
        if origin and origin in cors_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        # 2026-07-11 主蘇菲：原本沒貼任何保鮮標籤 → iPhone Safari 啟發式快取、Edward 連三版更新都看到舊頁
        # （症狀組合跟三版前完全一致才抓到）。一律要求「每次回來源頭驗一下有沒有新版」，鋪版即刻生效。
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        origin = (self.headers.get("Origin") or "").strip().rstrip("/")
        if not origin or origin not in cors_origins():
            self._json_error(403, "cors_origin_denied", "Origin is not allowed")
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, X-Munea-Key, X-Munea-Admin-Token, X-Munea-Provider-Token",
        )
        self.send_header("Access-Control-Max-Age", "600")
        for name, value in admin_security_headers(getattr(self, "path", "")).items():
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, obj):
        self._send(200, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode())

    def _json_error(self, code, err_code, message="Request could not be processed", detail=None, extra_headers=None):
        rid = request_id()
        body = {"ok": False, "error": {"code": err_code, "message": message, "requestId": rid}}
        if detail and os.environ.get("MUNEA_DEBUG_API") == "1":
            body["error"]["detail"] = str(detail)[:160]
        self._send(code, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode(), extra_headers=extra_headers)

    def _read_json_body(self):
        ln = int(self.headers.get("Content-Length", 0))
        if ln > MAX_JSON_BODY_BYTES:
            raise ValueError("payload_too_large")
        raw = self.rfile.read(ln).decode("utf-8", "replace") if ln else "{}"
        return json.loads(raw or "{}")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/version", "/version/"):
            self._json({"ok": True, "release": BRAIN_RELEASE_METADATA})
            return
        if path in ("/healthz", "/healthz/"):
            self._json({
                "ok": True,
                "service": "munea-local-engine",
                "release": BRAIN_RELEASE_METADATA,
                "time": utc_now(),
                "runtime": {"concurrency": "threading", "jsonStoreWrites": "atomic", "authRequired": auth_required_mode()},
                "contracts": ["auth-status", "account-bootstrap", "app-profile", "companion-profile", "persona-context", "entitlements", "credits-balance", "credits-grant", "credits-consume", "apple-transaction", "apple-notifications-v2", "voice-session", "avatar-session", "ai-brain-status", "memory-extract", "memory-retrieve", "conversation-summary", "butler-post-turn", "guardian-evaluate", "perception-topic-plan", "perception-snapshot", "product-event", "feedback", "family-invitations", "family-members", "family-relays", "consent-records", "routine-reminders", "medication-doses", "push-devices", "notification-inbox", "admin-accounts", "admin-north-star", "admin-usage", "admin-credits", "admin-conversation-summaries", "admin-privacy-requests", "admin-feedback", "admin-safety-events", "admin-audit-events", "admin-voice-diagnostics", "privacy-export", "account-deletion"],
                "backend": data_backend_status(),
                "notificationPush": apns_status(),
            })
            return
        if path in ("/", ""):
            path = "/index.html"
        rel = posixpath.normpath(path).lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):   # 防目錄穿越 + 404
            self._send(404, "text/plain; charset=utf-8", b"404"); return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            self._send(200, EXT.get(ext, "application/octet-stream"), f.read())

    def do_POST(self):
        scope_token = None
        try:
            # 薄門（正式上線 · 7/9）：環境設了 MUNEA_APP_KEY 就要帶對 X-Munea-Key（App 自動帶、用戶無感）。
            # 擋「雲端大門開了之後、陌生人拿網址直接來打」的流量。沒設 key＝不啟用、本機/區網照舊。
            _door = os.environ.get("MUNEA_APP_KEY", "").strip()
            request_path = self.path.split("?", 1)[0]
            # Apple cannot attach our app key. This one public webhook is instead
            # authenticated by Apple's nested JWS signatures before any mutation.
            if _door and request_path != "/apple/notifications" and self.headers.get("X-Munea-Key", "").strip() != _door:
                self._json_error(403, "app_key_required", "App key required")
                return
            data = self._read_json_body()
            # Voice→Brain 內部通道（通話記憶）：Voice 沒有用戶的登入 token，
            # 改用共用內部密語驗證（同家人傳話簽章密語的做法），身分由 call token
            # 的已驗證 user_id 在 Brain 端解析。密語沒設＝通道關閉，一律 403。
            if request_path in ("/voice/call-memory", "/voice/call-recap", "/voice/health-context"):
                _voice_secret = os.environ.get("MUNEA_VOICE_BRAIN_SECRET", "").strip()
                _supplied = (self.headers.get("Authorization") or "").replace("Bearer ", "", 1).strip()
                if not _voice_secret or not _supplied or not hmac.compare_digest(_supplied, _voice_secret):
                    self._json_error(403, "voice_internal_secret_required",
                                     "Voice internal secret is missing or wrong")
                    return
                _voice_internal = {
                    "/voice/call-memory": voice_call_memory_response,
                    "/voice/call-recap": voice_call_recap_response,
                    "/voice/health-context": voice_health_context_response,
                }
                self._json(_voice_internal[request_path](data))
                return
            auth_gate = require_verified_auth(self.headers, self.path, data)
            # Family-circle invites always require a verified identity, even in
            # local/demo mode where most endpoints may allow a guest preview.
            # A join code is never an authentication credential.
            if request_path in ("/family/invitations", "/family-relays", "/push/devices", "/notifications", "/notifications/settings"):
                family_auth = verify_auth_context(self.headers)
                if not family_auth.get("ok"):
                    self._json_error(401, family_auth.get("code") or "auth_required", "Verified account token is required")
                    return
                auth_gate = {"ok": True, "required": True, "auth": public_auth_context(family_auth)}
            if not auth_gate.get("ok"):
                self._json_error(401, auth_gate.get("code") or "auth_required", "Verified account token is required")
                return
            # AI 端點限流：驗完身分、還沒碰資料櫃/LLM 之前就擋，超額的請求不花後面任何成本。
            if request_path in AI_RATE_LIMITED_PATHS:
                _actor = (auth_gate.get("auth") or {}).get("authUserId")
                if not _actor:
                    _xff = self.headers.get("X-Forwarded-For") or ""
                    _actor = _xff.split(",")[0].strip() if _xff else (self.client_address[0] if self.client_address else "")
                _limited, _retry_after = ai_rate_limited(_actor, request_path)
                if _limited:
                    self._json_error(429, "rate_limited", "Too many requests, please slow down",
                                     extra_headers={"Retry-After": _retry_after})
                    return
            scope_token = bind_request_data_identity(
                auth_gate,
                allow_missing=self.path.split("?", 1)[0] == "/account-bootstrap",
            )
            authorize_request_data_scope(self.path, data, auth_gate)
            char = data.get("char") or DEFAULT_CHAR
            if self.path == "/open":
                t = eng.open_chat(char) if localization.normalize_locale(data.get("locale")) == "zh-TW" else reply_conv([], char, data)
                t = localization.assistant_output_text(t, data.get("locale"))
                self._json({"reply": t, "audio": tts_b64(t, char, data.get("locale"))})
            elif self.path == "/chat":
                self._json(chat_response(data, char))
            elif self.path == "/voice-session":
                self._json(voice_session(data))
            elif self.path == "/voice-note":
                self._json(decode_voice_note(data))
            elif self.path == "/avatar-session":
                self._json(avatar_session_response(data))
            elif self.path == "/feedback":
                self._json(feedback_response(data))
            elif self.path == "/product-event":
                self._json(product_event_response(data))
            elif self.path == "/ai/brain-status":
                self._json(model_router.brain_status_response())
            elif self.path == "/persona/context":
                self._json(persona_context_response(data))
            elif self.path == "/memory/extract":
                self._json(memory_extract_response(data))
            elif self.path == "/memory/retrieve":
                self._json(memory_retrieve_response(data))
            elif self.path == "/conversation-summary":
                self._json(conversation_summary_response(data))
            elif self.path == "/butler/post-turn":
                self._json(butler_post_turn_response(data))
            elif self.path == "/admin/login":
                _xff = self.headers.get("X-Forwarded-For") or ""
                _cip = _xff.split(",")[0].strip() if _xff else (self.client_address[0] if self.client_address else "")
                self._json(admin_login_response(data, client_ip=_cip))
            elif self.path == "/admin/memory-consolidate":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(consolidate_memory(data.get("personId") or data.get("person_id")))
            elif self.path == "/admin/memory-living-profile":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(refresh_living_profile(data.get("personId") or data.get("person_id")))
            elif self.path == "/family/state":
                self._json(family_state_response(data))
            elif self.path == "/family/invitations":
                _xff = self.headers.get("X-Forwarded-For") or ""
                _cip = _xff.split(",")[0].strip() if _xff else (self.client_address[0] if self.client_address else "")
                self._json(family_invitations_response(data, client_ip=_cip, actor=auth_gate.get("auth")))
            elif self.path == "/family-members":
                self._json(family_members_response(data))
            elif self.path == "/family-relays":
                self._json(family_relays_response(data))
            elif self.path == "/consent-records":
                self._json(consent_records_response(data))
            elif self.path == "/family/activity":
                self._json(family_activity_response(data))
            elif self.path == "/routine-reminders":
                self._json(routine_reminders_response(data))
            elif self.path == "/medication-doses":
                self._json(medication_doses_response(data))
            elif self.path == "/push/devices":
                self._json(push_devices_response(data))
            elif self.path == "/notifications/settings":
                self._json(notification_settings_response(data))
            elif self.path == "/notifications":
                self._json(notification_events_response(data))
            elif self.path == "/wellbeing/trend":
                self._json(wellbeing_trend_response(data))
            elif self.path == "/wellbeing/log":
                self._json(wellbeing_log_response(data))
            elif self.path == "/wellbeing/recent":
                self._json(wellbeing_recent_response(data))
            elif self.path == "/proactive/opening":
                self._json(proactive_opening_response(data))
            elif self.path == "/care-schedule":
                self._json(care_schedule_response(data))
            elif self.path == "/admin/daily-briefing":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(refresh_daily_briefing(data.get("region"), data.get("personId") or data.get("person_id")))
            elif self.path == "/guardian/evaluate":
                self._json(guardian_evaluate_response(data))
            elif self.path == "/perception/topic-plan":
                self._json(topic_perception_plan_response(data))
            elif self.path == "/perception/snapshot":
                self._json(perception_snapshot_response(data))
            elif self.path == "/admin/accounts":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_accounts_summary(data))
            elif self.path == "/admin/north-star":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(north_star_summary(data))
            elif self.path == "/admin/usage":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_usage_summary(data))
            elif self.path == "/admin/credits":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_credits_summary(data))
            elif self.path == "/admin/subscription-metrics":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_subscription_metrics(data))
            elif self.path == "/admin/conversation-summaries":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_conversation_summaries(data))
            elif self.path == "/admin/privacy-requests":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_privacy_requests_summary(data))
            elif self.path == "/admin/feedback":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_feedback_summary(data))
            elif self.path == "/admin/safety-events":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_safety_events_summary(data))
            elif self.path == "/admin/audit-events":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_audit_events_summary(data))
            elif self.path == "/admin/voice-diagnostics":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(admin_voice_diagnostics_summary(data))
            elif self.path == "/admin/notifications/drain":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(drain_notification_outbox_response(data))
            elif self.path == "/companion-profile":
                self._json(companion_profile_response(data))
            elif self.path == "/app-profile":
                self._json(app_profile_response(data))
            elif self.path == "/auth-status":
                self._json(auth_status_response(self.headers))
            elif self.path == "/account-bootstrap":
                self._json(bootstrap_account_response(data, self.headers))
            elif self.path == "/entitlements":
                action = (data.get("action") or "load").lower()
                if action in ("save", "replace"):
                    ok, code = privileged_billing_write_authorized(self.headers)
                    if not ok:
                        self._json_error(403, code, "Admin token is required for entitlement changes")
                        return
                response = entitlements_response(data)
                if action in ("save", "replace") and response.get("ok"):
                    append_audit_event({
                        "eventType": "entitlements_changed",
                        "targetTable": "subscription_ledger",
                        "details": {
                            **privileged_actor_context(self.headers),
                            "activePlan": response.get("billing", {}).get("activePlan"),
                            "action": action,
                        },
                    })
                self._json(response)
            elif self.path == "/subscription-event":
                ok, code = privileged_billing_write_authorized(self.headers, allow_provider=True)
                if not ok:
                    self._json_error(403, code, "Provider or admin token is required for subscription events")
                    return
                response = subscription_event_response(data)
                if response.get("ok"):
                    event = data.get("event") or {}
                    append_audit_event({
                        "eventType": "subscription_event_accepted",
                        "targetTable": "subscription_ledger",
                        "details": {
                            **privileged_actor_context(self.headers, allow_provider=True),
                            "provider": data.get("provider") or "apple-app-store-server-notifications-v2",
                            "eventType": event.get("type") or event.get("notificationType") or "unknown",
                            "serverVerificationRequired": True,
                        },
                    })
                self._json(response)
            elif self.path == "/credits/balance":
                self._json(credits_balance_response(data))
            elif self.path == "/apple/transaction":
                self._json(apple_transaction_response(data, auth_gate=auth_gate))
            elif self.path == "/apple/notifications":
                response = apple_notification_response(data)
                if response.get("ok"):
                    self._json(response)
                else:
                    error = response.get("error") or {}
                    self._json_error(
                        503 if response.get("retryable") else 400,
                        error.get("code") or "apple_notification_rejected",
                        "App Store notification could not be applied",
                    )
            elif self.path == "/credits/grant":
                ok, code = privileged_billing_write_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required for credit grants")
                    return
                response = credits_grant_response(data)
                if response.get("ok"):
                    tx = response.get("transaction") or {}
                    append_audit_event({
                        "eventType": "credits_granted",
                        "targetTable": "credit_transactions",
                        "details": {
                            **privileged_actor_context(self.headers),
                            "transactionId": tx.get("id"),
                            "amount": tx.get("amount"),
                            "walletType": tx.get("walletType"),
                            "source": tx.get("source"),
                            "reason": tx.get("reason"),
                        },
                    })
                self._json(response)
            elif self.path == "/credits/consume":
                ok, code = privileged_billing_write_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required for direct credit consumption")
                    return
                response = credits_consume_response(data)
                if response.get("ok"):
                    append_audit_event({
                        "eventType": "credits_consumed_directly",
                        "targetTable": "credit_transactions",
                        "details": {
                            **privileged_actor_context(self.headers),
                            "transactionIds": [tx.get("id") for tx in response.get("transactions", [])],
                            "amount": data.get("amount") or data.get("credits"),
                            "feature": data.get("feature"),
                        },
                    })
                self._json(response)
            elif self.path == "/dev/page-capture":
                # 本機開發用：把前端傳來的畫面 HTML 原樣存檔（僅綁 127.0.0.1、不對外）
                name = "".join(ch for ch in str(data.get("name") or "page") if ch.isalnum() or ch in "-_")[:40]
                cap_dir = os.path.join(os.path.dirname(HERE), ".design-sync", "captures")
                os.makedirs(cap_dir, exist_ok=True)
                with open(os.path.join(cap_dir, name + ".html"), "w", encoding="utf-8") as f:
                    f.write(str(data.get("html") or ""))
                self._json({"ok": True, "name": name})
            elif self.path == "/privacy-export":
                self._json(privacy_export_response(data))
            elif self.path == "/account-deletion":
                self._json(account_deletion_response(data, auth_gate=auth_gate))
            else:
                self._send(404, "text/plain; charset=utf-8", b"404")
        except json.JSONDecodeError as e:
            self._json_error(400, "invalid_json", "Request body must be valid JSON", e)
        except ValueError as e:
            if str(e) == "payload_too_large":
                self._json_error(413, "payload_too_large", "Request body is too large")
            elif str(e) == "audio_note_too_large":
                self._json_error(413, "audio_note_too_large", "Audio note is too large")
            elif str(e) == "unsupported_audio_mime":
                self._json_error(415, "unsupported_audio_mime", "Audio MIME type is not supported")
            else:
                self._json_error(400, "invalid_request", "Request could not be processed", e)
        except PermissionError as e:
            if str(e) == "account_scope_missing":
                self._json_error(403, "account_scope_missing", "This account must be initialized before accessing private data")
            else:
                self._json_error(403, "forbidden", "Request is not allowed", e)
        except Exception as e:
            try:
                notify.alert("engine", getattr(self, "path", "?"), str(e)[:200])
            except Exception as notify_error:
                log_fallback_exception("send engine error alert", notify_error)
            self._json_error(500, "internal_error", "Request could not be processed", e)
        finally:
            if scope_token is not None:
                REQUEST_DATA_IDENTITY.reset(scope_token)


if __name__ == "__main__":
    try:
        port = int(os.environ.get("MUNEA_PORT") or "8200")
    except ValueError:
        port = 8200
    print(f"沐寧 App 伺服器啟動 → http://localhost:{port}  （Ctrl+C 結束）")
    # 門向：本機照舊只開給自己家（安全）；雲端主機（Cloud Run）由配方設 MUNEA_HOST=0.0.0.0 開正門
    host = os.environ.get("MUNEA_HOST") or "127.0.0.1"
    ThreadingHTTPServer((host, port), H).serve_forever()
