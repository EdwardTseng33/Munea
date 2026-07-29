"""Static and startup guards for the Cloud Run RunPod controller wrapper."""
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "deploy" / "runpod-avatar" / "controller_service.py").read_text(
    encoding="utf-8"
)
DEPLOY = (ROOT / "scripts" / "cloud-run-deploy-runpod-controller.ps1").read_text(
    encoding="utf-8"
)
DOCKERFILE = (ROOT / "deploy" / "runpod-avatar" / "Dockerfile").read_text(
    encoding="utf-8"
)


@contextmanager
def _env(**overrides):
    saved = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _status(service, **overrides):
    saved = dict(service.STATUS)
    try:
        service.STATUS.update(overrides)
        yield
    finally:
        service.STATUS.clear()
        service.STATUS.update(saved)


def _load_service():
    sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))
    import controller_service

    return controller_service


def check_health_behaviour(service) -> None:
    """/health must classify, never explode.

    2026-07-29: a deploy left MUNEA_RUNPOD_SLOTS empty. Config.from_env() ran
    unguarded inside the handler, so the health check raised -- HTTP 500 plus a
    60-line traceback that reads like a dead service, while the controller
    process was fine and the real cause never reached the response body.
    """
    now = time.time()

    # 1. Broken env var -> reported as config_error on a failing status, and the
    #    call itself must not raise (an exception here is the bug we fixed).
    with _env(MUNEA_RUNPOD_SLOTS=""), _status(service, started_at=now, last_success_at=now):
        payload, status = service._health_payload()
    assert status == 503, status
    assert payload["ok"] is False
    assert payload["state"] == "config_error"
    assert "MUNEA_RUNPOD_SLOTS" in payload["config_error"], payload["config_error"]

    # 2. Loop completing cycles -> healthy.
    with _env(MUNEA_RUNPOD_SLOTS="2"), _status(
        service, started_at=now - 600, last_success_at=now, cycles=7
    ):
        payload, status = service._health_payload()
    assert status == 200, status
    assert payload["ok"] is True and payload["state"] == "ok"

    # 3. Fresh revision inside the boot window -> "starting", not a red uptime
    #    check: the first run_once needs a RunPod + Gateway round trip.
    with _env(MUNEA_RUNPOD_SLOTS="2"), _status(
        service, started_at=now, last_success_at=0.0, cycles=0
    ):
        payload, status = service._health_payload()
    assert status == 200, status
    assert payload["state"] == "starting"

    # 4. Stalled loop -> must FAIL the uptime check. ok=false on an HTTP 200
    #    used to read as healthy from the outside.
    with _env(MUNEA_RUNPOD_SLOTS="2"), _status(
        service, started_at=now - 7200, last_success_at=now - 3600
    ):
        payload, status = service._health_payload()
    assert status == 503, status
    assert payload["ok"] is False and payload["state"] == "stalled"

    # 5. Never succeeded and past the grace period -> stalled, not "starting".
    with _env(MUNEA_RUNPOD_SLOTS="2"), _status(
        service, started_at=now - 600, last_success_at=0.0, cycles=0
    ):
        payload, status = service._health_payload()
    assert status == 503, status
    assert payload["state"] == "stalled"


def main() -> None:
    assert 'config.mode != "active"' in SERVICE
    assert 'MUNEA_GATEWAY_ADMIN_KEY is required' in SERVICE
    assert 'MUNEA_AVATAR_APP_KEY is required' in SERVICE
    assert 'RUNPOD_API_KEY is required' in SERVICE
    assert "await asyncio.to_thread(controller.run_once)" in SERVICE
    # A bad startup config must surface via /health + logs and retry, not kill
    # the asyncio task silently.
    assert "_STARTUP_RETRY_SECONDS" in SERVICE
    assert 'f"startup:' in SERVICE
    # The health handler must not read config unguarded: one bad env var used to
    # turn the uptime probe into a 500 traceback.
    assert "def _health_payload()" in SERVICE
    assert "config_error" in SERVICE
    assert "_STARTUP_GRACE_SECONDS" in SERVICE
    assert "response.status_code = status_code" in SERVICE
    assert '"--min-instances", "1"' in DEPLOY
    assert '"--max-instances", "1"' in DEPLOY
    assert '"--no-cpu-throttling"' in DEPLOY
    assert '"--memory", "512Mi"' in DEPLOY
    assert "munea-runpod-api-key" in DEPLOY
    assert "uvicorn controller_service:app" in DOCKERFILE
    check_health_behaviour(_load_service())
    print("RunPod controller service contract: ALL PASS")


if __name__ == "__main__":
    main()
