# -*- coding: utf-8 -*-
"""RunPod Pod lifecycle client used by Munea's VocaFrame backup pool.

The module is import-safe for the capacity controller and also provides a small
CLI. Production creates require ``MUNEA_RUNPOD_TEMPLATE_ID`` so an empty GPU is
never opened by accident. Use ``create --allow-unbaked`` only for manual R&D.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://rest.runpod.io/v1"
DEFAULT_GPU_TYPES = (
    "NVIDIA GeForce RTX 4090",
    "NVIDIA RTX 6000 Ada Generation",
    "NVIDIA GeForce RTX 5090",
)


class RunPodError(RuntimeError):
    pass


def _csv(name: str, default: tuple[str, ...] = ()) -> list[str]:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise RunPodError(f"{name} must be an integer") from exc


def api_key() -> str:
    value = os.environ.get("RUNPOD_API_KEY", "").strip()
    if value:
        return value
    env_path = os.path.join(HERE, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8-sig") as handle:
            for line in handle:
                if line.strip().startswith("RUNPOD_API_KEY="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        return value
    raise RunPodError("RUNPOD_API_KEY is not configured")


def request(method: str, path: str, body: dict[str, Any] | None = None,
            timeout: int = 60) -> Any:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key(),
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:500]
        raise RunPodError(
            f"RunPod API {method} {path} failed: HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RunPodError(f"RunPod API {method} {path} unavailable: {exc}") from exc


def build_pod_spec(require_template: bool = True) -> dict[str, Any]:
    """Build a one-GPU, no-network-volume backup Pod specification."""
    template_id = os.environ.get("MUNEA_RUNPOD_TEMPLATE_ID", "").strip()
    if require_template and not template_id:
        raise RunPodError(
            "MUNEA_RUNPOD_TEMPLATE_ID is required for automated creation; "
            "publish the private VocaFrame image/template first"
        )

    spec: dict[str, Any] = {
        "name": os.environ.get("MUNEA_RUNPOD_POD_NAME", "munea-vocaframe-backup-01"),
        "computeType": "GPU",
        "gpuTypeIds": _csv("MUNEA_RUNPOD_GPU_TYPES", DEFAULT_GPU_TYPES),
        "gpuTypePriority": "custom",
        "gpuCount": 1,
        "cloudType": os.environ.get("MUNEA_RUNPOD_CLOUD_TYPE", "SECURE").upper(),
        "interruptible": False,
        "locked": False,
        "supportPublicIp": True,
        "containerDiskInGb": _int("MUNEA_RUNPOD_CONTAINER_DISK_GB", 60),
        "volumeInGb": _int("MUNEA_RUNPOD_VOLUME_GB", 0),
        "volumeMountPath": "/workspace",
        "ports": ["8188/http", "22/tcp"],
        "allowedCudaVersions": ["12.8"],
    }
    data_centers = _csv("MUNEA_RUNPOD_DATA_CENTERS", ("AP-JP-1",))
    if data_centers:
        spec["dataCenterIds"] = data_centers
        spec["dataCenterPriority"] = "custom"
    if template_id:
        spec["templateId"] = template_id
    else:
        spec["imageName"] = os.environ.get(
            "MUNEA_RUNPOD_IMAGE",
            "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404",
        )
    return spec


def create_pod(spec: dict[str, Any] | None = None,
               require_template: bool = True) -> dict[str, Any]:
    return request("POST", "/pods", spec or build_pod_spec(require_template))


def backup_update_spec() -> dict[str, Any]:
    """Bring a manually created Pod under the backup controller contract."""
    return {
        "name": os.environ.get("MUNEA_RUNPOD_POD_NAME", "munea-vocaframe-backup-01"),
        "ports": ["8188/http", "8888/http", "22/tcp"],
        "locked": False,
    }


def update_pod(pod_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Update a stopped Pod's boot configuration without exposing credentials."""
    if not pod_id or not spec:
        raise RunPodError("pod id and update spec are required")
    return request("PATCH", f"/pods/{pod_id}", spec)


def list_pods() -> list[dict[str, Any]]:
    result = request("GET", "/pods")
    return result if isinstance(result, list) else []


def list_templates() -> list[dict[str, Any]]:
    result = request("GET", "/templates")
    return result if isinstance(result, list) else []


def list_network_volumes() -> list[dict[str, Any]]:
    result = request("GET", "/networkvolumes")
    return result if isinstance(result, list) else []


def list_registry_auths() -> list[dict[str, Any]]:
    result = request("GET", "/containerregistryauth")
    return result if isinstance(result, list) else []


def create_template(spec: dict[str, Any]) -> dict[str, Any]:
    return request("POST", "/templates", spec)


def delete_network_volume(volume_id: str) -> dict[str, Any]:
    return request("DELETE", f"/networkvolumes/{volume_id}")


def get_pod(pod_id: str) -> dict[str, Any]:
    result = request("GET", f"/pods/{pod_id}")
    return result if isinstance(result, dict) else {}


def start_pod(pod_id: str) -> dict[str, Any]:
    return request("POST", f"/pods/{pod_id}/start")


