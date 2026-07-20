# -*- coding: utf-8 -*-
"""
Munea 企業席次 · 資料存取 + 狀態機（需求單 2.1-2.5、3.2、3.3）。

只放資料層與業務邏輯，不放 HTTP 路由——engine/server.py 的 /admin/enterprise/*
端點呼叫這裡的 xxx_response() 函式（同 server.py 既有 admin 端點「_response 函式」的
命名慣例）。Supabase 可用時走雲端四張表；連不上、缺表、或未設定 provider 時退本地
JSON 檔（跟 billing_store.json 那套本地備援同一個節奏，見 server.py 的 load_billing_store
/ save_billing_store）。

鐵律（需求單 2.5）：任何一筆非 Apple 來源的會員資格，subscription_ledger.grant_ref 必填；
沒有來源的授予一律拒絕——這是防止「改了 Pro 但沒人記得為什麼」的唯一手段。
見 validate_subscription_grant_ref()；資料庫另有 check constraint 當最後防線
（supabase/sql/020_enterprise_seats.sql）。

不碰的東西：enterprise_billing.py（月結／請款單／ESG 月報產出邏輯）——那是另一支檔案的責任，
本檔只提供 enterprise_seats / enterprise_clients / enterprise_seat_events 的資料與狀態機，
enterprise_invoices 只在 SQL 建表，CRUD 留給 billing 那支檔案自己加。
"""
import csv
import io
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import supabase_adapter

LOGGER = logging.getLogger("munea.enterprise_seats")
_JSON_STORE_LOCK = threading.RLock()

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENTS_PATH = os.environ.get("MUNEA_ENTERPRISE_CLIENTS_PATH") or os.path.join(HERE, "enterprise_clients_store.json")
SEATS_PATH = os.environ.get("MUNEA_ENTERPRISE_SEATS_PATH") or os.path.join(HERE, "enterprise_seats_store.json")
SEAT_EVENTS_PATH = os.environ.get("MUNEA_ENTERPRISE_SEAT_EVENTS_PATH") or os.path.join(HERE, "enterprise_seat_events_store.json")
LOCAL_GRANTS_PATH = os.environ.get("MUNEA_ENTERPRISE_LOCAL_GRANTS_PATH") or os.path.join(HERE, "enterprise_local_grants_store.json")
# 跟 engine/enterprise_billing.py 用同一個環境變數／同一個預設檔名（不 import 那支檔案，
# 避免循環 import；只是讀同一份本機備援檔）——Supabase 未啟用時，
# assert_client_has_paid_invoice() 才能看到 mark-paid 端點剛寫進本地檔的請款單狀態，
# 不然本機／測試模式下永遠查不到、鐵律 2 會一路誤擋（安全但沒用）。
INVOICES_PATH = os.environ.get("MUNEA_ENTERPRISE_INVOICES_PATH") or os.path.join(HERE, "enterprise_invoices_store.json")

CLIENT_PLAN_TIERS = ("plus", "pro")
CLIENT_STATUSES = ("active", "expiring", "ended")
SEAT_STATUSES = ("pending", "waiting", "active", "grace", "released")
VALID_RELEASE_REASONS = ("contract_end", "removed_by_client", "converted_to_personal")
GRACE_PERIOD_DAYS = 30

