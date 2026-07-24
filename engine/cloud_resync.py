#!/usr/bin/env python3
"""雲端回補工人（90 分路線 #2 · 2026-07-24）：把「寫雲端失敗、退到本機」的那筆資料自動補回雲端。

為什麼需要：正式機是多台會輪替的雲端主機，退到本機的資料別台看不到、主機收掉就沒了。
7/24 已補「告警」（會叫）；這支補「回補」（自己爬回去）——涵蓋三個核心陪伴數據：
記憶（memory_items）、聊天摘要（conversation_summaries）、心情訊號（wellbeing_signals）。

設計要點：
- 失敗當下把「原始資料＋當時的身分」收進專用待補檔（跟本機備份檔分開：備份檔是快取、
  待補檔是「欠雲端的帳」，兩者語意不同）。
- 背景工人每 60 秒醒來：雲端恢復就逐筆補寫；補寫前先按內容探測「雲端是不是其實已經有了」
  （逾時型失敗可能其實已寫入；這三張桌子是純疊加、不帶客端編號，盲補會變兩筆）。
- 補不回去不刪帳：留在佇列繼續等；重試次數到頂才放棄＋告警（原始資料仍在本機備份檔、可人工救）。
- 工人絕不擋正常流量：獨立執行緒、單筆失敗只影響那一筆、連線層一斷就整輪先睡。
"""
import json
import os
import threading
import time
import uuid

import notify
import supabase_adapter

HERE = os.path.dirname(os.path.abspath(__file__))
PENDING_PATH = os.environ.get("MUNEA_CLOUD_PENDING_PATH") or os.path.join(HERE, "cloud_pending_writes.json")

_LOCK = threading.Lock()
_WORKER = {"started": False}

MAX_PENDING = 500     # 佇列防爆：超過就丟最舊的並告警（本機備份檔仍留有資料）
MAX_ATTEMPTS = 120    # 60 秒一輪 ≈ 兩小時仍補不回去 → 放棄＋告警
INTERVAL_S = 60

# 每張桌子的「內容探測鍵」：補寫前先用這些欄位問雲端有沒有一模一樣的那筆（防重複）。
_STORES = {
    "memory_items": {"probe": ("account_id", "person_id", "memory_type", "content")},
    "conversation_summaries": {"probe": ("account_id", "person_id", "summary")},
    "wellbeing_signals": {"probe": ("account_id", "person_id", "mood")},
}


def _read_pending():
    try:
        with open(PENDING_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _write_pending(entries):
    tmp = f"{PENDING_PATH}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    os.replace(tmp, PENDING_PATH)


def pending_count():
    with _LOCK:
        return len(_read_pending())


def record_pending(store, item, identity=None):
    """失敗當下記一筆「欠雲端的帳」。identity＝當時已驗證的身分（工人重放時用同一個身分）。"""
    if store not in _STORES or not item:
        return
    entry = {
        "id": uuid.uuid4().hex,
        "store": store,
        "item": item,
        "identity": dict(identity or {}),
        "failedAt": time.time(),
        "attempts": 0,
    }
    with _LOCK:
        entries = _read_pending()
        entries.append(entry)
        dropped = 0
        if len(entries) > MAX_PENDING:
            dropped = len(entries) - MAX_PENDING
            entries = entries[-MAX_PENDING:]
        _write_pending(entries)
    if dropped:
        _alert("cloud resync queue overflow", f"待補佇列爆量、丟棄最舊 {dropped} 筆（本機備份檔仍有資料）")


def record_pending_many(store, items, identity=None):
    for item in items or []:
        record_pending(store, item, identity=identity)


def _alert(where, detail):
    try:
        notify.alert("data", where, detail)
    except Exception:
        pass


def _default_adapter_factory(identity):
    return supabase_adapter.make_adapter(identity=identity or None)


def _to_row(adapter, store, item):
    if store == "memory_items":
        return adapter.memory_item_to_row(item)
    if store == "conversation_summaries":
        return adapter.conversation_summary_to_row(item)
    if store == "wellbeing_signals":
        return adapter.wellbeing_signal_to_row(item)
    raise ValueError(f"unknown store {store}")


def _probe_exists(adapter, store, row, failed_at):
    query = {"select": "id", "limit": "1"}
    for key in _STORES[store]["probe"]:
        value = row.get(key)
        if value is None or value == "":
            continue
        query[key] = f"eq.{value}"
    if store == "wellbeing_signals" and failed_at:
        # 心情訊號沒有夠獨特的內容鍵：加「失敗時間點前後」窗，避免把昨天同心情誤判成今天這筆
        window_start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(failed_at - 180))
        query["created_at"] = f"gte.{window_start}"
    rows = adapter._select(store, query)
    return bool(rows)


