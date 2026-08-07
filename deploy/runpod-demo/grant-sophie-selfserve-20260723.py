#!/usr/bin/env python3
"""Edward 一鍵：把三條「允許蘇菲自己做」規則加進 Munea 專案權限檔。

加的三條（只有這三條、其他不動）：
  1. Bash(vercel deploy *)                       → 蘇菲可自己上線 munea-b2b 網站
  2. Bash(python deploy/runpod-demo/democtl.py *)（含絕對路徑版）
                                                 → 蘇菲可自己開/關「展示機」
                                                   （小工具本身鎖死名字、只認展示機，
                                                    App 正式線/備援線碰不到）
  3. Bash(python E:/Claude/Munea/deploy/runpod-demo/cleanup-eu-rescue-20260723.py *)
                                                 → 蘇菲可替你刪掉 7/23 那台歐洲救援機

用法：python E:/Claude/Munea/deploy/runpod-demo/grant-sophie-selfserve-20260723.py
"""

import json
from pathlib import Path

SETTINGS = Path(r"E:\Claude\Munea\.claude\settings.local.json")
NEW_RULES = [
    "Bash(vercel deploy *)",
    "Bash(python deploy/runpod-demo/democtl.py *)",
    "Bash(python E:/Claude/Munea/deploy/runpod-demo/democtl.py *)",
    "Bash(python E:/Claude/Munea/deploy/runpod-demo/cleanup-eu-rescue-20260723.py *)",
]


def main() -> None:
    data = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    added = [rule for rule in NEW_RULES if rule not in allow]
    allow.extend(added)
    SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if added:
        print("已加進權限檔：")
        for rule in added:
            print(" +", rule)
    else:
        print("三條規則本來就都在，沒有改動。")
    print("完成。新開的蘇菲對話就會生效；同一個對話裡也立即可用。")


if __name__ == "__main__":
    main()
