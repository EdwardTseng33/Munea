import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "deploy" / "glows" / "configure-worker-control.py"
SPEC = importlib.util.spec_from_file_location("configure_worker_control", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


with tempfile.TemporaryDirectory() as directory:
    env_file = Path(directory) / "service.env"
    env_file.write_text("KEEP=value\nMUNEA_WORKER_ID=old\n", encoding="utf-8")
    changed = MODULE.update_env(
        env_file,
        {
            "MUNEA_WORKER_ID": "worker-1",
            "MUNEA_WORKER_HEARTBEAT_SECONDS": "30",
        },
    )
    assert changed == ["MUNEA_WORKER_HEARTBEAT_SECONDS", "MUNEA_WORKER_ID"]
    assert env_file.read_text(encoding="utf-8") == (
        "KEEP=value\n"
        "MUNEA_WORKER_ID=worker-1\n"
        "MUNEA_WORKER_HEARTBEAT_SECONDS=30\n"
    )

print("FlashHead control settings updater: PASS")

with tempfile.TemporaryDirectory() as directory:
    env_file = Path(directory) / "service.env"
    env_file.write_text(
        "export KEEP=value\n"
        "export MUNEA_WORKER_ID=old\n"
        "MUNEA_CALL_PROTOCOL_REQUIRED=2\n",
        encoding="utf-8",
    )
    MODULE.update_env(
        env_file,
        {
            "MUNEA_WORKER_ID": "worker-1",
            "MUNEA_CALL_PROTOCOL_REQUIRED": "3",
            "MUNEA_RELEASE_COMMIT": "abc123",
        },
    )
    assert env_file.read_text(encoding="utf-8") == (
        "export KEEP=value\n"
        "export MUNEA_WORKER_ID=worker-1\n"
        "export MUNEA_CALL_PROTOCOL_REQUIRED=3\n"
        "export MUNEA_RELEASE_COMMIT=abc123\n"
    )

print("FlashHead exported control settings updater: PASS")