def _replay_one(entry, adapter_factory):
    """補一筆。回傳 'done'（補上了/雲端已有）、'retry'（下輪再試）、'unreachable'（整輪先睡）。"""
    adapter = adapter_factory(entry.get("identity"))
    if not adapter.enabled():
        return "retry"
    row = _to_row(adapter, entry["store"], entry["item"])
    try:
        if _probe_exists(adapter, entry["store"], row, entry.get("failedAt")):
            return "done"
        adapter._request("POST", entry["store"], query={"select": "id"}, payload=row)
        return "done"
    except supabase_adapter.SupabaseRequestError as e:
        if e.error_kind == "unreachable":
            return "unreachable"
        # 撞到「已存在」類錯誤（重複鍵）＝其實已經有了、算補上
        if e.error_code == "23505":
            return "done"
        return "retry"
    except Exception:
        return "retry"


def drain_once(adapter_factory=None, now=None):
    """跑一輪回補。獨立可測：不開執行緒、不睡覺，回傳統計。"""
    adapter_factory = adapter_factory or _default_adapter_factory
    with _LOCK:
        entries = _read_pending()
    if not entries:
        return {"pending": 0, "done": 0, "gaveUp": 0, "kept": 0}

    done_ids, gave_up = set(), []
    for entry in entries:
        result = _replay_one(entry, adapter_factory)
        if result == "unreachable":
            break  # 雲端還沒醒：這輪別再一筆筆撞（斷路器也會擋）、下輪再來
        if result == "done":
            done_ids.add(entry["id"])
            continue
        entry["attempts"] = int(entry.get("attempts") or 0) + 1
        if entry["attempts"] >= MAX_ATTEMPTS:
            done_ids.add(entry["id"])
            gave_up.append(entry)

    with _LOCK:
        current = _read_pending()
        kept = [e for e in current if e["id"] not in done_ids]
        # 帶回 attempts 累計（current 可能已有新進帳、以 id 對回）
        attempts_map = {e["id"]: e.get("attempts", 0) for e in entries}
        for e in kept:
            if e["id"] in attempts_map:
                e["attempts"] = max(int(e.get("attempts") or 0), attempts_map[e["id"]])
        _write_pending(kept)

    if gave_up:
        stores = ",".join(sorted({e["store"] for e in gave_up}))
        _alert("cloud resync give-up", f"{len(gave_up)} 筆重試 {MAX_ATTEMPTS} 次仍補不回雲端（{stores}）；原始資料在本機備份檔、需人工回補")
    return {"pending": len(entries), "done": len(done_ids) - len(gave_up), "gaveUp": len(gave_up), "kept": len(kept)}


def start_worker():
    """啟動背景回補工人（整個行程只啟動一次；MUNEA_CLOUD_RESYNC=0 可關）。"""
    if os.environ.get("MUNEA_CLOUD_RESYNC", "1") == "0":
        return False
    with _LOCK:
        if _WORKER["started"]:
            return False
        _WORKER["started"] = True

    def _loop():
        while True:
            time.sleep(INTERVAL_S)
            try:
                drain_once()
            except Exception:
                pass  # 工人絕不因單輪失敗而死；下輪再來

    threading.Thread(target=_loop, name="cloud-resync", daemon=True).start()
    return True
