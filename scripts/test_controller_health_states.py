# -*- coding: utf-8 -*-
"""看門狗該不該叫：管家自己壞掉 vs 對方不讓開卡（Edward 2026-08-07）。

背景：8/6-8/7 看門狗從早上 8 點叫到下午，每 5 分鐘一次「RunPod 備援控制器異常」。
查過去卻發現管家運作完全正常——它只是一直被 RunPod 拒絕（餘額不足）。
把「被拒絕」報成「服務掛了」，喊久了真的掛掉那次就沒人理。

規則分三段，這支測試釘住它：
  · 管家自己壞了（連不到總機、程式爆掉）        → 503，要叫人
  · 開不出備援，但沒有人在等                    → 200，別吵（狀態仍寫明原因）
  · 開不出備援，而且有人在等                    → 503，這是真的打不通
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))

import controller_service as cs  # noqa: E402


BALANCE_ERROR = (
    "RunPodError: RunPod API POST /pods failed: HTTP 500: "
    '{"error":"create pod: Your account balance is too low to rent a pod. '
    'Please add funds to your account."}'
)


def _stale_status(last_error: str, waiting: int) -> None:
    """把管家設成「很久沒成功跑完一輪」的狀態，附帶失敗原因與當下等待人數。"""
    cs.STATUS.update({
        "started_at": time.time() - 3600,     # 早就過了啟動寬限期
        "last_success_at": time.time() - 3600,  # 一小時沒成功過
        "last_error": last_error,
        "last_failure_waiting": waiting,
        "last_result": None,
        "cycles": 500,
    })


def _health():
    payload, status = cs._health_payload()
    return payload, status


def test_provider_out_of_funds_with_nobody_waiting_is_not_an_outage():
    _stale_status(BALANCE_ERROR, waiting=0)
    payload, status = _health()
    assert status == 200, "沒人在等的時候，開不出備援不該報成服務掛了"
    assert payload["state"] == "provider_unavailable"
    # 不是靜音：原因要留在回應裡，人一看就知道該補錢
    assert "balance is too low" in payload["last_error"]


def test_provider_out_of_funds_with_someone_waiting_is_an_outage():
    _stale_status(BALANCE_ERROR, waiting=2)
    payload, status = _health()
    assert status == 503, "有人在等卻開不出備援＝真的打不通，一定要叫"
    assert payload["state"] == "provider_unavailable_with_demand"


def test_controller_actually_broken_still_reports_outage():
    _stale_status("ConnectionError: gateway unreachable", waiting=0)
    payload, status = _health()
    assert status == 503, "管家自己壞掉一定要叫，不能被上面兩條吃掉"
    assert payload["state"] == "stalled"


def test_stockout_is_treated_like_out_of_funds():
    _stale_status("RunPodError: There are no instances currently available", waiting=0)
    payload, status = _health()
    assert status == 200
    assert payload["state"] == "provider_unavailable"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("看門狗三段判斷全過")
