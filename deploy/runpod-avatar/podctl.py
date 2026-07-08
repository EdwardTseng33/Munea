# -*- coding: utf-8 -*-
"""沐寧 · RunPod 開卡/關卡控制器（測試＝正式縮小版的 scale-to-zero 手動版）

用法：
  python podctl.py create           # 開一張 4090（Secure 優先、沒有就問 Community）
  python podctl.py list             # 看現有機器與狀態
  python podctl.py status <podId>   # 看單台細節（含 SSH 連線資訊）
  python podctl.py stop <podId>     # 關卡（保留磁碟、便宜待機）
  python podctl.py terminate <podId># 銷毀（停止一切計費）

鑰匙：同目錄 .env 的 RUNPOD_API_KEY。
"""
import json
import os
import sys
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://rest.runpod.io/v1"

def _key():
    for line in open(os.path.join(HERE, ".env"), encoding="utf-8-sig"):
        if line.strip().startswith("RUNPOD_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("找不到 RUNPOD_API_KEY（deploy/runpod-avatar/.env）")

def _req(method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + _key()},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500]
        sys.exit(f"API {method} {path} 失敗：HTTP {e.code} · {detail}")

POD_SPEC = {
    "name": "munea-avatar-d1",
    "imageName": "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04",
    "gpuTypeIds": ["NVIDIA GeForce RTX 4090"],
    "gpuCount": 1,
    "cloudType": "SECURE",
    "containerDiskInGb": 60,
    "volumeInGb": 0,
    "supportPublicIp": True,
    "ports": ["22/tcp", "8188/http", "8201/http", "8443/tcp"],
    "env": {},
}

def create():
    spec = dict(POD_SPEC)
    if "--community" in sys.argv:
        spec["cloudType"] = "COMMUNITY"
    print(f"開卡：4090 × 1 · {spec['cloudType']} · 磁碟 {spec['containerDiskInGb']}GB ...")
    pod = _req("POST", "/pods", spec)
    print(json.dumps(pod, indent=1, ensure_ascii=False)[:800])
    pid = pod.get("id")
    if pid:
        print(f"\npodId = {pid} · 之後用 `python podctl.py status {pid}` 看狀態/連線")

def list_pods():
    pods = _req("GET", "/pods")
    if not pods:
        print("目前沒有任何機器（=沒有在燒錢）")
        return
    for p in pods:
        print(f"- {p.get('id')} · {p.get('name')} · {p.get('desiredStatus')} · "
              f"${p.get('costPerHr', '?')}/hr · gpu={p.get('machine', {}).get('gpuTypeId', '?')}")

def status(pid):
    p = _req("GET", f"/pods/{pid}")
    print(json.dumps(p, indent=1, ensure_ascii=False)[:1500])
    ip = p.get("publicIp")
    ports = p.get("portMappings") or {}
    if ip and ports.get("22"):
        print(f"\nSSH：ssh root@{ip} -p {ports['22']} -i ~/.ssh/id_ed25519")

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "create":
        create()
    elif cmd == "list":
        list_pods()
    elif cmd == "status":
        status(sys.argv[2])
    elif cmd == "stop":
        print(json.dumps(_req("POST", f"/pods/{sys.argv[2]}/stop"), indent=1)[:400]); print("已暫停（磁碟保留、只付置物費）")
    elif cmd == "start":
        print(json.dumps(_req("POST", f"/pods/{sys.argv[2]}/start"), indent=1)[:600]); print("喚醒指令已送出")
    elif cmd == "terminate":
        _req("DELETE", f"/pods/{sys.argv[2]}")
        print("已銷毀（計費停止）")
    else:
        sys.exit(__doc__)

if __name__ == "__main__":
    main()
