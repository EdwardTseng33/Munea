# -*- coding: utf-8 -*-
"""Single-replica Cloud Run wrapper for the RunPod backup controller."""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Response

from runpod_backup import BackupController, Config


STATUS: dict[str, Any] = {
    "started_at": time.time(),
    "last_run_at": 0.0,
    "last_success_at": 0.0,
    "last_result": None,
    "last_failure_waiting": 0,
    "last_error": "",
    "cycles": 0,
}

# 開卡/收卡帳本（2026-07-31 · Edward 早上問「為什麼開了一張 5090」、
# 我們只能靠 pod 命名反推——因為 run_once 的決定只存 last_result 一格、
# 下一輪 no_change 就蓋掉，雲端日誌從來沒有這一筆）。
# 兩路並行：①每筆非 no_change 動作立刻 print 進 Cloud Run 日誌（永久帳）
# ②記憶體環形帳本供 /events 直接查（重啟會清空、日誌才是正本）。
EVENTS: deque[dict[str, Any]] = deque(maxlen=100)


def _record_event(result: dict[str, Any]) -> None:
    action = str(result.get("action") or "")
    if action in ("", "no_change"):
        return
    event = {
        "at": time.time(),
        "at_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **result,
    }
    EVENTS.append(event)
    print("[runpod-controller] event: " + json.dumps(event, ensure_ascii=False),
          flush=True)


def _validated_config() -> Config:
    config = Config.from_env()
    config.validate()
    if config.mode != "active":
        raise RuntimeError("Cloud Run backup controller must use active mode")
    if not config.gateway_url.startswith("https://"):
        raise RuntimeError("MUNEA_GATEWAY_URL must be an HTTPS URL")
    if not config.gateway_admin_key:
        raise RuntimeError("MUNEA_GATEWAY_ADMIN_KEY is required")
    if not config.worker_key:
        raise RuntimeError("MUNEA_AVATAR_APP_KEY is required")
    if not os.environ.get("RUNPOD_API_KEY", "").strip():
        raise RuntimeError("RUNPOD_API_KEY is required")
    return config


# Seconds to wait before retrying a failed startup (bad env/config). Keeping the
# loop alive and retrying -- instead of letting the task die -- means /health and
# the Cloud Run log keep reporting the real cause instead of a frozen ok=false.
_STARTUP_RETRY_SECONDS = 30

# Health window fallback for when Config.from_env() itself fails: the window
# must not depend on the very setting that may be broken.
_FALLBACK_POLL_SECONDS = 15

# A freshly started revision has not completed run_once yet (it needs a RunPod +
# Gateway round trip). Inside this window report "starting", not "down", so a
# routine deploy does not flash the uptime check red.
_STARTUP_GRACE_SECONDS = 120


async def _controller_loop(stop: asyncio.Event) -> None:
    controller: BackupController | None = None
    while not stop.is_set():
        if controller is None:
            # Build config + controller inside the guarded loop. A failed
            # validate() here used to raise straight out of this asyncio task and
            # kill it silently: cycles stuck at 0, last_error empty, nothing in
            # the log. Now the cause lands in STATUS["last_error"] (surfaced by
            # /health) and stdout, and we retry instead of dying.
            try:
                controller = BackupController(_validated_config())
                STATUS["last_error"] = ""
            except Exception as exc:
                STATUS["last_error"] = f"startup: {type(exc).__name__}: {str(exc)[:300]}"
                print("[runpod-controller] " + STATUS["last_error"], flush=True)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=_STARTUP_RETRY_SECONDS)
                except asyncio.TimeoutError:
                    pass
                continue

        STATUS["last_run_at"] = time.time()
        try:
            result = await asyncio.to_thread(controller.run_once)
            STATUS.update({
                "last_success_at": time.time(),
                "last_result": result,
                "last_error": "",
                "cycles": int(STATUS["cycles"]) + 1,
            })
            _record_event(result)
        except Exception as exc:
            # 失敗的時候順手記下「當下有沒有人在等」——健康檢查靠這個決定要不要叫人。
            # 開不出備援，沒人在等的時候只是浪費；有人在等就是打不通，兩者不能同一個等級。
            waiting = 0
            try:
                snap = controller.gateway.snapshot() or {}
                waiting = max(
                    int(snap.get("queue_depth") or 0),
                    int(snap.get("avatar_active") or 0),
                    int(snap.get("active_calls") or 0),
                )
            except Exception:
                waiting = 0   # 連總機都問不到就當沒人在等，這種情況本來就會被 stalled 抓到
            STATUS.update({
                "last_error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "last_failure_waiting": waiting,
                "cycles": int(STATUS["cycles"]) + 1,
            })
            print("[runpod-controller] run_once failed (waiting=%d): %s"
                  % (waiting, STATUS["last_error"]), flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=controller.config.poll_seconds)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = asyncio.Event()
    task = asyncio.create_task(_controller_loop(stop))
    yield
    stop.set()
    await task


