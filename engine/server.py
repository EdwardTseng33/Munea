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
import os, sys, json, base64, io, wave, time, posixpath
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from env_loader import load_engine_env
load_engine_env()
import chat_engine as eng
import supabase_adapter
import model_router
from google.genai import types

if not os.environ.get("GEMINI_API_KEY"):
    sys.exit("需要 GEMINI_API_KEY")

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.normpath(os.path.join(HERE, "..", "web"))
DEFAULT_CHAR = "寧寧"
COMPANION_PROFILE_PATH = os.environ.get("MUNEA_COMPANION_PROFILE_PATH") or os.path.join(HERE, "companion_profile.json")
APP_PROFILE_STORE_PATH = os.environ.get("MUNEA_APP_PROFILE_STORE_PATH") or os.path.join(HERE, "app_profile_store.json")
BILLING_STORE_PATH = os.environ.get("MUNEA_BILLING_STORE_PATH") or os.path.join(HERE, "billing_store.json")
PRIVACY_REQUESTS_PATH = os.environ.get("MUNEA_PRIVACY_REQUESTS_PATH") or os.path.join(HERE, "privacy_requests.json")
PRODUCT_EVENTS_PATH = os.environ.get("MUNEA_PRODUCT_EVENTS_PATH") or os.path.join(HERE, "product_events.json")
MEMORY_ITEMS_PATH = os.environ.get("MUNEA_MEMORY_ITEMS_PATH") or os.path.join(HERE, "memory_items.json")
PRIMARY_CARE_RECIPIENT_ID = "local-person-self"
MAX_JSON_BODY_BYTES = 1_000_000
MAX_AUDIO_NOTE_BYTES = 12_000_000
ALLOWED_AUDIO_MIMES = {"audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}
AVATAR_ENGINE_MODES = {"static-css", "2d-viseme", "ditto", "liveavatar"}
PREMIUM_AVATAR_MODES = {"ditto", "liveavatar"}
MEANINGFUL_EVENT_NAMES = {
    "routine_reminder_completed",
    "family_interaction_sent",
    "family_message_sent",
    "family_message_viewed",
    "family_dashboard_viewed",
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
    except Exception:
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
    except Exception:
        return fallback


def write_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def data_backend():
    return supabase_adapter.make_adapter()


def data_backend_status():
    status = data_backend().status()
    status["fallback"] = "json"
    return status


def load_memory_items(limit=200):
    items = read_json_file(MEMORY_ITEMS_PATH, [])
    if not isinstance(items, list):
        items = []
    return items[-limit:]


def save_memory_items(items):
    write_json_file(MEMORY_ITEMS_PATH, list(items)[-1000:])
    return items


def memory_extract_response(data):
    data = data or {}
    response = model_router.memory_extract_response(data)
    if (data.get("action") or "preview") == "store":
        existing = load_memory_items(limit=1000)
        person_id = data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID
        new_items = [model_router.normalize_memory_item(c, person_id) for c in response["candidates"]]
        save_memory_items(existing + new_items)
        response["stored"] = len(new_items)
        response["memoryItems"] = new_items
    else:
        response["stored"] = 0
    return response


def memory_retrieve_response(data):
    return model_router.memory_retrieve_response(data or {}, load_memory_items())


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


def normalize_family_member(member):
    member = member or {}
    member_id = str(member.get("id") or PRIMARY_CARE_RECIPIENT_ID)
    return {
        "id": member_id,
        "role": str(member.get("role") or ("primary_user" if member_id == PRIMARY_CARE_RECIPIENT_ID else "family_contact")),
        "displayName": str(member.get("displayName") or member.get("display_name") or "Member").strip()[:40] or "Member",
        "relationship": str(member.get("relationship") or "family"),
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


def load_app_profile_store():
    try:
        remote_store = data_backend().load_app_profile_store()
        if remote_store:
            return normalize_app_profile_store(remote_store)
    except Exception:
        pass
    return load_json_app_profile_store()


def save_app_profile_store(data):
    store = normalize_app_profile_store({**data, "updatedAt": utc_now()})
    try:
        remote_store = data_backend().save_app_profile_store(store)
        if remote_store:
            store = normalize_app_profile_store(remote_store)
    except Exception:
        pass
    write_json_file(APP_PROFILE_STORE_PATH, store)
    return store


def bootstrap_account_response(data, headers=None):
    data = data or {}
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
            append_product_event({"eventName": "account_bootstrapped", "properties": {"backend": "supabase"}})
            return {
                "ok": True,
                "store": store,
                "activeCompanionProfile": active_companion_profile(store),
                "auth": public_auth_context(auth_context),
                "backend": data_backend_status(),
            }
    except Exception as e:
        if data_backend().enabled():
            raise e

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
    return {
        "ok": True,
        "store": store,
        "activeCompanionProfile": active_companion_profile(store),
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
    except Exception:
        pass
    return active_companion_profile(load_app_profile_store())


def save_companion_profile(data):
    profile = normalize_companion_profile({**data, "updatedAt": utc_now()})
    try:
        remote_profile = data_backend().save_companion_profile(profile)
        if remote_profile:
            profile = normalize_companion_profile(remote_profile)
    except Exception:
        pass
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
    except Exception:
        pass
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
    except Exception:
        pass
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
        elif name in ("family_interaction_sent", "family_message_sent", "family_message_viewed", "family_dashboard_viewed"):
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


def product_event_response(data):
    event = append_product_event(data)
    return {"ok": True, "event": event, "northStar": north_star_summary({"days": 7})}


def admin_authorized(headers):
    token = os.environ.get("MUNEA_ADMIN_API_TOKEN") or ""
    if not token:
        return False, "admin_token_not_configured"
    supplied = headers.get("X-Munea-Admin-Token") or headers.get("x-munea-admin-token") or ""
    if supplied != token:
        return False, "invalid_admin_token"
    return True, None


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
            "realtimeAvatar": False,
            "premiumAvatarMinutesMonthly": 0,
            "familyMembersMax": 2,
        },
        "usageLedger": {
            "period": time.strftime("%Y-%m"),
            "voiceMinutesUsed": 0,
            "avatarMinutesUsed": 0,
        },
        "serverVerificationRequired": True,
        "updatedAt": utc_now(),
    }


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


def load_billing_store():
    try:
        remote_store = data_backend().load_billing_store()
        if remote_store:
            return normalize_billing_store(remote_store)
    except Exception:
        pass
    return normalize_billing_store(read_json_file(BILLING_STORE_PATH, {}))


def save_billing_store(data):
    store = normalize_billing_store({**data, "updatedAt": utc_now()})
    try:
        remote_store = data_backend().save_billing_store(store)
        if remote_store:
            store = normalize_billing_store(remote_store)
    except Exception:
        pass
    write_json_file(BILLING_STORE_PATH, store)
    return store


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
        "note": "Local prototype only. Production must verify Apple signedTransactionInfo / signedRenewalInfo server-side.",
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
    selected_mode = requested_mode
    fallback_reason = None

    if requested_mode in PREMIUM_AVATAR_MODES:
        if not premium_allowed:
            selected_mode = "2d-viseme"
            fallback_reason = "premium_avatar_not_entitled"
        elif premium_grant <= 0:
            selected_mode = "2d-viseme"
            fallback_reason = "premium_avatar_no_monthly_grant"
        elif premium_used + duration_minutes > premium_grant:
            selected_mode = "2d-viseme"
            fallback_reason = "premium_avatar_minutes_exhausted"

    usage_committed = False
    if action in ("complete", "record-usage", "record_usage") and selected_mode in PREMIUM_AVATAR_MODES and duration_minutes > 0:
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
    except Exception:
        pass
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
    except Exception:
        pass
    store = load_privacy_requests_store()
    req = normalize_privacy_request({**data, "type": req_type, "requestedAt": utc_now()})
    store["requests"].append(req)
    save_privacy_requests_store(store)
    return req


def privacy_export_response(data):
    action = (data.get("action") or "preview").lower()
    if action in ("request", "create"):
        export_request = append_privacy_request("export", data)
    else:
        export_request = normalize_privacy_request({"type": "export", "status": "preview", "requiresReauth": True})

    return {
        "ok": True,
        "request": export_request,
        "exportPackage": {
            "generatedAt": utc_now(),
            "account": load_app_profile_store().get("account"),
            "familyGroup": load_app_profile_store().get("familyGroup"),
            "primaryCareRecipientId": load_app_profile_store().get("primaryCareRecipientId"),
            "companionProfiles": load_app_profile_store().get("companionProfiles"),
            "billing": load_billing_store(),
            "privacyRequests": load_privacy_requests_store(),
        },
        "format": "json",
        "productionNote": "Production export should run asynchronously, require authentication, and redact provider secrets/internal logs.",
    }


def account_deletion_response(data):
    action = (data.get("action") or "status").lower()
    store = load_privacy_requests_store()
    deletion_requests = [r for r in store["requests"] if r["type"] == "account_deletion"]
    if action in ("request", "create"):
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
    base = c["persona"] + eng.RED + (eng._profile_ctx() if c["type"] == "human" else "")
    return base, c


def reply_conv(history, char=DEFAULT_CHAR):
    """帶完整對話脈絡，用該角色的腦＋記憶回話。"""
    base, _ = _sys_for(char)
    contents = [types.Content(role=h["role"], parts=[types.Part(text=h["text"])]) for h in history]
    for _ in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = eng.client.models.generate_content(
                    model=m, contents=contents,
                    config=types.GenerateContentConfig(system_instruction=base, temperature=0.85))
                return r.text.strip()
            except Exception:
                pass
        time.sleep(2)
    return "（不好意思，我這邊連線有點不順，等一下再陪你好不好？）"


def tts_b64(text, char=DEFAULT_CHAR):
    """用該角色的聲音（＋動物的演技開場白）把文字唸成語音，回 base64 wav。"""
    c = eng.CHARS.get(char, eng.CHARS[DEFAULT_CHAR])
    content = (c["style"] or "") + text
    for m in ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"):
        try:
            r = eng.client.models.generate_content(
                model=m, contents=content,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=c["voice"])))))
            pcm = r.candidates[0].content.parts[0].inline_data.data
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass
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
    return {
        "ok": bool(audio_bytes),
        "bytes": len(audio_bytes),
        "mime": mime,
        "durationMs": max(0, min(int(data.get("durationMs") or 0), 180000)),
        "reply": "我收到你的語音了。下一步會把這段接到即時語音理解。",
    }


