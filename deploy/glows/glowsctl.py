# -*- coding: utf-8 -*-
"""沐寧 · Glows.ai 台灣 4090 開卡/關卡控制器（照 runpod-avatar/podctl.py 同款做）

用法：
  python glowsctl.py list                       # 看現有機器（含門牌 accesses）
  python glowsctl.py specs                      # 查庫存/價格（台灣區 4090）
  python glowsctl.py create [snapshot_id]        # 開一台 4090（給 snapshot_id 就從快照開，
                                                  # 不給就走原本的 CUDA12.8 Torch2.7.1 Base）
  python glowsctl.py status <ins-id>             # 單台細節（SSH 埠 + HTTP 門牌 + 密碼）
  python glowsctl.py access <ins-id>             # 只印 HTTP 8888 對外門牌（App 用）
  python glowsctl.py snapshot <ins-id> <名字>    # 拍快照保存環境
  python glowsctl.py release <ins-id>            # 退還機器、停止計費

鑰匙：同目錄 .env 的 GLOWS_SDK_TOKEN=...（已 gitignore）
API 說明書：https://sdkdoc.glows.ai/（Edward 2026-07-11 提供）

2026-07-13 補（卡西法）：把「印出來給人看」跟「return dict 給程式呼叫」拆開——
list_instances() / get_status() / create() / release() / snapshot() / parse_access()
這幾支不印東西、只 return，給 deploy/glows/autoscale.py 串流程用；cmd_* 系列維持
原本的 CLI 印法，內部改叫這幾支資料層函式，行為對人不變。

create() 新增 from_snapshot_id 支援（快速重建用，不必每次 15 分鐘重裝環境）。
警告：from_snapshot_id 這個 body 欄位名是照 GLOWS 既有的 from_image_id 命名風格推測，
還沒被真 token 驗證過（見 docs/容量監控告警與自動擴縮-方案-2026-07-13.md 第E-4項）
——token 到位後第一次真跑 open_card(from_snapshot_id=...) 要順手確認這欄位名對
不對，不對就在這裡改一行，呼叫端（autoscale.py）介面不用動。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://a.glows.ai/sdk/v1"
HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_IMAGE = "img-gzq2xep6"
DEFAULT_GPU = "NVIDIA GeForce RTX 4090"
DEFAULT_REGIONS = ["TW-03", "TW-04"]
DEFAULT_PORTS = '[{"port":8888,"protocol":2},{"port":22,"protocol":1}]'


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


# ---------------------------------------------------------------------------
# 資料層——不印東西，return dict/list，給程式呼叫用（autoscale.py 靠這幾支組流程）。
# ---------------------------------------------------------------------------

def list_instances():
    """回傳 instance dict 清單（原始 API 形狀，未整理）。"""
    j = _call("GET", "/instance/list", {"page": 1, "per_page": 20})
    return j.get("instances") or j.get("data") or []


def get_status(instance_id):
    """單台細節 dict（原始 API 形狀）。"""
    j = _call("GET", "/instance", {"request_id": instance_id})
    return j.get("instance") or j


def parse_access(instance_data):
    """從 status/create 回應的 instance dict 撈 ssh/http 門牌。

    警告：accesses 欄位命名（protocol/listenPort/url 的實際值）目前沒有真 token
    可以驗證——這裡用最合理猜測（README 已知 http 用 protocol=="http"；ssh 那筆
    退而求其次用 protocol in ("ssh","tcp") 或 innerPort/port==22 判斷）。token
    到位後第一次真跑 open_card()，要順手核對這支抓得對不對（回報清單第 3 點）。
    """
    accesses = instance_data.get("accesses") or []
    http_url = None
    ssh_host = None
    ssh_port = None
    for a in accesses:
        proto = str(a.get("protocol") or "").lower()
        inner_port = a.get("innerPort") or a.get("port")
        listen_port = a.get("listenPort") or a.get("port")
        url = (a.get("url") or "").split("?")[0]
        is_http = proto == "http" or inner_port == 8888
        is_ssh = proto in ("ssh", "tcp") or inner_port == 22
        if is_http and not is_ssh:
            http_url = url or http_url
        elif is_ssh:
            ssh_port = listen_port or ssh_port
            host = a.get("host") or a.get("ip")
            if not host and url:
                host = url.replace("ssh://", "").split("@")[-1].split(":")[0]
            ssh_host = host or ssh_host
    return {"http_url": http_url, "ssh_host": ssh_host, "ssh_port": ssh_port}


def create(from_snapshot_id=None, regions=None, meta_prefix="munea-face"):
    """開一台機器。優先從快照開（from_snapshot_id 給了就走這條，帶著整組模型
    環境，省掉 README 裡 5 分鐘手動重裝流程）；沒給快照就退回原本 base image
    路徑。兩區 fallback（TW-03 缺卡跳 TW-04）沿用原 cmd_create 邏輯。

    回傳 (instance_dict, region_used)；兩區都開不出來丟 RuntimeError。
    """
    regions = regions or DEFAULT_REGIONS
    meta = meta_prefix + "-" + str(int(time.time()))
    body = {
        "custom_meta_key": meta,
        "gpu_name": DEFAULT_GPU,
        "unit_qty": 1,
        "instance_category": "container",
        "remark": "munea realtime-avatar (glowsctl)",
        "ports": DEFAULT_PORTS,
    }
    if from_snapshot_id:
        body["from_snapshot_id"] = from_snapshot_id
    else:
        body["from_image_id"] = DEFAULT_IMAGE

    last_err = None
    for region in regions:
        try:
            req_body = dict(body, region_name=region)
            j = _call("POST", "/instance", body=req_body)
            data = j.get("instance") or j
            return data, region
        except Exception as e:
            last_err = e
    raise RuntimeError("兩區都開不出來：" + str(last_err))


def release(instance_id):
    return _call("DELETE", "/instance", {"request_id": instance_id})


def snapshot(instance_id, name):
    return _call("POST", "/snapshot", body={"instance_id": instance_id, "name": name})


def get_specs(regions=None):
    out = {}
    for region in (regions or DEFAULT_REGIONS):
        out[region] = _call("GET", "/spec/list", {"machine_category": 0, "from_image_id": DEFAULT_IMAGE,
                                                    "region_name": region})
    return out


# ---------------------------------------------------------------------------
# CLI 層——印出來給人看，內部都是叫上面的資料層函式，行為對人不變。
# ---------------------------------------------------------------------------

def cmd_list():
    instances = list_instances()
    if not instances:
        print(json.dumps({"instances": instances}, ensure_ascii=False, indent=1)[:800])
        return
    for ins in instances:
        print("-", ins.get("instanceID"), "·", ins.get("regionName"), "·", ins.get("status"))
        for a in ins.get("accesses", []):
            print("   ", a.get("protocol"), a.get("listenPort"), "->", a.get("url"))


def cmd_specs():
    specs = get_specs()
    for region, j in specs.items():
        print("==", region, "==")
        print(json.dumps(j, ensure_ascii=False, indent=1)[:1200])


def cmd_create(from_snapshot_id=None):
    try:
        data, region = create(from_snapshot_id=from_snapshot_id)
    except RuntimeError as e:
        raise SystemExit(str(e))
    tag = "（從快照 " + from_snapshot_id + "）" if from_snapshot_id else ""
    print("[" + region + "] 開出來了" + tag + "：")
    print(json.dumps(data, ensure_ascii=False, indent=1))


def cmd_status(ins):
    print(json.dumps(get_status(ins), ensure_ascii=False, indent=1))


def cmd_access(ins):
    data = get_status(ins)
    access = parse_access(data)
    if access["http_url"]:
        print(access["http_url"])
    else:
        print("找不到 http 門牌，完整回應：", json.dumps(data, ensure_ascii=False)[:600])


def cmd_snapshot(ins, name):
    print(json.dumps(snapshot(ins, name), ensure_ascii=False))


def cmd_release(ins):
    print(json.dumps(release(ins), ensure_ascii=False))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "list":
        cmd_list()
    elif args[0] == "specs":
        cmd_specs()
    elif args[0] == "create":
        cmd_create(args[1] if len(args) > 1 else None)
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
