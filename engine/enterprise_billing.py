# -*- coding: utf-8 -*-
"""
Munea 企業席次 · 月結（計費 + 請款單 + ESG 成效月報）
需求單：docs/企業席次-後台管理與月結-需求單-2026-07-20.md 第 4 節（4.1-4.5）、
5.2（收款紀錄欄位）、5.3（欠款階梯）、5A（waiting 不計費）。

不碰的東西：engine/server.py（HTTP 路由）、engine/enterprise_seats.py（席次 CRUD／狀態機）、
supabase/sql/*（表結構）——本檔只讀 enterprise_seats.py 提供的資料存取函式，
自己加 enterprise_invoices 的 CRUD（見 020_enterprise_seats.sql 檔頭註解：
「CRUD 留給 billing 那支檔案自己加」），沿用 supabase_adapter 通用的
_select/_request/_first（跟 enterprise_seats.py 用同一套，不新增 adapter 方法）。

2026-07-20 更新：需求單 5.2 的 6 個收款欄位（sent_at / paid_at / paid_amount_twd /
payment_note / invoice_number / invoice_issued_at）已由資料層補進
020_enterprise_seats.sql（status 也補了 invoiced），_invoice_item_to_supabase_row()
已解禁全欄位寫入——見該函式與檔案本身的最新定義，欄位名／型別以那份 SQL 為準。
"""
import calendar
import html
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import enterprise_seats
import supabase_adapter

LOGGER = logging.getLogger("munea.enterprise_billing")
_JSON_STORE_LOCK = threading.RLock()

HERE = os.path.dirname(os.path.abspath(__file__))
INVOICES_PATH = os.environ.get("MUNEA_ENTERPRISE_INVOICES_PATH") or os.path.join(HERE, "enterprise_invoices_store.json")

TAX_RATE = Decimal("0.05")
PAYMENT_DUE_DAY = 15  # 需求單 4.2／5.2：付款期限＝次月 15 日前
OVERDUE_GRACE_DAYS = 7  # 需求單 4.3／5.3：逾期 7 天以上 → 不出月報
PRIVACY_MIN_GROUP_SIZE = 5  # 需求單 4.4 第 3 條：分組人數 < 5 不單獨呈現

INVOICE_STATUSES = ("draft", "issued", "paid", "invoiced", "void")  # 需求單 5.2：020_enterprise_seats.sql 狀態流
NON_BILLABLE_SEAT_STATUSES = {"pending", "waiting"}  # 需求單 4.1 + 5A：pending／waiting 一律不計費

# 需求單 4.4 隱私鐵律用的關鍵字掃描表（都是「正規化後的 key 名稱」比對，不分大小寫、
# 不分底線／空白）。這份清單只抓「常見會不小心加進去」的欄位命名，不是萬能——
# 真正的防線是 build_esg_report() 一開始就只組出白名單欄位，這裡是第二道防線。
_PII_KEY_HINTS = (
    "name", "displayname", "residentname", "eldername", "personname", "username",
    "email", "phone", "contact", "address", "identifier",
    "accountid", "personid", "userid", "authuserid", "seatinviteemail", "inviteemail",
    "姓名", "電話", "信箱", "地址", "身分證",
)
_CONVERSATION_KEY_HINTS = (
    "transcript", "summary", "conversation", "dialogue", "message",
    "memorytag", "memory", "chatlog", "utterance", "note",
    "對話", "摘要", "逐字稿", "訊息", "備註",
)
# 這幾個欄位是報告本來就需要的內容（公司自己的名稱／給人看的敘述段落／識別碼本身），
# 不算長輩個資外洩，白名單放行，不參與規則 1／2 的 key 掃描。
REPORT_ALLOWLISTED_KEYS = {"name", "grinarrative", "griNarrative".lower(), "label"}
_SAFE_LONG_TEXT_KEY_NAMES = {"grinarrative"}
_ID_FIELD_KEY_NAMES = {"id"}  # 允許值是 UUID 的欄位（公司／報告自己的識別碼，不是長輩的）
_MAX_PLAIN_TEXT_LEN = 100  # 一般欄位超過這個長度視為可疑，可能夾帶對話內容或摘要片段

_UUID_VALUE_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

# 4.3 五區塊要查的分析表：欄位名稱與時間欄位型別（date 直接用 YYYY-MM-DD 比對；
# timestamp 要補整天的時分秒，才不會漏掉月初 00:00 之前或月底 23:59 之後被 truncate）。
_COHORT_TABLE_DATE_FIELDS = {
    "daily_user_metrics": ("metric_date", "date"),
    "voice_session_metrics": ("started_at", "timestamp"),
    "reminder_events": ("event_time", "timestamp"),
    "family_interaction_events": ("event_time", "timestamp"),
    "safety_events": ("created_at", "timestamp"),
}


class PrivacyViolationError(RuntimeError):
    """需求單 4.4 隱私鐵律任一條被違反時丟出——月報一律不准產出，靠程式擋，不靠人記得。"""


