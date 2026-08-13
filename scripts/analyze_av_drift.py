#!/usr/bin/env python3
"""聲嘴漂移曲線分析（2026-08-13 · Edward「延遲越來越嚴重、從結構上找原因」）。

吃 voice_avatar_direct_e2e.py 產出的 metrics.json（含 av_series），
把每一輪的她講話切成一段一段（靜默 ≥350ms 分段），逐段量
「聲音起 → 嘴巴動」的差，印出整輪的漂移曲線。

曲線形狀＝指認兇手：
  - 平的（每段差不多）        → 固定延遲：畫格倉深 / 起跑墊——量的是高原高度
  - 樓梯往上（一段比一段晚）  → 一輪內累積：生成慢於即時且沒還債
  - 錄影裡根本沒歪            → 手機端的儀表在句尾高估（尺不準）
"""
import json
import sys
from pathlib import Path


def segments(audio, quiet_gap_s=0.35, threshold_ratio=0.35, floor=0.012):
    """把聲音序列切成「一段一段的講話」：回傳每段的起點時間。"""
    peak = max((r for _, r in audio), default=0.0)
    th = max(floor, min(0.045, peak * threshold_ratio))
    starts = []
    last_loud = None
    for t, r in audio:
        if r >= th:
            if last_loud is None or (t - last_loud) >= quiet_gap_s:
                starts.append(t)
            last_loud = t
    return starts, th


def mouth_onset_near(motion, t0, before_s=0.20, after_s=1.60,
                     strong=0.025, weak=0.010):
    """在聲音段起點附近找嘴巴開始動的時間（單格強門檻，或連兩格弱門檻）。"""
    window = [(t, m) for t, m in motion if t0 - before_s <= t <= t0 + after_s]
    for i, (t, m) in enumerate(window):
        if m >= strong:
            return t
        nearby = [m2 for t2, m2 in window[i:i + 4] if 0 <= t2 - t <= 0.16]
        if len(nearby) >= 2 and all(v >= weak for v in nearby[:2]):
            return t
    return None


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "metrics.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = data.get("turns") or ([data] if "av_series" in data else [])
    if not turns:
        print("找不到 av_series（要用加了序列傾印的 voice_avatar_direct_e2e 跑）")
        return 2
    for turn in turns:
        series = turn.get("av_series") or {}
        audio = [(float(t), float(r)) for t, r in (series.get("audio") or [])]
        motion = [(float(t), float(m)) for t, m in (series.get("motion") or [])]
        n = turn.get("turn", "?")
        if not audio or not motion:
            print(f"— 第 {n} 輪：序列是空的（audio {len(audio)} / motion {len(motion)}）")
            continue
        t_base = audio[0][0]
        starts, th = segments(audio)
        dur = audio[-1][0] - t_base
        print(f"— 第 {n} 輪：講了 {dur:.1f} 秒、切出 {len(starts)} 段（聲音門檻 {th:.3f}）")
        lags = []
        for k, t0 in enumerate(starts, 1):
            mouth = mouth_onset_near(motion, t0)
            lag_ms = None if mouth is None else round((mouth - t0) * 1000)
            lags.append(lag_ms)
            mark = "" if lag_ms is None else ("▁" if lag_ms < 150 else ("▃" if lag_ms < 350 else ("▆" if lag_ms < 700 else "█")))
            when = t0 - t_base
            print(f"   段{k:2d}  開講後 {when:6.1f}s   嘴慢 {'—' if lag_ms is None else str(lag_ms)+' ms'}  {mark}")
        seen = [v for v in lags if v is not None]
        if len(seen) >= 2:
            head = seen[0]
            tail = seen[-1]
            print(f"   ▶ 開頭 {head}ms → 結尾 {tail}ms（{'累積 +' + str(tail-head) + 'ms' if tail > head + 100 else '沒有明顯累積'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