# 需求單 5A：waiting＝已比對到帳號、但該帳號個人已購買的等級 > 企業方案等級，暫不授予。
# active <-> waiting 雙向：綁定時可能一開始就判定 waiting；授予時若發現個人已到期，
# grant_enterprise_membership() 會呼叫 transition_seat 把 waiting 轉正成 active。
# active -> waiting 這條是為了涵蓋『先綁定成 active、稍後批次授予才發現個人等級較高』的情境
#（3.2 匯入時只比對『是否已註冊』，沒有比對個人訂閱等級——那是授予當下才查的）。
ALLOWED_SEAT_TRANSITIONS = {
    "pending": {"active", "waiting", "released"},
    "waiting": {"active", "released"},
    "active": {"grace", "waiting"},
    "grace": {"released"},
    "released": set(),
}


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iso_plus_days(iso_str, days):
    try:
        base = datetime.strptime(str(iso_str), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_uuid(value):
    try:
        uuid.UUID(str(value or ""))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _is_missing_table_error(exc):
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


def normalize_client(item=None):
    item = item or {}
    plan_tier = item.get("planTier") or item.get("plan_tier") or "plus"
    status = item.get("status") or "active"
    return {
        "id": item.get("id") or "",
        "name": str(item.get("name") or "").strip()[:200],
        # 選填、非強制（2026-07-20 二次需求）：給請款單號一個比 id 前 8 碼好認的代碼；
        # 沒填就是 None，enterprise_billing.py 的 derive_client_code() 目前仍走
        # id 前 8 碼那條路，兩邊本次不強制耦合。
        "clientCode": item.get("clientCode") or item.get("client_code"),
        "taxId": item.get("taxId") or item.get("tax_id"),
        "billingAddress": item.get("billingAddress") or item.get("billing_address"),
        "contactName": item.get("contactName") or item.get("contact_name"),
        "contactEmail": item.get("contactEmail") or item.get("contact_email"),
        "contactPhone": item.get("contactPhone") or item.get("contact_phone"),
        "planTier": plan_tier if plan_tier in CLIENT_PLAN_TIERS else "plus",
        "unitPriceTwd": _safe_number(
            item.get("unitPriceTwd") if item.get("unitPriceTwd") is not None else item.get("unit_price_twd")
        ),
        "contractStart": item.get("contractStart") or item.get("contract_start"),
        "contractEnd": item.get("contractEnd") or item.get("contract_end"),
        "seatQuota": int(item.get("seatQuota") or item.get("seat_quota") or 0),
        "status": status if status in CLIENT_STATUSES else "active",
        "reportRecipients": item.get("reportRecipients") or item.get("report_recipients") or [],
        "notes": item.get("notes"),
        "createdAt": item.get("createdAt") or item.get("created_at"),
        "updatedAt": item.get("updatedAt") or item.get("updated_at"),
    }


def normalize_seat(item=None):
    item = item or {}
    status = item.get("status") or "pending"
    return {
        "id": item.get("id") or "",
        "enterpriseClientId": item.get("enterpriseClientId") or item.get("enterprise_client_id") or "",
        "inviteEmail": str(item.get("inviteEmail") or item.get("invite_email") or "").strip().lower(),
        "accountId": item.get("accountId") or item.get("account_id"),
        "status": status if status in SEAT_STATUSES else "pending",
        "activatedAt": item.get("activatedAt") or item.get("activated_at"),
        "waitingUntil": item.get("waitingUntil") or item.get("waiting_until"),
        "graceStartedAt": item.get("graceStartedAt") or item.get("grace_started_at"),
        "graceUntil": item.get("graceUntil") or item.get("grace_until"),
        "releasedAt": item.get("releasedAt") or item.get("released_at"),
        "releasedReason": item.get("releasedReason") or item.get("released_reason"),
        "notes": item.get("notes"),
        "createdAt": item.get("createdAt") or item.get("created_at"),
        "updatedAt": item.get("updatedAt") or item.get("updated_at"),
    }


def normalize_seat_event(item=None):
    item = item or {}
    return {
        "id": item.get("id") or "",
        "seatId": item.get("seatId") or item.get("seat_id") or "",
        "fromStatus": item.get("fromStatus") or item.get("from_status"),
        "toStatus": item.get("toStatus") or item.get("to_status") or "",
        "actor": item.get("actor") or "admin",
        "reason": item.get("reason"),
        "metadata": item.get("metadata") or {},
        "createdAt": item.get("createdAt") or item.get("created_at"),
    }


# ---- 企業客戶 CRUD（2.1）----

def list_clients(query=None, status=None):
    backend = _backend()
    try:
        remote = backend.load_enterprise_clients(query=query, status=status)
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("load enterprise clients from Supabase", exc)
    items = _read_json_file(CLIENTS_PATH, [])
    if not isinstance(items, list):
        items = []
    items = [normalize_client(item) for item in items]
    if status:
        items = [i for i in items if i["status"] == status]
    if query:
        q = str(query).strip().lower()
        items = [
            i for i in items
            if q in (i.get("name") or "").lower()
            or q in (i.get("taxId") or "").lower()
            or q in (i.get("contactEmail") or "").lower()
        ]
    items.sort(key=lambda i: i.get("createdAt") or "", reverse=True)
    return items


def get_client(client_id):
    if not client_id:
        return None
    backend = _backend()
    try:
        remote = backend.get_enterprise_client(client_id)
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"get enterprise client {client_id} from Supabase", exc)
    items = _read_json_file(CLIENTS_PATH, [])
    if not isinstance(items, list):
        items = []
    for item in items:
        if item.get("id") == client_id:
            return normalize_client(item)
    return None


def upsert_client(payload):
    """整列覆寫語意（跟 supabase_adapter.save_enterprise_client 一致，不是局部 PATCH）。
    呼叫端若要做「部分更新」，要先把既有資料與 patch 合併好再傳進來——
    見 enterprise_clients_response() 的 update 分支。"""
    client = normalize_client(payload)
    backend = _backend()
    try:
        remote = backend.save_enterprise_client(client)
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("save enterprise client to Supabase", exc)
    items = _read_json_file(CLIENTS_PATH, [])
    if not isinstance(items, list):
        items = []
    now = _utc_now()
    if not client.get("id"):
        client["id"] = str(uuid.uuid4())
        client["createdAt"] = now
    client["updatedAt"] = now
    replaced = False
    for idx, item in enumerate(items):
        if item.get("id") == client["id"]:
            client["createdAt"] = item.get("createdAt") or client.get("createdAt") or now
            items[idx] = client
            replaced = True
            break
    if not replaced:
        client.setdefault("createdAt", now)
        items.append(client)
    _write_json_file(CLIENTS_PATH, items)
    return client


# ---- 席次 CRUD（2.2）----

def list_seats(client_id=None, status=None, account_id=None, invite_email=None):
    backend = _backend()
    try:
        remote = backend.load_enterprise_seats(
            client_id=client_id, status=status, account_id=account_id, invite_email=invite_email,
        )
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("load enterprise seats from Supabase", exc)
    items = _read_json_file(SEATS_PATH, [])
    if not isinstance(items, list):
        items = []
    items = [normalize_seat(item) for item in items]
    if client_id:
        items = [i for i in items if i["enterpriseClientId"] == client_id]
    if status:
        items = [i for i in items if i["status"] == status]
    if account_id:
        items = [i for i in items if i.get("accountId") == account_id]
    if invite_email:
        needle = str(invite_email).strip().lower()
        items = [i for i in items if needle in (i["inviteEmail"] or "")]
    items.sort(key=lambda i: i.get("createdAt") or "")
    return items


def get_seat(seat_id):
    if not seat_id:
        return None
    backend = _backend()
    try:
        remote = backend.get_enterprise_seat(seat_id)
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"get enterprise seat {seat_id} from Supabase", exc)
    items = _read_json_file(SEATS_PATH, [])
    if not isinstance(items, list):
        items = []
    for item in items:
        if item.get("id") == seat_id:
            return normalize_seat(item)
    return None


