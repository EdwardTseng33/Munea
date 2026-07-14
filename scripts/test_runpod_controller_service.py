"""Static and startup guards for the Cloud Run RunPod controller wrapper."""
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


def main() -> None:
    assert 'config.mode != "active"' in SERVICE
    assert 'MUNEA_GATEWAY_ADMIN_KEY is required' in SERVICE
    assert 'MUNEA_AVATAR_APP_KEY is required' in SERVICE
    assert 'RUNPOD_API_KEY is required' in SERVICE
    assert "await asyncio.to_thread(controller.run_once)" in SERVICE
    assert '"--min-instances", "1"' in DEPLOY
    assert '"--max-instances", "1"' in DEPLOY
    assert '"--no-cpu-throttling"' in DEPLOY
    assert "munea-runpod-api-key" in DEPLOY
    assert "uvicorn controller_service:app" in DOCKERFILE
    print("RunPod controller service contract: ALL PASS")


if __name__ == "__main__":
    main()
