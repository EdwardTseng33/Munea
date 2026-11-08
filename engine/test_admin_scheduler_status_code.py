# -*- coding: utf-8 -*-
"""定時任務端點失敗要真的回失敗（2026-11-08）

守的線：Cloud Scheduler 打的 5 支端點（/admin/daily-briefing、
/admin/worker-clock-patrol、/admin/notifications/drain、/admin/retention/run、
/admin/enterprise/seats/sweep）結果 ok:false 時要回 HTTP 500，Scheduler 才會
記成失敗、觸發重試/告警。原本一律用 _json 回 200，Scheduler 以為全部成功。

這支測試直接測 _json_scheduler 這個共用方法本身（跟 test_admin_security_headers.py
量表頭的手法一樣：建一個假 handler，不需要真的啟動 HTTP 伺服器），
並確認全域 _json（其餘幾十支 /admin/* 讀取接口在用）的行為完全沒被改動。

跑法：python engine/test_admin_scheduler_status_code.py
"""
import io
import os
import sys

os.environ.setdefault("GEMINI_API_KEY", "admin-scheduler-status-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def send_via(method_name, path, obj):
    handler = server.H.__new__(server.H)
    handler.path = path
    handler.headers = {}
    handler.wfile = io.BytesIO()
    captured = {}
    handler.send_response = lambda code: captured.update({"status": code})
    handler.send_header = lambda name, value: None
    handler.end_headers = lambda: None
    getattr(handler, method_name)(obj)
    return captured["status"]


# ── _json_scheduler：ok:false → 500，其餘（ok:true／沒有 ok 欄位）→ 200 ──

check(
    "排程端點 ok:false 回 HTTP 500",
    send_via("_json_scheduler", "/admin/retention/run", {"ok": False, "error": "retention_run_failed"}) == 500,
)
check(
    "排程端點 ok:true 回 HTTP 200",
    send_via("_json_scheduler", "/admin/retention/run", {"ok": True, "deletedCount": 0}) == 200,
)
check(
    "排程端點沒有 ok 欄位時預設當成功回 200（不誤判既有回應格式）",
    send_via("_json_scheduler", "/admin/daily-briefing", {"region": "tw"}) == 200,
)
check(
    "排程端點 ok 是別的真值（非 False）也回 200",
    send_via("_json_scheduler", "/admin/worker-clock-patrol", {"ok": 1}) == 200,
)

# ── 全域 _json 行為完全沒變：一律 200，不受這次加固影響 ──

check(
    "一般讀取接口 _json 在 ok:false 時仍然回 200（沒有被這次改動波及）",
    send_via("_json", "/admin/usage", {"ok": False, "error": "whatever"}) == 200,
)
check(
    "一般讀取接口 _json 在 ok:true 時回 200",
    send_via("_json", "/admin/usage", {"ok": True}) == 200,
)

print()
if FAILS:
    print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
    sys.exit(1)
print("✅ 定時任務失敗回報護欄全過")
