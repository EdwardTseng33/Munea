"""Static launch contract for the FlashHead worker heartbeat loop."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "deploy" / "runpod-avatar" / "flashhead_server.py").read_text(
    encoding="utf-8"
)


for required in (
    'MUNEA_WORKER_HEARTBEAT_SECONDS',
    '"/v1/internal/workers/" + _worker_id + "/health"',
    '{"healthy": True, "active": active}',
    'asyncio.create_task(_worker_heartbeat_loop())',
    'worker heartbeat disabled (configuration incomplete)',
):
    assert required in SOURCE, f"missing FlashHead heartbeat contract: {required}"

assert 'max(\n            10, int(os.environ.get("MUNEA_WORKER_HEARTBEAT_SECONDS", "30"))' in SOURCE
assert 'except Exception as exc:\n                    print("[call-control] worker heartbeat failed:' in SOURCE

print("FlashHead Gateway heartbeat contract: PASS")
