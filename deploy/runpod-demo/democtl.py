#!/usr/bin/env python3
"""RunPod lifecycle guard for the isolated Munea B2B Demo.

`release` terminates only the exact Demo Pod after an explicit ID confirmation.
The network volume is preserved and `wake` recreates the Pod on that volume.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE = "https://rest.runpod.io/v1"
POD_NAME = os.environ.get("MUNEA_RUNPOD_DEMO_NAME", "munea-flashhead-demo-768-r6000ada")
VOLUME_ID = os.environ.get("MUNEA_RUNPOD_DEMO_VOLUME_ID", "7d3vqi99dm")
IMAGE = os.environ.get(
    "MUNEA_RUNPOD_DEMO_IMAGE",
    "runpod/pytorch:1.0.7-rc.138-cu1281-torch271-ubuntu2204",
)


class DemoControlError(RuntimeError):
    pass


def api_key() -> str:
    value = os.environ.get("RUNPOD_API_KEY", "").strip()
    if value:
        return value
    candidates = [
        Path(__file__).resolve().parents[1] / "runpod-avatar" / ".env",
        Path.cwd() / "deploy" / "runpod-avatar" / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("RUNPOD_API_KEY="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    raise DemoControlError("RUNPOD_API_KEY is not configured")


def request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise DemoControlError(f"RunPod {method} {path}: HTTP {exc.code}: {detail}") from exc


def demo_pods() -> list[dict[str, Any]]:
    pods = request("GET", "/pods")
    return [pod for pod in pods if pod.get("name") == POD_NAME]


def safe_summary(pod: dict[str, Any]) -> dict[str, Any]:
    mappings = pod.get("portMappings") or {}
    return {
        "id": pod.get("id"),
        "name": pod.get("name"),
        "status": pod.get("desiredStatus"),
        "costPerHr": pod.get("costPerHr"),
        "publicIp": pod.get("publicIp"),
        "sshPort": mappings.get("22") or mappings.get(22),
        "avatarHttp": f"https://{pod.get('id')}-8188.proxy.runpod.net",
        "networkVolumeId": VOLUME_ID,
    }


def wake() -> dict[str, Any]:
    existing = demo_pods()
    if existing:
        return safe_summary(existing[0])
    spec = {
        "name": POD_NAME,
        "computeType": "GPU",
        "gpuTypeIds": ["NVIDIA RTX 6000 Ada Generation"],
        "gpuTypePriority": "availability",
        "gpuCount": 1,
        "cloudType": "ALL",
        "interruptible": False,
        "locked": False,
        "supportPublicIp": True,
        "containerDiskInGb": 60,
        "networkVolumeId": VOLUME_ID,
        "volumeMountPath": "/workspace",
        "ports": ["8188/http", "8888/http", "22/tcp"],
        "allowedCudaVersions": ["12.8"],
        "dataCenterIds": ["US-IL-1"],
        "dataCenterPriority": "custom",
        "imageName": IMAGE,
        "dockerStartCmd": [
            "bash",
            "-lc",
            "ln -sf /workspace/munea-demo/current/post_start.sh /post_start.sh; exec /start.sh",
        ],
    }
    return safe_summary(request("POST", "/pods", spec))


def release(confirm_id: str) -> dict[str, Any]:
    matches = demo_pods()
    if len(matches) != 1:
        raise DemoControlError(f"expected exactly one Demo Pod, found {len(matches)}")
    pod = matches[0]
    pod_id = str(pod.get("id") or "")
    if not confirm_id or confirm_id != pod_id:
        raise DemoControlError("refusing release: pass --confirm-id with the current Demo Pod ID")
    request("DELETE", f"/pods/{pod_id}")
    return {"releasedPodId": pod_id, "preservedNetworkVolumeId": VOLUME_ID}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "wake", "release"))
    parser.add_argument("--confirm-id", default="")
    args = parser.parse_args()
    if args.action == "status":
        result: Any = [safe_summary(pod) for pod in demo_pods()]
    elif args.action == "wake":
        result = wake()
    else:
        result = release(args.confirm_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DemoControlError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
