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
import os, sys, json, base64, io, wave, time, posixpath, threading, logging
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
CREDITS_STORE_PATH = os.environ.get("MUNEA_CREDITS_STORE_PATH") or os.path.join(HERE, "credits_store.json")
FAMILY_STATE_STORE_PATH = os.environ.get("MUNEA_FAMILY_STATE_STORE_PATH") or os.path.join(HERE, "family_state_store.json")
PRIVACY_REQUESTS_PATH = os.environ.get("MUNEA_PRIVACY_REQUESTS_PATH") or os.path.join(HERE, "privacy_requests.json")
PRODUCT_EVENTS_PATH = os.environ.get("MUNEA_PRODUCT_EVENTS_PATH") or os.path.join(HERE, "product_events.json")
AUDIT_EVENTS_STORE_PATH = os.environ.get("MUNEA_AUDIT_EVENTS_STORE_PATH") or os.path.join(HERE, "audit_events_store.json")
MEMORY_ITEMS_PATH = os.environ.get("MUNEA_MEMORY_ITEMS_PATH") or os.path.join(HERE, "memory_items.json")
PERCEPTION_SNAPSHOTS_PATH = os.environ.get("MUNEA_PERCEPTION_SNAPSHOTS_PATH") or os.path.join(HERE, "perception_snapshots.json")
RELATIONSHIP_STATES_PATH = os.environ.get("MUNEA_RELATIONSHIP_STATES_PATH") or os.path.join(HERE, "companion_relationship_states.json")
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


PUBLIC_POST_PATHS = {"/auth-status", "/account-bootstrap"}
ADMIN_POST_PATHS = {"/admin/north-star", "/admin/usage", "/admin/credits"}
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


def data_backend():
    return supabase_adapter.make_adapter()


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


LIVING_PROFILE_PATH = os.environ.get("MUNEA_LIVING_PROFILE_PATH") or os.path.join(HERE, "living_profile.json")


def load_living_profile():
    prof = read_json_file(LIVING_PROFILE_PATH, {})
    return prof if isinstance(prof, dict) else {}


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
        save_living_profile(profile)
    return {"ok": bool(profile), "brain": "butler", "action": "living_profile",
            "profile": profile, "basedOnMemories": len(items)}


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


def append_wellbeing_signal(signal):
    """存一筆「心情觀察」訊號（統一格式 WellbeingSignal：V2 影像/動作將來也吐同格式）。"""
    signals = read_json_file(WELLBEING_PATH, [])
    if not isinstance(signals, list):
        signals = []
    signals.append(signal)
    write_json_file(WELLBEING_PATH, signals[-2000:])
    return signal


def load_wellbeing_signals(person_id=None, limit=200):
    signals = read_json_file(WELLBEING_PATH, [])
    if not isinstance(signals, list):
        signals = []
    if person_id:
        signals = [s for s in signals if s.get("personId") == person_id]
    return signals[-limit:]


FAMILY_STATE_KEYS = {"activities", "familyFeed", "meds", "visit", "routine", "wallet"}

def family_state_response(data):
    """家庭共享狀態（原型底座）：單一家庭 key-value；正式版由 Codex 換成雲端表、格式不變。"""
    data = data or {}
    action = data.get("action") or "load"
    state = {}
    try:
        state = read_json_file(FAMILY_STATE_STORE_PATH) or {}
    except Exception:
        state = {}
    if action == "save":
        key = data.get("key")
        if key not in FAMILY_STATE_KEYS:
            return {"ok": False, "error": "key_not_allowed"}
        state[key] = {"value": data.get("value"), "updatedAt": now_iso() if "now_iso" in globals() else time.strftime("%Y-%m-%dT%H:%M:%S")}
        write_json_file(FAMILY_STATE_STORE_PATH, state)
        return {"ok": True, "key": key}
    return {"ok": True, "state": {k: v.get("value") for k, v in state.items() if isinstance(v, dict)}}

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
    items = read_json_file(CARE_SCHEDULE_PATH, [])
    if not isinstance(items, list):
        items = []
    if action == "add":
        item = {
            "id": "cs_" + uuid.uuid4().hex[:10],
            "personId": person_id,
            "label": (data.get("label") or "").strip()[:60],
            "date": data.get("date"),
            "weekday": data.get("weekday"),
            "createdAt": utc_now(),
        }
        if item["label"]:
            items.append(item)
            write_json_file(CARE_SCHEDULE_PATH, items[-500:])
        return {"ok": True, "action": "add", "item": item}
    if action == "remove":
        rid = data.get("id")
        items = [i for i in items if i.get("id") != rid]
        write_json_file(CARE_SCHEDULE_PATH, items)
        return {"ok": True, "action": "remove", "id": rid}
    return {"ok": True, "action": "list", "items": load_care_schedule(person_id),
            "today": today_care_items(person_id)}


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
    """每日簡報功課：抓真天氣＋真空品 → 一句人話 → 存感知抽屜（帶當天到期）。
    設計為清晨定時跑（預設 06:30）；也可由管理端手動觸發。"""
    import perception_engine
    person_id = person_id or PRIMARY_CARE_RECIPIENT_ID
    try:
        briefing = perception_engine.build_briefing(region)
    except Exception as e:
        log_fallback_exception("build daily briefing", e)
        return {"ok": False, "brain": "butler", "action": "daily_briefing", "error": "briefing_failed"}
    briefing["scheduleToday"] = today_care_items(person_id)  # 今天的回診/重要日子
    try:
        news = perception_engine.fetch_daily_news()  # 每日一則暖新聞（有護欄、找不到寧可不給）
        briefing["newsLine"] = (news or {}).get("line") or ""
    except Exception:
        briefing["newsLine"] = ""
    expires = briefing["date"] + "T23:59:59+08:00"  # 當天有效、隔天自然過期
    append_perception_snapshots([{
        "personId": person_id,
        "snapshotType": "daily_briefing",
        "expiresAt": expires,
        "facts": briefing,
        "source": "perception_engine",
    }])
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
        if data_backend().enabled() and not is_missing_table_error(e):
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
        if data_backend().enabled() and not is_missing_table_error(e):
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


