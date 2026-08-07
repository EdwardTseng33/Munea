#!/usr/bin/env python3
"""一次性清理：刪掉 2026-07-23 傍晚的展示救援機 munea-demo-avatar-01。

背景：正牌展示機（munea-flashhead-demo-768-r6000ada）已重開並接回
munea-b2b 網站，這台救援機功成身退、留著只是燒錢（$0.69/hr）。
它掛的置物櫃（fz8pl9udh4）會保留、不受影響；App 正式線/備援線
（munea-vocaframe-*）完全不在本工具射程內。

用法（Edward 一鍵）：python E:/Claude/Munea/deploy/runpod-demo/cleanup-eu-rescue-20260723.py
"""

import json
import urllib.request
from pathlib import Path

TARGET_ID = "7joewzkghg8oma"
TARGET_NAME = "munea-demo-avatar-01"
BASE = "https://rest.runpod.io/v1"


def api_key() -> str:
    env = Path(__file__).resolve().parents[1] / "runpod-avatar" / ".env"
    for line in env.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("RUNPOD_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("RUNPOD_API_KEY not found")


def call(method: str, path: str):
    req = urllib.request.Request(
        BASE + path, headers={"Authorization": "Bearer " + api_key()}, method=method
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def main() -> None:
    try:
        pod = call("GET", f"/pods/{TARGET_ID}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"已經不在了（{TARGET_ID}），不用刪。")
            return
        raise
    name = str(pod.get("name") or "")
    if name != TARGET_NAME:
        raise SystemExit(f"身分不符（{name}），為安全起見不刪。")
    if "vocaframe" in name:
        raise SystemExit("App 線機器，絕不刪。")
    call("DELETE", f"/pods/{TARGET_ID}")
    print(f"已刪：{TARGET_NAME}（{TARGET_ID}）。置物櫃保留。")
    print("目前還在跑的機器：")
    for p in call("GET", "/pods"):
        print(" -", p.get("id"), "|", p.get("name"))


if __name__ == "__main__":
    main()