def voice_session(data):
    """回傳前端語音層能力；未來 Gemini Live / Interactions token 從這裡核發。"""
    return {
        "ok": True,
        "provider": "stt-chat-tts",
        "fallback": "typed-chat",
        "locale": data.get("locale") or "zh-TW",
        "char": data.get("char") or DEFAULT_CHAR,
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


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        self._send(200, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode())

    def _json_error(self, code, err_code, message="Request could not be processed", detail=None):
        rid = request_id()
        body = {"ok": False, "error": {"code": err_code, "message": message, "requestId": rid}}
        if detail and os.environ.get("MUNEA_DEBUG_API") == "1":
            body["error"]["detail"] = str(detail)[:160]
        self._send(code, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode())

    def _read_json_body(self):
        ln = int(self.headers.get("Content-Length", 0))
        if ln > MAX_JSON_BODY_BYTES:
            raise ValueError("payload_too_large")
        raw = self.rfile.read(ln).decode("utf-8", "replace") if ln else "{}"
        return json.loads(raw or "{}")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._json({
                "ok": True,
                "service": "munea-local-engine",
                "time": utc_now(),
                "contracts": ["auth-status", "account-bootstrap", "app-profile", "companion-profile", "entitlements", "voice-session", "avatar-session", "ai-brain-status", "memory-extract", "memory-retrieve", "guardian-evaluate", "product-event", "admin-north-star", "privacy-export", "account-deletion"],
                "backend": data_backend_status(),
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
        try:
            data = self._read_json_body()
            char = data.get("char") or DEFAULT_CHAR
            if self.path == "/open":
                t = eng.open_chat(char)
                self._json({"reply": t, "audio": tts_b64(t, char)})
            elif self.path == "/chat":
                t = reply_conv(data.get("history", []), char)
                self._json({"reply": t, "audio": tts_b64(t, char)})
            elif self.path == "/voice-session":
                self._json(voice_session(data))
            elif self.path == "/voice-note":
                self._json(decode_voice_note(data))
            elif self.path == "/avatar-session":
                self._json(avatar_session_response(data))
            elif self.path == "/product-event":
                self._json(product_event_response(data))
            elif self.path == "/ai/brain-status":
                self._json(model_router.brain_status_response())
            elif self.path == "/memory/extract":
                self._json(memory_extract_response(data))
            elif self.path == "/memory/retrieve":
                self._json(memory_retrieve_response(data))
            elif self.path == "/guardian/evaluate":
                self._json(guardian_evaluate_response(data))
            elif self.path == "/admin/north-star":
                ok, code = admin_authorized(self.headers)
                if not ok:
                    self._json_error(403, code, "Admin token is required")
                else:
                    self._json(north_star_summary(data))
            elif self.path == "/companion-profile":
                self._json(companion_profile_response(data))
            elif self.path == "/app-profile":
                self._json(app_profile_response(data))
            elif self.path == "/auth-status":
                self._json(auth_status_response(self.headers))
            elif self.path == "/account-bootstrap":
                self._json(bootstrap_account_response(data, self.headers))
            elif self.path == "/entitlements":
                self._json(entitlements_response(data))
            elif self.path == "/subscription-event":
                self._json(subscription_event_response(data))
            elif self.path == "/privacy-export":
                self._json(privacy_export_response(data))
            elif self.path == "/account-deletion":
                self._json(account_deletion_response(data))
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
        except Exception as e:
            self._json_error(500, "internal_error", "Request could not be processed", e)


if __name__ == "__main__":
    print("沐寧 App 伺服器啟動 → http://localhost:8200  （Ctrl+C 結束）")
    HTTPServer(("127.0.0.1", 8200), H).serve_forever()
