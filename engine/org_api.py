# -*- coding: utf-8 -*-
"""機構端專區 `/org/*`（第 2 段 · PR-a · 2026-10-29）。

設計書：docs/後台-B2B2C-產品框架設計-2026-10-28.md。這支檔案就是第 4.2 節選 B 的理由本身——
「機構只能看自家、只能看已同意的長輩、永遠看不到對話內容」這三條鐵線，全部在這一處做對，
不靠 45 支後台接口各自記得過濾。

誰能叫（第 2.3 節權限矩陣）：
  org_admin     機構管理者：整家彙總、已同意長輩名單＋旗標（L1）、週關懷摘要（L2）、月報
  case_manager  社工／個管：同上，但限自己分點；是週關懷摘要的主要使用者（Q4 A）
  care_worker   照服員：自己分點的名單＋旗標（L1）；**不看摘要內文**
  esg 客戶      企業福利：不管什麼角色，永遠只有彙總＋月報（L0）

三條鐵線（第 1.2 節）：
  1. 不含對話內容——這裡連摘要正文都不撈（supabase_adapter.load_org_person_conversation_summaries 只選時間欄位）。
  2. 沒同意的長輩在 L1／L2 查詢裡根本不會被撈出來（_consented_seats 是 inner join，不是撈出來再遮名字）。
  3. 查不到／不屬於你／沒同意一律回同一句 not_found——不讓人用回應差異試探別家有沒有這位。

身分（Q3 B）：Supabase Auth 的登入證（跟 App 同一套），server.py 驗完把 {authUserId, email} 交進來；
這裡對 org_staff 表：先比 auth_user_id，比不到就比邀請 email（第一次登入綁定）。
機構人員沒有 App 帳號，所以**不能**用 server.data_backend()（那是以呼叫者的 account_id 篩的）；
替長輩讀資料一律走 supabase_adapter 裡「帳號＋人都明講」的 load_org_* 方法，或由呼叫端注入 loaders（測試）。

稽核（第 3.2 節）：L2 每次讀寫一筆 org_care_week_read；同意切換寫 org_consent_granted／revoked；開人員寫 org_staff_invited。
第 2 段先走現有 audit_events（server.append_audit_event），第 3 段搬專用表時只換 AUDIT_SINK。
稽核寫不進去時 L2 讀取**不給**（audit_unavailable）——可問責優先於可用。
"""
import datetime as _dt
import json
import logging
import os
import threading
import time
import uuid

import care_week
import enterprise_seats
import org_portal
import supabase_adapter

LOGGER = logging.getLogger("munea.org_api")
HERE = os.path.dirname(os.path.abspath(__file__))
_JSON_LOCK = threading.RLock()

STAFF_PATH = os.environ.get("MUNEA_ORG_STAFF_PATH") or os.path.join(HERE, "org_staff_store.json")
CONSENTS_PATH = os.environ.get("MUNEA_ORG_CONSENTS_PATH") or os.path.join(HERE, "org_care_consents_store.json")
# 本機／測試模式替長輩讀資料時用的本子，跟 server.py 同一份（同一個環境變數、同一個預設檔名）。
WELLBEING_PATH = os.environ.get("MUNEA_WELLBEING_PATH") or os.path.join(HERE, "wellbeing_signals.json")
CONVERSATION_SUMMARIES_PATH = os.environ.get("MUNEA_CONVERSATION_SUMMARIES_PATH") or os.path.join(HERE, "conversation_summaries.json")

ROLES = ("org_admin", "case_manager", "care_worker")
STAFF_STATUSES = ("invited", "active", "disabled")
CONSENT_STATUSES = ("granted", "revoked")
GRANTED_BY_ROLES = ("self", "family")
SEAT_STATUSES_VISIBLE = ("active",)  # 機構端只算正在生效的席次；pending／waiting 還不是人、grace／released 已經不是
L1_DAYS = 7
MAX_ELDERS = 500

# 送出去之前再掃一次：機構端任何回應都不准出現這些鍵（比 org_portal.FORBIDDEN_KEYS 寬一點，
# 因為 L1／L2 本來就要帶「這一位」的事實；但個資欄位、原句、正文、身分鍵一律禁）。
ORG_FORBIDDEN_KEYS = {
    "accountid", "account_id", "personid", "person_id", "authuserid", "auth_user_id", "userid", "user_id",
    "familygroupid", "family_group_id",
    "email", "inviteemail", "invite_email", "contactemail", "contact_email", "contactphone", "contact_phone",
    "phone", "address", "billingaddress", "billing_address", "taxid", "tax_id", "contactname", "contact_name",
    "said", "lastsaid", "last_said", "wordobs", "chatobs", "transcript", "transcripts",
    "summary", "summaries", "content", "utterance", "message", "messages", "conversation", "conversations",
    "memorytags", "memory_tags", "positives", "reporthtml", "report_html", "notes",
}

# 可問責的寫入口：server.py 啟動時設成 append_audit_event；測試可換成自己的收集器。
AUDIT_SINK = None


def set_audit_sink(fn):
    global AUDIT_SINK
    AUDIT_SINK = fn


