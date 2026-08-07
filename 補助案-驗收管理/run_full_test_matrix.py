#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐支跑完出貨檢查的每一支測試，不中斷，產出完整的整合測試紀錄。

為什麼要另外寫：`npm run test:launch` 是用 && 一路串下去的，**第一支失敗整串就停**，
後面的測試根本沒被跑到。當驗收紀錄用會誤導——看起來只有一支紅，其實後面幾十支
是「沒驗過」而不是「通過」。2026-08-10 就踩到：跑到第 39 支停住，後面 57 支全沒跑。

用法：
    python run_full_test_matrix.py                # 全跑（約 10-15 分鐘）
    python run_full_test_matrix.py --list         # 只列出會跑哪些，不執行

產出：
    out/test-matrix-<日期>.md    給人看的整合測試紀錄
    out/test-matrix-<日期>.json  給程式用的原始結果
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
OUT = ROOT / "out"
TAIPEI = timezone(timedelta(hours=8))


def launch_commands():
    """從 package.json 的 test:launch 拆出每一支指令。單一真相來源，不另外抄一份清單。"""
    pkg = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    raw = pkg["scripts"]["test:launch"]
    return [c.strip() for c in raw.split("&&") if c.strip()]


def classify(cmd):
    """粗分類，讓紀錄看得出涵蓋面。依檔名關鍵字歸類。"""
    name = cmd.lower()
    buckets = [
        ("安全與危機", ("guardian", "crisis", "escalation", "impossible_promise", "fabrication", "reasoning_leak")),
        ("健康知識與衛教", ("health", "tcm", "supplement", "food", "metabolic", "chronic", "clinic", "vitals", "medication")),
        ("聊聊與語音", ("voice", "live_lookup", "lookup_model", "persona", "relationship", "flashhead")),
        ("通知與推播", ("notification", "apns")),
        ("後台與權限", ("admin", "thin_door", "rate_limit", "security_headers", "cors", "scope")),
        ("金流與訂閱", ("apple_store", "store-verification", "subscription", "free_signup")),
        ("資料與同步", ("cloud", "person_profile", "privacy_export", "family", "wellbeing", "mood")),
        ("部署與監控", ("deploy", "gateway_monitor", "watchdog", "canary", "release", "clock")),
        ("介面與多語", ("i18n", "localization", "ui-contracts", "locale")),
    ]
    for label, keys in buckets:
        if any(k in name for k in keys):
            return label
    return "其他"


def run_one(cmd, timeout=300):
    started = time.time()
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=str(REPO),
            capture_output=True, timeout=timeout,
        )
        out = (proc.stdout or b"").decode("utf-8", "replace")
        err = (proc.stderr or b"").decode("utf-8", "replace")
        blob = out + "\n" + err
        cases = sum(int(n) for n in re.findall(r"Ran (\d+) tests? in", blob))
        return {
            "cmd": cmd,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "cases": cases,
            "seconds": round(time.time() - started, 1),
            "tail": blob.strip().splitlines()[-6:] if proc.returncode != 0 else [],
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "ok": False, "returncode": -1, "cases": 0,
                "seconds": round(time.time() - started, 1), "tail": ["逾時未完成"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    cmds = launch_commands()
    if args.list:
        for i, c in enumerate(cmds, 1):
            print(f"{i:3}. [{classify(c)}] {c}")
        print(f"\n合計 {len(cmds)} 支")
        return 0

    stamp = datetime.now(TAIPEI)
    results = []
    for i, cmd in enumerate(cmds, 1):
        r = run_one(cmd)
        r["order"] = i
        r["group"] = classify(cmd)
        results.append(r)
        mark = "OK  " if r["ok"] else "FAIL"
        print(f"{mark} {i:3}/{len(cmds)} [{r['group']}] {cmd}  ({r['seconds']}s)", flush=True)

    OUT.mkdir(exist_ok=True)
    day = stamp.strftime("%Y%m%d")
    (OUT / f"test-matrix-{day}.json").write_text(
        json.dumps({"generatedAt": stamp.isoformat(), "results": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n",
    )

    passed = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    cases = sum(r["cases"] for r in results)

    lines = [
        "# Munea 沐寧 · 整合測試紀錄",
        "",
        f"執行時間：{stamp.strftime('%Y-%m-%d %H:%M')}（台灣時間）",
        f"測試支數：{len(results)} 支　｜　通過 {len(passed)}　失敗 {len(failed)}",
        f"個別測試案例：約 {cases} 項（僅計回報「Ran N tests」的部分）",
        "",
        "> 本紀錄逐支執行、不中斷。出貨檢查本身是串接式的，第一支失敗會整串停下，",
        "> 那種跑法無法得知後面的測試是通過還是沒跑到，因此驗收紀錄一律用這支工具產生。",
        "",
        "## 一、依類別統計",
        "",
        "| 類別 | 支數 | 通過 | 失敗 |",
        "|---|---:|---:|---:|",
    ]
    groups = {}
    for r in results:
        g = groups.setdefault(r["group"], {"n": 0, "ok": 0})
        g["n"] += 1
        g["ok"] += 1 if r["ok"] else 0
    for name, g in sorted(groups.items(), key=lambda kv: -kv[1]["n"]):
        lines.append(f"| {name} | {g['n']} | {g['ok']} | {g['n'] - g['ok']} |")

    lines += ["", "## 二、失敗清單", ""]
    if failed:
        for r in failed:
            lines.append(f"### {r['order']}. {r['cmd']}")
            lines.append("")
            for t in r["tail"]:
                lines.append(f"    {t}")
            lines.append("")
    else:
        lines.append("本次無失敗。")

    lines += ["", "## 三、逐支結果", "", "| # | 類別 | 指令 | 結果 | 秒 |", "|---:|---|---|:-:|---:|"]
    for r in results:
        lines.append(f"| {r['order']} | {r['group']} | `{r['cmd']}` | {'✅' if r['ok'] else '❌'} | {r['seconds']} |")

    (OUT / f"test-matrix-{day}.md").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8", newline="\n")
    print(f"\n完成：{len(passed)} 通過 / {len(failed)} 失敗，共 {len(results)} 支")
    print(f"紀錄：{OUT / f'test-matrix-{day}.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
