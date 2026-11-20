"""免費額度與家人圈共用分鐘的規則（2026-11-20 拍板）。

這裡只放「怎麼算」的純函式，不碰檔案、不碰雲端；server.py 的 JSON 後備模式用它，
Supabase 模式的同一套規則寫在 supabase/sql/034_family_shared_minutes_daily_free.sql
（gateway 直接呼叫資料庫函式扣點，所以兩邊都要有；改規則兩邊一起改，測試兩邊都有）。

規則：
- 帳號建立那天（台灣時間）＝第 1 天。第 1～7 天每天一個 10 點的免費錢包，台灣時間午夜到期；
  第 8 天起每週一（台灣時間）一個 10 點的錢包。用不完不累積。有自己付費方案的帳號不發。
- 本月（台灣時間）全平台免費消耗 ≥ 上限（預設 1360 分鐘）→ 之後新發的「每日」額度改 5。
- 來電者是別人家人圈的非圈主成員、圈主有有效 plus／pro：先扣自己的免費額度，
  再扣圈主的錢包（月額度優先），最後才扣自己其他錢包；交易記來電者的 personId。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

# 台灣沒有日光節約時間，固定 UTC+8；不依賴系統的時區資料庫（Windows 常常沒有 tzdata）。
TAIPEI = timezone(timedelta(hours=8))
FREE_WALLET_TYPE = "free_allowance"
PAID_PLANS = ("plus", "pro")
PLAN_MONTHLY_MINUTES = {"plus": 100, "pro": 200}
DEFAULT_SETTINGS = {
    "trialDays": 7,
    "trialDailyMinutes": 10,
    "reducedDailyMinutes": 5,
    "weeklyMinutes": 10,
    "monthlyCapMinutes": 1360,
}
_ENV_KEYS = {
    "trialDays": "MUNEA_FREE_TRIAL_DAYS",
    "trialDailyMinutes": "MUNEA_FREE_TRIAL_DAILY_MINUTES",
    "reducedDailyMinutes": "MUNEA_FREE_REDUCED_DAILY_MINUTES",
    "weeklyMinutes": "MUNEA_FREE_WEEKLY_MINUTES",
    "monthlyCapMinutes": "MUNEA_FREE_MONTHLY_CAP_MINUTES",
}


def settings_from_env(env=None):
    """JSON 後備模式的設定（Supabase 模式讀 free_allowance_settings 那一列）。"""
    env = os.environ if env is None else env
    out = dict(DEFAULT_SETTINGS)
    for key, env_key in _ENV_KEYS.items():
        raw = str(env.get(env_key) or "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value < 0:
            continue
        out[key] = int(value) if key == "trialDays" else value
    return out


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


def taipei_midnight(day):
    """台灣日期 → 那天 00:00（台灣時間）的 aware datetime。"""
    return datetime(day.year, day.month, day.day, tzinfo=TAIPEI)


def month_start(now):
    local = now.astimezone(TAIPEI)
    return datetime(local.year, local.month, 1, tzinfo=TAIPEI)


def allowance_window(created_at, now, settings=None, month_free_used=0):
    """現在該領哪一個免費錢包。created_at 抓不到就當舊帳號（直接走每週）。"""
    settings = {**DEFAULT_SETTINGS, **(settings or {})}
    now = parse_time(now) or datetime.now(timezone.utc)
    today = now.astimezone(TAIPEI).date()
    created = parse_time(created_at)
    trial_days = int(settings["trialDays"])
    if created is None:
        day = trial_days + 1
    else:
        day = max(1, (today - created.astimezone(TAIPEI).date()).days + 1)
    cap_reached = False
    if day <= trial_days:
        mode = "free_daily"
        start = today
        end = today + timedelta(days=1)
        cap_reached = float(month_free_used or 0) >= float(settings["monthlyCapMinutes"])
        amount = settings["reducedDailyMinutes"] if cap_reached else settings["trialDailyMinutes"]
        period = f"free-daily:{start.isoformat()}"
    else:
        mode = "free_weekly"
        start = today - timedelta(days=today.weekday())  # 週一
        end = start + timedelta(days=7)
        amount = settings["weeklyMinutes"]
        period = f"free-weekly:{start.isoformat()}"
    return {
        "mode": mode,
        "trialDay": day if mode == "free_daily" else None,
        "trialDays": trial_days,
        "period": period,
        "amount": float(amount),
        "startsAt": iso_z(taipei_midnight(start)),
        "expiresAt": iso_z(taipei_midnight(end)),
        "capReached": cap_reached,
    }


def _wallet_active(wallet, now):
    if wallet.get("status") != "active" or float(wallet.get("balance") or 0) <= 0:
        return False
    expires = parse_time(wallet.get("expiresAt") or wallet.get("expires_at"))
    return expires is None or expires > now


def free_used_in_month(stores, now):
    """本月（台灣時間）這些帳本裡、從免費錢包扣掉的分鐘數。"""
    now = parse_time(now) or datetime.now(timezone.utc)
    since = month_start(now)
    total = 0.0
    for store in stores or []:
        free_ids = {w.get("id") for w in (store or {}).get("wallets") or [] if w.get("type") == FREE_WALLET_TYPE}
        for tx in (store or {}).get("transactions") or []:
            if tx.get("type") != "consume":
                continue
            if tx.get("walletType") != FREE_WALLET_TYPE and tx.get("walletId") not in free_ids:
                continue
            created = parse_time(tx.get("createdAt"))
            if created is not None and created < since:
                continue
            total += abs(float(tx.get("amount") or 0))
    return round(total, 4)


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


def allowance_block(window, store, now, *, paid_plan=None, plan_resets_at=None):
    """/credits/balance 的 allowance。有自己付費方案＝mode plan。"""
    if paid_plan:
        return {
            "mode": "plan", "plan": paid_plan, "trialDay": None, "trialDays": None,
            "todayGrant": None, "todayRemaining": None, "weekGrant": None, "weekRemaining": None,
            "resetsAt": plan_resets_at,
        }
    if not window:
        return None
    now = parse_time(now) or datetime.now(timezone.utc)
    wallet = find_free_wallet(store, window["period"])
    grant = float(((wallet or {}).get("metadata") or {}).get("grant") or 0) if wallet else 0.0
    if wallet and grant <= 0:
        grant = float(window["amount"])
    remaining = float(wallet.get("balance") or 0) if wallet and _wallet_active(wallet, now) else 0.0
    daily = window["mode"] == "free_daily"
    return {
        "mode": window["mode"],
        "trialDay": window.get("trialDay"),
        "trialDays": window.get("trialDays"),
        "todayGrant": as_number(grant) if daily else None,
        "todayRemaining": as_number(remaining) if daily else None,
        "weekGrant": None if daily else as_number(grant),
        "weekRemaining": None if daily else as_number(remaining),
        "resetsAt": window.get("expiresAt"),
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
