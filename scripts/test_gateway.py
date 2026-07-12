# -*- coding: utf-8 -*-
"""聊聊分流閘道 · 本機單元測試（2026-07-12 卡西法）。

零外部依賴——deploy/gateway/gateway_core.py 不 import fastapi，這裡直接測真的邏輯
（不是重寫一份假的）：聯合准入 min 邏輯、fullest-first 配對、FIFO 排隊 pop/遞補/
滿載拒絕、通話結束釋放後自動把佇列往前推。

跑法：python scripts/test_gateway.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "gateway"))

import gateway_core as gc  # noqa: E402


def test_joint_admission_is_min_of_gpu_and_voice():
    gw = gc.Gateway(voice=gc.VoicePool(limit=5))
    gw.workers.register("w1", "https://w1", slots=3)
    # GPU 有 3 個空位，語音池滿（active=5/5=0 free）-> joint_free 該是 0（語音天花板卡住）
    gw.voice.set_active(5)
    assert gw.joint_free() == 0, "voice pool exhausted must cap joint_free even with free GPU slots"

    gw.voice.set_active(4)   # 語音剩 1 個空位，GPU 剩 3 -> min=1
    assert gw.joint_free() == 1

    gw.voice.set_active(0)   # 語音空 5、GPU 空 3 -> min=3
    assert gw.joint_free() == 3
    print("test_joint_admission_is_min_of_gpu_and_voice: PASS")


def test_fullest_first_prefers_partially_used_worker():
    gw = gc.Gateway(voice=gc.VoicePool(limit=99))
    w_empty = gw.workers.register("empty", "https://empty", slots=3)
    w_partial = gw.workers.register("partial", "https://partial", slots=3)
    w_partial.active = 2   # 已經有人在用、還有 1 空槽

    picked = gw.workers.pick_fullest_first()
    assert picked is w_partial, "should prefer the already-busier worker over an idle one"

    # 都是空卡時，任一台皆可（取第一個，順序穩定）
    w_empty.active = 0
    w_partial.active = 0
    gw2 = gc.Gateway(voice=gc.VoicePool(limit=99))
    only = gw2.workers.register("only", "https://only", slots=2)
    assert gw2.workers.pick_fullest_first() is only
    print("test_fullest_first_prefers_partially_used_worker: PASS")


def test_request_call_connects_when_space_available():
    gw = gc.Gateway(voice=gc.VoicePool(limit=5))
    gw.workers.register("w1", "https://w1", slots=1)
    r = gw.request_call("client-A")
    assert r["status"] == "connect"
    assert r["worker"]["worker_id"] == "w1"
    # 重複請求同一個 client 應該回同一台（不會再佔一格）
    r2 = gw.request_call("client-A")
    assert r2 == r
    assert gw.workers.get("w1").active == 1, "must not double-reserve on repeated request"
    print("test_request_call_connects_when_space_available: PASS")


def test_request_call_queues_when_full_and_rejects_when_queue_full():
    gw = gc.Gateway(voice=gc.VoicePool(limit=5), queue=gc.CallQueue(max_depth=2))
    gw.workers.register("w1", "https://w1", slots=1)

    r1 = gw.request_call("client-A")
    assert r1["status"] == "connect"

    r2 = gw.request_call("client-B")
    assert r2["status"] == "queued"
    assert r2["queue"]["position"] == 1

    r3 = gw.request_call("client-C")
    assert r3["status"] == "queued"
    assert r3["queue"]["position"] == 2

    r4 = gw.request_call("client-D")
    assert r4["status"] == "reject" and r4["reason"] == "queue_full", \
        "queue at max_depth must reject, not silently drop or fall back to voice-only"
    print("test_request_call_queues_when_full_and_rejects_when_queue_full: PASS")


def test_queue_fifo_skips_offline_and_reorders():
    q = gc.CallQueue(max_depth=10)
    q.enqueue("A")
    q.enqueue("B")
    q.enqueue("C")
    q.mark_offline("B")
    # B 離線 -> pop_next_online 應該跳過 B，先給 A，之後給 C（B 被丟棄不再遞補）
    assert q.pop_next_online() == "A"
    assert q.pop_next_online() == "C"
    assert q.pop_next_online() is None
    print("test_queue_fifo_skips_offline_and_reorders: PASS")


def test_release_call_advances_queue_to_next_online_client():
    gw = gc.Gateway(voice=gc.VoicePool(limit=5))
    gw.workers.register("w1", "https://w1", slots=1)

    gw.request_call("client-A")            # 佔滿唯一的槽
    r_b = gw.request_call("client-B")       # 排隊
    assert r_b["status"] == "queued"

    # 通話結束（worker webhook）-> 應該自動把 client-B 接上，且記錄通話時長
    advanced = gw.release_call("w1", duration_s=42.0)
    assert advanced is not None
    assert advanced["client_id"] == "client-B"
    assert advanced["worker"]["worker_id"] == "w1"

    poll_b = gw.poll("client-B")
    assert poll_b["status"] == "connect"
    assert poll_b["worker"]["worker_id"] == "w1"

    # 通話時長要真的被記進滾動平均（下一輪排隊 ETA 估算會用到）
    assert list(gw.queue._recent_call_s) == [42.0]
    print("test_release_call_advances_queue_to_next_online_client: PASS")


def test_cancel_removes_from_queue_without_side_effects():
    gw = gc.Gateway(voice=gc.VoicePool(limit=5))
    gw.workers.register("w1", "https://w1", slots=1)
    gw.request_call("client-A")
    gw.request_call("client-B")   # 排隊中

    result = gw.cancel_call("client-B")
    assert result["cancelled_queue"] is True
    assert gw.queue.status("client-B") is None
    # 取消後佇列釋放的空位不該影響已經在通話中的 client-A
    assert gw.poll("client-A")["status"] == "connect"
    print("test_cancel_removes_from_queue_without_side_effects: PASS")


def test_poll_unknown_client_returns_unknown_status():
    gw = gc.Gateway(voice=gc.VoicePool(limit=5))
    gw.workers.register("w1", "https://w1", slots=1)
    assert gw.poll("never-seen-client") == {"status": "unknown"}
    print("test_poll_unknown_client_returns_unknown_status: PASS")


def test_worker_health_and_enabled_exclude_from_admission():
    gw = gc.Gateway(voice=gc.VoicePool(limit=5))
    gw.workers.register("w1", "https://w1", slots=2)
    gw.workers.mark_health("w1", healthy=False)
    assert gw.workers.total_free() == 0, "unhealthy worker must contribute zero free slots"
    r = gw.request_call("client-A")
    assert r["status"] == "queued", "no healthy worker available -> must queue, not error"

    gw.workers.mark_health("w1", healthy=True)
    gw.workers.set_enabled("w1", False)
    assert gw.workers.total_free() == 0, "disabled (maintenance) worker must also be excluded"
    print("test_worker_health_and_enabled_exclude_from_admission: PASS")


def main():
    test_joint_admission_is_min_of_gpu_and_voice()
    test_fullest_first_prefers_partially_used_worker()
    test_request_call_connects_when_space_available()
    test_request_call_queues_when_full_and_rejects_when_queue_full()
    test_queue_fifo_skips_offline_and_reorders()
    test_release_call_advances_queue_to_next_online_client()
    test_cancel_removes_from_queue_without_side_effects()
    test_poll_unknown_client_returns_unknown_status()
    test_worker_health_and_enabled_exclude_from_admission()
    print("Gateway core smoke test: ALL PASS")


if __name__ == "__main__":
    main()