app = FastAPI(title="munea-runpod-capacity-controller", lifespan=lifespan)


def _health_payload() -> tuple[dict[str, Any], int]:
    """Return the health snapshot plus the HTTP status it deserves.

    Never raises. Config.from_env() used to run unguarded in the handler, so one
    malformed env var (e.g. an empty MUNEA_RUNPOD_SLOTS) made the health check
    itself throw: a 500 with a 60-line traceback that reads like a dead service,
    and -- worse -- it hid the startup cause that _controller_loop had carefully
    recorded in STATUS["last_error"] for this endpoint to report.
    """
    last_success = float(STATUS["last_success_at"] or 0)
    payload: dict[str, Any] = {
        "service": "munea-runpod-capacity-controller",
        "cycles": STATUS["cycles"],
        "last_success_at": last_success,
        "last_error": STATUS["last_error"],
        "last_action": (STATUS["last_result"] or {}).get("action"),
    }

    try:
        config = Config.from_env()
    except Exception as exc:
        # Reading the config is itself a health signal: the loop cannot work
        # either. Report the cause on a failing status instead of a stack trace.
        payload.update({
            "ok": False,
            "state": "config_error",
            "mode": "unknown",
            "config_error": f"{type(exc).__name__}: {str(exc)[:300]}",
        })
        return payload, 503

    payload["mode"] = config.mode
    max_age = max(90, (config.poll_seconds or _FALLBACK_POLL_SECONDS) * 4)

    if last_success > 0 and (time.time() - last_success) <= max_age:
        payload.update({"ok": True, "state": "ok"})
        return payload, 200

    if last_success == 0 and (
        time.time() - float(STATUS["started_at"]) <= _STARTUP_GRACE_SECONDS
    ):
        payload.update({"ok": False, "state": "starting"})
        return payload, 200

    # 這裡要分兩種「跑不完」，因為它們該叫的人完全不同
    # （Edward 2026-08-07：看門狗從早上 8 點叫到下午，但服務本身根本沒壞）。
    #
    #   ① 管家自己壞了（程式爆掉、連不到總機）→ 真的要叫工程的人來看 → 503
    #   ② 對方不讓我開卡（餘額不足、機房沒貨）→ 管家運作完全正常，只是被拒絕。
    #      報成 503 等於天天喊「服務掛了」，查過去卻發現服務好好的——狼來了喊久了，
    #      真的掛掉那次就沒人理。這種要回 200，但把原因寫在狀態上讓人看得見。
    #
    # 不是靜音：state 會明說 provider_unavailable、last_error 原樣保留，
    # 該補錢的事實一眼看得到，只是不再偽裝成服務故障。
    err = str(STATUS.get("last_error") or "")
    provider_blocked = any(k in err.lower() for k in (
        "balance is too low", "add funds", "insufficient",
        "no instances currently available", "out of capacity",
    ))
    # 但「開不出卡」什麼時候該叫，要看有沒有人在等：
    #   沒人在等 → 開不出來不影響任何人，回 200（別喊狼來了）
    #   有人在等 → 有人打進來卻沒機器接，那是真的服務中斷，一定要叫
    waiting = int(STATUS.get("last_failure_waiting") or 0)
    if provider_blocked and waiting == 0:
        payload.update({
            "ok": True,
            "state": "provider_unavailable",
            "note": "備援開不出來（餘額不足或機房沒貨），但目前沒有人在等；管家本身運作正常",
        })
        return payload, 200
    if provider_blocked:
        payload.update({
            "ok": False,
            "state": "provider_unavailable_with_demand",
            "note": "有人在等卻開不出備援——餘額不足或機房沒貨，這會讓使用者打不通",
        })
        return payload, 503

    # Cycles are not completing. This has to fail the uptime check: ok=false on
    # an HTTP 200 let a stalled control loop read as healthy from the outside.
    payload.update({"ok": False, "state": "stalled"})
    return payload, 503


@app.get("/health")
def health(response: Response) -> dict[str, Any]:
    payload, status_code = _health_payload()
    response.status_code = status_code
    return payload


@app.get("/")
def root(response: Response) -> dict[str, Any]:
    return health(response)


@app.get("/events")
def events() -> dict[str, Any]:
    """最近的開卡/收卡動作（新到舊）。重啟會清空；完整歷史看 Cloud Run 日誌
    的 "[runpod-controller] event:" 行。"""
    return {"events": list(reversed(EVENTS)), "count": len(EVENTS)}
