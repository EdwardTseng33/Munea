# -*- coding: utf-8 -*-
"""B 路掐錶：Modal 快照喚醒 → 臉引擎就緒（2026-07-09）
第 1 次呼叫＝拍快照的冷啟動（慢、正常）；等容器睡掉（40 秒沒人用）→
第 2 次呼叫＝從快照喚醒 ← 這才是我們要的數字。連量 3 輪冷喚醒取樣。
"""
import time

import modal

Nening = modal.Cls.from_name("munea-nening-avatar", "Nening")

def cold_call(tag):
    eng = Nening()
    t0 = time.time()
    r = eng.probe.remote()
    dt = time.time() - t0
    print(f"[{tag}] 呼叫→回應 {dt:.1f}s · 引擎自報 {r['load_report']} · "
          f"單塊 {r['chunk_ms']}ms · 產格 {r['frames_delta']}", flush=True)
    return dt

print("== 第 1 次（建快照的冷啟動、慢是正常）==", flush=True)
cold_call("首次")

for i in (1, 2, 3):
    print(f"== 等容器入睡（70 秒）→ 第 {i} 輪快照喚醒 ==", flush=True)
    time.sleep(70)
    cold_call(f"快照喚醒{i}")

print("PROBE COMPLETE", flush=True)
