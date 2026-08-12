# -*- coding: utf-8 -*-
"""她還講不講得出話（2026-07-29 · 當晚事故後立刻補）。

**為什麼這個存在**：今晚模型鑰匙的預付額度用完，正式機的大腦跟聊聊**兩台都啞了**——
真的用戶打不通、也聊不了。而八個服務的巡邏燈**全是綠的**。

因為巡邏只問「機器有沒有回應」，不問「她還講不講得出話」。
機器活著、程式沒壞、網頁回 200——但她一個字都吐不出來。
**服務看起來健康、用戶其實被晾在那裡，這比壞掉更可怕：沒有人會知道。**

這支補的就是那個盲點。兩層，優先用不花錢的那層：

  ① **搭真流量的便車**（零成本）：每次真的呼叫模型之後，把成功／失敗記一筆。
     有人在用的時候，這就是最真實的訊號——不必自己另外去打招呼。
  ② **沒人用的時候才自己探一次**（極省）：超過 CHECK_IDLE_S 沒有任何真流量，
     才發一次最小的呼叫確認嘴巴還在。結果快取 PROBE_TTL_S，不重複燒。

判定要誠實：**「不知道」不等於「沒事」**。從來沒有任何一筆紀錄時回 unknown，
不回 ok——今晚就是「看起來沒事」害的。
"""
import os
import threading
import time

STATE_OK = "ok"
STATE_DOWN = "down"
STATE_UNKNOWN = "unknown"

# 沒有真流量超過這麼久，才自己探一次（有人在用就搭便車、不多花錢）
CHECK_IDLE_S = int(os.environ.get("MUNEA_AI_HEALTH_IDLE_S") or 1200)      # 20 分鐘
# 探測結果的保鮮期（巡邏每 5 分鐘一輪，這樣大約每 20 分鐘才真的探一次）
PROBE_TTL_S = int(os.environ.get("MUNEA_AI_HEALTH_PROBE_TTL_S") or 1200)
# 連續幾次失敗才算真的倒（單次網路抖動不算）
DOWN_AFTER_FAILURES = 2

_lock = threading.Lock()
_state = {
    "lastOkAt": 0.0,
    "lastErrAt": 0.0,
    "lastError": "",
    "consecutiveFailures": 0,
    "probedAt": 0.0,
}


def record_success(now=None):
    """真的成功呼叫過模型——這是最可信的訊號，零成本。"""
    with _lock:
        _state["lastOkAt"] = now or time.time()
        _state["consecutiveFailures"] = 0
        _state["lastError"] = ""


def record_failure(detail="", now=None):
    """模型呼叫失敗。detail 只留去識別的錯誤摘要，不留對話內容。"""
    with _lock:
        _state["lastErrAt"] = now or time.time()
        _state["consecutiveFailures"] += 1
        _state["lastError"] = str(detail or "")[:200]


def _verdict(now):
    """只看已經記下的東西下判斷；不夠判斷就老實說不知道。"""
    if _state["consecutiveFailures"] >= DOWN_AFTER_FAILURES:
        return STATE_DOWN
    if _state["lastOkAt"] and (now - _state["lastOkAt"]) <= CHECK_IDLE_S:
        return STATE_OK
    if not _state["lastOkAt"] and not _state["lastErrAt"]:
        return STATE_UNKNOWN        # 從來沒叫過——不知道，不等於沒事
    return STATE_UNKNOWN            # 太久沒有真流量了，要探一次才知道


def _probe():
    """最小成本的一次確認：只要她吐得出任何一個字就算活著。"""
    try:
        import chat_engine as eng
        r = eng.client.models.generate_content(
            model="gemini-2.5-flash", contents="回一個字：好")
        if (getattr(r, "text", "") or "").strip():
            record_success()
            return True
        record_failure("模型有回應但內容是空的")
        return False
    except Exception as e:
        record_failure("%s:%s" % (type(e).__name__, str(e)[:150]))
        return False


def status(now=None, allow_probe=True):
    """給 /healthz 用。回傳 dict：{state, ok, lastOkAgoS, lastError, probed}"""
    now = now or time.time()
    verdict = _verdict(now)
    probed = False
    # 2026-08-12（Edward 儲值後才發現）：原本只有 unknown 才自己探一次，
    # **判成 down 之後就再也不探**——所以它會告訴你倒了，卻永遠不會告訴你已經好了。
    # 這次額度用完，Edward 儲了值、鑰匙實測也通了，儀表卻整整 16 小時還寫著 down。
    # 一個只會報壞消息、不會報復原的儀表，跟壞掉的儀表一樣不能信。
    if verdict in (STATE_UNKNOWN, STATE_DOWN) and allow_probe:
        if now - _state["probedAt"] >= PROBE_TTL_S:
            with _lock:
                _state["probedAt"] = now
            if _probe():
                # 探到活的就把連敗歸零——不然 _verdict 會繼續判 down
                with _lock:
                    _state["consecutiveFailures"] = 0
            probed = True
            verdict = _verdict(now)
    last_ok = _state["lastOkAt"]
    return {
        "state": verdict,
        # ok=True 只在真的確認過會講話時才給。unknown 一律不算 ok——
        # 「看起來沒事」正是今晚沒有人發現的原因。
        "ok": verdict == STATE_OK,
        "lastOkAgoS": int(now - last_ok) if last_ok else None,
        "consecutiveFailures": _state["consecutiveFailures"],
        "lastError": _state["lastError"],
        "probed": probed,
    }


def reset_for_test():
    with _lock:
        _state.update({"lastOkAt": 0.0, "lastErrAt": 0.0, "lastError": "",
                       "consecutiveFailures": 0, "probedAt": 0.0})