def find_seats_by_email(email, exclude_client_id=None):
    """該 email 目前掛在哪些席次上（不限公司）。用於 3.2 預檢第 4 種情況：
    『幾筆已屬於其他公司』。exclude_client_id 用來排除自己這家公司（同公司內的
    重複交給 duplicate 分類處理，不算『其他公司』）。"""
    email = str(email or "").strip().lower()
    if not email:
        return []
    seats = [s for s in list_seats(invite_email=email) if s["inviteEmail"] == email]
    if exclude_client_id:
        seats = [s for s in seats if s["enterpriseClientId"] != exclude_client_id]
    return seats


def create_pending_seat(client_id, email, note=None):
    seat = normalize_seat({
        "enterpriseClientId": client_id,
        "inviteEmail": email,
        "status": "pending",
        "notes": note,
    })
    backend = _backend()
    try:
        remote = backend.create_enterprise_seat(seat)
        if remote is not None:
            write_seat_event(
                {"id": remote["id"], "status": None}, "pending",
                actor="system", reason="seat_created_from_import",
                metadata={"source": "csv_import"},
            )
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("create enterprise seat in Supabase", exc)
    items = _read_json_file(SEATS_PATH, [])
    if not isinstance(items, list):
        items = []
    now = _utc_now()
    record = {**seat, "id": str(uuid.uuid4()), "createdAt": now, "updatedAt": now}
    items.append(record)
    _write_json_file(SEATS_PATH, items)
    write_seat_event(
        {"id": record["id"], "status": None}, "pending",
        actor="system", reason="seat_created_from_import",
        metadata={"source": "csv_import"},
    )
    return record


# ---- 異動紀錄 + 狀態機（2.3、需求單施工順序階段一）----

_SEAT_PATCH_FIELD_MAP = {
    "status": "status",
    "accountId": "account_id",
    "activatedAt": "activated_at",
    "waitingUntil": "waiting_until",
    "graceStartedAt": "grace_started_at",
    "graceUntil": "grace_until",
    "releasedAt": "released_at",
    "releasedReason": "released_reason",
    "notes": "notes",
}


def _seat_patch_to_row(patch):
    return {_SEAT_PATCH_FIELD_MAP[k]: v for k, v in patch.items() if k in _SEAT_PATCH_FIELD_MAP}


def _patch_seat(seat_id, patch):
    backend = _backend()
    try:
        remote = backend.update_enterprise_seat(seat_id, _seat_patch_to_row(patch))
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"update enterprise seat {seat_id} in Supabase", exc)
    items = _read_json_file(SEATS_PATH, [])
    if not isinstance(items, list):
        items = []
    updated = None
    for idx, item in enumerate(items):
        if item.get("id") == seat_id:
            item = {**item, **patch, "updatedAt": _utc_now()}
            items[idx] = item
            updated = normalize_seat(item)
            break
    if updated is None:
        raise ValueError("enterprise_seat_not_found")
    _write_json_file(SEATS_PATH, items)
    return updated


def write_seat_event(seat, to_status, actor, reason, metadata=None):
    """只負責落一筆異動紀錄，不檢查狀態機——給『狀態沒變但要留痕』的場景用（例如批次授予、
    剛建立的席次）。真的要轉狀態，用 transition_seat()，它會呼叫這個函式。
    seat 只需要 id 與 status（status=None 代表『這是這筆席次的第一筆事件』）。"""
    event = {
        "seatId": seat.get("id"),
        "fromStatus": seat.get("status"),
        "toStatus": to_status,
        "actor": actor or "admin",
        "reason": reason,
        "metadata": metadata or {},
    }
    backend = _backend()
    try:
        remote = backend.append_enterprise_seat_event(event)
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("append enterprise seat event to Supabase", exc)
    items = _read_json_file(SEAT_EVENTS_PATH, [])
    if not isinstance(items, list):
        items = []
    record = normalize_seat_event({**event, "id": str(uuid.uuid4()), "createdAt": _utc_now()})
    items.append(record)
    _write_json_file(SEAT_EVENTS_PATH, items)
    return record


def load_seat_events(seat_id=None, limit=500):
    backend = _backend()
    try:
        remote = backend.load_enterprise_seat_events(seat_id=seat_id, limit=limit)
        if remote is not None:
            return remote
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("load enterprise seat events from Supabase", exc)
    items = _read_json_file(SEAT_EVENTS_PATH, [])
    if not isinstance(items, list):
        items = []
    items = [normalize_seat_event(i) for i in items]
    if seat_id:
        items = [i for i in items if i["seatId"] == seat_id]
    items.sort(key=lambda i: i.get("createdAt") or "", reverse=True)
    return items[:limit]


def transition_seat(seat_id, to_status, actor="admin", reason=None, *, account_id=None,
                     released_reason=None, waiting_until=None):
    """需求單 2.2＋5A 狀態機：pending -> {active, waiting} -> grace -> released
    （另允許 pending -> released 撤銷還沒生效的邀請；active <-> waiting 雙向見
    ALLOWED_SEAT_TRANSITIONS 上方註解）。每次流轉都寫一筆 enterprise_seat_events——
    鐵律，不是可選項。

    account_id：轉 active／waiting 時要綁定的帳號；沒帶就沿用該席次現有的 accountId
   （給『同一顆席次在 waiting 與 active 間來回』時不必每次重傳）。
    waiting_until：轉 waiting 時，記下個人訂閱到期日（需求單 5A『記下個人訂閱到期日』）；
    轉 active 時一律清空（不管是不是從 waiting 轉過來，接手了就沒有等待這回事）。"""
    seat = get_seat(seat_id)
    if not seat:
        raise ValueError("enterprise_seat_not_found")
    current = seat.get("status") or "pending"
    allowed = ALLOWED_SEAT_TRANSITIONS.get(current, set())
    if to_status not in allowed:
        raise ValueError(f"invalid_seat_transition:{current}->{to_status}")

    patch = {"status": to_status}
    if to_status in ("active", "waiting"):
        resolved_account_id = account_id or seat.get("accountId")
        if not resolved_account_id or not _is_uuid(resolved_account_id):
            raise ValueError("valid_account_id_required_to_activate_seat")
        patch["accountId"] = resolved_account_id
        if to_status == "active":
            patch["activatedAt"] = _utc_now()
            patch["waitingUntil"] = None
        else:
            patch["waitingUntil"] = waiting_until
    elif to_status == "grace":
        now = _utc_now()
        patch["graceStartedAt"] = now
        patch["graceUntil"] = _iso_plus_days(now, GRACE_PERIOD_DAYS)
    elif to_status == "released":
        if released_reason not in VALID_RELEASE_REASONS:
            raise ValueError("invalid_released_reason")
        patch["releasedAt"] = _utc_now()
        patch["releasedReason"] = released_reason

    updated = _patch_seat(seat_id, patch)
    write_seat_event(
        seat, to_status, actor, reason,
        metadata={"patch": {k: v for k, v in patch.items() if k != "status"}},
    )
    return updated


