"""Cloud Run service wrapper for the Munea Gateway monitor."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from monitor import GatewayMonitor, build_monitor_from_env


STATE: dict[str, object] = {
    "started_at": 0.0,
    "last_cycle_at": 0.0,
    "last_report": None,
    "last_error": "",
    "cycles": 0,
}


async def _monitor_loop(monitor: GatewayMonitor, interval: float) -> None:
    while True:
        try:
            report = await asyncio.to_thread(monitor.run_once)
            STATE["last_report"] = report
            STATE["last_error"] = ""
        except Exception as exc:  # Keep monitoring after transient provider failures.
            STATE["last_error"] = str(exc)[:500]
        STATE["last_cycle_at"] = time.time()
        STATE["cycles"] = int(STATE["cycles"]) + 1
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor, interval = build_monitor_from_env()
    STATE["started_at"] = time.time()
    task = asyncio.create_task(_monitor_loop(monitor, interval))
    app.state.monitor_task = task
    try:
        yield
    finally:
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
        "cycles": STATE["cycles"],
        "last_cycle_at": STATE["last_cycle_at"],
        "last_error": STATE["last_error"],
        "last_report": STATE["last_report"],
    }