class OrgPrivacyError(RuntimeError):
    """機構端回應裡混進了不該有的鍵——程式的錯，寧可整支炸掉也不能送出去。"""


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _utc_now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _today():
    try:
        import perception_engine
        return (perception_engine.now_context() or {}).get("date") or None
    except Exception as exc:  # perception_engine 要 GEMINI 設定；拿不到就用本機今天
        LOGGER.debug("org_api today fallback: %s", exc)
        return None


def _backend():
    return supabase_adapter.make_adapter()


def _is_missing_table_error(exc):
    kind = getattr(exc, "error_kind", None)
    if kind in ("missing_table", "configuration", "unreachable"):
        return True
    text = str(exc).lower()
    return "pgrst205" in text or "could not find the table" in text or "does not exist" in text


def _read_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback
    except Exception as exc:
        LOGGER.warning("org_api read %s failed, using fallback: %s", os.path.basename(path), exc)
        return fallback


def _write_json(path, data):
    with _JSON_LOCK:
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}.{int(time.time() * 1000)}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError as exc:
                    LOGGER.warning("org_api remove temp %s failed: %s", os.path.basename(tmp), exc)


def _lower(value):
    return str(value or "").strip().lower()


def _seat_code(seat_id):
    """給機構看的席次代號：id 前 8 碼，看得出是哪一位、但從代號反推不回帳號。"""
    return str(seat_id or "")[:8].upper()


def _not_found():
    return {"ok": False, "error": "not_found"}