# ---- 會員資格授予（2.5、5.1、5A 三條鐵律 + 3.3 批次授予）----
#
# 三條不可妥協的鐵律（違反任一條都要在 grant_enterprise_membership() 內被擋下，
# 不是靠呼叫端自律）：
#   1. provider=enterprise 的授予，grant_ref 必填——validate_subscription_grant_ref()
#   2. 未付款不得開通：授予前必查該公司「當期」請款單狀態為 paid（或已開發票的 invoiced）
#      ——assert_client_has_paid_invoice()。查不到任何一張已付款的請款單一律拒絕，
#      沒有任何自動開通的旁路。
#   3. 不得重複授予：先比對帳號現有的個人（非企業）有效訂閱等級——
#      企業等級大於等於個人等級才正常授予；企業等級低於個人等級時，
#      席次轉 waiting、不寫 subscription_ledger、記下個人訂閱到期日，
#      等到期當天由本函式自動接手（見 5A）。

PLAN_RANK = {"free": 0, "plus": 1, "pro": 2}


def _plan_rank(tier):
    return PLAN_RANK.get(str(tier or "free").strip().lower(), 0)


def validate_subscription_grant_ref(provider, grant_ref):
    """需求單 2.5 鐵律 1：任何一筆非 Apple 來源的會員資格，grant_ref 必填。
    沒有來源的授予一律拒絕——這是防止改了 Pro 但沒人記得為什麼的唯一手段。
    資料庫另有 subscription_ledger_enterprise_requires_grant_ref check constraint 做最後防線
    （見 supabase/sql/020_enterprise_seats.sql），這裡是 app 層先擋，給更快更明確的錯誤訊息。"""
    provider_key = str(provider or "").strip().lower()
    if provider_key != "apple" and not grant_ref:
        raise ValueError("grant_ref_required_for_non_apple_provider")


PAID_INVOICE_STATUSES = ("paid", "invoiced")


def _read_local_invoices(client_id=None):
    """讀 enterprise_billing.py 本地備援檔（同一個環境變數／預設路徑，不 import 該模組）。
    Supabase 未啟用時的最後一道查詢——沒有這層，本機模式下 mark-paid 之後
    grant_enterprise_membership 永遠查不到剛入帳的請款單，鐵律 2 會一路誤擋。"""
    items = _read_json_file(INVOICES_PATH, [])
    if not isinstance(items, list):
        items = []
    if client_id:
        items = [i for i in items if i.get("enterpriseClientId") == client_id]
    items.sort(key=lambda i: i.get("periodStart") or "", reverse=True)
    return items


def client_latest_invoice(client_id):
    """該公司「當期」請款單，即依 period_start 排序最新一張（見 supabase_adapter.py
    load_enterprise_invoices 的 order）。請款單的產生與收款登記屬 engine/enterprise_billing.py，
    這裡只唯讀。Supabase 啟用但查不到任何請款單時，安全預設視為未付款（鐵律 2 寧可
    誤擋、不可誤放）；Supabase 未啟用（本機／測試）才退到本地備援檔，讓 mark-paid
    寫進去的狀態真的能被看見。"""
    backend = _backend()
    try:
        invoices = backend.load_enterprise_invoices(client_id=client_id, limit=1)
        if invoices is not None:
            return invoices[0] if invoices else None
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"load enterprise invoices for {client_id}", exc)
    local = _read_local_invoices(client_id=client_id)
    return local[0] if local else None


def assert_client_has_paid_invoice(client_id):
    """需求單 5.1 鐵律 2「未付款不得開通」：授予前必須有一張狀態為 paid（或已開發票的
    invoiced）的請款單，否則一律拒絕，不存在任何先開通、之後補款的例外路徑。
    連 Edward 個案核准的 3 到 5 席試辦，也是在 enterprise_invoices 手動記一筆 paid
    才能過這關，不是繞過程式碼另開後門（需求單 5.1 例外條款原文）。"""
    invoice = client_latest_invoice(client_id)
    if not invoice or invoice.get("status") not in PAID_INVOICE_STATUSES:
        raise ValueError("enterprise_invoice_not_paid")


INDIVIDUAL_ACTIVE_STATUSES = ("active", "trial", "grace_period")