def build_reply_context(history, char=DEFAULT_CHAR, data=None):
    data = data or {}
    text = conversation_text(history)
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
        # 簡報保鮮：沒有今天的就背景補做（不擋這一次回話——這輪不提天氣、下一輪就有）
        import threading
        threading.Thread(target=refresh_daily_briefing, daemon=True).start()
    return {
        "persona": persona,
        "guardian": guardian,
        "memories": memories,
        "perception": perception,
        "livingProfile": load_living_profile(),
        "now": now_ctx,                                # 真時間（台灣、時段、語氣提示）
        "dailyBriefing": briefing,                     # 今日簡報（清晨備好的真天氣/空品/行程/暖聞）
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
    if brief.get("briefingLine") or brief.get("careHints") or brief.get("scheduleToday") or brief.get("newsLine"):
        seg = "（今日簡報（已核實的真實資料，可自然帶進關心、不要照唸）："
        if brief.get("briefingLine"):
            seg += brief["briefingLine"] + "。"
        if brief.get("careHints"):
            seg += "關心提示：" + "；".join(brief["careHints"]) + "。"
        if brief.get("scheduleToday"):
            seg += "今天的重要日子：" + "、".join(brief["scheduleToday"]) + "（要記得溫柔提醒）。"
        if brief.get("newsLine"):
            seg += "今日暖聞（可當話題）：" + brief["newsLine"]
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
    memory_lines = [
        f"- {item.get('type')}: {item.get('content')}"
        for item in memories[:5]
        if item.get("content")
    ]
    domain_lines = [
        f"- {item.get('domain')} needs {', '.join(item.get('requiredSources') or [])}"
        for item in perception.get("domains", [])
    ]
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
        "（智慧鏡頭：可溫柔用台灣諺語、生活智慧、簡單的反思提問陪伴；對方有信仰才順著其信仰語彙。絕不捏造經文、不強加宗教、不說教；危機時安全規則優先於一切。）",
        living_line,
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
        if data_backend().enabled() and not is_missing_table_error(e):
            raise e
        log_fallback_exception("bootstrap account through Supabase", e)

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


def provider_webhook_authorized(headers):
    token = os.environ.get("MUNEA_PROVIDER_WEBHOOK_TOKEN") or ""
    if not token:
        return False, "provider_token_not_configured"
    supplied = headers.get("X-Munea-Provider-Token") or headers.get("x-munea-provider-token") or ""
    if supplied != token:
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
    included = sum(float(w.get("balance") or 0) for w in wallets if w.get("type") == "included_monthly" and w.get("status") == "active")
    purchased = sum(float(w.get("balance") or 0) for w in wallets if w.get("type") == "purchased" and w.get("status") == "active")
    return {
        "includedMonthly": round(included, 4),
        "purchased": round(purchased, 4),
        "total": round(included + purchased, 4),
        "currencyCode": store.get("currencyCode") or "MUNEA_CREDIT",
    }


def find_credit_wallet(store, wallet_type):
    wallets = store.setdefault("wallets", [])
    for wallet in wallets:
        if wallet.get("type") == wallet_type and wallet.get("status") == "active":
            return wallet
    wallet = normalize_credit_wallet({"type": wallet_type}, wallet_type=wallet_type)
    wallets.append(wallet)
    return wallet


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
    wallet = find_credit_wallet(store, wallet_type)
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


def credits_consume_response(data):
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
    for wallet_type in ("included_monthly", "purchased"):
        wallet = find_credit_wallet(store, wallet_type)
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


def load_billing_store():
    try:
        remote_store = data_backend().load_billing_store()
        if remote_store:
            return normalize_billing_store(remote_store)
    except Exception as e:
        log_fallback_exception("load billing store from Supabase", e)
    return normalize_billing_store(read_json_file(BILLING_STORE_PATH, {}))


def save_billing_store(data):
    store = normalize_billing_store({**data, "updatedAt": utc_now()})
    try:
        remote_store = data_backend().save_billing_store(store)
        if remote_store:
            store = normalize_billing_store(remote_store)
    except Exception as e:
        log_fallback_exception("save billing store to Supabase", e)
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
    base = c["persona"] + eng.RED  # 收斂：記憶單一來源＝memory_items（由 reply_context_instruction 注入），不再疊舊 user_profile 側寫
    return base, c


def reply_conv(history, char=DEFAULT_CHAR, data=None, context=None):
    """帶完整對話脈絡，用該角色的腦＋記憶回話。"""
    base, _ = _sys_for(char)
    context = context or build_reply_context(history, char, data)
    base = base + reply_context_instruction(context)
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
        return "（嗨，我在的，想聊什麼都可以，先跟我說說今天過得怎麼樣？）"
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
    return "（不好意思，我這邊連線有點不順，等一下再陪你好不好？）"


def chat_response(data, char=DEFAULT_CHAR):
    history = data.get("history", [])
    context = build_reply_context(history, char, data)
    t = reply_conv(history, char, data, context)
    return {
        "reply": t,
        "audio": tts_b64(t, char),
        "aiContext": ai_context_summary(context),
    }


def relationship_state_from_turn(data, context, stored_memories):
    data = data or {}
    context = context or {}
    persona = context.get("persona") or {}
    text = conversation_text(data.get("history") or [])
    topic_domains = [
        item.get("domain")
        for item in (context.get("perception") or {}).get("domains", [])
        if item.get("domain")
    ]
    turn_count = len([h for h in (data.get("history") or []) if h.get("role") == "user"])
    sensitive_count = len([m for m in stored_memories if m.get("sensitivity") in {"sensitive", "restricted"}])
    has_emotional_memory = any(m.get("type") == "emotion" for m in stored_memories)
    rapport = "new"
    if turn_count >= 3 or stored_memories:
        rapport = "familiar"
    if turn_count >= 6 or has_emotional_memory:
        rapport = "trusted"
    if turn_count >= 10 and has_emotional_memory:
        rapport = "close"
    return normalize_relationship_state({
        "personId": data.get("personId") or data.get("person_id") or PRIMARY_CARE_RECIPIENT_ID,
        "personaTemplateId": persona.get("templateId") or "nening-real-female",
        "preferredAddress": data.get("preferredAddress") or data.get("preferred_address"),
        "rapportLevel": rapport,
        "toneOverrides": {
            "reduceHumor": sensitive_count > 0 or has_emotional_memory,
            "preferShortResponses": len(text) > 1200,
            "speechFirst": True,
        },
        "userBoundaries": {
            "noRawTranscriptRetention": True,
            "medicalAdviceBoundary": True,
        },
        "relationshipMemory": {
            "lastTopicDomains": topic_domains[:5],
            "lastMeaningfulTurnCount": turn_count,
            "storedMemoryCount": len(stored_memories),
            "lastSafetyLevel": ((context.get("guardian") or {}).get("risk") or {}).get("level", "none"),
            "updatedFrom": "butler_post_turn",
        },
    })


def _post_turn_extract(history, person_id, store=True):
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
    extract = _post_turn_extract(history, person_id, store=(data.get("storeMemory") is not False))
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
        "locale": data.get("locale") or "zh-TW",
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
                "runtime": {"concurrency": "threading", "jsonStoreWrites": "atomic", "authRequired": auth_required_mode()},
                "contracts": ["auth-status", "account-bootstrap", "app-profile", "companion-profile", "persona-context", "entitlements", "credits-balance", "credits-grant", "credits-consume", "voice-session", "avatar-session", "ai-brain-status", "memory-extract", "memory-retrieve", "butler-post-turn", "guardian-evaluate", "perception-topic-plan", "perception-snapshot", "product-event", "admin-north-star", "admin-usage", "admin-credits", "privacy-export", "account-deletion"],
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
            auth_gate = require_verified_auth(self.headers, self.path, data)
            if not auth_gate.get("ok"):
                self._json_error(401, auth_gate.get("code") or "auth_required", "Verified account token is required")
                return
            char = data.get("char") or DEFAULT_CHAR
            if self.path == "/open":
                t = eng.open_chat(char)
                self._json({"reply": t, "audio": tts_b64(t, char)})
            elif self.path == "/chat":
                self._json(chat_response(data, char))
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
            elif self.path == "/persona/context":
                self._json(persona_context_response(data))
            elif self.path == "/memory/extract":
                self._json(memory_extract_response(data))
            elif self.path == "/memory/retrieve":
                self._json(memory_retrieve_response(data))
            elif self.path == "/butler/post-turn":
                self._json(butler_post_turn_response(data))
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
            elif self.path == "/wellbeing/trend":
                self._json(wellbeing_trend_response(data))
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
    try:
        port = int(os.environ.get("MUNEA_PORT") or "8200")
    except ValueError:
        port = 8200
    print(f"沐寧 App 伺服器啟動 → http://localhost:{port}  （Ctrl+C 結束）")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