def assert_no_forbidden(payload, forbidden=ORG_FORBIDDEN_KEYS, path=""):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).strip().lower() in forbidden:
                raise OrgPrivacyError(f"org response leaked key {path}.{key}")
            assert_no_forbidden(value, forbidden, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_no_forbidden(item, forbidden, f"{path}[{i}]")
    return payload


def _audit(event):
    """寫一筆稽核。回 True／False；呼叫端決定失敗要不要擋（L2 讀取要擋）。"""
    if AUDIT_SINK is None:
        LOGGER.warning("org_api audit sink not configured; event dropped: %s", event.get("eventType"))
        return False
    try:
        AUDIT_SINK(event)
        return True
    except Exception as exc:
        LOGGER.error("org_api audit write failed (%s): %s", event.get("eventType"), exc)
        return False


# ---------------------------------------------------------------------------
# 資料層：org_staff／org_care_consents（Supabase 優先、退本機 JSON）
# ---------------------------------------------------------------------------

def normalize_staff(item=None):
    item = item or {}
    role = item.get("role") or "case_manager"
    status = item.get("status") or "invited"
    return {
        "id": item.get("id") or "",
        "enterpriseClientId": item.get("enterpriseClientId") or item.get("enterprise_client_id") or "",
        "email": _lower(item.get("email")),
        "authUserId": item.get("authUserId") or item.get("auth_user_id"),
        "displayName": str(item.get("displayName") or item.get("display_name") or "").strip()[:80],
        "role": role if role in ROLES else "case_manager",
        "siteLabel": (str(item.get("siteLabel") or item.get("site_label") or "").strip()[:80] or None),
        "status": status if status in STAFF_STATUSES else "invited",
        "invitedBy": item.get("invitedBy") or item.get("invited_by") or "admin",
        "invitedAt": item.get("invitedAt") or item.get("invited_at"),
        "activatedAt": item.get("activatedAt") or item.get("activated_at"),
        "disabledAt": item.get("disabledAt") or item.get("disabled_at"),
        "lastLoginAt": item.get("lastLoginAt") or item.get("last_login_at"),
        "notes": item.get("notes"),
        "createdAt": item.get("createdAt") or item.get("created_at"),
        "updatedAt": item.get("updatedAt") or item.get("updated_at"),
    }


def normalize_consent(item=None):
    item = item or {}
    status = item.get("status") or "granted"
    by_role = item.get("grantedByRole") or item.get("granted_by_role") or "family"
    return {
        "id": item.get("id") or "",
        "enterpriseClientId": item.get("enterpriseClientId") or item.get("enterprise_client_id") or "",
        "seatId": item.get("seatId") or item.get("seat_id") or "",
        "accountId": item.get("accountId") or item.get("account_id") or "",
        "status": status if status in CONSENT_STATUSES else "granted",
        "scope": item.get("scope") or "care_week",
        "grantedByAuthUserId": item.get("grantedByAuthUserId") or item.get("granted_by_auth_user_id"),
        "grantedByRole": by_role if by_role in GRANTED_BY_ROLES else "family",
        "grantedAt": item.get("grantedAt") or item.get("granted_at"),
        "revokedAt": item.get("revokedAt") or item.get("revoked_at"),
        "revokedByAuthUserId": item.get("revokedByAuthUserId") or item.get("revoked_by_auth_user_id"),
        "note": item.get("note"),
        "createdAt": item.get("createdAt") or item.get("created_at"),
        "updatedAt": item.get("updatedAt") or item.get("updated_at"),
    }


def list_staff(client_id=None, auth_user_id=None, email=None, status=None):
    backend = _backend()
    try:
        remote = backend.load_org_staff(client_id=client_id, auth_user_id=auth_user_id, email=email, status=status)
        if remote is not None:
            return [normalize_staff(r) for r in remote]
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        LOGGER.warning("org_api list_staff from Supabase failed; using local: %s", exc)
    items = [normalize_staff(i) for i in (_read_json(STAFF_PATH, []) or []) if isinstance(i, dict)]
    if client_id:
        items = [i for i in items if i["enterpriseClientId"] == client_id]
    if auth_user_id:
        items = [i for i in items if i.get("authUserId") == auth_user_id]
    if email:
        items = [i for i in items if i["email"] == _lower(email)]
    if status:
        items = [i for i in items if i["status"] == status]
    items.sort(key=lambda i: i.get("createdAt") or "")
    return items


def get_staff(staff_id):
    if not staff_id:
        return None
    backend = _backend()
    try:
        remote = backend.get_org_staff(staff_id)
        if remote is not None:
            return normalize_staff(remote)
        if backend.enabled():
            return None
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        LOGGER.warning("org_api get_staff from Supabase failed; using local: %s", exc)
    for item in _read_json(STAFF_PATH, []) or []:
        if isinstance(item, dict) and item.get("id") == staff_id:
            return normalize_staff(item)
    return None


def create_staff(item):
    now = _utc_now()
    record = normalize_staff({**item, "invitedAt": item.get("invitedAt") or now, "createdAt": now, "updatedAt": now})
    backend = _backend()
    try:
        remote = backend.create_org_staff(record)
        if remote is not None:
            return normalize_staff(remote)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        LOGGER.warning("org_api create_staff to Supabase failed; using local: %s", exc)
    record["id"] = record["id"] or str(uuid.uuid4())
    with _JSON_LOCK:
        items = [i for i in (_read_json(STAFF_PATH, []) or []) if isinstance(i, dict)]
        items.append(record)
        _write_json(STAFF_PATH, items)
    return record


def update_staff(staff_id, patch):
    """patch 用 camelCase（authUserId／status／activatedAt／lastLoginAt／disabledAt）。"""
    snake = {
        "authUserId": "auth_user_id", "status": "status", "activatedAt": "activated_at",
        "lastLoginAt": "last_login_at", "disabledAt": "disabled_at", "role": "role",
        "siteLabel": "site_label", "displayName": "display_name",
    }
    remote_patch = {snake[k]: v for k, v in (patch or {}).items() if k in snake}
    backend = _backend()
    try:
        remote = backend.update_org_staff(staff_id, remote_patch)
        if remote is not None:
            return normalize_staff(remote)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        LOGGER.warning("org_api update_staff to Supabase failed; using local: %s", exc)
    with _JSON_LOCK:
        items = [i for i in (_read_json(STAFF_PATH, []) or []) if isinstance(i, dict)]
        updated = None
        for item in items:
            if item.get("id") == staff_id:
                item.update({k: v for k, v in (patch or {}).items() if k in snake})
                item["updatedAt"] = _utc_now()
                updated = normalize_staff(item)
        if updated is not None:
            _write_json(STAFF_PATH, items)
        return updated


def list_consents(client_id=None, seat_id=None, account_id=None, status=None):
    backend = _backend()
    try:
        remote = backend.load_org_care_consents(client_id=client_id, seat_id=seat_id, account_id=account_id, status=status)
        if remote is not None:
            return [normalize_consent(r) for r in remote]
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        LOGGER.warning("org_api list_consents from Supabase failed; using local: %s", exc)
    items = [normalize_consent(i) for i in (_read_json(CONSENTS_PATH, []) or []) if isinstance(i, dict)]
    if client_id:
        items = [i for i in items if i["enterpriseClientId"] == client_id]
    if seat_id:
        items = [i for i in items if i["seatId"] == seat_id]
    if account_id:
        items = [i for i in items if i["accountId"] == account_id]
    if status:
        items = [i for i in items if i["status"] == status]
    return items


def save_consent(item):
    """一個席次一列（upsert by seatId）。"""
    now = _utc_now()
    record = normalize_consent({**item, "updatedAt": now})
    backend = _backend()
    try:
        remote = backend.upsert_org_care_consent(record)
        if remote is not None:
            return normalize_consent(remote)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        LOGGER.warning("org_api save_consent to Supabase failed; using local: %s", exc)
    with _JSON_LOCK:
        items = [i for i in (_read_json(CONSENTS_PATH, []) or []) if isinstance(i, dict)]
        for i, existing in enumerate(items):
            if existing.get("seatId") == record["seatId"]:
                record["id"] = existing.get("id") or record["id"]
                record["createdAt"] = existing.get("createdAt") or now
                items[i] = record
                break
        else:
            record["id"] = record["id"] or str(uuid.uuid4())
            record["createdAt"] = now
            items.append(record)
        _write_json(CONSENTS_PATH, items)
    return record


def granted_seat_ids(client_id):
    return {c["seatId"] for c in list_consents(client_id=client_id, status="granted") if c.get("seatId")}


# ---------------------------------------------------------------------------
# 身分：登入證 → org_staff
# ---------------------------------------------------------------------------

def resolve_staff(auth):
    """auth = server 驗完的 {authUserId, email}。回 staff 或 None（None 一律當 not_found）。

    第一次登入：auth_user_id 還沒綁，用邀請 email 對上後綁起來、狀態 invited → active。
    停用的人就算 email 對得上也不給（disabled 是硬停）。
    """
    auth = auth or {}
    auth_user_id = str(auth.get("authUserId") or "").strip()
    email = _lower(auth.get("email"))
    if not auth_user_id:
        return None
    staff = None
    for cand in list_staff(auth_user_id=auth_user_id):
        if cand["status"] == "active":
            staff = cand
            break
        if cand["status"] == "disabled":
            return None
    if staff is None and email:
        for cand in list_staff(email=email):
            if cand["status"] == "disabled":
                return None
            if cand["status"] == "invited" and not cand.get("authUserId"):
                staff = update_staff(cand["id"], {"authUserId": auth_user_id, "status": "active", "activatedAt": _utc_now()}) or cand
                _audit({
                    "eventType": "org_staff_activated", "actorUserId": auth_user_id,
                    "targetTable": "org_staff", "targetId": staff.get("id"),
                    "details": {"clientId": staff.get("enterpriseClientId"), "role": staff.get("role"), "actorType": "org_staff"},
                })
                break
    if staff is None:
        return None
    try:
        update_staff(staff["id"], {"lastLoginAt": _utc_now()})
    except Exception as exc:  # 最後登入時間只是方便營運看，寫不進去不該擋人
        LOGGER.warning("org_api lastLoginAt update failed: %s", exc)
    return staff


def _client_kind(client):
    kind = (client or {}).get("clientKind") or "care"
    return kind if kind in enterprise_seats.CLIENT_KINDS else "care"


def capabilities_for(staff, client):
    """角色 × 客戶類型 → 做得到什麼（第 2.3 節矩陣，第 2 段只開讀的部分）。"""
    role = (staff or {}).get("role") or "case_manager"
    esg = _client_kind(client) == "esg"
    site_scoped = role != "org_admin"
    return {
        "summary": True,
        "elders": (not esg) and role in ("org_admin", "case_manager", "care_worker"),
        "careWeek": (not esg) and role in ("org_admin", "case_manager"),
        "reports": role in ("org_admin", "case_manager"),
        "siteScoped": site_scoped,
        "siteLabel": (staff or {}).get("siteLabel") if site_scoped else None,
        "level": "L0" if esg else ("L2" if role in ("org_admin", "case_manager") else "L1"),
    }


def _visible_seats(staff, client):
    """這位人員看得到的席次：這家、生效中、（非管理者）限自己分點。沒標分點的人員＝整家。"""
    seats = enterprise_seats.list_seats(client_id=client["id"])
    seats = [s for s in seats if s.get("status") in SEAT_STATUSES_VISIBLE]
    caps = capabilities_for(staff, client)
    if caps["siteScoped"] and caps["siteLabel"]:
        seats = [s for s in seats if (s.get("siteLabel") or None) == caps["siteLabel"]]
    return seats


def _consented_seats(staff, client):
    """鐵線 2：只拿已同意的席次。這裡是 inner join，不是撈出來再遮。"""
    if _client_kind(client) == "esg":
        return []
    granted = granted_seat_ids(client["id"])
    return [s for s in _visible_seats(staff, client) if s.get("id") in granted and s.get("accountId")]


def _staff_and_client(auth):
    staff = resolve_staff(auth)
    if not staff:
        return None, None
    client = enterprise_seats.get_client(staff["enterpriseClientId"])
    if not client or client.get("status") == "ended":
        return None, None
    return staff, client


def _public_staff(staff):
    return {
        "id": staff["id"], "displayName": staff["displayName"], "role": staff["role"],
        "siteLabel": staff.get("siteLabel"), "status": staff["status"],
    }


def _public_org(client):
    return {
        "id": client["id"], "name": client.get("name") or "", "clientKind": _client_kind(client),
        "planTier": client.get("planTier") or "", "contractEnd": client.get("contractEnd"),
    }


# ---------------------------------------------------------------------------
# 替長輩讀資料（loaders 可注入；預設走 supabase_adapter 的明講版，退本機本子）
# ---------------------------------------------------------------------------

def default_loaders():
    backend = _backend()

    def persons(account_ids):
        try:
            remote = backend.load_org_primary_persons(account_ids)
            if remote is not None:
                return remote
        except Exception as exc:
            if backend.enabled() and not _is_missing_table_error(exc):
                raise
            LOGGER.warning("org_api persons from Supabase failed; local has no persons table: %s", exc)
        return {}

    def signals(account_id, person_id):
        try:
            remote = backend.load_org_person_wellbeing_signals(account_id, person_id)
            if remote is not None:
                return remote
        except Exception as exc:
            if backend.enabled() and not _is_missing_table_error(exc):
                raise
            LOGGER.warning("org_api signals from Supabase failed; using local: %s", exc)
        rows = _read_json(WELLBEING_PATH, []) or []
        return [s for s in rows if isinstance(s, dict) and str(s.get("personId") or "") == str(person_id)]

    def summaries(account_id, person_id):
        try:
            remote = backend.load_org_person_conversation_summaries(account_id, person_id)
            if remote is not None:
                return remote
        except Exception as exc:
            if backend.enabled() and not _is_missing_table_error(exc):
                raise
            LOGGER.warning("org_api summaries from Supabase failed; using local: %s", exc)
        rows = _read_json(CONVERSATION_SUMMARIES_PATH, []) or []
        if isinstance(rows, dict):
            rows = rows.get("summaries") or rows.get("items") or []
        return [
            {"id": s.get("id"), "personId": s.get("personId"), "summary": "", "createdAt": s.get("createdAt"), "deletedAt": s.get("deletedAt")}
            for s in rows if isinstance(s, dict) and str(s.get("personId") or "") == str(person_id)
        ]

    def guardian_events(account_ids, since_iso):
        activity = org_portal.load_cohort_activity(account_ids, since_iso, since_iso[:10], backend=backend)
        out = []
        for ev in activity.get("productEvents") or []:
            if not isinstance(ev, dict) or ev.get("eventName") != "guardian_risk_evaluated":
                continue
            props = ev.get("properties") or {}
            out.append({
                "accountId": ev.get("accountId") or ev.get("account_id"),
                "personId": ev.get("personId") or ev.get("person_id"),
                "eventTime": ev.get("eventTime") or ev.get("createdAt"),
                "riskLevel": props.get("riskLevel") or props.get("risk_level"),
                "categories": props.get("categories") or [],
            })
        return out

    return {"persons": persons, "signals": signals, "summaries": summaries, "guardianEvents": guardian_events}


def _elder_label(person_info, seat, consent_granted):
    """稱呼只在已同意時顯示（經同意）；沒有稱呼就用席次代號。"""
    if consent_granted and person_info:
        label = person_info.get("nickname") or person_info.get("profileName") or ""
        if label:
            return str(label).strip()[:40]
    return f"席次 {_seat_code(seat.get('id'))}"


def _build_week(person_id, account_id, loaders, events_for_person, today, days):
    partial = []
    signals, summaries = [], []
    try:
        signals = [s for s in (loaders["signals"](account_id, person_id) or []) if isinstance(s, dict)]
    except Exception as exc:
        LOGGER.warning("org_api load signals failed: %s", exc)
        partial.append("mood")
    try:
        summaries = [s for s in (loaders["summaries"](account_id, person_id) or []) if isinstance(s, dict)]
    except Exception as exc:
        LOGGER.warning("org_api load summaries failed: %s", exc)
        partial.append("contact")
    week = care_week.build_person_week({"id": person_id}, signals, summaries, events_for_person, today=today, days=days)
    week["partial"] = partial
    return week


def _strip_week_for_org(week):
    """L2 給機構的版本：留趨勢與類別、拿掉原句與正文（設計書 4.3「不回什麼」）。"""
    mood = week.get("mood") or {}
    daily = [{"date": d.get("date"), "level": d.get("level"), "chats": d.get("chats")} for d in mood.get("daily") or []]
    lowest = mood.get("lowestDay") or None
    contact = week.get("contact") or {}
    safety = week.get("safety") or {}
    return {
        "period": week.get("period"),
        "contact": {
            "source": contact.get("source"), "calls": contact.get("calls"), "daysWithCall": contact.get("daysWithCall"),
            "longestGapDays": contact.get("longestGapDays"), "lastCallDate": contact.get("lastCallDate"),
            "daysSinceLastCall": contact.get("daysSinceLastCall"), "empty": contact.get("empty"),
        },
        "moodTrend": {
            "source": mood.get("source"), "daysWithChat": mood.get("daysWithChat"), "daily": daily,
            "weekAverage": mood.get("weekAverage"), "baselineAverage": mood.get("baselineAverage"),
            "baselineDays": mood.get("baselineDays"),
            "lowestDay": {"date": lowest.get("date"), "level": lowest.get("level")} if lowest else None,
            "empty": mood.get("empty"),
        },
        "spokenHealth": {
            "source": "本人口述的症狀類別（由記憶層萃取的短語；不是原句、不是臨床事實）",
            "categories": list((week.get("spokenHealth") or {}).get("items") or [])[:10],
            "empty": (week.get("spokenHealth") or {}).get("empty", True),
        },
        "safety": {
            "source": safety.get("source"), "counts": safety.get("counts") or {},
            "highOrCritical": safety.get("highOrCritical") or 0, "empty": safety.get("empty", True),
        },
        "honesty": week.get("honesty"),
        "partial": week.get("partial") or [],
    }


def _strip_anomalies(anomalies):
    return [{"type": a.get("type"), "when": a.get("when"), "fact": a.get("fact"), "suggestion": a.get("suggestion")}
            for a in anomalies or []]


# ---------------------------------------------------------------------------
# /org/* 回應
# ---------------------------------------------------------------------------

def org_me_response(auth, data=None):
    staff, client = _staff_and_client(auth)
    if not staff:
        return _not_found()
    return {"ok": True, "staff": _public_staff(staff), "org": _public_org(client), "capabilities": capabilities_for(staff, client)}


def org_summary_response(auth, data=None):
    staff, client = _staff_and_client(auth)
    if not staff:
        return _not_found()
    caps = capabilities_for(staff, client)
    seats = _visible_seats(staff, client)
    try:
        summary = org_portal.build_portal_summary(client["id"], seats=seats, client=client)
    except org_portal.PortalTokenError as exc:
        LOGGER.warning("org_api summary build failed: %s", exc.code)
        return _not_found()
    summary["scope"] = {"siteLabel": caps["siteLabel"], "siteScoped": caps["siteScoped"]}
    summary["consent"] = {"grantedSeats": len([s for s in seats if s.get("id") in granted_seat_ids(client["id"])])} if caps["elders"] else None
    return assert_no_forbidden({"ok": True, **summary}, org_portal.FORBIDDEN_KEYS | {"email", "phone"})


def org_elders_response(auth, data=None, loaders=None):
    """L1：已同意長輩的名單＋三個旗標。沒同意的根本不在清單裡。"""
    data = data or {}
    staff, client = _staff_and_client(auth)
    if not staff:
        return _not_found()
    caps = capabilities_for(staff, client)
    if not caps["elders"]:
        return _not_found()
    loaders = loaders or default_loaders()
    seats = _consented_seats(staff, client)[:MAX_ELDERS]
    account_ids = [s["accountId"] for s in seats]
    today = _today()
    start, end = care_week.period_bounds(L1_DAYS, today)
    since_iso = (start - _dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    partial = []
    try:
        persons = loaders["persons"](account_ids) or {}
    except Exception as exc:
        LOGGER.warning("org_api persons lookup failed: %s", exc)
        persons, partial = {}, partial + ["persons"]
    try:
        events = loaders["guardianEvents"](account_ids, since_iso) or []
    except Exception as exc:
        LOGGER.warning("org_api guardian events failed: %s", exc)
        events, partial = [], partial + ["safety"]
    settings = {}
    try:
        if data.get("noContactDays") is not None:
            settings["noContactDays"] = max(1, min(30, int(data.get("noContactDays"))))
    except (TypeError, ValueError) as exc:
        LOGGER.warning("org_api bad noContactDays ignored: %s", exc)

    elders = []
    for seat in seats:
        account_id = seat["accountId"]
        info = persons.get(account_id) or {}
        person_id = info.get("personId")
        flags = {"noInteractionToday": None, "lowMood": False, "guardianLit": False}
        last_date, anomaly_types, week_partial = None, [], []
        if person_id:
            ev_for = [e for e in events if str(e.get("personId") or "") == str(person_id) or
                      (not e.get("personId") and str(e.get("accountId") or "") == str(account_id))]
            week = _build_week(person_id, account_id, loaders, ev_for, today, L1_DAYS)
            anomalies = care_week.detect_anomalies(week, settings)
            anomaly_types = sorted({a["type"] for a in anomalies})
            last_date = week["contact"].get("lastCallDate")
            flags = {
                "noInteractionToday": last_date != end.isoformat(),
                "lowMood": "mood_drop" in anomaly_types,
                "guardianLit": (week["safety"].get("highOrCritical") or 0) > 0,
            }
            week_partial = week.get("partial") or []
        else:
            week_partial = ["person"]
        elders.append({
            "seatId": seat["id"], "seatCode": _seat_code(seat["id"]), "label": _elder_label(info, seat, True),
            "siteLabel": seat.get("siteLabel"), "flags": flags, "anomalyTypes": anomaly_types,
            "lastInteractionDate": last_date, "partial": week_partial,
        })
    # 旗標多的排前面（今天該先聯繫誰），同樣多的照稱呼排。
    elders.sort(key=lambda e: (-sum(1 for v in e["flags"].values() if v), e["label"]))
    payload = {
        "ok": True, "period": {"start": start.isoformat(), "end": end.isoformat(), "days": L1_DAYS},
        "scope": {"siteLabel": caps["siteLabel"], "siteScoped": caps["siteScoped"], "level": caps["level"]},
        "count": len(elders), "elders": elders, "partial": partial,
        "privacy": {"statement": "只列出長輩或家人已同意「機構照護模式」的人；沒同意的不會出現在這裡。沒有對話內容。"},
    }
    return assert_no_forbidden(payload)


def org_elder_care_week_response(auth, data=None, loaders=None):
    """L2：某位已同意長輩的週關懷摘要（機構版）。每次讀寫一筆稽核，寫不進去就不給。"""
    data = data or {}
    staff, client = _staff_and_client(auth)
    if not staff:
        return _not_found()
    caps = capabilities_for(staff, client)
    if not caps["careWeek"]:
        return _not_found()
    seat_id = str(data.get("seatId") or data.get("seat_id") or "").strip()
    if not seat_id:
        return _not_found()
    seat = next((s for s in _consented_seats(staff, client) if s.get("id") == seat_id), None)
    if not seat:
        return _not_found()
    loaders = loaders or default_loaders()
    try:
        days = max(1, min(31, int(data.get("days") or care_week.DEFAULT_DAYS)))
    except (TypeError, ValueError):
        days = care_week.DEFAULT_DAYS
    settings = {}
    try:
        if data.get("noContactDays") is not None:
            settings["noContactDays"] = max(1, min(30, int(data.get("noContactDays"))))
    except (TypeError, ValueError) as exc:
        LOGGER.warning("org_api bad noContactDays ignored: %s", exc)
    account_id = seat["accountId"]
    today = _today()
    start, end = care_week.period_bounds(days, today)
    since_iso = (start - _dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    partial = []
    try:
        info = (loaders["persons"]([account_id]) or {}).get(account_id) or {}
    except Exception as exc:
        LOGGER.warning("org_api person lookup failed: %s", exc)
        info, partial = {}, ["persons"]
    person_id = info.get("personId")
    if not person_id:
        return {"ok": True, "seatId": seat_id, "seatCode": _seat_code(seat_id), "label": _elder_label(info, seat, True),
                "siteLabel": seat.get("siteLabel"), "week": None, "anomalies": [], "partial": partial + ["person"],
                "privacy": {"statement": "這個席次還沒綁到長輩本人，沒有可讀的紀錄。"}}
    try:
        events = [e for e in (loaders["guardianEvents"]([account_id], since_iso) or [])
                  if str(e.get("personId") or "") == str(person_id) or
                  (not e.get("personId") and str(e.get("accountId") or "") == str(account_id))]
    except Exception as exc:
        LOGGER.warning("org_api guardian events failed: %s", exc)
        events, partial = [], partial + ["safety"]
    audited = _audit({
        "eventType": "org_care_week_read", "actorUserId": staff.get("authUserId"), "accountId": account_id,
        "targetTable": "enterprise_seats", "targetId": seat_id,
        "details": {"actorType": "org_staff", "staffId": staff["id"], "role": staff["role"], "clientId": client["id"],
                    "siteLabel": seat.get("siteLabel"), "periodStart": start.isoformat(), "periodEnd": end.isoformat()},
    })
    if not audited:
        return {"ok": False, "error": "audit_unavailable"}
    week = _build_week(person_id, account_id, loaders, events, today, days)
    anomalies = care_week.detect_anomalies(week, settings)
    payload = {
        "ok": True, "seatId": seat_id, "seatCode": _seat_code(seat_id), "label": _elder_label(info, seat, True),
        "siteLabel": seat.get("siteLabel"), "week": _strip_week_for_org(week), "anomalies": _strip_anomalies(anomalies),
        "partial": partial + (week.get("partial") or []),
        "privacy": {"statement": "這一頁是事實排列不是判定；沒有對話內容、沒有原句。這次查看已留下紀錄（誰、何時、看了誰）。"},
    }
    return assert_no_forbidden(payload)


def org_reports_response(auth, data=None):
    """月報清單＋一張 1 天效期的下載憑證（沿用 GET /enterprise/portal/report?t=&id=）。"""
    staff, client = _staff_and_client(auth)
    if not staff:
        return _not_found()
    if not capabilities_for(staff, client)["reports"]:
        return _not_found()
    reports = org_portal.build_reports_section(org_portal._load_reports(client["id"]))
    token = None
    try:
        token = org_portal.issue_portal_token(client["id"], ttl_days=1)
    except org_portal.PortalTokenError as exc:
        LOGGER.warning("org_api report token not issued: %s", exc.code)
    return assert_no_forbidden({"ok": True, "reports": reports, "downloadToken": token,
                                "downloadPath": "/enterprise/portal/report" if token else None})


# ---------------------------------------------------------------------------
# App 端（家庭成員）：機構照護模式同意
# ---------------------------------------------------------------------------

def _consent_view(seat, client, consent):
    return {
        "seatId": seat["id"], "seatCode": _seat_code(seat["id"]), "seatStatus": seat.get("status"),
        "siteLabel": seat.get("siteLabel"),
        "org": {"id": client.get("id"), "name": client.get("name") or "", "clientKind": _client_kind(client)},
        "consent": {
            "status": (consent or {}).get("status") or "none",
            "grantedAt": (consent or {}).get("grantedAt"), "revokedAt": (consent or {}).get("revokedAt"),
            "grantedByRole": (consent or {}).get("grantedByRole") if consent else None,
        },
        "whatOrgSees": ["整家彙總", "名單與三個旗標（今天沒互動／心情低落／守護亮燈）", "週關懷摘要（通話次數、心情走勢、症狀類別、亮燈次數）"],
        "whatOrgNeverSees": ["對話內容", "心情與口述的原句", "用藥明細", "家人帶話"],
    }


def org_consent_status_response(identity, data=None):
    identity = identity or {}
    account_id = identity.get("accountId")
    if not account_id:
        return {"ok": False, "error": "identity_required"}
    seats = [s for s in enterprise_seats.list_seats(account_id=account_id) if s.get("status") in ("active", "waiting", "grace")]
    consents = {c["seatId"]: c for c in list_consents(account_id=account_id)}
    items = []
    for seat in seats:
        client = enterprise_seats.get_client(seat.get("enterpriseClientId"))
        if not client:
            continue
        items.append(_consent_view(seat, client, consents.get(seat["id"])))
    return {"ok": True, "count": len(items), "seats": items}


def org_consent_set_response(identity, data=None):
    data = data or {}
    identity = identity or {}
    account_id = identity.get("accountId")
    if not account_id:
        return {"ok": False, "error": "identity_required"}
    seat_id = str(data.get("seatId") or data.get("seat_id") or "").strip()
    if not seat_id:
        return {"ok": False, "error": "seat_id_required"}
    seat = enterprise_seats.get_seat(seat_id)
    if not seat or str(seat.get("accountId") or "") != str(account_id):
        return _not_found()
    client = enterprise_seats.get_client(seat.get("enterpriseClientId"))
    if not client:
        return _not_found()
    granted = data.get("granted")
    if isinstance(granted, str):
        granted = granted.strip().lower() in ("1", "true", "yes", "on")
    if granted is None:
        return {"ok": False, "error": "granted_required"}
    by_role = "self" if identity.get("personId") and str(data.get("asRole") or "") == "self" else "family"
    existing = next(iter(list_consents(seat_id=seat_id)), None)
    now = _utc_now()
    if granted:
        record = save_consent({
            **(existing or {}), "enterpriseClientId": client["id"], "seatId": seat_id, "accountId": account_id,
            "status": "granted", "grantedByAuthUserId": identity.get("authUserId"), "grantedByRole": by_role,
            "grantedAt": now, "revokedAt": None, "revokedByAuthUserId": None, "note": str(data.get("note") or "")[:200] or None,
        })
    else:
        if not existing:
            return {"ok": True, "changed": False, "seat": _consent_view(seat, client, None)}
        record = save_consent({**existing, "status": "revoked", "revokedAt": now, "revokedByAuthUserId": identity.get("authUserId")})
    _audit({
        "eventType": "org_consent_granted" if granted else "org_consent_revoked",
        "actorUserId": identity.get("authUserId"), "accountId": account_id,
        "targetTable": "org_care_consents", "targetId": record.get("id"),
        "details": {"actorType": "family" if by_role == "family" else "self", "clientId": client["id"], "seatId": seat_id},
    })
    return {"ok": True, "changed": True, "seat": _consent_view(seat, client, record)}


# ---------------------------------------------------------------------------
# 營運後台（要萬能鑰匙；server.py 的 /admin/enterprise/* 路由已先驗 admin_authorized）
# ---------------------------------------------------------------------------

def admin_org_staff_invite_response(data=None, actor="admin"):
    """幫機構開第一個（或任何一個）人員帳號。之後機構管理者自己開其他人是第 3 段的事。"""
    data = data or {}
    client_id = str(data.get("clientId") or data.get("client_id") or "").strip()
    email = _lower(data.get("email"))
    role = str(data.get("role") or "org_admin").strip()
    if not client_id:
        return {"ok": False, "error": "client_id_required"}
    if not email or "@" not in email or len(email) > 200:
        return {"ok": False, "error": "email_invalid"}
    if role not in ROLES:
        return {"ok": False, "error": "role_invalid", "allowed": list(ROLES)}
    client = enterprise_seats.get_client(client_id)
    if not client:
        return {"ok": False, "error": "client_not_found"}
    if any(s["email"] == email and s["status"] != "disabled" for s in list_staff(client_id=client_id)):
        return {"ok": False, "error": "staff_exists"}
    staff = create_staff({
        "enterpriseClientId": client_id, "email": email,
        "displayName": str(data.get("displayName") or data.get("display_name") or "").strip()[:80],
        "role": role, "siteLabel": data.get("siteLabel") or data.get("site_label"),
        "status": "invited", "invitedBy": str(actor or "admin")[:80], "notes": str(data.get("notes") or "")[:200] or None,
    })
    _audit({
        "eventType": "org_staff_invited", "actorUserId": None, "targetTable": "org_staff", "targetId": staff.get("id"),
        "details": {"actorType": "admin", "clientId": client_id, "role": role, "siteLabel": staff.get("siteLabel")},
    })
    return {"ok": True, "staff": staff, "howToSignIn": "請這位人員用邀請信箱對應的 Google 或 Apple 帳號登入機構專區；第一次登入時會自動對上。"}


def admin_org_consent_status_response(data=None):
    """營運要知道「為什麼某位長輩沒出現在機構名單」：逐席次列同意狀態。"""
    data = data or {}
    client_id = str(data.get("clientId") or data.get("client_id") or "").strip()
    if not client_id:
        return {"ok": False, "error": "client_id_required"}
    client = enterprise_seats.get_client(client_id)
    if not client:
        return {"ok": False, "error": "client_not_found"}
    consents = {c["seatId"]: c for c in list_consents(client_id=client_id)}
    seats = enterprise_seats.list_seats(client_id=client_id)
    rows, counts = [], {"granted": 0, "revoked": 0, "none": 0}
    for seat in seats:
        consent = consents.get(seat["id"])
        status = consent["status"] if consent else "none"
        counts[status] = counts.get(status, 0) + 1
        rows.append({
            "seatId": seat["id"], "seatCode": _seat_code(seat["id"]), "inviteEmail": seat.get("inviteEmail"),
            "seatStatus": seat.get("status"), "siteLabel": seat.get("siteLabel"), "accountBound": bool(seat.get("accountId")),
            "consent": {
                "status": status, "grantedAt": (consent or {}).get("grantedAt"), "revokedAt": (consent or {}).get("revokedAt"),
                "grantedByRole": (consent or {}).get("grantedByRole") if consent else None,
            },
        })
    staff = [{"id": s["id"], "email": s["email"], "displayName": s["displayName"], "role": s["role"],
              "siteLabel": s.get("siteLabel"), "status": s["status"], "lastLoginAt": s.get("lastLoginAt")}
             for s in list_staff(client_id=client_id)]
    return {"ok": True, "clientId": client_id, "clientName": client.get("name") or "", "clientKind": _client_kind(client),
            "counts": counts, "seats": rows, "staff": staff}