def _individual_active_ledger(account_id):
    """讀該帳號目前非企業來源的有效訂閱（provider 不是 enterprise、且 status 仍在生效
    狀態）。用於需求單 5A：判斷長輩是不是已經自己在 App Store 買了 Plus 或 Pro。
    找不到、或目前有效訂閱本來就是企業授予的，一律回 None，代表沒有個人已購買要顧慮。
    本機 JSON 備援模式（Supabase 未設定）查不到個人訂閱資料——billing_store.json 是
    server.py 另一支檔案管理的，這裡不跨檔案讀取；回 None（視為個人無購買），
    這是已知限制，只在 Supabase 已配置時才有真正的比對能力，回報中會明確標註。"""
    backend = _backend()
    row = None
    try:
        row = backend.get_latest_subscription_ledger(account_id)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"get latest subscription ledger for {account_id}", exc)
        row = None
    if not row:
        return None
    provider = str(row.get("provider") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    if provider == "enterprise" or status not in INDIVIDUAL_ACTIVE_STATUSES:
        return None
    return row


def _find_active_ledger_by_grant_ref(grant_ref):
    """鐵律 3 的 idempotent 防線：同一顆席次已經授予過，就不要再插第二筆
    subscription_ledger（不得重複授予不只指個人跟企業，也包含同一筆企業授予被按兩次）。"""
    backend = _backend()
    try:
        row = backend.get_subscription_ledger_by_grant_ref(grant_ref)
        if row is not None:
            status = str(row.get("status") or "").strip().lower()
            return row if status == "active" else None
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"get subscription ledger by grant_ref {grant_ref}", exc)
    grants = _read_json_file(LOCAL_GRANTS_PATH, [])
    if not isinstance(grants, list):
        return None
    for g in reversed(grants):
        if g.get("grantRef") == grant_ref:
            return g
    return None


def grant_enterprise_membership(seat_id, actor="admin", reason="batch_grant"):
    """需求單 3.3 批次授予：對一筆已綁定帳號的席次寫入 subscription_ledger
    （provider=enterprise、active_plan=公司的 plan_tier、grant_ref=這筆席次 id），
    並在 enterprise_seat_events 留一筆痕跡。

    三條鐵律依序檢查，任一條不過就整個函式失敗或轉 waiting，不會有部分執行：
      1. grant_ref 必填 —— validate_subscription_grant_ref()
      2. 未付款不得開通 —— assert_client_has_paid_invoice()，ValueError 直接中止，不授予
      3. 不得重複授予 —— 比對個人現有等級；個人等級較高就轉 waiting、不寫 ledger

    回傳：
      granted=True 時 → granted/waiting/ledger/seat
      waiting=True 時 → granted=False、waiting=True、seat、reason=individual_plan_higher
    """
    seat = get_seat(seat_id)
    if not seat:
        raise ValueError("enterprise_seat_not_found")
    if seat.get("status") not in ("active", "waiting", "grace"):
        raise ValueError("seat_must_be_active_or_waiting_to_grant_membership")
    account_id = seat.get("accountId")
    if not account_id:
        raise ValueError("seat_has_no_bound_account")
    client = get_client(seat["enterpriseClientId"])
    if not client:
        raise ValueError("enterprise_client_not_found")

    # 鐵律 2：未付款不得開通，不管席次現在是什麼狀態，這關永遠先過，沒有旁路。
    assert_client_has_paid_invoice(client["id"])

    # 鐵律 3：不得重複授予，先看帳號現有的個人（非企業）有效訂閱等級。
    individual = _individual_active_ledger(account_id)
    individual_plan = (individual or {}).get("active_plan") or (individual or {}).get("activePlan") or "free"
    if individual and _plan_rank(individual_plan) > _plan_rank(client["planTier"]):
        expires_at = individual.get("expires_at") or individual.get("expiresAt")
        if seat.get("status") == "waiting":
            updated_seat = seat
        else:
            updated_seat = transition_seat(
                seat_id, "waiting", actor=actor, reason="grant_blocked_individual_plan_higher",
                account_id=account_id, waiting_until=expires_at,
            )
        return {
            "granted": False, "waiting": True, "seat": updated_seat,
            "reason": "individual_plan_higher",
            "individualPlan": individual_plan, "individualExpiresAt": expires_at,
        }

    # 鐵律 1：grant_ref 必填（企業來源永遠有 grant_ref=seat id，這裡主要是防禦 seat.id 空字串）。
    grant_ref = seat["id"]
    validate_subscription_grant_ref("enterprise", grant_ref)

    # 鐵律 3 續：同一席次已經授予過，別再插第二筆（idempotent，不算錯誤）。
    existing_grant = _find_active_ledger_by_grant_ref(grant_ref)
    if existing_grant:
        return {"granted": True, "waiting": False, "ledger": existing_grant, "seat": seat, "idempotent": True}

    payload = {
        "account_id": account_id,
        "platform": "web",
        "provider": "enterprise",
        "product_id": f"enterprise:{client['planTier']}",
        "status": "active",
        "active_plan": client["planTier"],
        "entitlements": {},
        "grant_ref": grant_ref,
        "verified_at": _utc_now(),
        "raw_event_ref": f"enterprise_client:{client['id']}",
    }

    ledger_row = None
    backend = _backend()
    try:
        ledger_row = backend.insert_enterprise_subscription_grant(payload)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("insert enterprise subscription grant to Supabase", exc)
    if ledger_row is None:
        ledger_row = {
            "accountId": account_id,
            "provider": "enterprise",
            "activePlan": client["planTier"],
            "grantRef": grant_ref,
            "status": "active",
            "verifiedAt": _utc_now(),
        }
        grants = _read_json_file(LOCAL_GRANTS_PATH, [])
        if not isinstance(grants, list):
            grants = []
        grants.append(ledger_row)
        _write_json_file(LOCAL_GRANTS_PATH, grants)

    # 原本是 waiting（個人剛好到期、輪到企業接手）就順手把席次轉正成 active。
    seat_after = seat
    if seat.get("status") == "waiting":
        seat_after = transition_seat(
            seat_id, "active", actor=actor, reason="individual_plan_expired_handover",
            account_id=account_id,
        )

    write_seat_event(
        seat_after, seat_after.get("status"), actor, reason,
        metadata={
            "grantRef": grant_ref,
            "planTier": client["planTier"],
            "enterpriseClientId": client["id"],
            "accountId": account_id,
        },
    )
    return {"granted": True, "waiting": False, "ledger": ledger_row, "seat": seat_after}


