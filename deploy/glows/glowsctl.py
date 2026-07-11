# -*- coding: utf-8 -*-
"""沐寧 · Glows.ai 台灣 4090 開卡/關卡控制器（照 runpod-avatar/podctl.py 同款做）

用法：
  python glowsctl.py list                # 看現有機器（含門牌 accesses）
  python glowsctl.py specs               # 查庫存/價格（台灣區 4090）
  python glowsctl.py create              # 開一台 4090（CUDA12.8 Torch2.7.1 Base）
  python glowsctl.py status <ins-id>     # 單台細節（SSH 埠 + HTTP 門牌 + 密碼）
  python glowsctl.py access <ins-id>     # 只印 HTTP 8888 對外門牌（App 用）
  python glowsctl.py snapshot <ins-id> <名字>   # 拍快照保存環境
  python glowsctl.py release <ins-id>    # 退還機器、停止計費

鑰匙：同目錄 .env 的 GLOWS_SDK_TOKEN=...（已 gitignore）
API 說明書：https://sdkdoc.glows.ai/（Edward 2026-07-11 提供）
"""
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://a.glows.ai/sdk/v1"
HERE = os.path.dirname(os.path.abspath(__file__))

# 開機預設值（2026-07-11 試車定案：跟手開的那台同規格）
DEFAULT_IMAGE = "img-gzq2xep6"          # CUDA12.8 Torch2.7.1 Base（py3.11+torch2.7.1+cu128 預裝）
DEFAULT_GPU = "NVIDIA GeForce RTX 4090"
DEFAULT_REGIONS = ["TW-03", "TW-04"]    # 先 03、缺卡跳 04
DEFAULT_PORTS = '[{"port":8888,"protocol":2},{"port":22,"protocol":1}]'  # protocol 待實測校正


def _token():
    for line in open(os.path.join(HERE, ".env"), encoding="utf-8"):
        line = line.strip()
        if line.startswith("GLOWS_SDK_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("缺鑰匙：deploy/glows/.env 裡放 GLOWS_SDK_TOKEN=...")


def _call(method, path, params=None, body=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", "Bearer " + _token())
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def cmd_list():
    j = _call("GET", "/instance/list", {"page": 1, "per_page": 20})
    for ins in (j.get("instances") or j.get("data") or []):
        print("-", ins.get("instanceID"), "·", ins.get("regionName"), "·", ins.get("status"))
        for a in ins.get("accesses", []):
            print("   ", a.get("protocol"), a.get("listenPort"), "->", a.get("url"))
    if not (j.get("instances") or j.get("data")):
        print(json.dumps(j, ensure_ascii=False, indent=1)[:800])


def cmd_specs():
    for region in DEFAULT_REGIONS:
        j = _call("GET", "/spec/list", {"machine_category": 0, "from_image_id": DEFAULT_IMAGE,
                                        "region_name": region})
        print("==", region, "==")
        print(json.dumps(j, ensure_ascii=False, indent=1)[:1200])


def cmd_create():
    import time as _t
    meta = "munea-face-" + str(int(_t.time()))
    last_err = None
    for region in DEFAULT_REGIONS:
        try:
            j = _call("POST", "/instance", body={
                "from_image_id": DEFAULT_IMAGE,
                "custom_meta_key": meta,
                "gpu_name": DEFAULT_GPU,
                "unit_qty": 1,
                "instance_category": "container",
                "region_name": region,
                "remark": "munea realtime-avatar (glowsctl)",
                "ports": DEFAULT_PORTS,
            })
            print(json.dumps(j, ensure_ascii=False, indent=1))
            return
        except Exception as e:
            last_err = e
            print(f"[{region}] 開不出來：{e}，換下一區…")
    raise SystemExit(f"兩區都開不出來：{last_err}")


def cmd_status(ins):
    j = _call("GET", "/instance", {"request_id": ins})
    print(json.dumps(j, ensure_ascii=False, indent=1))


def cmd_access(ins):
    j = _call("GET", "/instance", {"request_id": ins})
    blob = json.dumps(j)
    data = j.get("instance") or j
    for a in (data.get("accesses") or []):
        if a.get("protocol") == "http":
            url = (a.get("url") or "").split("?")[0]
            print(url)
            return
    print("找不到 http 門牌，完整回應：", blob[:600])


def cmd_snapshot(ins, name):
    print(json.dumps(_call("POST", "/snapshot", body={"instance_id": ins, "name": name}),
                     ensure_ascii=False))


def cmd_release(ins):
    print(json.dumps(_call("DELETE", "/instance", {"request_id": ins}), ensure_ascii=False))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "list":
        cmd_list()
    elif args[0] == "specs":
        cmd_specs()
    elif args[0] == "create":
        cmd_create()
    elif args[0] == "status":
        cmd_status(args[1])
    elif args[0] == "access":
        cmd_access(args[1])
    elif args[0] == "snapshot":
        cmd_snapshot(args[1], args[2] if len(args) > 2 else "munea-face")
    elif args[0] == "release":
        cmd_release(args[1])
    else:
        print(__doc__)
