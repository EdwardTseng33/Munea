"""免費額度與分鐘扣法的規則（2026-11-26 Edward 拍板）。

這裡只放「怎麼算」的純函式，不碰檔案、不碰雲端；server.py 的 JSON 後備模式用它，
Supabase 模式的同一套規則寫在 supabase/sql/035_per_account_minutes.sql
（gateway 直接呼叫資料庫函式扣點，所以兩邊都要有；改規則兩邊一起改，測試兩邊都有）。

規則：
- 免費＝註冊時送一次 5 分鐘（free_allowance 錢包、period "free-once"、不會到期），用完就要訂閱或加買，
  不會每天／每週再給。「拿過」＝有 "free-signup-trial:<帳號>" 的發點交易、或已經有 free-once 錢包；
  11/20 以前送的 5 點（舊的購買錢包）也算拿過。有自己付費方案的帳號這時不發。
- 每個帳號各扣各的：自己的一次性免費 → 自己的方案月額度 → 自己的購買分鐘。
  （家人圈共用分鐘的扣法 plan_spend(owner_store=...) 還留著，只在 server.FAMILY_SHARED_MINUTES 打開時才會用。）
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

# 台灣沒有日光節約時間，固定 UTC+8；不依賴系統的時區資料庫（Windows 常常沒有 tzdata）。
TAIPEI = timezone(timedelta(hours=8))
FREE_WALLET_TYPE = "free_allowance"
PAID_PLANS = ("plus", "pro")
PLAN_MONTHLY_MINUTES = {"plus": 100, "pro": 200}
FREE_ONCE_PERIOD = "free-once"
SIGNUP_KEY_PREFIX = "free-signup-trial:"
LEGACY_SIGNUP_REASON = "free_signup_voice_avatar_trial"   # 11/20 以前一次性 5 點的交易原因
DEFAULT_FREE_ONCE_MINUTES = 5


def free_once_minutes(env=None):
    """JSON 後備模式的一次性免費分鐘數（Supabase 模式讀 free_allowance_settings.signup_once_minutes）。"""
    env = os.environ if env is None else env
    raw = str(env.get("MUNEA_FREE_SIGNUP_MINUTES") or "").strip()
    try:
        value = float(raw) if raw else DEFAULT_FREE_ONCE_MINUTES
    except ValueError:
        value = DEFAULT_FREE_ONCE_MINUTES
    return value if value >= 0 else DEFAULT_FREE_ONCE_MINUTES


def parse_time(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso_z(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def month_start(now):
    local = now.astimezone(TAIPEI)
    return datetime(local.year, local.month, 1, tzinfo=TAIPEI)


def free_once_window(amount=None):
    """免費額度長什麼樣子（跟資料庫 munea_free_allowance_window 同一個格式）。"""
    return {
        "mode": "free_once",
        "period": FREE_ONCE_PERIOD,
        "amount": float(free_once_minutes() if amount is None else amount),
        "expiresAt": None,
    }


def _wallet_active(wallet, now):
    if wallet.get("status") != "active" or float(wallet.get("balance") or 0) <= 0:
        return False
    expires = parse_time(wallet.get("expiresAt") or wallet.get("expires_at"))
    return expires is None or expires > now


def free_once_received(store, account_id=None):
    """這個帳本拿過一次性免費沒有（035 起的 free-once 錢包、或 11/20 以前的註冊送點）。"""
    store = store or {}
    if find_free_wallet(store, FREE_ONCE_PERIOD):
        return True
    for tx in store.get("transactions") or []:
        if tx.get("type") != "grant":
            continue
        key = str(tx.get("idempotencyKey") or "")
        if key.startswith(SIGNUP_KEY_PREFIX) and (not account_id or key == SIGNUP_KEY_PREFIX + str(account_id)):
            return True
        if tx.get("reason") == LEGACY_SIGNUP_REASON:
            return True
    return False


def free_once_remaining(store, now, account_id=None):
    """一次性免費還剩多少。11/20 以前的帳號那 5 點放在購買錢包裡，最多算 5。"""
    now = parse_time(now) or datetime.now(timezone.utc)
    wallet = find_free_wallet(store, FREE_ONCE_PERIOD)
    if wallet:
        return float(wallet.get("balance") or 0) if _wallet_active(wallet, now) else 0.0
    if not free_once_received(store, account_id):
        return 0.0
    purchased = sum(float(w.get("balance") or 0) for w in (store or {}).get("wallets") or []
                    if w.get("type") == "purchased" and _wallet_active(w, now))
    return min(float(DEFAULT_FREE_ONCE_MINUTES), purchased)


def close_periodic_free_wallets(store, now):
    """11/20–11/26 發的每日／每週免費錢包：還沒到期的收掉（資料庫那邊是 035 的一次性 update）。回收掉幾個。"""
    now = parse_time(now) or datetime.now(timezone.utc)
    closed = 0
    for wallet in (store or {}).get("wallets") or []:
        period = str(wallet.get("period") or "")
        if wallet.get("type") != FREE_WALLET_TYPE or not period.startswith(("free-daily:", "free-weekly:")):
            continue
        expires = parse_time(wallet.get("expiresAt"))
        if expires is None or expires > now:
            wallet["expiresAt"] = iso_z(now)
            wallet.setdefault("metadata", {})["closedBy"] = "035_free_once"
            closed += 1
    return closed


def find_free_wallet(store, period):
    for wallet in (store or {}).get("wallets") or []:
        if wallet.get("type") == FREE_WALLET_TYPE and wallet.get("period") == period:
            return wallet
    return None


def free_wallet_for(window):
    return {
        "id": f"wallet_{window['period'].replace(':', '_')}",
        "type": FREE_WALLET_TYPE,
        "period": window["period"],
        "balance": float(window["amount"]),
        "expiresAt": window["expiresAt"],
        "status": "active",
        "metadata": {"purpose": FREE_WALLET_TYPE, "grant": float(window["amount"]), "mode": window["mode"]},
    }


def _spend_key(wallet, owner_account_id, caller_account_id, account_of):
    account = account_of(wallet)
    is_free = wallet.get("type") == FREE_WALLET_TYPE
    if account == caller_account_id and is_free:
        tier = 0
    elif owner_account_id and account == owner_account_id:
        tier = 1
    else:
        tier = 2
    return (
        tier,
        0 if wallet.get("type") == "included_monthly" else 1,
        wallet.get("expiresAt") or "9999",
        str(wallet.get("id") or ""),
    )


def plan_spend(own_store, amount, now, *, owner_store=None, caller_account_id="self", owner_account_id=None):
    """決定這次要從哪些錢包扣多少。夠就回 [(帳本, 錢包, 扣多少)]，不夠回 None。

    圈主錢包只拿非免費的（圈主自己的免費額度不分給別人）。不改任何資料。
    """
    now = parse_time(now) or datetime.now(timezone.utc)
    entries = []
    for wallet in (own_store or {}).get("wallets") or []:
        if _wallet_active(wallet, now):
            entries.append((own_store, wallet, caller_account_id))
    if owner_store is not None and owner_account_id:
        for wallet in owner_store.get("wallets") or []:
            if wallet.get("type") != FREE_WALLET_TYPE and _wallet_active(wallet, now):
                entries.append((owner_store, wallet, owner_account_id))
    accounts = {id(w): a for _, w, a in entries}
    entries.sort(key=lambda item: _spend_key(item[1], owner_account_id, caller_account_id, lambda w: accounts[id(w)]))
    available = sum(float(w.get("balance") or 0) for _, w, _ in entries)
    if available + 1e-9 < float(amount):
        return None
    remaining = float(amount)
    plan = []
    for store, wallet, _account in entries:
        if remaining <= 0:
            break
        take = min(float(wallet.get("balance") or 0), remaining)
        if take <= 0:
            continue
        plan.append((store, wallet, round(take, 4)))
        remaining = round(remaining - take, 4)
    return plan


def spendable(store, now, *, exclude_free=False):
    now = parse_time(now) or datetime.now(timezone.utc)
    return round(sum(
        float(w.get("balance") or 0)
        for w in (store or {}).get("wallets") or []
        if _wallet_active(w, now) and not (exclude_free and w.get("type") == FREE_WALLET_TYPE)
    ), 4)


def allowance_block(store, now, *, paid_plan=None, plan_resets_at=None, account_id=None):
    """/credits/balance 的 allowance：免費＝{mode: free_once, grant, remaining}；有自己付費方案＝mode plan。"""
    if paid_plan:
        return {"mode": "plan", "plan": paid_plan, "resetsAt": plan_resets_at}
    now = parse_time(now) or datetime.now(timezone.utc)
    received = free_once_received(store, account_id)
    wallet = find_free_wallet(store, FREE_ONCE_PERIOD)
    grant = float(((wallet or {}).get("metadata") or {}).get("grant") or DEFAULT_FREE_ONCE_MINUTES) if received else 0.0
    return {
        "mode": "free_once",
        "grant": as_number(grant),
        "remaining": as_number(free_once_remaining(store, now, account_id)),
    }


def as_number(value):
    value = round(float(value or 0), 4)
    return int(value) if value == int(value) else value


def usage_rows(transactions, since, *, owner_person_id=None, family_wallet_ids=None):
    """圈主帳本裡、這個週期每個人用了幾分鐘：{personId: minutes}。免費錢包不算進共用分鐘。"""
    totals = {}
    for tx in transactions or []:
        if tx.get("type") != "consume" or tx.get("walletType") == FREE_WALLET_TYPE:
            continue
        if family_wallet_ids is not None and tx.get("walletId") not in family_wallet_ids:
            continue
        created = parse_time(tx.get("createdAt"))
        if since is not None and created is not None and created < since:
            continue
        person = tx.get("personId") or owner_person_id or ""
        totals[person] = totals.get(person, 0.0) + abs(float(tx.get("amount") or 0))
    return totals


def visible_usage(usage, *, role, viewer_person_id, names=None):
    """圈主看全部；成員只看自己那一列。名字只用家人圈顯示名，沒有就空字串（絕不用 email）。"""
    names = names or {}
    rows = []
    for person_id, minutes in (usage or {}).items():
        is_me = bool(viewer_person_id) and person_id == viewer_person_id
        if role != "owner" and not is_me:
            continue
        rows.append({
            "personId": person_id,
            "name": str(names.get(person_id) or ""),
            "minutes": as_number(round(float(minutes or 0))),
            "isMe": is_me,
        })
    rows.sort(key=lambda row: (-float(row["minutes"]), row["personId"]))
    return rows


def circle_names(circle):
    """家人圈狀態（family_state circle：[{name, personId, ...}]）→ {personId: name}。"""
    out = {}
    for member in circle or []:
        if not isinstance(member, dict):
            continue
        person_id = str(member.get("personId") or "").strip()
        name = str(member.get("name") or member.get("displayName") or "").strip()
        if person_id and name and "@" not in name:
            out[person_id] = name[:40]
    return out
