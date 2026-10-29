# -*- coding: utf-8 -*-
"""企業窗口專區（C1 查核點 P0-5：組織窗口只讀彙總）。

需求單 C1 · P0-5 要求「本公司管理員 vs 組織窗口只讀彙總；組織窗口看不到管理功能」。

為什麼不做帳號密碼：機構窗口（長照中心的主任、企業的人資）不會為了看一個月報去記一組
密碼，而多一組密碼就多一個外洩面。改成「管理員產生一條有簽章、會過期的專屬連結」，
窗口點連結就看得到自己組織的彙總——業界報表分享的常見做法。

三條不可退讓的界線（照需求單第三節「資料界線」）：
  1. 窗口只看得到「自己那一家」——組織代號寫在簽章裡，改一個字簽章就對不上
  2. 只給匿名彙總數字，任何個別長輩的姓名、對話、健康明細都不出現（build_portal_summary
     的輸出經 assert_no_personal_data 把關，違反就丟例外，不是靜靜回一包髒資料）
  3. 沒有任何管理動作——這支模組整支沒有寫入資料的函式

2026-10-26 擴充（B2B2C 評估拍板方案 C）：從「只有席次數字」加到 HR／機構窗口真的用得上的
月度彙總——使用狀況、守護件數、月報下載。新加的每一個數字都還是「整家加總」，而且：
  · 全部只算「這家席次 active 綁定的 account_id」那一群人，別家的一筆都不碰
  · 啟用人數不到 5 人的機構，比率類欄位一律回 null＋smallSampleSuppressed=true——
    兩個人裡「50% 有互動」等於直接點名；守護件數同樣壓下（一個人的機構「1 件高風險」
    就是在講他），只留使用人數這種合約層本來就知道的數字
  · 守護這一區只有「件數」：不給內容、不給分類、不給是哪一戶、不給時間點
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

import enterprise_seats
import supabase_adapter

LOGGER = logging.getLogger("munea.org_portal")
HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_TTL_DAYS = 30
MAX_TTL_DAYS = 180
TOKEN_VERSION = "v1"

# 彙總視窗：近 30 天（含今天）＋再往前 30 天當「上一期」算留存。
# 用滾動 30 天、不用「本月 1 號到今天」——月初一兩天的數字會小到沒意義，而且留存的
# 分母（上一期有互動的人）也要一樣長才公平。
PERIOD_DAYS = 30
# 小樣本門檻，跟 enterprise_billing.PRIVACY_MIN_GROUP_SIZE 同一個數字（需求單 4.4 第 3 條）。
MIN_GROUP_SIZE = 5

# 守護腦事件裡算「高風險」的等級（跟 care_week.HIGH_LEVELS 同一組）。
HIGH_RISK_LEVELS = {"high", "critical", "crisis"}
# 這幾個事件是系統自己跑出來的，不代表長輩「有來用」——算互動時要剔掉。
NON_INTERACTION_EVENT_NAMES = {
    "guardian_risk_evaluated",
    "voice_call_diagnostic",
    "companion_summary_created",
}

# 本機（沒接 Supabase）備援檔：跟 engine/server.py 用同一個環境變數／同一個預設檔名，
# 不 import server（那支一萬行、而且開機就要 GEMINI 鑰匙）——只是讀同一份檔。
PRODUCT_EVENTS_PATH = os.environ.get("MUNEA_PRODUCT_EVENTS_PATH") or os.path.join(HERE, "product_events.json")
MEDICATION_DOSES_PATH = os.environ.get("MUNEA_MEDICATION_DOSES_PATH") or os.path.join(HERE, "medication_doses.json")

# 彙總裡「絕對不准出現」的欄位名。多一層保險：就算未來有人手滑把席次明細塞進來，
# 也會在回應送出前炸掉，而不是安靜地把長輩個資送給機構。
#
# 注意這裡故意不擋通用的 "name"——機構自己的名稱（org.name）本來就要顯示給窗口看，
# 那是公司資訊不是個資。要擋的是「指向某一個人」的欄位。
FORBIDDEN_KEYS = {
    "accountid", "account_id", "accountids", "account_ids",
    "personid", "person_id", "personids", "person_ids",
    "familygroupid", "family_group_id", "authuserid", "auth_user_id", "userid", "user_id",
    "email", "inviteemail", "invite_email",
    "contactemail", "contact_email", "contactname", "contact_name",
    "phone", "contactphone", "contact_phone",
    "displayname", "display_name", "username", "user_name",
    "eldername", "elder_name", "personname", "person_name", "birthday",
    "transcript", "transcripts", "conversation", "conversations", "message", "messages",
    "summary", "summaries", "content", "text", "utterance",
    "healthdata", "health_data", "vitals",
    "mood", "moods", "medication", "medications", "medicationname", "medication_name",
    "note", "notes",
    # 守護事件的分類／時間點會縮小到「是誰」——窗口只能拿到件數
    "categories", "category", "risklevel", "risk_level", "eventtime", "event_time",
    # 月報本體不走彙總回應（走憑證驗過的下載路由），彙總裡只准有清單
    "reporthtml", "report_html", "reportdata", "report_data",
    "properties", "metadata", "rows", "events", "items", "people", "persons", "recent",
}


class PortalTokenError(RuntimeError):
    """憑證不能用。code 給呼叫端判斷要回什麼訊息，不要把細節透給前端。"""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class PortalPrivacyError(RuntimeError):
    """彙總裡混進了個資——這是程式的錯，寧可 500 也不能送出去。"""


def _utc_now():
    return datetime.now(timezone.utc)


def _secret():
    value = str(os.environ.get("MUNEA_ORG_PORTAL_SECRET") or "").strip()
    # 沒設鑰匙就明講「沒設定」，不要自己編一把預設的——預設鑰匙等於沒有鑰匙。
    if not value:
        raise PortalTokenError("portal_secret_not_configured")
    return value.encode("utf-8")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str) -> str:
    return _b64e(hmac.new(_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest())


def issue_portal_token(client_id, ttl_days=DEFAULT_TTL_DAYS, issued_at=None):
    """簽一張「只能看這家、只能看到這天」的憑證。"""
    client_id = str(client_id or "").strip()
    if not client_id:
        raise PortalTokenError("client_id_required")
    # 不可以寫 `ttl_days or DEFAULT`——那會把「0 天」當成沒填、悄悄變成 30 天，
    # 等於有人想發一張立刻失效的憑證，卻拿到一張能用一個月的。
    try:
        ttl_days = DEFAULT_TTL_DAYS if ttl_days is None else int(ttl_days)
    except (TypeError, ValueError):
        raise PortalTokenError("invalid_ttl")
    if ttl_days < 1 or ttl_days > MAX_TTL_DAYS:
        raise PortalTokenError("invalid_ttl")

    now = issued_at or _utc_now()
    payload = {
        "v": TOKEN_VERSION,
        "cid": client_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl_days)).timestamp()),
    }
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_portal_token(token, now=None):
    """驗憑證，回組織代號。任何一關不過都丟 PortalTokenError。"""
    text = str(token or "").strip()
    if not text or text.count(".") != 1:
        raise PortalTokenError("invalid_token")
    payload_b64, signature = text.split(".", 1)

    # 先比簽章再解內容：內容是攻擊者可控的，沒驗過就不要拿來用。
    expected = _sign(payload_b64)
    if not hmac.compare_digest(signature, expected):
        raise PortalTokenError("invalid_token")

    try:
        payload = json.loads(_b64d(payload_b64).decode("utf-8"))
    except Exception:
        raise PortalTokenError("invalid_token")

    if payload.get("v") != TOKEN_VERSION:
        raise PortalTokenError("invalid_token")
    client_id = str(payload.get("cid") or "").strip()
    if not client_id:
        raise PortalTokenError("invalid_token")

    moment = int((now or _utc_now()).timestamp())
    try:
        expires_at = int(payload.get("exp") or 0)
    except (TypeError, ValueError):
        raise PortalTokenError("invalid_token")
    if expires_at <= moment:
        raise PortalTokenError("token_expired")

    return {"clientId": client_id, "expiresAt": expires_at, "issuedAt": payload.get("iat")}


def assert_no_personal_data(payload):
    """送出前掃一遍：只要有一個欄位名落在黑名單，就當作程式出錯、直接炸掉。"""
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).strip().lower() in FORBIDDEN_KEYS:
                    raise PortalPrivacyError(f"forbidden_field:{key}")
                stack.append(value)
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
    return True


def _seat_status_counts(seats):
    counts = {}
    for seat in seats or []:
        status = str((seat or {}).get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# 資料撈取：一次撈整組 account_id（不是每戶一查），本機 JSON 備援也走得通
# ---------------------------------------------------------------------------

def _read_json_file(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback
    except Exception as exc:
        LOGGER.warning("org_portal read %s failed; using fallback: %s", os.path.basename(path), exc)
        return fallback


def _is_missing_table_error(exc):
    msg = str(exc)
    return (
        "PGRST205" in msg
        or "Could not find the table" in msg
        or "circuit open" in msg
        or "unreachable" in msg
    )


def _local_product_events(account_ids, since_iso):
    raw = _read_json_file(PRODUCT_EVENTS_PATH, {}) or {}
    events = raw.get("events", []) if isinstance(raw, dict) else raw
    out = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        acc = str(ev.get("accountId") or ev.get("account_id") or "")
        when = str(ev.get("eventTime") or ev.get("event_time") or ev.get("createdAt") or "")
        if acc in account_ids and when >= since_iso:
            out.append(ev)
    return out


def _local_medication_doses(account_ids, since_date):
    raw = _read_json_file(MEDICATION_DOSES_PATH, []) or []
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        acc = str(item.get("accountId") or item.get("account_id") or "")
        when = str(item.get("scheduledDate") or item.get("scheduled_date") or "")[:10]
        if acc in account_ids and when >= since_date:
            out.append(item)
    return out


def load_cohort_activity(account_ids, since_iso, since_date, backend=None):
    """撈這群帳號在視窗內的互動事件＋用藥紀錄。

    接 Supabase 時走 supabase_adapter 的批次查詢（account_id=in.(...) 一次撈整組）；
    沒接、或表不在／斷路器打開時，退回本機 JSON 檔（測試與本機開發用）。
    回 {"productEvents": [...], "medicationDoses": [...], "source": "supabase"|"json"}。
    """
    ids = sorted({str(a) for a in (account_ids or []) if a})
    if not ids:
        return {"productEvents": [], "medicationDoses": [], "source": "none"}
    backend = backend or supabase_adapter.make_adapter()
    try:
        if backend.enabled():
            events = backend.load_org_cohort_product_events(ids, since_iso=since_iso)
            doses = backend.load_org_cohort_medication_doses(ids, since_date=since_date)
            if events is not None and doses is not None:
                return {"productEvents": events, "medicationDoses": doses, "source": "supabase"}
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        LOGGER.warning("org_portal cohort activity from Supabase failed; using local fallback: %s", exc)
    id_set = set(ids)
    return {
        "productEvents": _local_product_events(id_set, since_iso),
        "medicationDoses": _local_medication_doses(id_set, since_date),
        "source": "json",
    }


# ---------------------------------------------------------------------------
# 彙總計算（純函式；資料由上面撈好或測試直接注入）
# ---------------------------------------------------------------------------

def _event_account(ev):
    return str(ev.get("accountId") or ev.get("account_id") or "")


def _event_time(ev):
    return str(ev.get("eventTime") or ev.get("event_time") or ev.get("createdAt") or "")


def _event_props(ev):
    props = ev.get("properties")
    return props if isinstance(props, dict) else {}


def _is_interaction_event(ev):
    """長輩「真的有來用」才算互動：排掉系統自己產生的評估／診斷事件，
    以及事件自己標了不算指標（analyticsExcluded）的。"""
    name = str(ev.get("eventName") or ev.get("event_name") or "")
    if not name or name in NON_INTERACTION_EVENT_NAMES:
        return False
    if _event_props(ev).get("analyticsExcluded"):
        return False
    return True


def _is_high_risk_event(ev):
    name = str(ev.get("eventName") or ev.get("event_name") or "")
    if name != "guardian_risk_evaluated":
        return False
    props = _event_props(ev)
    level = str(props.get("riskLevel") or props.get("risk_level") or "").lower()
    return level in HIGH_RISK_LEVELS


def _ratio(numerator, denominator):
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def build_usage_section(cohort_ids, events, doses, this_start_iso, prev_start_iso, period_days=PERIOD_DAYS):
    """使用狀況：啟用人數、近 30 天有互動人數、留存、平均每人每週互動次數。"""
    cohort = set(cohort_ids)
    enabled = len(cohort)
    this_active, prev_active = set(), set()
    this_count = 0
    for ev in events or []:
        acc = _event_account(ev)
        if acc not in cohort or not _is_interaction_event(ev):
            continue
        when = _event_time(ev)
        if when >= this_start_iso:
            this_active.add(acc)
            this_count += 1
        elif when >= prev_start_iso:
            prev_active.add(acc)
    # 吃藥按「已服用」也算有來用（提醒完成）——這是 App 上真人的動作
    for item in doses or []:
        acc = str(item.get("accountId") or item.get("account_id") or "")
        if acc not in cohort or str(item.get("status") or "") != "taken":
            continue
        when = str(item.get("takenAt") or item.get("taken_at") or item.get("scheduledDate") or item.get("scheduled_date") or "")
        if when >= this_start_iso[:10]:
            this_active.add(acc)
            this_count += 1
        elif when >= prev_start_iso[:10]:
            prev_active.add(acc)

    retained = len(prev_active & this_active)
    weeks = max(period_days / 7.0, 1e-9)
    suppressed = enabled < MIN_GROUP_SIZE
    return {
        "enabledCount": enabled,
        "activeCount": len(this_active),
        "activeRate": None if suppressed else _ratio(len(this_active), enabled),
        "retentionRate": None if suppressed else _ratio(retained, len(prev_active)),
        "retentionBaseCount": None if suppressed else len(prev_active),
        "avgWeeklyInteractionsPerPerson": None if suppressed else (round(this_count / enabled / weeks, 2) if enabled else None),
        "smallSampleSuppressed": suppressed,
    }


def build_guardian_section(cohort_ids, events, doses, this_start_iso):
    """守護：高風險件數＋已有人跟進件數＋用藥提醒完成率。只有數字，沒有任何內容。"""
    cohort = set(cohort_ids)
    suppressed = len(cohort) < MIN_GROUP_SIZE
    high = 0
    for ev in events or []:
        if _event_account(ev) in cohort and _event_time(ev) >= this_start_iso and _is_high_risk_event(ev):
            high += 1
    taken = skipped = missed = 0
    for item in doses or []:
        if str(item.get("accountId") or item.get("account_id") or "") not in cohort:
            continue
        when = str(item.get("scheduledDate") or item.get("scheduled_date") or "")[:10]
        if when < this_start_iso[:10]:
            continue
        status = str(item.get("status") or "")
        if status == "taken":
            taken += 1
        elif status == "skipped":
            skipped += 1
        elif status == "missed":
            missed += 1
    decided = taken + skipped + missed
    return {
        "highRiskEventCount": None if suppressed else high,
        # 「已有人跟進」目前系統沒有任何一處在記（守護腦 high/critical 只進 Slack、窗口還沒有
        # 「已處理／誤報／觀察中」的標記功能）。沒資料就明講沒資料，不填 0 冒充「沒人跟進」。
        "followedUpCount": None,
        "followUpTrackingAvailable": False,
        "medicationCompletionRate": None if suppressed else _ratio(taken, decided),
        "medicationDecidedCount": None if suppressed else decided,
        "smallSampleSuppressed": suppressed,
    }


def _period_label(period_start, period_end):
    text = str(period_start or "")[:7]
    if len(text) == 7 and text[4] == "-":
        return f"{text[:4]}年{int(text[5:7])}月"
    return f"{period_start or ''} ~ {period_end or ''}"


def build_reports_section(reports):
    """月報清單：只有月份、產生時間、能不能下載。月報本體走憑證驗過的下載路由。"""
    items = []
    for rep in reports or []:
        if not isinstance(rep, dict) or not rep.get("id"):
            continue
        items.append({
            "id": str(rep.get("id")),
            "period": _period_label(rep.get("periodStart"), rep.get("periodEnd")),
            "periodStart": rep.get("periodStart"),
            "periodEnd": rep.get("periodEnd"),
            "generatedAt": rep.get("generatedAt"),
            "available": bool(rep.get("reportHtml")),
        })
    items.sort(key=lambda r: str(r.get("periodStart") or ""), reverse=True)
    return {"count": len(items), "list": items}


def _load_reports(client_id):
    # 延後 import：enterprise_billing 載入時會拉一整串請款模組，彙總頁用不到時不必付這個代價。
    try:
        import enterprise_billing
        return enterprise_billing.list_reports(client_id=client_id, limit=60)
    except Exception as exc:
        LOGGER.warning("org_portal list reports failed; showing none: %s", exc)
        return []


def lookup_report_for_client(client_id, report_id):
    """下載路由用：只回「屬於這家」的月報，別家的一律當不存在（不透露有沒有這份）。"""
    client_id = str(client_id or "").strip()
    report_id = str(report_id or "").strip()
    if not client_id or not report_id:
        return None
    import enterprise_billing
    report = enterprise_billing.get_report(report_id)
    if not report or str(report.get("enterpriseClientId") or "") != client_id:
        return None
    return report


def build_portal_summary(client_id, seats=None, client=None, activity=None, reports=None, today=None):
    """組織維度的匿名彙總。這裡只放數字與組織自己的基本資料，不放任何個別長輩的東西。

    seats／client／activity／reports 可以直接注入（測試或已查好時用），沒給就即時查。
    activity = {"productEvents": [...], "medicationDoses": [...]}，由 load_cohort_activity 撈。
    """
    client_id = str(client_id or "").strip()
    if not client_id:
        raise PortalTokenError("client_id_required")

    record = client if client is not None else enterprise_seats.get_client(client_id)
    if not record:
        raise PortalTokenError("client_not_found")

    rows = seats if seats is not None else enterprise_seats.list_seats(client_id=client_id)
    counts = _seat_status_counts(rows)
    active = int(counts.get("active", 0))
    quota = int(record.get("seatQuota") or 0)

    # 彙總對象＝這家 active 席次綁定的帳號。沒綁帳號的 pending／waiting 不算人、released 更不算。
    cohort_ids = sorted({
        str(s.get("accountId") or s.get("account_id"))
        for s in (rows or [])
        if s and s.get("status") == "active" and (s.get("accountId") or s.get("account_id"))
    })

    end_day = today or _utc_now().date()
    if isinstance(end_day, datetime):
        end_day = end_day.date()
    this_start = end_day - timedelta(days=PERIOD_DAYS - 1)
    prev_start = this_start - timedelta(days=PERIOD_DAYS)
    this_start_iso = f"{this_start.isoformat()}T00:00:00Z"
    prev_start_iso = f"{prev_start.isoformat()}T00:00:00Z"

    if activity is None:
        activity = load_cohort_activity(cohort_ids, prev_start_iso, prev_start.isoformat())
    events = (activity or {}).get("productEvents") or []
    doses = (activity or {}).get("medicationDoses") or []
    report_rows = reports if reports is not None else _load_reports(client_id)

    usage = build_usage_section(cohort_ids, events, doses, this_start_iso, prev_start_iso)
    guardian = build_guardian_section(cohort_ids, events, doses, this_start_iso)
    suppressed = usage["smallSampleSuppressed"] or guardian["smallSampleSuppressed"]

    summary = {
        "org": {
            "name": record.get("name") or "",
            "planTier": record.get("planTier") or "",
            "contractStart": record.get("contractStart"),
            "contractEnd": record.get("contractEnd"),
        },
        "seats": {
            "quota": quota,
            "active": active,
            "pending": int(counts.get("pending", 0)),
            "released": int(counts.get("released", 0)),
            "unusedQuota": max(quota - active, 0),
            "utilization": round(active / quota, 4) if quota > 0 else None,
        },
        "period": {
            "start": this_start.isoformat(),
            "end": end_day.isoformat(),
            "days": PERIOD_DAYS,
            "previousStart": prev_start.isoformat(),
        },
        "usage": usage,
        "guardian": guardian,
        "reports": build_reports_section(report_rows),
        "privacy": {
            "personalDataIncluded": False,
            "smallSampleSuppressed": bool(suppressed),
            "minGroupSize": MIN_GROUP_SIZE,
            "statement": (
                "本頁只顯示整家加總的數字。長輩的對話內容、心情、用藥明細與每一次的守護事件，"
                "僅家屬本人可見，機構端不提供；啟用人數未滿 5 人時，比率與守護件數不單獨呈現，"
                "避免從比例反推到個人。"
            ),
        },
        "generatedAt": _utc_now().isoformat(),
    }
    assert_no_personal_data(summary)
    return summary


def build_portal_link(base_url, token):
    """組合窗口拿到的網址。base_url 沒帶就只回相對路徑，讓呼叫端自己接。"""
    path = f"/org-portal.html?t={token}"
    base = str(base_url or "").strip().rstrip("/")
    return f"{base}{path}" if base else path