class ClientOverdueBlockedError(RuntimeError):
    """需求單 4.3：公司逾期 7 天以上，月報不產出（請款單照常產）。呼叫端要接住這個例外，
    不是讓它整批月結任務中斷——一家公司逾期不該連累其他正常繳費的公司。"""

    def __init__(self, client_id, overdue_days):
        super().__init__(
            f"enterprise_client_overdue_blocked: client={client_id} "
            f"overdue_days={overdue_days} (>= {OVERDUE_GRACE_DAYS})"
        )
        self.client_id = client_id
        self.overdue_days = overdue_days


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _utc_now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value):
    """寬鬆解析 date／datetime／ISO 字串成 date 物件，解析不出來回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _round_half_up_int(value):
    """四捨五入到整數元。Python 內建 round() 是銀行家捨入（四捨六入五成雙），
    金額一律要標準四捨五入，用 Decimal 才準。"""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _fmt_money(value):
    try:
        return f"{int(round(_safe_number(value))):,}"
    except (TypeError, ValueError):
        return "0"


def _fmt_pct(value, digits=1):
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def _is_missing_table_error(exc):
    """跟 enterprise_seats.py 同一套判斷——缺表／斷路器打開／連不上，都當「查不到」處理，
    退回本地備援，不整支炸掉。"""
    msg = str(exc)
    return (
        "PGRST205" in msg
        or "Could not find the table" in msg
        or "circuit open" in msg
        or "unreachable" in msg
    )


def _log_fallback(context, exc):
    LOGGER.warning("%s failed; using local fallback: %s", context, exc)


def _backend():
    return supabase_adapter.make_adapter()


def _read_json_file(path, fallback=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return fallback
    except Exception as exc:
        _log_fallback(f"read_json_file({os.path.basename(path)})", exc)
        return fallback


def _write_json_file(path, data):
    with _JSON_STORE_LOCK:
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
                except OSError:
                    pass


def _account_ids_in_filter(account_ids):
    ids = sorted({str(a) for a in (account_ids or []) if a})
    return f"in.({','.join(ids)})" if ids else None


# ---------------------------------------------------------------------------
# 帳單期間
# ---------------------------------------------------------------------------

def billing_period_for(year, month):
    """回傳 (period_start, period_end) 兩個 date 物件：該月第一天與最後一天。"""
    last_day = calendar.monthrange(int(year), int(month))[1]
    return date(int(year), int(month), 1), date(int(year), int(month), last_day)


def previous_month_period(today=None):
    """月結預設結算「上個月」（需求單 4：每月 1 日，結算上個月）。"""
    today = today or datetime.now(timezone.utc).date()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    return billing_period_for(last_of_prev_month.year, last_of_prev_month.month)


def resolve_billing_period(year=None, month=None, today=None):
    if year and month:
        return billing_period_for(year, month)
    return previous_month_period(today=today)


def compute_due_date(period_end):
    """付款期限＝次月 15 日前（需求單 4.2、5.2）。"""
    year = period_end.year + (1 if period_end.month == 12 else 0)
    month = 1 if period_end.month == 12 else period_end.month + 1
    return date(year, month, PAYMENT_DUE_DAY)


# ---------------------------------------------------------------------------
# A. 計費規則（需求單 4.1，一字不差）
# ---------------------------------------------------------------------------

def is_seat_billable(seat, period_start, period_end):
    """需求單 4.1：
      - 計費席次數 = 帳單月最後一天仍為 active 的席次數
      - 當月新加入的席次 → 當月免費，次月起計費
      - 當月中途被移除的席次 → 當月照收（已提供服務）
      - grace 狀態的席次 → 不計費
      - waiting 狀態的席次 → 不計費（需求單 5A：個人已自費，企業席次尚未接手）
      - pending 從沒生效過 → 不計費

    「月底仍為 active」跟「中途移除仍照收」字面上互斥（移除後狀態變成 grace，
    月底就不是 active 了）——用席次的狀態轉換時間點（activatedAt／graceStartedAt）
    還原實際的服務區間，而不是只看「跑月結當下」這一個時間點的狀態快照：
      1. activatedAt 落在本月內 → 不論目前狀態，當月新加入 → 這個月免費
      2. status == active 且不是本月新加入 → 本來就在服務、月底也還是 active → 計費
      3. status in (grace, released) 且 graceStartedAt 落在本月內
         → 月初還是 active、月中才轉出 → 服務已提供 → 當月照收
      4. status in (grace, released) 且 graceStartedAt 早於本月開始
         → 整個月都已經不是在服務的狀態 → 不計費
    """
    status = seat.get("status") or "pending"
    if status in NON_BILLABLE_SEAT_STATUSES:
        return False

    activated_at = _parse_date(seat.get("activatedAt"))
    if not activated_at:
        return False  # 從沒生效過（active/grace/released 理論上一定有 activatedAt，這裡防呆）

    if period_start <= activated_at <= period_end:
        return False  # 規則：當月新加入 → 當月免費

    if status == "active":
        return True  # 不是本月新加入、目前仍 active → 計費

    if status in ("grace", "released"):
        grace_started_at = _parse_date(seat.get("graceStartedAt"))
        if not grace_started_at:
            return False  # 查不到轉出時間，保守判定不計費
        if period_start <= grace_started_at <= period_end:
            return True  # 當月中途被移除 → 當月照收
        return False  # 早於本月就已經不是活躍服務 → 不計費

    return False


def billable_seats_for_client(client_id, period_start, period_end, seats=None):
    """回傳這期間計費的席次清單。seats 可注入（測試／已經查好時用），
    不給就用 enterprise_seats.list_seats() 真查。"""
    seats = seats if seats is not None else enterprise_seats.list_seats(client_id=client_id)
    return [s for s in seats if is_seat_billable(s, period_start, period_end)]


def compute_invoice_amounts(billable_seat_count, unit_price_twd):
    """需求單 4.1：金額 = 席次數 × 單價（未稅），稅 5%，總計四捨五入到整數元。
    小計、總計各自四捨五入到整數；稅額 = 總計 − 小計，確保三個數字加總永遠一致
    （不會因為小計與稅額分開四捨五入，出現『小計＋稅≠總計』的一元誤差），
    同時 totalTwd 精準對上需求單第 7 節驗收公式：席次數 × 單價 × 1.05（四捨五入）。"""
    seats = Decimal(str(int(billable_seat_count or 0)))
    unit_price = Decimal(str(unit_price_twd or 0))
    raw_subtotal = seats * unit_price
    raw_total = raw_subtotal * (Decimal("1") + TAX_RATE)
    subtotal_twd = _round_half_up_int(raw_subtotal)
    total_twd = _round_half_up_int(raw_total)
    tax_twd = total_twd - subtotal_twd
    return {
        "billableSeats": int(billable_seat_count or 0),
        "unitPriceTwd": _round_half_up_int(unit_price),
        "subtotalTwd": subtotal_twd,
        "taxTwd": tax_twd,
        "totalTwd": total_twd,
    }


def compute_overdue_days(invoice, today=None):
    """需求單 4.1／5.2：逾期天數 = 今天 − due_date（未付款時）。
    已付款（paidAt 有值）或根本還沒發出（draft／void）都不算逾期。"""
    if not invoice:
        return 0
    if invoice.get("paidAt"):
        return 0
    if invoice.get("status") != "issued":
        return 0
    due = _parse_date(invoice.get("dueDate"))
    if not due:
        return 0
    today = today or datetime.now(timezone.utc).date()
    return max(0, (today - due).days)


def compute_outstanding_total(invoices, today=None):
    """需求單 4.1：累計欠款 = 所有 issued 未 paid 的總額（不看有沒有逾期，issued 就是欠款）。"""
    total = 0
    for inv in invoices or []:
        if inv.get("status") == "issued" and not inv.get("paidAt"):
            total += int(inv.get("totalTwd") or 0)
    return total


def client_overdue_days(client_id, invoices=None, today=None):
    """這家公司目前『最久』逾期未繳天數（5.3 欠款階梯、4.3 月報產出前置檢查用）。
    invoices 可注入（測試／已經查好時用），不給就查這家公司所有 issued 的單。"""
    invoices = invoices if invoices is not None else list_invoices(client_id=client_id, status="issued")
    days = [compute_overdue_days(inv, today=today) for inv in invoices]
    return max(days) if days else 0


def is_client_blocked_for_report(client_id, invoices=None, today=None):
    """需求單 4.3：公司逾期 7 天以上 → 該公司月報不產出。"""
    return client_overdue_days(client_id, invoices=invoices, today=today) >= OVERDUE_GRACE_DAYS



# ---------------------------------------------------------------------------
# B. 請款單（需求單 4.2 + 5.2）
# ---------------------------------------------------------------------------

def derive_client_code(client):
    """需求單沒有替企業客戶另外定義「公司代碼」欄位（2.1 只有 name／taxId 等），
    取 client id 前 8 碼（去掉連字號、轉大寫）當代碼——穩定、不受公司改名影響、
    不必處理中文轉拼音。之後若正式定義了公司代碼欄位，這裡要跟著改成讀那個欄位。"""
    client_id = str((client or {}).get("id") or "")
    stripped = client_id.replace("-", "")
    code = (stripped[:8] or "UNKNOWN").upper()
    return code or "UNKNOWN"


def generate_invoice_no(client, period_start):
    """單號格式 MU-YYYYMM-<公司代碼>（需求單 2.4／4.2）。YYYYMM 取的是帳單期間
    （被結算的那個月），不是產出當下的月份。"""
    yyyymm = period_start.strftime("%Y%m")
    return f"MU-{yyyymm}-{derive_client_code(client)}"


_INVOICE_SUPABASE_COLUMNS = (
    "invoice_no", "enterprise_client_id", "period_start", "period_end",
    "billable_seats", "unit_price_twd", "subtotal_twd", "tax_twd", "total_twd",
    "status", "due_date", "seat_snapshot", "report_ref",
    # 需求單 5.2 收款欄位（2026-07-20 解禁：020_enterprise_seats.sql 已補齊這六欄）
    "sent_at", "paid_at", "paid_amount_twd", "payment_note", "invoice_number", "invoice_issued_at",
)


def _invoice_item_to_supabase_row(item):
    """對齊 020_enterprise_seats.sql 的 enterprise_invoices 定義送出整列。
    5.2 的六個收款欄位（2026-07-20 解禁）：sent_at／paid_at／invoice_issued_at 是
    timestamptz，None 就送 null（欄位本身可空）；paid_amount_twd 是 numeric、
    有 check(paid_amount_twd is null or >=0)，同樣 None 就送 null，不能塞 0 混充「還沒收」。"""
    item = item or {}
    return {
        "invoice_no": item.get("invoiceNo"),
        "enterprise_client_id": item.get("enterpriseClientId"),
        "period_start": item.get("periodStart"),
        "period_end": item.get("periodEnd"),
        "billable_seats": int(item.get("billableSeats") or 0),
        "unit_price_twd": item.get("unitPriceTwd") or 0,
        "subtotal_twd": item.get("subtotalTwd") or 0,
        "tax_twd": item.get("taxTwd") or 0,
        "total_twd": item.get("totalTwd") or 0,
        "status": item.get("status") or "draft",
        "due_date": item.get("dueDate"),
        "seat_snapshot": item.get("seatSnapshot") or [],
        "report_ref": item.get("reportRef"),
        "sent_at": item.get("sentAt"),
        "paid_at": item.get("paidAt"),
        "paid_amount_twd": item.get("paidAmountTwd"),
        "payment_note": item.get("paymentNote"),
        "invoice_number": item.get("invoiceNumber"),
        "invoice_issued_at": item.get("invoiceIssuedAt"),
    }


def _invoice_row_to_item(row):
    """把 Supabase row 或本地 JSON record（兩種都是 dict，鍵名可能是 snake_case
    或已經是 camelCase）正規化成統一的 camelCase item。5.2 的 6 個欄位如果來源
    沒有（目前的 Supabase row 就沒有）一律預設 None，不是錯誤。"""
    row = row or {}

    def pick(camel, snake):
        if camel in row and row.get(camel) is not None:
            return row.get(camel)
        return row.get(snake)

    return {
        "id": row.get("id") or "",
        "invoiceNo": pick("invoiceNo", "invoice_no") or "",
        "enterpriseClientId": pick("enterpriseClientId", "enterprise_client_id") or "",
        "periodStart": pick("periodStart", "period_start"),
        "periodEnd": pick("periodEnd", "period_end"),
        "billableSeats": int(pick("billableSeats", "billable_seats") or 0),
        "unitPriceTwd": pick("unitPriceTwd", "unit_price_twd") or 0,
        "subtotalTwd": pick("subtotalTwd", "subtotal_twd") or 0,
        "taxTwd": pick("taxTwd", "tax_twd") or 0,
        "totalTwd": pick("totalTwd", "total_twd") or 0,
        "status": row.get("status") or "draft",
        "dueDate": pick("dueDate", "due_date"),
        "seatSnapshot": pick("seatSnapshot", "seat_snapshot") or [],
        "reportRef": pick("reportRef", "report_ref"),
        "sentAt": pick("sentAt", "sent_at"),
        "paidAt": pick("paidAt", "paid_at"),
        "paidAmountTwd": pick("paidAmountTwd", "paid_amount_twd"),
        "paymentNote": pick("paymentNote", "payment_note"),
        "invoiceNumber": pick("invoiceNumber", "invoice_number"),
        "invoiceIssuedAt": pick("invoiceIssuedAt", "invoice_issued_at"),
        "createdAt": pick("createdAt", "created_at"),
        "updatedAt": pick("updatedAt", "updated_at"),
    }


def _load_invoices_remote(backend, client_id=None, status=None, limit=500):
    if not backend.enabled():
        return None
    filters = {"select": "*", "order": "period_start.desc", "limit": str(max(1, min(2000, int(limit or 500))))}
    if client_id:
        filters["enterprise_client_id"] = f"eq.{client_id}"
    if status:
        filters["status"] = f"eq.{status}"
    rows = backend._select("enterprise_invoices", filters)
    return [_invoice_row_to_item(row) for row in rows or []]


def list_invoices(client_id=None, status=None, limit=500):
    backend = _backend()
    try:
        remote = _load_invoices_remote(backend, client_id=client_id, status=status, limit=limit)
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("load enterprise invoices from Supabase", exc)
    items = _read_json_file(INVOICES_PATH, [])
    if not isinstance(items, list):
        items = []
    items = [_invoice_row_to_item(item) for item in items]
    if client_id:
        items = [i for i in items if i["enterpriseClientId"] == client_id]
    if status:
        items = [i for i in items if i["status"] == status]
    items.sort(key=lambda i: i.get("periodStart") or "", reverse=True)
    return items[:limit]


def get_invoice(invoice_id):
    if not invoice_id:
        return None
    backend = _backend()
    try:
        if backend.enabled():
            row = backend._first("enterprise_invoices", {"id": f"eq.{invoice_id}", "select": "*"})
            if row:
                return _invoice_row_to_item(row)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"get enterprise invoice {invoice_id} from Supabase", exc)
    items = _read_json_file(INVOICES_PATH, [])
    if not isinstance(items, list):
        items = []
    for item in items:
        if item.get("id") == invoice_id:
            return _invoice_row_to_item(item)
    return None


def get_invoice_by_no(invoice_no):
    if not invoice_no:
        return None
    for item in list_invoices():
        if item.get("invoiceNo") == invoice_no:
            return item
    return None


def _upsert_invoice_remote(backend, item):
    if not backend.enabled():
        return None
    payload = _invoice_item_to_supabase_row(item)
    invoice_id = item.get("id")
    if invoice_id and backend._is_uuid(invoice_id):
        payload["id"] = invoice_id
    rows = backend._request(
        "POST", "enterprise_invoices",
        query={"on_conflict": "invoice_no", "select": "*"},
        payload=payload, prefer="resolution=merge-duplicates,return=representation",
    )
    return _invoice_row_to_item(rows[0]) if rows else None


def _save_invoice_local(item):
    items = _read_json_file(INVOICES_PATH, [])
    if not isinstance(items, list):
        items = []
    now = _utc_now_iso()
    record = dict(item)
    existing_idx = None
    for idx, existing in enumerate(items):
        if existing.get("invoiceNo") and existing.get("invoiceNo") == record.get("invoiceNo"):
            existing_idx = idx
            break
    if existing_idx is not None:
        record["id"] = items[existing_idx].get("id") or record.get("id") or str(uuid.uuid4())
        record["createdAt"] = items[existing_idx].get("createdAt") or record.get("createdAt") or now
        record["updatedAt"] = now
        items[existing_idx] = {**items[existing_idx], **record}
        final_record = items[existing_idx]
    else:
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("createdAt", now)
        record["updatedAt"] = now
        items.append(record)
        final_record = record
    _write_json_file(INVOICES_PATH, items)
    return _invoice_row_to_item(final_record)


def save_invoice(item):
    """新建／覆寫一張請款單。本模組只在月結時建立 draft；issued/paid 之後的狀態
    流轉屬於 /admin/enterprise/invoice/mark-sent、mark-paid 端點的責任
    （engine/server.py，不在本檔範圍），這裡只負責把算好的 draft 落地。"""
    item = dict(item or {})
    backend = _backend()
    try:
        remote = _upsert_invoice_remote(backend, item)
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("save enterprise invoice to Supabase", exc)
    return _save_invoice_local(item)


def build_invoice_draft(client, seats, period_start, period_end):
    """需求單 4.2：算出一張 draft 請款單，純計算不落地——落地交給 save_invoice()，
    讓呼叫端可以先檢查／預覽再決定要不要真的寫進去。"""
    billable = billable_seats_for_client(client.get("id"), period_start, period_end, seats=seats)
    amounts = compute_invoice_amounts(len(billable), client.get("unitPriceTwd") or 0)
    invoice_no = generate_invoice_no(client, period_start)
    due_date = compute_due_date(period_end)
    seat_snapshot = [
        {
            "seatId": s.get("id"),
            "status": s.get("status"),
            "activatedAt": s.get("activatedAt"),
            "graceStartedAt": s.get("graceStartedAt"),
        }
        for s in billable
    ]
    return {
        "invoiceNo": invoice_no,
        "enterpriseClientId": client.get("id"),
        "periodStart": period_start.isoformat(),
        "periodEnd": period_end.isoformat(),
        **amounts,
        "status": "draft",
        "dueDate": due_date.isoformat(),
        "seatSnapshot": seat_snapshot,
        "reportRef": None,
        "sentAt": None,
        "paidAt": None,
        "paidAmountTwd": None,
        "paymentNote": None,
        "invoiceNumber": None,
        "invoiceIssuedAt": None,
    }


def generate_monthly_invoice(client, seats, period_start, period_end, persist=True):
    draft = build_invoice_draft(client, seats, period_start, period_end)
    if not persist:
        return draft
    return save_invoice(draft)


_INVOICE_HTML_STYLE = """
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
         color: #1f2933; margin: 0; padding: 24px; background: #eef1f5; }
  .sheet { width: 210mm; min-height: 297mm; margin: 0 auto; background: #fff;
           padding: 18mm; box-shadow: 0 0 12px rgba(0,0,0,0.12); }
  .draft-badge { display: inline-block; padding: 4px 12px; border: 1px solid #b45309;
                 color: #b45309; font-weight: 600; border-radius: 4px; font-size: 13px; }
  h1 { font-size: 26px; margin: 0 0 4px; }
  .sub { color: #52606d; font-size: 13px; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }
  .box { border: 1px solid #d9dfe6; border-radius: 6px; padding: 14px 16px; }
  .box h2 { font-size: 13px; color: #52606d; margin: 0 0 8px; font-weight: 600; }
  .box p { margin: 2px 0; font-size: 14px; }
  table.items { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
  table.items th, table.items td { border-bottom: 1px solid #d9dfe6; padding: 10px 8px;
                                    text-align: left; font-size: 14px; }
  table.items th { color: #52606d; font-weight: 600; font-size: 12px; text-transform: uppercase; }
  table.items td.num, table.items th.num { text-align: right; }
  .totals { width: 320px; margin-left: auto; }
  .totals div { display: flex; justify-content: space-between; padding: 6px 0; font-size: 14px; }
  .totals .grand { font-size: 22px; font-weight: 700; border-top: 2px solid #1f2933;
                    margin-top: 6px; padding-top: 10px; }
  .remit { margin-top: 24px; padding: 14px 16px; background: #f4f6f8; border-radius: 6px; font-size: 13px; }
  .payment-status { margin-top: 16px; font-size: 13px; color: #52606d; }
  .footer { margin-top: 32px; font-size: 11px; color: #9aa5b1; }
  @media print {
    body { background: #fff; padding: 0; }
    .sheet { box-shadow: none; margin: 0; }
    @page { size: A4 portrait; margin: 16mm; }
  }
"""


def render_invoice_html(invoice, client):
    """需求單 4.2＋5.2：請款單 HTML（可直接列印成 A4 直式 PDF）。
    含公司抬頭／統編／地址、單號、帳單期間、席次數×單價=小計、營業稅 5%、總計、
    付款期限、匯款帳戶資訊；5.2 收款欄位有值才顯示（draft 階段通常還沒有）。"""
    client = client or {}
    invoice = invoice or {}
    company_name = html.escape(str(client.get("name") or ""))
    tax_id = html.escape(str(client.get("taxId") or "—"))
    billing_address = html.escape(str(client.get("billingAddress") or "—"))
    contact_name = html.escape(str(client.get("contactName") or "—"))
    contact_email = html.escape(str(client.get("contactEmail") or "—"))

    period_label = f"{invoice.get('periodStart') or ''} ~ {invoice.get('periodEnd') or ''}"
    status = invoice.get("status") or "draft"
    draft_badge = "<span class=\"draft-badge\">草稿 DRAFT · 尚未人工放行</span>" if status == "draft" else ""

    bank_info = os.environ.get(
        "MUNEA_ENTERPRISE_REMIT_INFO",
        "匯款銀行：（待財務部提供）｜戶名：沐寧股份有限公司（暫定）｜帳號：（待財務部提供）",
    )

    payment_rows = []
    if invoice.get("sentAt"):
        payment_rows.append(f"寄出日：{html.escape(str(invoice.get('sentAt')))}")
    if invoice.get("paidAt"):
        payment_rows.append(f"實際入帳日：{html.escape(str(invoice.get('paidAt')))}")
    if invoice.get("paidAmountTwd") is not None:
        payment_rows.append(f"實收金額：NT$ {_fmt_money(invoice.get('paidAmountTwd'))}")
    if invoice.get("paymentNote"):
        payment_rows.append(f"備註：{html.escape(str(invoice.get('paymentNote')))}")
    if invoice.get("invoiceNumber"):
        payment_rows.append(f"發票號碼：{html.escape(str(invoice.get('invoiceNumber')))}")
    payment_block = ""
    if payment_rows:
        payment_block = "<div class=\"payment-status\">" + "　｜　".join(payment_rows) + "</div>"

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>請款單 {html.escape(str(invoice.get('invoiceNo') or ''))}</title>
<style>{_INVOICE_HTML_STYLE}</style>
</head>
<body>
<div class="sheet">
  <h1>請款單 INVOICE</h1>
  <div class="sub">單號 {html.escape(str(invoice.get('invoiceNo') or ''))}　{draft_badge}</div>

  <div class="grid">
    <div class="box">
      <h2>買方（企業客戶）</h2>
      <p><strong>{company_name}</strong></p>
      <p>統一編號：{tax_id}</p>
      <p>地址：{billing_address}</p>
      <p>聯絡人：{contact_name}（{contact_email}）</p>
    </div>
    <div class="box">
      <h2>帳單資訊</h2>
      <p>帳單期間：{html.escape(period_label)}</p>
      <p>付款期限：{html.escape(str(invoice.get('dueDate') or '—'))}</p>
      <p>單據狀態：{html.escape(status)}</p>
      <p>對應月報：{html.escape(str(invoice.get('reportRef') or '（見後附 ESG 成效月報）'))}</p>
    </div>
  </div>

  <table class="items">
    <thead>
      <tr><th>項目</th><th class="num">席次數</th><th class="num">單價（未稅）</th><th class="num">小計</th></tr>
    </thead>
    <tbody>
      <tr>
        <td>Munea 企業席次月費</td>
        <td class="num">{invoice.get('billableSeats', 0)}</td>
        <td class="num">NT$ {_fmt_money(invoice.get('unitPriceTwd'))}</td>
        <td class="num">NT$ {_fmt_money(invoice.get('subtotalTwd'))}</td>
      </tr>
    </tbody>
  </table>

  <div class="totals">
    <div><span>小計</span><span>NT$ {_fmt_money(invoice.get('subtotalTwd'))}</span></div>
    <div><span>營業稅（5%）</span><span>NT$ {_fmt_money(invoice.get('taxTwd'))}</span></div>
    <div class="grand"><span>總計</span><span>NT$ {_fmt_money(invoice.get('totalTwd'))}</span></div>
  </div>

  <div class="remit">{html.escape(bank_info)}</div>
  {payment_block}

  <div class="footer">Munea 企業席次月結系統自動產出 · {html.escape(_utc_now_iso())}</div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# C. ESG 成效月報（需求單 4.3）
# ---------------------------------------------------------------------------

def _period_bounds_for_field(period_start, period_end, kind):
    if kind == "date":
        return period_start.isoformat(), period_end.isoformat()
    lower = f"{period_start.isoformat()}T00:00:00Z"
    upper = f"{period_end.isoformat()}T23:59:59Z"
    return lower, upper


def _load_cohort_table_rows(backend, table, account_ids, period_start, period_end, limit=5000):
    """企業月報用：查某張分析表在這段期間、這批帳號 id 底下的所有列。
    backend.enabled() 為 False（本地開發、沒接 Supabase）時回傳空陣列——月報本來就是
    給正式營運後台用，本地假資料模式下沒有這些分析表，回空陣列讓上層照樣能跑（顯示無資料）。"""
    account_filter = _account_ids_in_filter(account_ids)
    if not account_filter:
        return []
    field, kind = _COHORT_TABLE_DATE_FIELDS[table]
    lower, upper = _period_bounds_for_field(period_start, period_end, kind)
    try:
        if not backend.enabled():
            return []
        filters = {
            "select": "*",
            "account_id": account_filter,
            field: f"gte.{lower}",
            "and": f"({field}.lte.{upper})",
            "limit": str(limit),
        }
        return backend._select(table, filters) or []
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"load {table} for enterprise report", exc)
        return []


def gather_esg_metrics(client, cohort_seats, period_start, period_end, *,
                        daily_user_metrics=None, voice_session_metrics=None,
                        reminder_events=None, family_interaction_events=None,
                        safety_events=None, backend=None):
    """需求單 4.3 五區塊的原始數據彙總。cohort_seats＝這期間計費的席次
    （is_seat_billable 判定過的，也就是這期間真正在服務的人）。各表資料可以直接
    注入（測試／已經查好時用），沒給就即時查 Supabase。"""
    backend = backend or _backend()
    account_ids = sorted({s.get("accountId") for s in cohort_seats if s.get("accountId")})
    if daily_user_metrics is None:
        daily_user_metrics = _load_cohort_table_rows(backend, "daily_user_metrics", account_ids, period_start, period_end)
    if voice_session_metrics is None:
        voice_session_metrics = _load_cohort_table_rows(backend, "voice_session_metrics", account_ids, period_start, period_end)
    if reminder_events is None:
        reminder_events = _load_cohort_table_rows(backend, "reminder_events", account_ids, period_start, period_end)
    if family_interaction_events is None:
        family_interaction_events = _load_cohort_table_rows(backend, "family_interaction_events", account_ids, period_start, period_end)
    if safety_events is None:
        safety_events = _load_cohort_table_rows(backend, "safety_events", account_ids, period_start, period_end)
    return {
        "accountIds": account_ids,
        "dailyUserMetrics": daily_user_metrics,
        "voiceSessionMetrics": voice_session_metrics,
        "reminderEvents": reminder_events,
        "familyInteractionEvents": family_interaction_events,
        "safetyEvents": safety_events,
    }


def _build_section_coverage(client, all_seats, cohort_seats):
    """區塊一・涵蓋與參與。資料來源：enterprise_seats（需求單 4.3 表格第 1 列）。
    這一區只放「合約層級」的數字（席次數／啟用數／使用率），不是個人行為的平均值，
    所以不受規則 3（<5 人遮蔽）限制——公司自己本來就知道買了幾個席次、指派給誰。"""
    seat_quota = int(client.get("seatQuota") or 0)
    total_seats = len([s for s in all_seats if s.get("status") != "released"])
    active_seats = len([s for s in all_seats if s.get("status") == "active"])
    actually_used_seats = len(cohort_seats)
    denominator = seat_quota or total_seats or 1
    activation_rate = round(active_seats / denominator, 4) if denominator else None
    return {
        "seatQuota": seat_quota,
        "totalSeats": total_seats,
        "activeSeats": active_seats,
        "actuallyUsedSeats": actually_used_seats,
        "activationRate": activation_rate,
        "lowUtilizationFlag": bool(activation_rate is not None and activation_rate < 0.5),
        "sampleSize": None,
        "suppressed": False,
    }


def _build_section_companionship(cohort_size, period_start, period_end, daily_rows, voice_rows):
    """區塊二・陪伴成效。資料來源：daily_user_metrics、voice_session_metrics
    （需求單 4.3 表格第 2 列）。cohort_size < 5 時整區塊遮蔽（規則 3）。"""
    suppressed = cohort_size < PRIVACY_MIN_GROUP_SIZE
    days_in_period = (period_end - period_start).days + 1
    total_voice_sessions = sum(_safe_number(r.get("voice_sessions")) for r in daily_rows)
    total_voice_minutes = sum(_safe_number(r.get("voice_minutes")) for r in daily_rows)
    meaningful_days = sum(1 for r in daily_rows if r.get("meaningful_companion_day"))
    accounts_with_activity = len({
        r.get("account_id") for r in daily_rows if _safe_number(r.get("voice_sessions")) > 0
    })
    total_call_duration_ms = sum(_safe_number(r.get("duration_ms")) for r in voice_rows)
    call_count = len(voice_rows)

    weeks_in_period = max(days_in_period / 7.0, 1e-9)
    avg_weekly_call_count = round(total_voice_sessions / cohort_size / weeks_in_period, 2) if cohort_size else None
    meaningful_day_ratio = round(meaningful_days / (cohort_size * days_in_period), 4) if cohort_size and days_in_period else None
    if call_count:
        avg_call_minutes = round((total_call_duration_ms / call_count) / 60000, 2)
    elif total_voice_sessions:
        avg_call_minutes = round(total_voice_minutes / total_voice_sessions, 2)
    else:
        avg_call_minutes = None
    continued_usage_rate = round(accounts_with_activity / cohort_size, 4) if cohort_size else None

    return {
        "sampleSize": cohort_size,
        "suppressed": suppressed,
        "avgWeeklyCallCount": None if suppressed else avg_weekly_call_count,
        "meaningfulCompanionDayRatio": None if suppressed else meaningful_day_ratio,
        "avgCallMinutes": None if suppressed else avg_call_minutes,
        "continuedUsageRate": None if suppressed else continued_usage_rate,
    }


def _build_section_care(cohort_size, reminder_rows, safety_rows):
    """區塊三・照護成效。資料來源：reminder_events、safety_events
    （需求單 4.3 表格第 3 列）。cohort_size < 5 時整區塊遮蔽（規則 3）。"""
    suppressed = cohort_size < PRIVACY_MIN_GROUP_SIZE
    sent = sum(1 for r in reminder_rows if r.get("event_type") == "sent")
    completed = sum(1 for r in reminder_rows if r.get("event_type") == "completed")
    completion_rate = round(completed / sent, 4) if sent else None
    notifications_sent = sum(1 for r in safety_rows if r.get("status") in ("notified", "resolved"))
    caught_in_time = sum(1 for r in safety_rows if r.get("status") == "resolved")
    return {
        "sampleSize": cohort_size,
        "suppressed": suppressed,
        "reminderCompletionRate": None if suppressed else completion_rate,
        "careNotificationsSent": None if suppressed else notifications_sent,
        "anomaliesCaughtInTime": None if suppressed else caught_in_time,
    }


def _build_section_family_value(cohort_size, cohort_account_ids, family_rows):
    """區塊四・員工端價值。資料來源：family_interaction_events
    （需求單 4.3 表格第 4 列）。cohort_size < 5 時整區塊遮蔽（規則 3）。"""
    suppressed = cohort_size < PRIVACY_MIN_GROUP_SIZE
    notified_accounts = {
        r.get("account_id") for r in family_rows if r.get("event_type") == "safety_notification_sent"
    }
    ratio = round(len(notified_accounts) / cohort_size, 4) if cohort_size else None
    return {
        "sampleSize": cohort_size,
        "suppressed": suppressed,
        "familiesNotifiedRatio": None if suppressed else ratio,
    }


def _build_section_gri(client, section1, section2, section3, section4):
    """區塊五・GRI 對應。純文字敘述段落，組裝上面四區已經算好（也已經套過遮蔽規則）
    的數字，不重新碰原始資料——遮蔽區塊本來就不會被寫進這段敘述。"""
    company_label = client.get("name") or "本企業"
    lines = [
        f"{company_label}於本期透過 Munea 為 {section1['activeSeats']} 位員工眷屬提供 AI 陪伴照護服務"
        f"（合約席次 {section1['seatQuota']} 席，啟用率 {_fmt_pct(section1['activationRate'])}）。"
    ]
    if not section2.get("suppressed"):
        lines.append(
            f"服務期間平均每人每週對話 {section2['avgWeeklyCallCount']} 次，"
            f"有意義陪伴日比例 {_fmt_pct(section2['meaningfulCompanionDayRatio'])}。"
        )
    if not section3.get("suppressed"):
        lines.append(
            f"用藥／回診提醒完成率 {_fmt_pct(section3['reminderCompletionRate'])}，"
            f"本期及時接住 {section3['anomaliesCaughtInTime']} 次異常狀況。"
        )
    if not section4.get("suppressed"):
        lines.append(f"{_fmt_pct(section4['familiesNotifiedRatio'])} 的家庭本期收到過近況或安全通知。")
    if section2.get("suppressed") or section3.get("suppressed") or section4.get("suppressed"):
        lines.append("（本期部分區塊因服務人數低於 5 人，依隱私規定不單獨呈現細項數字。）")
    narrative = " ".join(lines)
    return {
        "griReferences": ["GRI 401-2 提供予正職員工的福利", "GRI 403-6 促進員工健康"],
        "griNarrative": narrative,
        "sampleSize": None,
        "suppressed": False,
    }


def build_esg_report(client, all_seats, period_start, period_end, *, invoices=None, raw_metrics=None, today=None):
    """需求單 4.3：產出五區塊 ESG 成效月報。
    - 逾期 7 天以上的公司直接擋下（丟 ClientOverdueBlockedError，帶原因），不是靜靜回空報告
    - 產出前一定跑 4.4 隱私鐵律檢查——這兩關都不是「可選」，呼叫端不能繞過
    """
    client_id = client.get("id")
    overdue_days = client_overdue_days(client_id, invoices=invoices, today=today)
    if overdue_days >= OVERDUE_GRACE_DAYS:
        raise ClientOverdueBlockedError(client_id=client_id, overdue_days=overdue_days)

    cohort_seats = billable_seats_for_client(client_id, period_start, period_end, seats=all_seats)
    cohort_account_ids = sorted({s.get("accountId") for s in cohort_seats if s.get("accountId")})
    cohort_size = len(cohort_account_ids)

    raw = raw_metrics if raw_metrics is not None else gather_esg_metrics(client, cohort_seats, period_start, period_end)

    section1 = _build_section_coverage(client, all_seats, cohort_seats)
    section2 = _build_section_companionship(
        cohort_size, period_start, period_end, raw["dailyUserMetrics"], raw["voiceSessionMetrics"]
    )
    section3 = _build_section_care(cohort_size, raw["reminderEvents"], raw["safetyEvents"])
    section4 = _build_section_family_value(cohort_size, cohort_account_ids, raw["familyInteractionEvents"])
    section5 = _build_section_gri(client, section1, section2, section3, section4)

    period_label = f"{period_start.year}年{period_start.month}月"
    report = {
        "client": {"id": client_id, "name": client.get("name") or ""},
        "reportPeriod": {"start": period_start.isoformat(), "end": period_end.isoformat(), "label": period_label},
        "generatedAt": _utc_now_iso(),
        "sections": {
            "coverage": section1,
            "companionship": section2,
            "care": section3,
            "familyValue": section4,
            "gri": section5,
        },
    }
    enforce_privacy_guard(report)
    return report


# ---------------------------------------------------------------------------
# D. 隱私檢查（需求單 4.4）——產出前一定會跑，四條全部要能擋，靠程式強制，不靠人記得
# ---------------------------------------------------------------------------

def _normalize_key(key):
    return str(key).strip().lower().replace("_", "").replace(" ", "").replace("-", "")


def _iter_dict_keys(obj):
    """遞迴收集所有 dict key（正規化前的原始字串），用來比對規則 1／2 的關鍵字清單。"""
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(str(k))
            keys.extend(_iter_dict_keys(v))
    elif isinstance(obj, list):
        for item in obj:
            keys.extend(_iter_dict_keys(item))
    return keys


def _iter_string_leaves(obj, key_context=""):
    """遞迴收集所有 (key_context, string_value)——key_context 是這個字串值最近的
    上層 dict key，用來判斷是不是白名單欄位（例如 griNarrative／id）。"""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_iter_string_leaves(v, str(k)))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_iter_string_leaves(item, key_context))
    elif isinstance(obj, str):
        out.append((key_context, obj))
    return out


def _iter_list_of_dicts(obj):
    """找出所有『值是 list、且 list 內至少一個元素是 dict』的地方——
    用來抓規則 4（月報只准放彙總數字，不准逐人列出清單）。"""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and any(isinstance(item, dict) for item in v):
                found.append((k, v))
            found.extend(_iter_list_of_dicts(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_iter_list_of_dicts(item))
    return found


def enforce_privacy_guard(report):
    """需求單 4.4 隱私鐵律，一次全部檢查，任一條違反就丟 PrivacyViolationError，
    呼叫端不准接著產出。四條規則：
      1. 不得含任何長輩姓名、帳號識別、聯絡方式
      2. 不得含任何對話內容或摘要片段
      3. 任何分組人數 < 5 時該組數字不單獨呈現（要真的遮蔽，不是只標注）
      4. 只輸出彙總數字與比例（不准放逐人清單）
    """
    violations = []

    all_keys = _iter_dict_keys(report)
    for key in all_keys:
        norm = _normalize_key(key)
        if norm in REPORT_ALLOWLISTED_KEYS:
            continue
        for hint in _PII_KEY_HINTS:
            if hint in norm:
                violations.append(f"規則1違反：欄位「{key}」疑似長輩姓名／帳號識別／聯絡方式（命中關鍵字「{hint}」）")
                break
        for hint in _CONVERSATION_KEY_HINTS:
            if hint in norm:
                violations.append(f"規則2違反：欄位「{key}」疑似對話內容或摘要片段（命中關鍵字「{hint}」）")
                break

    for key_ctx, text in _iter_string_leaves(report):
        norm_ctx = _normalize_key(key_ctx)
        if norm_ctx not in _SAFE_LONG_TEXT_KEY_NAMES and len(text) > _MAX_PLAIN_TEXT_LEN:
            violations.append(
                f"規則2違反：欄位「{key_ctx}」內容長度 {len(text)} 字超過 {_MAX_PLAIN_TEXT_LEN} 字上限，疑似夾帶對話內容或摘要片段"
            )
        if norm_ctx not in _ID_FIELD_KEY_NAMES and _UUID_VALUE_PATTERN.search(text):
            violations.append(f"規則1違反：欄位「{key_ctx}」的值含有 UUID 格式字串，疑似洩漏帳號／使用者識別碼")

    for key, lst in _iter_list_of_dicts(report):
        if _normalize_key(key) in REPORT_ALLOWLISTED_KEYS:
            continue
        violations.append(f"規則4違反：欄位「{key}」是一個物件陣列（{len(lst)} 筆），月報只准放彙總數字，不准逐筆列出個人資料")

    for section_name, section in (report.get("sections") or {}).items():
        if not isinstance(section, dict):
            continue
        sample_size = section.get("sampleSize")
        if sample_size is not None and sample_size < PRIVACY_MIN_GROUP_SIZE and not section.get("suppressed"):
            violations.append(f"規則3違反：區塊「{section_name}」樣本數 {sample_size} < 5，但沒有被標記為 suppressed，數字外洩風險")

    if violations:
        raise PrivacyViolationError("；".join(violations))
    return True


# ---------------------------------------------------------------------------
# ESG 月報 HTML 產出
# ---------------------------------------------------------------------------

_REPORT_HTML_STYLE = """
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", sans-serif;
         color: #1f2933; margin: 0; padding: 24px; background: #eef1f5; }
  .sheet { width: 210mm; min-height: 297mm; margin: 0 auto; background: #fff; padding: 18mm;
           box-shadow: 0 0 12px rgba(0,0,0,0.12); }
  h1 { font-size: 26px; margin: 0 0 4px; }
  .sub { color: #52606d; font-size: 13px; margin-bottom: 28px; }
  .section { margin-bottom: 26px; }
  .section h2 { font-size: 15px; color: #16324f; border-left: 4px solid #16324f;
                padding-left: 10px; margin: 0 0 12px; }
  .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  .metric { border: 1px solid #d9dfe6; border-radius: 6px; padding: 14px; }
  .metric .label { font-size: 12px; color: #52606d; margin-bottom: 6px; }
  .metric .value { font-size: 28px; font-weight: 700; color: #16324f; }
  .metric .value.suppressed { font-size: 15px; font-weight: 500; color: #9aa5b1; }
  .flag { display: inline-block; margin-top: 10px; padding: 4px 10px; border-radius: 4px;
          background: #fef3cd; color: #92620a; font-size: 12px; }
  .narrative { font-size: 14px; line-height: 1.8; background: #f4f6f8; border-radius: 6px;
               padding: 16px; }
  .gri-refs { font-size: 12px; color: #52606d; margin-top: 10px; }
  .privacy-note { margin-top: 30px; font-size: 11px; color: #9aa5b1; border-top: 1px solid #d9dfe6;
                  padding-top: 12px; }
  .footer { margin-top: 16px; font-size: 11px; color: #9aa5b1; }
  @media print {
    body { background: #fff; padding: 0; }
    .sheet { box-shadow: none; margin: 0; }
    @page { size: A4 portrait; margin: 16mm; }
  }
"""


def _metric_html(label, value, suppressed=False, is_pct=False, suffix=""):
    if suppressed or value is None:
        display = "資料不足（樣本 &lt; 5 人，依隱私規定不單獨呈現）" if suppressed else "—"
        css_class = "value suppressed"
    else:
        display = f"{_fmt_pct(value)}" if is_pct else f"{value}{suffix}"
        css_class = "value"
    return f"""<div class="metric">
        <div class="label">{html.escape(label)}</div>
        <div class="{css_class}">{display}</div>
      </div>"""


def render_esg_report_html(report):
    """需求單 4.3：ESG 成效月報 HTML（可直接列印成 A4 直式 PDF）。
    產出前（也就是這裡，正要變成看得到的文件的那一刻）一定再跑一次隱私鐵律檢查——
    就算呼叫端沒經過 build_esg_report()、直接手動組了一個 dict 傳進來，也一樣會被擋。"""
    enforce_privacy_guard(report)

    client = report.get("client") or {}
    period = report.get("reportPeriod") or {}
    sections = report.get("sections") or {}
    coverage = sections.get("coverage") or {}
    companionship = sections.get("companionship") or {}
    care = sections.get("care") or {}
    family_value = sections.get("familyValue") or {}
    gri = sections.get("gri") or {}

    low_util_flag = ""
    if coverage.get("lowUtilizationFlag"):
        low_util_flag = "<div class=\"flag\">席次使用率低於 50%——續約談判時建議一併討論推廣方案</div>"

    gri_refs = "".join(f"<div>{html.escape(str(ref))}</div>" for ref in gri.get("griReferences") or [])

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>ESG 成效月報 {html.escape(str(period.get('label') or ''))}</title>
<style>{_REPORT_HTML_STYLE}</style>
</head>
<body>
<div class="sheet">
  <h1>ESG 成效月報</h1>
  <div class="sub">{html.escape(str(client.get('name') or ''))}　·　{html.escape(str(period.get('label') or ''))}
    （{html.escape(str(period.get('start') or ''))} ~ {html.escape(str(period.get('end') or ''))}）</div>

  <div class="section">
    <h2>一、涵蓋與參與</h2>
    <div class="metrics">
      {_metric_html("合約席次數", coverage.get('seatQuota'))}
      {_metric_html("已啟用數", coverage.get('activeSeats'))}
      {_metric_html("實際使用數", coverage.get('actuallyUsedSeats'))}
      {_metric_html("啟用率", coverage.get('activationRate'), is_pct=True)}
    </div>
    {low_util_flag}
  </div>

  <div class="section">
    <h2>二、陪伴成效</h2>
    <div class="metrics">
      {_metric_html("平均每人每週對話次數", companionship.get('avgWeeklyCallCount'), suppressed=companionship.get('suppressed'), suffix=" 次")}
      {_metric_html("有意義陪伴日比例", companionship.get('meaningfulCompanionDayRatio'), suppressed=companionship.get('suppressed'), is_pct=True)}
      {_metric_html("平均通話長度", companionship.get('avgCallMinutes'), suppressed=companionship.get('suppressed'), suffix=" 分鐘")}
      {_metric_html("持續使用比例", companionship.get('continuedUsageRate'), suppressed=companionship.get('suppressed'), is_pct=True)}
    </div>
  </div>

  <div class="section">
    <h2>三、照護成效</h2>
    <div class="metrics">
      {_metric_html("用藥／回診提醒完成率", care.get('reminderCompletionRate'), suppressed=care.get('suppressed'), is_pct=True)}
      {_metric_html("關懷通知發出次數", care.get('careNotificationsSent'), suppressed=care.get('suppressed'), suffix=" 次")}
      {_metric_html("及時接住的異常次數", care.get('anomaliesCaughtInTime'), suppressed=care.get('suppressed'), suffix=" 次")}
    </div>
  </div>

  <div class="section">
    <h2>四、員工端價值</h2>
    <div class="metrics">
      {_metric_html("收到過近況／安全通知的家庭比例", family_value.get('familiesNotifiedRatio'), suppressed=family_value.get('suppressed'), is_pct=True)}
    </div>
  </div>

  <div class="section">
    <h2>五、GRI 對應</h2>
    <div class="narrative">{html.escape(str(gri.get('griNarrative') or ''))}</div>
    <div class="gri-refs">{gri_refs}</div>
  </div>

  <div class="privacy-note">
    本報告僅呈現彙總數字與比例，不含任何長輩姓名、帳號識別、聯絡方式或對話內容；
    任何分組人數低於 5 人的區塊，數字皆已依隱私規定遮蔽不單獨呈現。
  </div>
  <div class="footer">Munea 企業席次月結系統自動產出 · {html.escape(str(report.get('generatedAt') or ''))}</div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 月結整合（需求單 4、施工順序階段三）
# ---------------------------------------------------------------------------

def run_monthly_close_for_client(client, seats, period_start, period_end, *,
                                  existing_invoices=None, today=None,
                                  persist_invoice=True, raw_metrics=None):
    """對一家公司跑一次月結，同時出請款單與月報。
    請款單一定產出（逾期是催收的對象，不是不開單的理由）；月報則照需求單 4.3 鐵律，
    逾期 >= 7 天就不產、只回報原因，呼叫端（例如批次寄送流程）自己決定怎麼處理
    （例如：請款單照常寄，月報改成內部提醒催收，不寄給客戶）。"""
    invoice = generate_monthly_invoice(client, seats, period_start, period_end, persist=persist_invoice)
    result = {"invoice": invoice, "report": None, "reportBlocked": None}
    try:
        report = build_esg_report(
            client, seats, period_start, period_end,
            invoices=existing_invoices, raw_metrics=raw_metrics, today=today,
        )
        result["report"] = report
    except ClientOverdueBlockedError as exc:
        result["reportBlocked"] = {
            "reason": "overdue",
            "overdueDays": exc.overdue_days,
            "message": str(exc),
        }
    return result


def run_monthly_close(period_start=None, period_end=None, *, clients=None, today=None, persist_invoice=True):
    """需求單 4：每月一次月結，對『所有』企業客戶跑一輪，同時出請款單＋月報。
    clients 可注入（測試／已經查好時用），不給就用 enterprise_seats.list_clients() 真查全部。
    回傳 {clientId: {"invoice":…, "report":…, "reportBlocked":…}} 給呼叫端逐家寄送／下載。"""
    if period_start is None or period_end is None:
        period_start, period_end = resolve_billing_period(today=today)
    clients = clients if clients is not None else enterprise_seats.list_clients()
    results = {}
    for client in clients:
        client_id = client.get("id")
        seats = enterprise_seats.list_seats(client_id=client_id)
        results[client_id] = run_monthly_close_for_client(
            client, seats, period_start, period_end,
            persist_invoice=persist_invoice, today=today,
        )
    return results

