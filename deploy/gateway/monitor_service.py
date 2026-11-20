"""Cloud Run service wrapper for the Munea Gateway monitor.

Two ways to drive the monitor:

* scheduled (default deploy since 2026-11-17): Cloud Scheduler calls
  ``POST /run-once`` every couple of minutes. The service bills per request
  and can scale to zero, so it costs next to nothing.
* always-on (legacy, ``MUNEA_GATEWAY_MONITOR_LOOP=1``): a background loop
  polls every ``MUNEA_GATEWAY_MONITOR_INTERVAL_SECONDS``. This only works
  when the service keeps one instance with CPU always allocated, which is
  what made it the single most expensive line of the cloud bill. On
  2026-11-05 the minimum instance was dropped without switching modes, and
  the loop silently stopped running for twelve days: no instance, no alarm.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from monitor import GatewayMonitor, build_monitor_from_env


STATE: dict[str, object] = {
    "started_at": 0.0,
    "last_cycle_at": 0.0,
    "last_report": None,
    "last_error": "",
    "cycles": 0,
    "mode": "",
}

# One cycle at a time: the lifecycle/dedup state files are not safe for two
# overlapping run_once() calls (a slow poll plus the next scheduler tick).
_CYCLE_LOCK = threading.Lock()


def loop_enabled() -> bool:
    """Background loop is opt-in; scheduled ticks are the default."""
    return os.environ.get("MUNEA_GATEWAY_MONITOR_LOOP", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def run_cycle(monitor: GatewayMonitor) -> dict[str, object] | None:
    """Run one monitor cycle and record it. Never raises."""
    with _CYCLE_LOCK:
        report: dict[str, object] | None = None
        try:
            report = monitor.run_once()
            STATE["last_report"] = report
            STATE["last_error"] = ""
        except Exception as exc:  # Keep monitoring after transient provider failures.
            STATE["last_error"] = str(exc)[:500]
        STATE["last_cycle_at"] = time.time()
        STATE["cycles"] = int(STATE["cycles"]) + 1
        return report


async def _monitor_loop(monitor: GatewayMonitor, interval: float) -> None:
    while True:
        await asyncio.to_thread(run_cycle, monitor)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor, interval = build_monitor_from_env()
    app.state.monitor = monitor
    STATE["started_at"] = time.time()
    STATE["mode"] = "loop" if loop_enabled() else "scheduled"
    task = asyncio.create_task(_monitor_loop(monitor, interval)) if loop_enabled() else None
    app.state.monitor_task = task
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="munea-gateway-monitor", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": not bool(STATE["last_error"]),
        "mode": STATE["mode"],
        "cycles": STATE["cycles"],
        "last_cycle_at": STATE["last_cycle_at"],
        "last_error": STATE["last_error"],
        "last_report": STATE["last_report"],
    }


@app.post("/run-once")
def run_once() -> JSONResponse:
    """One monitor cycle per call (Cloud Scheduler tick).

    A failed cycle answers 500 so the scheduler records the tick as failed
    and retries; alerts found by a successful cycle are not failures.
    """
    report = run_cycle(app.state.monitor)
    ok = report is not None
    return JSONResponse(
        {
            "ok": ok,
            "mode": STATE["mode"],
            "cycles": STATE["cycles"],
            "last_error": STATE["last_error"],
            "report": report,
        },
        status_code=200 if ok else 500,
    )
