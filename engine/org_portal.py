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
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

import enterprise_seats

DEFAULT_TTL_DAYS = 30
MAX_TTL_DAYS = 180
TOKEN_VERSION = "v1"

# 彙總裡「絕對不准出現」的欄位名。多一層保險：就算未來有人手滑把席次明細塞進來，
# 也會在回應送出前炸掉，而不是安靜地把長輩個資送給機構。
#
# 注意這裡故意不擋通用的 "name"——機構自己的名稱（org.name）本來就要顯示給窗口看，
# 那是公司資訊不是個資。要擋的是「指向某一個人」的欄位。
FORBIDDEN_KEYS = {
    "accountid", "account_id", "email", "inviteemail", "invite_email",
    "contactemail", "contact_email", "contactname", "contact_name",
    "phone", "contactphone", "contact_phone",
    "displayname", "display_name", "username", "user_name",
    "eldername", "elder_name", "personname", "person_name", "birthday",
    "transcript", "conversation", "message", "healthdata", "health_data",
    "mood", "medication", "note", "notes",
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


def build_portal_summary(client_id, seats=None, client=None):
    """組織維度的匿名彙總。這裡只放數字與組織自己的基本資料，不放任何個別長輩的東西。"""
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
        "privacy": {
            "personalDataIncluded": False,
            "statement": "本頁只顯示彙總數字。長輩的對話內容與健康明細僅家屬本人可見，機構端不提供。",
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
