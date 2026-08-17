#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""聲嘴同步驗收尺（2026-08-17 · Edward「想辦法能正確驗收」）。

不再用「打一通感覺一下」當驗收。判準寫死成數字、兩邊用同一把尺：
  A. 機器側：假手機三輪長講（voice_avatar_direct_e2e 的 av_series）逐段量
  B. 實機側：Edward 打一通，他手機自己回報的逐段帳（av_onset_lag_ms）同樣量

判準（v1 · 依 8/13 手術前後的實測校準）：
  ① 中段不准歪：除每輪最後一段外，任何一段嘴慢 ≤ 500ms
     （術前中段成叢 500-1350ms、術後 0——這條抓「病有沒有復發」）
  ② 整輪中位 ≤ 300ms（整體體感）
  ③ 天花板：任何一段 ≤ 900ms（術前最重 1351ms；最後一段的新起句延遲
     另案第二刀在修，先給 900 的緩衝、修完再收緊）
  ④ 不准成叢：不得連續 3 段都 > 500ms（成叢＝「越講越歪」復發的形狀）

跑法：
  python scripts/accept_av_sync.py --machine <result.json>     # 機器側評分
  python scripts/accept_av_sync.py --device [--minutes 30]     # 實機側評分（拉最近一通的帳）
"""
import argparse
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_av_drift import mouth_onset_near, segments  # noqa: E402

MID_MAX_MS = 500
MEDIAN_MAX_MS = 300
CEIL_MS = 900
CLUSTER_LEN = 3


def score(lags_by_turn):
    """lags_by_turn: [(輪次, [各段嘴慢ms（可含 None）]), ...] → (整體過不過, 報表行)"""
    lines = []
    overall = True
    for turn, lags in lags_by_turn:
        seen = [v for v in lags if v is not None]
        if not seen:
            lines.append(f"  第 {turn} 輪：量不到段落（樣本不足）→ 不計分")
            continue
        mid = seen[:-1] if len(seen) > 1 else seen
        c1 = all(v <= MID_MAX_MS for v in mid)
        med = sorted(seen)[len(seen) // 2]
        c2 = med <= MEDIAN_MAX_MS
        c3 = all(v <= CEIL_MS for v in seen)
        streak = best = 0
        for v in seen:
            streak = streak + 1 if v > MID_MAX_MS else 0
            best = max(best, streak)
        c4 = best < CLUSTER_LEN
        ok = c1 and c2 and c3 and c4
        overall = overall and ok
        mark = "✅" if ok else "❌"
        lines.append(
            f"  第 {turn} 輪 {mark}  段數 {len(seen)}  中位 {med}ms"
            f"  ①中段≤{MID_MAX_MS}:{'過' if c1 else '破（最重 ' + str(max(mid)) + 'ms）'}"
            f"  ②中位≤{MEDIAN_MAX_MS}:{'過' if c2 else '破'}"
            f"  ③天花板≤{CEIL_MS}:{'過' if c3 else '破（最重 ' + str(max(seen)) + 'ms）'}"
            f"  ④不成叢:{'過' if c4 else '破（連 ' + str(best) + ' 段）'}"
        )
    return overall, lines


def machine_mode(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    turns = data.get("turns") or []
    lags_by_turn = []
    for t in turns:
        series = t.get("av_series") or {}
        audio = [(float(a), float(b)) for a, b in (series.get("audio") or [])]
        motion = [(float(a), float(b)) for a, b in (series.get("motion") or [])]
        if not audio:
            continue
        starts, _ = segments(audio)
        lags = []
        for t0 in starts:
            m = mouth_onset_near(motion, t0)
            lags.append(None if m is None else round((m - t0) * 1000))
        lags_by_turn.append((t.get("turn", "?"), lags))
    return lags_by_turn


def device_mode(minutes):
    key = (os.environ.get("SUPA_KEY") or "").strip()
    if not key:
        print("需要 SUPA_KEY（正式資料庫鑰匙）"); sys.exit(2)
    base = "https://fespbkdwafueyonppzwq.supabase.co/rest/v1"
    import datetime
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    def q(path):
        h = {"apikey": key}
        if not key.startswith("sb_secret_"):
            h["Authorization"] = "Bearer " + key
        return json.load(urllib.request.urlopen(
            urllib.request.Request(base + path, headers=h), timeout=30))
    rows = q(f"/product_events?event_name=eq.av_onset_lag_ms&created_at=gte.{since}"
             f"&select=created_at,properties&order=created_at.asc&limit=500")
    by_turn = {}
    for r in rows:
        p = r.get("properties") or {}
        by_turn.setdefault(int(p.get("turn") or 0), []).append(int(p.get("ms") or 0))
    if not by_turn:
        print(f"最近 {minutes} 分鐘實機沒有逐段帳——請先打一通、講久一點（每輪 30 秒以上）")
        sys.exit(3)
    return sorted(by_turn.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", metavar="RESULT_JSON")
    ap.add_argument("--device", action="store_true")
    ap.add_argument("--minutes", type=int, default=30)
    args = ap.parse_args()
    if args.machine:
        lags = machine_mode(args.machine)
        title = "機器側（假手機長講）"
    elif args.device:
        lags = device_mode(args.minutes)
        title = f"實機側（最近 {args.minutes} 分鐘、他手機自己回報的逐段帳）"
    else:
        ap.print_help(); return 2
    ok, lines = score(lags)
    print(f"═══ 聲嘴同步驗收 · {title} ═══")
    for ln in lines:
        print(ln)
    print(f"\n判定：{'✅ 通過' if ok else '❌ 未通過'}"
          f"（判準：中段≤{MID_MAX_MS}ms／中位≤{MEDIAN_MAX_MS}ms／"
          f"天花板≤{CEIL_MS}ms／不得連 {CLUSTER_LEN} 段破 500）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
