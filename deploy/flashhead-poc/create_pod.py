# -*- coding: utf-8 -*-
"""FlashHead PoC 專用開卡（沿用 podctl 的 key/_req，換映像：torch2.7.1+cu12.8.1）"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runpod-avatar"))
import podctl

spec = {
    "name": "munea-flashhead-poc",
    "imageName": "runpod/pytorch:1.0.7-rc.138-cu1281-torch271-ubuntu2204",
    "gpuTypeIds": ["NVIDIA GeForce RTX 4090"],
    "gpuCount": 1,
    "cloudType": "SECURE",
    "containerDiskInGb": 60,
    "volumeInGb": 0,
    "supportPublicIp": True,
    "ports": ["22/tcp"],
    "env": {},
}
if "--community" in sys.argv:
    spec["cloudType"] = "COMMUNITY"
print(f"開卡：4090 x1 · {spec['cloudType']} · image={spec['imageName']}")
pod = podctl._req("POST", "/pods", spec)
print(json.dumps(pod, indent=1, ensure_ascii=False)[:800])
pid = pod.get("id")
if pid:
    print(f"\npodId = {pid}")
