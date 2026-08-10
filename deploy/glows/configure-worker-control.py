"""Update FlashHead control-plane settings without printing secret values."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ALLOWED_KEYS = {
    "MUNEA_APP_KEY",
    "MUNEA_ALLOW_LEGACY_APP_KEY",
    "MUNEA_CALL_CONTROL_URL",
    "MUNEA_CALL_PROTOCOL_REQUIRED",
    "MUNEA_CALL_TOKEN_SECRET",
    "MUNEA_RELEASE_COMMIT",
    "MUNEA_RELEASE_VERSION",
    "MUNEA_FH_CHAR_A05",
    "MUNEA_FH_CHAR_A06",
    "MUNEA_FH_CKPT_DIR",
    "MUNEA_FH_FRAME_SIZE",
    "MUNEA_FH_REPO",
    "MUNEA_FH_SLOTS",
    "MUNEA_FH_WAV2VEC_DIR",
    "MUNEA_GATEWAY_ADMIN_KEY",
    "MUNEA_PYTHON_BIN",
    "MUNEA_WORKER_HEARTBEAT_SECONDS",
    "MUNEA_WORKER_ID",
}


def update_env(path: Path, values: dict[str, str]) -> list[str]:
    unexpected = sorted(set(values) - ALLOWED_KEYS)
    if unexpected:
        raise ValueError("unsupported settings: " + ", ".join(unexpected))

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    export_style = any(line.lstrip().startswith("export ") for line in lines)
    updated: list[str] = []
    seen: set[str] = set()
    for line in lines:
        assignment = line.lstrip()
        if assignment.startswith("export "):
            assignment = assignment[len("export "):]
        key = assignment.split("=", 1)[0].strip() if "=" in assignment else ""
        if key in values:
            if key in seen:
                continue
            prefix = "export " if export_style else ""
            updated.append(f"{prefix}{key}={values[key]}")
            seen.add(key)
        else:
            updated.append(line)
    for key, value in values.items():
        if key not in seen:
            prefix = "export " if export_style else ""
            updated.append(f"{prefix}{key}={value}")
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return sorted(values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    # PowerShell pipelines can prefix UTF-8 JSON with a BOM. Accept it so the
    # same secret-safe configurator works from both Windows and Linux hosts.
    raw = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    values = {str(key): str(value) for key, value in raw.items()}
    changed = update_env(args.env_file, values)
    print("updated control settings: " + ",".join(changed))


if __name__ == "__main__":
    main()
