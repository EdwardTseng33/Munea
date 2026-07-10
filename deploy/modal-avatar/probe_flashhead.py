# -*- coding: utf-8 -*-
"""FlashHead 掐錶：Modal 快照喚醒 -> 引擎就緒 -> 換角色 -> 穩態每塊耗時（2026-07-10）
用法同 probe_wake.py：第1次呼叫是拍快照的冷啟動（慢，正常）；等容器睡掉（scaledown_window=120s）
之後的呼叫才是「快照喚醒」數字。這支預設只做 1 次冷呼叫 + 1 次角色切換測試，
不像 probe_wake.py 那樣自動連測 3 輪喚醒（避免預設就燒太多 L4 時間，需要多輪自己改 N）。
"""
import time
import json

import modal

FlashHead = modal.Cls.from_name("munea-flashhead-avatar-dev", "FlashHead")


def call(tag, char=""):
    eng = FlashHead()
    t0 = time.time()
    r = eng.probe.remote(char=char)
    dt = time.time() - t0
    print(f"[{tag}] 呼叫->回應 {dt:.1f}s · {json.dumps(r, ensure_ascii=False)}", flush=True)
    return dt, r


if __name__ == "__main__":
    print("== 第 1 次呼叫（可能是冷啟或快照喚醒，視容器現況而定）==", flush=True)
    call("first")

    print("== 換角色測試（a06）==", flush=True)
    call("switch-a06", char="a06")

    print("== 換回 a05 ==", flush=True)
    call("switch-a05", char="a05")

    print("PROBE COMPLETE（要測快照喚醒秒數：手動等 scaledown_window=120s 後再跑一次這支）", flush=True)
