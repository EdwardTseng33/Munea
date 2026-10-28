#!/usr/bin/env python3
"""把分批跑的成績單合成一份總表，算出每題「跑幾次過幾次」。

為什麼要這支（2026-08-18）：整份 76 題各跑三次是 228 通電話、要四個多小時，
一次跑完中途出事就整批白費，所以拆批跑。但拆了之後每批各存一份成績單，
沒辦法回答「整份題庫到底穩不穩」——這支就是把它們接回來。

判讀方式：
  0/N   每次都不過 → 真的有問題，該修
  1..N-1/N  有時過有時不過 → 她的回答本來就有隨機性，別拿單次結果下結論
  N/N   每次都過 → 穩

跑法：
  python engine/eval/merge_runs.py results/chat-quality-live-A.json results/...-B.json
  python engine/eval/merge_runs.py --latest 6      # 直接取最近 6 份語音線成績單
"""
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")


def load(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("results", []):
            rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser(description="把分批跑的成績單合成一份總表")
    ap.add_argument("files", nargs="*", help="成績單路徑（可多份）")
    ap.add_argument("--latest", type=int, help="改成直接取最近 N 份語音線成績單")
    args = ap.parse_args()

    paths = list(args.files)
    if args.latest:
        found = sorted(glob.glob(os.path.join(RESULTS_DIR, "chat-quality-live-*.json")),
                       key=os.path.getmtime, reverse=True)[:args.latest]
        paths.extend(found)
    if not paths:
        print("沒有指定成績單（用檔名或 --latest N）", file=sys.stderr)
        sys.exit(2)

    rows = load(paths)
    if not rows:
        print("這幾份成績單裡沒有任何題目", file=sys.stderr)
        sys.exit(2)

    runs, passes, labels, iron = defaultdict(int), defaultdict(int), {}, defaultdict(int)
    skipped = set()
    for r in rows:
        sid = r["id"]
        labels[sid] = r.get("label", "")
        if r.get("verdict") in ("SKIP", "ERROR"):
            # 跳過的（這條線考不了）跟出錯的（服務忙碌、額度用完）都沒真的考到，
            # 算進去會冤枉那題。
            skipped.add(sid)
            continue
        runs[sid] += 1
        if r.get("verdict") == "PASS":
            passes[sid] += 1
        hr = r.get("hardRules") or {}
        iron[sid] += len(hr.get("violations") or [])

    total_runs = sum(runs.values())
    total_pass = sum(passes.values())
    never = sorted(k for k in runs if passes[k] == 0)
    shaky = sorted(k for k in runs if 0 < passes[k] < runs[k])
    solid = sorted(k for k in runs if passes[k] == runs[k])

    print("=" * 76)
    print(f"合併 {len(paths)} 份成績單：{len(runs)} 題、共跑 {total_runs} 次"
          + (f"（另有 {len(skipped)} 題這條線考不了、不算分）" if skipped else ""))
    if not total_runs:
        print("這幾份成績單裡沒有任何題目真的考到（可能全被跳過、或中途出錯）", file=sys.stderr)
        sys.exit(2)
    print(f"整體通過率：{total_pass}/{total_runs}（{total_pass / total_runs:.1%}）"
          f"　鐵律違反合計 {sum(iron.values())} 項")
    print("-" * 76)

    if never:
        print(f"🔴 每次都不過（{len(never)} 題）——真的有問題，要修：")
        for k in never:
            print(f"   0/{runs[k]}  {k}  {labels[k]}")
        print()
    if shaky:
        print(f"🟡 有時過有時不過（{len(shaky)} 題）——她的回答本來就有隨機性，"
              f"別拿單次結果下結論：")
        for k in shaky:
            print(f"   {passes[k]}/{runs[k]}  {k}  {labels[k]}")
        print()
    print(f"🟢 每次都過：{len(solid)} 題")
    if not never and not shaky:
        print("   整份題庫每一題每一次都過")
    print("=" * 76)


if __name__ == "__main__":
    main()
