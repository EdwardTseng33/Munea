#!/usr/bin/env python3
"""把兩份考卷成績單並排比較（2026-07-27 · 思考深度 A/B 用，但任何兩份都能比）。

用法：
  python engine/eval/compare_runs.py <前.json> <後.json>

看什麼：
  ① 過關題數與鐵律違反（守不守規矩）
  ② 七維各自的加減分（哪一項變好、哪一項退步）
  ③ 第一聲反應毫秒（她慢了多少）——語音線才有
  ④ 逐題判定變化（哪幾題翻盤，是變好還是變壞）

這支不呼叫任何模型、不花錢，純讀檔比對。
"""
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def label_of(doc, path):
    s = doc.get("summary") or {}
    bits = [s.get("line") or "text"]
    if s.get("thinkingLevel"):
        bits.append(f"思考={s['thinkingLevel']}")
    return f"{'／'.join(bits)}  ({path.split(chr(92))[-1].split('/')[-1]})"


def delta(before, after, digits=2):
    if before is None or after is None:
        return "—"
    d = round(after - before, digits)
    return f"{d:+.{digits}f}" if isinstance(d, float) else f"{d:+d}"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    a_path, b_path = sys.argv[1], sys.argv[2]
    a, b = load(a_path), load(b_path)
    sa, sb = a["summary"], b["summary"]

    print("=" * 76)
    print("成績單並排比較")
    print(f"  A（前）：{label_of(a, a_path)}")
    print(f"  B（後）：{label_of(b, b_path)}")
    print("-" * 76)
    print(f"{'項目':<22}{'A':>12}{'B':>12}{'變化':>12}")
    rows = [
        ("跑了幾題", "itemsRun", 0), ("PASS 題數", "passCount", 0),
        ("REVIEW 題數", "reviewCount", 0), ("FAIL 題數", "failCount", 0),
        ("ERROR 題數", "errorCount", 0), ("跳過題數", "skipCount", 0),
        ("鐵律違反總數", "hardRuleViolationTotal", 0),
    ]
    for name, key, _ in rows:
        va, vb = sa.get(key), sb.get(key)
        print(f"{name:<22}{va!s:>12}{vb!s:>12}{delta(va, vb, 0):>12}")
    pa, pb = sa.get("passRate"), sb.get("passRate")
    if pa is not None and pb is not None:
        print(f"{'PASS 率':<22}{pa*100:>11.1f}%{pb*100:>11.1f}%{(pb-pa)*100:>+11.1f}%")

    la, lb = sa.get("firstAudioLatency"), sb.get("firstAudioLatency")
    if la or lb:
        print("-" * 76)
        print("第一聲反應（她隔多久開口，長輩感受到的快慢）")
        for name, key in (("中位數 ms", "medianMs"), ("平均 ms", "meanMs"),
                           ("最慢 ms", "slowestMs")):
            va = (la or {}).get(key)
            vb = (lb or {}).get(key)
            print(f"{name:<22}{va!s:>12}{vb!s:>12}{delta(va, vb, 0):>12}")

    print("-" * 76)
    print("七維度平均分")
    dims = sorted(set(sa.get("dimensionAverages", {})) | set(sb.get("dimensionAverages", {})))
    for name in dims:
        va = sa.get("dimensionAverages", {}).get(name)
        vb = sb.get("dimensionAverages", {}).get(name)
        print(f"{name:<22}{va!s:>12}{vb!s:>12}{delta(va, vb):>12}")

    print("-" * 76)
    print("逐題判定變化（只列有變的）")
    va = {r["id"]: r for r in a["results"]}
    vb = {r["id"]: r for r in b["results"]}
    changed = 0
    for sid in sorted(set(va) | set(vb)):
        ra, rb = va.get(sid), vb.get(sid)
        pa_ = ra["verdict"] if ra else "（沒跑）"
        pb_ = rb["verdict"] if rb else "（沒跑）"
        if pa_ != pb_:
            changed += 1
            label = (rb or ra).get("label", "")
            print(f"  {sid:<5} {pa_:>7} → {pb_:<7}  {label}")
    if not changed:
        print("  （沒有任何一題翻盤）")
    print("=" * 76)


if __name__ == "__main__":
    main()
