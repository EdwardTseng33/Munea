# -*- coding: utf-8 -*-
"""Single-replica Cloud Run wrapper for the RunPod backup controller."""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response

from runpod_backup import BackupController, Config


STATUS: dict[str, Any] = {
    "started_at": time.time(),
    "last_run_at": 0.0,
    "last_success_at": 0.0,
    "last_result": None,
    "last_error": "",
    "cycles": 0,
}


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
        except Exception as exc:
            STATUS.update({
                "last_error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "cycles": int(STATUS["cycles"]) + 1,
            })
            print("[runpod-controller] run_once failed: " + STATUS["last_error"], flush=True)
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