def batch_grant_enterprise_membership(seat_ids, actor="admin", reason="batch_grant"):
    """需求單 3.3、3.6 /admin/enterprise/seats/grant：對多筆席次批次授予，逐筆呼叫
    grant_enterprise_membership()，單筆失敗不影響其他筆，回傳逐筆結果，不是全部回滾。"""
    results = []
    for seat_id in seat_ids or []:
        try:
            outcome = grant_enterprise_membership(seat_id, actor=actor, reason=reason)
            results.append({"seatId": seat_id, "ok": True, **outcome})
        except Exception as exc:
            results.append({"seatId": seat_id, "ok": False, "error": str(exc)})
    granted = sum(1 for r in results if r.get("ok") and r.get("granted"))
    waiting = sum(1 for r in results if r.get("ok") and r.get("waiting"))
    blocked = sum(1 for r in results if not r.get("ok"))
    return {
        "results": results,
        "summary": {"granted": granted, "waiting": waiting, "blocked": blocked, "total": len(results)},
    }


# ---- 名單匯入（3.2 五種分類預檢 + 執行匯入）----

IMPORT_CSV_EMAIL_KEYS = ("email", "e-mail", "信箱", "電子郵件")
IMPORT_CSV_NOTE_KEYS = ("備註", "note", "notes", "remark")


def parse_seat_import_csv(csv_text):
    """需求單 3.2 範本欄位：email（必填）、備註（選填）。欄名中英皆收，不管大小寫。"""
    reader = csv.DictReader(io.StringIO(csv_text or ""))
    rows = []
    for row in reader:
        email, note = None, None
        for key, value in row.items():
            key_norm = str(key or "").strip().lower()
            if key_norm in IMPORT_CSV_EMAIL_KEYS:
                email = value
            elif key_norm in IMPORT_CSV_NOTE_KEYS:
                note = value
        rows.append({"email": email, "note": note})
    return rows