def stop_pod(pod_id: str) -> dict[str, Any]:
    return request("POST", f"/pods/{pod_id}/stop")


def terminate_pod(pod_id: str) -> dict[str, Any]:
    return request("DELETE", f"/pods/{pod_id}")


def proxy_url(pod_id: str, port: int = 8188) -> str:
    return f"https://{pod_id}-{port}.proxy.runpod.net"


def managed_pods(prefix: str = "munea-vocaframe-backup") -> list[dict[str, Any]]:
    return [pod for pod in list_pods() if str(pod.get("name", "")).startswith(prefix)]


def _print_list() -> None:
    pods = list_pods()
    if not pods:
        print("No RunPod Pods are currently allocated.")
        return
    for pod in pods:
        machine = pod.get("machine") or {}
        gpu = pod.get("gpu") or {}
        gpu_name = machine.get("gpuDisplayName") or gpu.get("displayName") or "?"
        print(
            f"- {pod.get('id')} | {pod.get('name')} | {pod.get('desiredStatus')} | "
            f"${pod.get('costPerHr', '?')}/hr | {gpu_name}"
        )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: podctl.py list|status ID|create [--allow-unbaked]|configure-backup ID|"
            "start ID|stop ID|terminate ID"
        )
    command = sys.argv[1]
    try:
        if command == "list":
            _print_list()
        elif command == "audit":
            pods = list_pods()
            templates = list_templates()
            volumes = list_network_volumes()
            registry_auths = list_registry_auths()
            print(json.dumps({
                "pods": [{"id": p.get("id"), "name": p.get("name"),
                          "status": p.get("desiredStatus"), "costPerHr": p.get("costPerHr")}
                         for p in pods],
                "templates": [{"id": t.get("id"), "name": t.get("name"),
                               "image": t.get("imageName") or t.get("image"),
                               "isServerless": t.get("isServerless")}
                              for t in templates],
                "networkVolumes": [{"id": v.get("id"), "name": v.get("name"),
                                    "size": v.get("size"), "dataCenterId": v.get("dataCenterId")}
                                   for v in volumes],
                "registryAuths": [{"id": a.get("id"), "name": a.get("name")}
                                  for a in registry_auths],
            }, indent=2, ensure_ascii=False))
        elif command == "templates":
            templates = list_templates()
            if not templates:
                print("No private RunPod templates found.")
            for template in templates:
                print(
                    f"- {template.get('id')} | {template.get('name')} | "
                    f"image={template.get('imageName') or template.get('image')} | "
                    f"serverless={template.get('isServerless')}"
                )
        elif command == "volumes":
            volumes = list_network_volumes()
            if not volumes:
                print("No RunPod network volumes found.")
            for volume in volumes:
                print(
                    f"- {volume.get('id')} | {volume.get('name')} | "
                    f"{volume.get('size')}GB | {volume.get('dataCenterId')}"
                )
        elif command == "create-template":
            with open(sys.argv[2], encoding="utf-8") as handle:
                spec = json.load(handle)
            if spec.get("isPublic") is not False or spec.get("isServerless") is not False:
                raise RunPodError("VocaFrame backup template must be private and non-serverless")
            print(json.dumps(create_template(spec), indent=2, ensure_ascii=False)[:3000])
        elif command == "delete-volumes":
            volume_ids = sys.argv[2:]
            if not volume_ids or len(volume_ids) > 10:
                raise RunPodError("pass 1-10 explicit network volume IDs")
            existing = {str(v.get("id")): v for v in list_network_volumes()}
            unknown = [volume_id for volume_id in volume_ids if volume_id not in existing]
            if unknown:
                raise RunPodError("refusing to delete unknown volume IDs: " + ", ".join(unknown))
            for volume_id in volume_ids:
                volume = existing[volume_id]
                print(f"deleting {volume_id} | {volume.get('name')} | {volume.get('size')}GB")
                delete_network_volume(volume_id)
            remaining = list_network_volumes()
            print(json.dumps({
                "deleted": volume_ids,
                "remaining": [{"id": v.get("id"), "name": v.get("name"), "size": v.get("size")}
                              for v in remaining],
            }, indent=2, ensure_ascii=False))
        elif command == "status":
            print(json.dumps(get_pod(sys.argv[2]), indent=2, ensure_ascii=False)[:5000])
        elif command == "create":
            allow_unbaked = "--allow-unbaked" in sys.argv
            pod = create_pod(require_template=not allow_unbaked)
            print(json.dumps(pod, indent=2, ensure_ascii=False)[:3000])
        elif command == "configure-backup":
            print(json.dumps(
                update_pod(sys.argv[2], backup_update_spec()),
                indent=2,
                ensure_ascii=False,
            )[:3000])
        elif command == "start":
            print(json.dumps(start_pod(sys.argv[2]), indent=2, ensure_ascii=False))
        elif command == "stop":
            print(json.dumps(stop_pod(sys.argv[2]), indent=2, ensure_ascii=False))
        elif command == "terminate":
            print(json.dumps(terminate_pod(sys.argv[2]), indent=2, ensure_ascii=False))
        else:
            raise RunPodError("unknown command: " + command)
    except (RunPodError, IndexError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