def build_seat_import_template_csv():
    """3.2 範本匯出：CSV，欄位 email(必填)、備註(選填)。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "備註"])
    writer.writerow(["example@company.com", ""])
    return buf.getvalue()


def build_seat_export_csv(client_id=None, status=None):
    """3.6 /admin/enterprise/seats/export：匯出現有席次明細（不是範本，範本另呼叫
    build_seat_import_template_csv）。"""
    seats = list_seats(client_id=client_id, status=status)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "status", "account_id", "activated_at", "waiting_until", "grace_until", "released_at", "note"])
    for s in seats:
        writer.writerow([
            s.get("inviteEmail", ""), s.get("status", ""), s.get("accountId") or "",
            s.get("activatedAt") or "", s.get("waitingUntil") or "", s.get("graceUntil") or "",
            s.get("releasedAt") or "", s.get("notes") or "",
        ])
    return buf.getvalue()


def _categorize_import_rows(client, rows):
    """3.2 預檢核心：五種分類共用邏輯，import_preview（唯讀）與 import_commit（真的寫入）
    都呼叫這個函式，避免預檢結果跟實際匯入結果兜不起來。

    判斷順序（一封 email 只落在一個分類）：
      1. 空或格式不對，直接跳過，不計入任何分類，避免髒資料污染統計
      2. 這批次裡重複、或本公司已存在，歸 duplicates
      3. 屬於其他公司的既有席次，歸 ownedByOtherClient，一律擋下不自動搶
      4. 加進來後會超過 seat_quota，歸 overQuota（不論原本是新的還是已註冊）
      5. 其餘：該 email 已有對應的已註冊帳號，歸 alreadyRegistered；否則歸 newSeats
    """
    existing_client_seats = list_seats(client_id=client["id"])
    existing_emails = {s["inviteEmail"] for s in existing_client_seats}
    occupied = len([s for s in existing_client_seats if s["status"] != "released"])
    quota = int(client.get("seatQuota") or 0)

    buckets = {"newSeats": [], "alreadyRegistered": [], "duplicates": [], "ownedByOtherClient": [], "overQuota": []}
    seen_in_batch = set()
    projected = occupied
    backend = _backend()

    for raw in rows or []:
        email = str((raw or {}).get("email") or "").strip().lower()
        note = (raw or {}).get("note") or (raw or {}).get("備註") or (raw or {}).get("notes")
        if not email or "@" not in email:
            continue
        entry = {"email": email, "note": note}
        if email in seen_in_batch or email in existing_emails:
            buckets["duplicates"].append(entry)
            continue
        seen_in_batch.add(email)

        others = find_seats_by_email(email, exclude_client_id=client["id"])
        if others:
            buckets["ownedByOtherClient"].append({**entry, "ownedByClientId": others[0]["enterpriseClientId"]})
            continue

        account_id = None
        try:
            auth_user = backend.find_auth_user_by_email(email)
        except Exception as exc:
            if backend.enabled() and not _is_missing_table_error(exc):
                raise
            _log_fallback(f"find auth user by email {email}", exc)
            auth_user = None
        if auth_user and auth_user.get("id"):
            try:
                identity = backend.resolve_auth_identity(auth_user["id"])
                account_id = (identity or {}).get("accountId")
            except Exception as exc:
                if backend.enabled() and not _is_missing_table_error(exc):
                    raise
                _log_fallback(f"resolve auth identity for {email}", exc)

        projected += 1
        target_entry = {**entry, "accountId": account_id} if account_id else entry
        if quota and projected > quota:
            buckets["overQuota"].append({**target_entry, "wouldBe": "alreadyRegistered" if account_id else "newSeats"})
        elif account_id:
            buckets["alreadyRegistered"].append(target_entry)
        else:
            buckets["newSeats"].append(target_entry)

    return buckets


def import_preview(client_id, rows):
    """3.6 /admin/enterprise/seats/import-preview：唯讀，不寫入任何資料。"""
    client = get_client(client_id)
    if not client:
        raise ValueError("enterprise_client_not_found")
    return _categorize_import_rows(client, rows)


def import_commit(client_id, rows, actor="admin", confirm_over_quota=False):
    """3.6 /admin/enterprise/seats/import-commit：真的寫入。
    newSeats 建 pending；alreadyRegistered 建立後立刻轉 active（綁帳號，對齊 2.2
    狀態圖「該 email 註冊或比對成功轉 active」）——注意這裡只是綁定，不是授予會員資格，
    後者是分開的 3.3 批次授予，仍會走鐵律 2、3 的付款與個人等級檢查。duplicates 與
    ownedByOtherClient 一律跳過，不自動搶。overQuota 預設跳過，confirm_over_quota=True
    時才依原本分類（新增或已註冊）照常匯入，這是介面上「超過要二次確認」的伺服器端落地。"""
    client = get_client(client_id)
    if not client:
        raise ValueError("enterprise_client_not_found")
    buckets = _categorize_import_rows(client, rows)

    created, activated, skipped, failed = [], [], [], []
    to_process = list(buckets["newSeats"]) + list(buckets["alreadyRegistered"])
    if confirm_over_quota:
        to_process += list(buckets["overQuota"])
    else:
        skipped += [{**e, "skipReason": "over_quota"} for e in buckets["overQuota"]]
    skipped += [{**e, "skipReason": "duplicate"} for e in buckets["duplicates"]]
    skipped += [{**e, "skipReason": "owned_by_other_client"} for e in buckets["ownedByOtherClient"]]

    for entry in to_process:
        email = entry["email"]
        try:
            seat = create_pending_seat(client_id, email, note=entry.get("note"))
            if entry.get("accountId"):
                seat = transition_seat(
                    seat["id"], "active", actor=actor, reason="import_matched_registered_account",
                    account_id=entry["accountId"],
                )
                activated.append(seat)
            else:
                created.append(seat)
        except Exception as exc:
            failed.append({**entry, "error": str(exc)})

    return {
        "created": created,
        "activated": activated,
        "skipped": skipped,
        "failed": failed,
        "summary": {
            "createdCount": len(created),
            "activatedCount": len(activated),
            "skippedCount": len(skipped),
            "failedCount": len(failed),
        },
    }


# ---- 後台總覽（3.1 企業客戶列表 + 3.4 單一公司明細）----

def _seat_counts_for_client(client_id):
    seats = list_seats(client_id=client_id)
    counts = {"pending": 0, "waiting": 0, "active": 0, "grace": 0, "released": 0}
    for s in seats:
        status = s.get("status") or "pending"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _client_status_light(client, overdue_days):
    """statusLight：overdue（有逾期未付欠款）優先於 expiring（合約 30 天內到期），其餘 ok。"""
    if overdue_days and overdue_days > 0:
        return "overdue"
    contract_end = client.get("contractEnd") or client.get("contract_end")
    if contract_end:
        try:
            end_date = datetime.strptime(str(contract_end)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_left = (end_date - datetime.now(timezone.utc)).days
            if days_left <= 30:
                return "expiring"
        except ValueError:
            pass
    return "ok"


def _client_billing_snapshot(client_id):
    """唯讀彙總：累計欠款（未 paid/invoiced/void 的請款單金額加總）、最大逾期天數。
    寫入（產出請款單、標已寄出或已入帳）屬 engine/enterprise_billing.py 的責任。
    Supabase 未啟用時退到本地備援檔（同 client_latest_invoice 的理由）。"""
    backend = _backend()
    invoices = None
    try:
        invoices = backend.load_enterprise_invoices(client_id=client_id, limit=200)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback(f"load enterprise invoices for {client_id}", exc)
        invoices = None
    if invoices is None:
        invoices = _read_local_invoices(client_id=client_id)
    outstanding = 0.0
    overdue_days = 0
    today = datetime.now(timezone.utc).date()
    for inv in invoices:
        status = inv.get("status")
        if status in ("paid", "invoiced", "void"):
            continue
        outstanding += _safe_number(inv.get("totalTwd"))
        due_date = inv.get("dueDate")
        if due_date:
            try:
                due = datetime.strptime(str(due_date)[:10], "%Y-%m-%d").date()
                overdue_days = max(overdue_days, (today - due).days)
            except ValueError:
                pass
    return {"outstandingTwd": outstanding, "overdueDays": max(0, overdue_days), "invoices": invoices}


def clients_overview(query=None, status=None):
    """3.6 /admin/enterprise/clients：每家含 id、name、合約期間、seatQuota、activeSeats、
    waitingSeats、graceSeats、statusLight、estimatedMonthlyTwd、overdueDays、outstandingTwd。"""
    clients = list_clients(query=query, status=status)
    overview = []
    for client in clients:
        counts = _seat_counts_for_client(client["id"])
        billing = _client_billing_snapshot(client["id"])
        estimated_monthly = counts["active"] * _safe_number(client.get("unitPriceTwd"))
        overview.append({
            **client,
            "activeSeats": counts["active"],
            "waitingSeats": counts["waiting"],
            "graceSeats": counts["grace"],
            "pendingSeats": counts["pending"],
            "releasedSeats": counts["released"],
            "statusLight": _client_status_light(client, billing["overdueDays"]),
            "estimatedMonthlyTwd": round(estimated_monthly, 2),
            "overdueDays": billing["overdueDays"],
            "outstandingTwd": round(billing["outstandingTwd"], 2),
        })
    return overview


def client_detail(client_id):
    """3.6 /admin/enterprise/client/detail：公司資料加席次明細加收款紀錄（請款單清單，
    含 reportRef 供下載月報或請款單）。"""
    client = get_client(client_id)
    if not client:
        return None
    seats = list_seats(client_id=client_id)
    counts = _seat_counts_for_client(client_id)
    billing = _client_billing_snapshot(client_id)
    return {
        "client": {
            **client,
            "activeSeats": counts["active"],
            "waitingSeats": counts["waiting"],
            "graceSeats": counts["grace"],
            "pendingSeats": counts["pending"],
            "releasedSeats": counts["released"],
            "statusLight": _client_status_light(client, billing["overdueDays"]),
            "outstandingTwd": round(billing["outstandingTwd"], 2),
            "overdueDays": billing["overdueDays"],
        },
        "seats": seats,
        "invoices": billing["invoices"],
    }


# ---- 開票／收款設定（單列表 · 2026-07-20 二次需求 · Edward 親提）----
# 背景：Edward 目前是一人公司，開發票要借用另一家公司的抬頭，開票方資訊
# （抬頭／統編／收款銀行）不能寫死、未來會換。原本 enterprise_billing.py 用環境變數
# MUNEA_ENTERPRISE_REMIT_INFO 頂著一個假字串，現在改成後台可填的一列設定。
#
# 給 enterprise_billing.py 用的入口（那支檔案的責任是把請款單上寫死的字串換成這份
# 設定，不在本檔範圍）：
#   enterprise_seats.get_billing_settings()              -> 讀目前設定（一定回 dict，不是 None）
#   enterprise_seats.is_billing_settings_configured(...)  -> 核心欄位是否都填了；
#     沒填時請款單／後台要顯示明顯提示，不能靜默印出空白（沒填不是錯誤，是還沒設定）

BILLING_SETTINGS_PATH = os.environ.get("MUNEA_ENTERPRISE_BILLING_SETTINGS_PATH") or os.path.join(HERE, "enterprise_billing_settings_store.json")
DEFAULT_PAYMENT_TERMS_DAYS = 15  # 對應需求單 4.2「次月 15 日前」既有邏輯的預設值，可調
# 核心欄位：任一沒填就視為「尚未設定開票資訊」——抬頭／收款銀行／戶名／帳號缺一不可，
# 沒有這些請款單印出來也沒意義（統編／電話／聯絡人／備註算選填，不影響 configured 判定）。
BILLING_SETTINGS_REQUIRED_FIELDS = ("issuerCompanyName", "bankName", "bankAccountName", "bankAccountNo")


def normalize_billing_settings(item=None):
    item = item or {}
    return {
        "issuerCompanyName": item.get("issuerCompanyName") or item.get("issuer_company_name"),
        "issuerTaxId": item.get("issuerTaxId") or item.get("issuer_tax_id"),
        "issuerAddress": item.get("issuerAddress") or item.get("issuer_address"),
        "issuerPhone": item.get("issuerPhone") or item.get("issuer_phone"),
        "issuerContactName": item.get("issuerContactName") or item.get("issuer_contact_name"),
        "bankName": item.get("bankName") or item.get("bank_name"),
        "bankBranch": item.get("bankBranch") or item.get("bank_branch"),
        "bankAccountName": item.get("bankAccountName") or item.get("bank_account_name"),
        "bankAccountNo": item.get("bankAccountNo") or item.get("bank_account_no"),
        "paymentTermsDays": int(
            item.get("paymentTermsDays") or item.get("payment_terms_days") or DEFAULT_PAYMENT_TERMS_DAYS
        ),
        "invoiceFooterNote": item.get("invoiceFooterNote") or item.get("invoice_footer_note"),
        "updatedAt": item.get("updatedAt") or item.get("updated_at"),
        "updatedBy": item.get("updatedBy") or item.get("updated_by"),
    }


def get_billing_settings():
    """唯一讀取入口。回傳一定是 normalize_billing_settings() 過的 dict，沒設定過就是
    核心欄位皆空——不是 None、呼叫端不必先判斷 None，直接用 is_billing_settings_configured()
    決定要不要顯示警示。"""
    backend = _backend()
    try:
        remote = backend.get_enterprise_billing_settings()
        if remote is not None:
            return normalize_billing_settings(remote)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("load enterprise billing settings from Supabase", exc)
    local = _read_json_file(BILLING_SETTINGS_PATH, None)
    return normalize_billing_settings(local)


def is_billing_settings_configured(settings=None):
    """需求單二次補充：沒設定完就不准靜默印空白，呼叫端（後台／請款單 HTML）用這個
    決定要不要顯示『尚未設定開票資訊』提示。不傳 settings 就自己查目前的；
    server.py 已經查過一次時可以把查到的傳進來，不必重複打一次。"""
    settings = settings if settings is not None else get_billing_settings()
    if not settings:
        return False
    return all((settings.get(field) or "").strip() for field in BILLING_SETTINGS_REQUIRED_FIELDS)


def save_billing_settings(payload, updated_by="admin"):
    settings = normalize_billing_settings(payload)
    settings["updatedAt"] = _utc_now()
    settings["updatedBy"] = updated_by or "admin"
    backend = _backend()
    try:
        remote = backend.save_enterprise_billing_settings(settings)
        if remote is not None:
            return normalize_billing_settings(remote)
    except Exception as exc:
        if backend.enabled() and not _is_missing_table_error(exc):
            raise
        _log_fallback("save enterprise billing settings to Supabase", exc)
    _write_json_file(BILLING_SETTINGS_PATH, settings)
    return settings
