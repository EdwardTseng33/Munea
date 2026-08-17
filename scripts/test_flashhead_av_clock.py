#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""聲嘴對錶守門（2026-08-13 · Edward「延遲越來越嚴重、從結構上找原因」）。

結構病（真儀器量到的）：畫格出口是不看時間的傳送帶、聲音照自己的鐘走，
顯卡一慢那一段嘴型就整段遲到照播（單輪 45 秒遲到畫格、舊追齊 0 次觸發）。

這支守的新契約——聲音永遠是主時鐘、聲音永遠不等畫面：
  ① 畫格帶錶入隊；那格的聲音還沒播到（早到 > LEAD）＝扣住不播
  ② 那格的聲音早播完了（遲到 > LAG）＝整段丟掉、嘴跳回「現在」
  ③ idle 畫格沒有聲音＝不帶錶、照舊直接播
  ④ 沒綁錶（舊呼叫者/測試）＝行為與傳送帶相同
跑法：python scripts/test_flashhead_av_clock.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))

from flashhead_engine_core import (  # noqa: E402
    AudioOutBuffer,
    FrameSink,
    should_fast_first,
)

FPS = 12.5


def frames(n, tag=0):
    out = np.zeros((n, 2, 2, 3), dtype=np.uint8)
    out[:, 0, 0, 0] = np.arange(tag, tag + n) % 250
    return out


def check(name, ok):
    print(("  OK  " if ok else " FAIL ") + name)
    return ok


def main():
    results = []

    # ④ 沒綁錶＝傳送帶（舊呼叫姿勢 positional 也要通）
    sink = FrameSink(FPS)
    sink.push_many(frames(3), 0.0, FPS)
    popped = [sink.pop() for _ in range(3)]
    results.append(check("沒綁錶＝先到先播（相容舊行為）",
                         all(f is not None for f in popped) and sink.pop() is None))

    # ③ idle 畫格不帶錶＝照舊直接播（就算錶已綁）
    sink = FrameSink(FPS)
    sink.audio_pos_fn = lambda: 0.0
    sink.push_many(frames(2), 0.0, FPS, start_audio_pos=None)
    results.append(check("idle 畫格（沒聲音）不對錶、直接播", sink.pop() is not None))

    # ① 早到扣住：聲音錶在 0 秒、畫格是 2 秒後的內容 → 不播、隊列不動
    sink = FrameSink(FPS)
    sink.audio_pos_fn = lambda: 0.0
    sink.push_many(frames(3), 0.0, FPS, start_audio_pos=2.0)
    held = sink.pop()
    results.append(check("早到（聲音還沒播到那）＝扣住不播",
                         held is None and sink.depth() == 3 and sink.av_hold_events == 1))

    # 對齊窗內（畫面微微領先 0.2 秒 ≤ LEAD 0.28）＝正常播
    sink = FrameSink(FPS)
    sink.audio_pos_fn = lambda: 1.0
    sink.push_many(frames(2), 0.0, FPS, start_audio_pos=1.2)
    results.append(check("微微領先（設計內）＝正常播", sink.pop() is not None))

    # ② 遲到丟段：聲音錶在 5 秒、隊裡是 3.0~3.9 秒的舊嘴型＋4.99 起的新嘴型
    sink = FrameSink(FPS)
    sink.audio_pos_fn = lambda: 5.0
    sink.push_many(frames(12, tag=10), 0.0, FPS, start_audio_pos=3.0)    # 全部過期
    sink.push_many(frames(4, tag=100), 0.0, FPS, start_audio_pos=4.99)   # 對齊現在
    got = sink.pop()
    results.append(check("遲到＝整段丟掉、跳回現在",
                         got is not None and got[0, 0, 0] == 100
                         and sink.av_resync_events == 1 and sink.av_resync_frames == 12))

    # 全部過期＝丟光回 None（下一塊真話進來會接上）
    sink = FrameSink(FPS)
    sink.audio_pos_fn = lambda: 9.0
    sink.push_many(frames(5), 0.0, FPS, start_audio_pos=1.0)
    results.append(check("全部過期＝丟光、不播殭屍嘴型",
                         sink.pop() is None and sink.depth() == 0 and sink.av_resync_frames == 5))

    # 聲音錶讀數：AudioOutBuffer 只算真的播出去的樣本
    ao = AudioOutBuffer(24000, prebuffer_s=0.0)
    ao.push(np.ones(4800, dtype=np.int16))
    ao.pop_frame(); ao.pop_frame()
    results.append(check("聲音錶＝真播出的樣本數（480×2/24000=0.04s）",
                         abs(ao.played_pos_s() - 0.04) < 1e-6))

    # 帳要進健康快照：欄位存在
    sink = FrameSink(FPS)
    results.append(check("對錶儀表欄位齊全",
                         hasattr(sink, "av_resync_events") and hasattr(sink, "av_hold_events")
                         and hasattr(sink, "last_av_offset_ms")))

    # 錶要真的有被綁上（伺服器 wake 時）＋真話畫格要真的帶錶入隊——
    # 少任何一條，上面的行為測試全綠也只是「引擎會對錶」而不是「正式機在對錶」。
    server_src = (ROOT / "deploy" / "runpod-avatar" / "flashhead_server.py").read_text(encoding="utf-8")
    core_src = (ROOT / "deploy" / "runpod-avatar" / "flashhead_engine_core.py").read_text(encoding="utf-8")
    results.append(check("伺服器 wake 有把聲音錶綁上畫格出口",
                         "sink.audio_pos_fn = slot.audio_out.played_pos_s" in server_src))
    results.append(check("真話畫格入隊帶錶（start_audio_pos）",
                         "start_audio_pos=chunk_audio_pos" in core_src))

    # ─── 新起句首塊加速（fast-first · 2026-08-17 第二刀）────────────────
    # 病：一輪第一塊要攢滿 0.96 秒才開工＝新起句嘴巴遲到 0.6-1.5 秒的主因。
    # 契約：新起句、真聲音 ≥0.18s、等了 ≥0.25s 還沒滿塊 → 墊零先開工；
    #       但只推「真聲音那幾格」——墊零尾格會佔住下一塊真嘴型的時間位置。
    cs = 15360  # 0.96s @16kHz
    results.append(check("新起句等 0.25s 有 0.25s 真聲音＝提早開工",
                         should_fast_first(True, 4000, cs, 0.30)))
    results.append(check("不是新起句（首塊已出）＝不出手",
                         not should_fast_first(False, 4000, cs, 0.30)))
    results.append(check("真聲音太少（<0.18s）＝再等等",
                         not should_fast_first(True, 2000, cs, 0.30)))
    results.append(check("還沒等滿 0.25s＝再等等",
                         not should_fast_first(True, 4000, cs, 0.20)))
    results.append(check("已攢滿一塊＝走正常路、不搶",
                         not should_fast_first(True, cs, cs, 0.30)))
    results.append(check("總開關關掉＝完全不出手",
                         not should_fast_first(True, 4000, cs, 0.30, enabled=False)))
    # 接線：這條路真的縫進迴圈與生成端了（行為測試綠≠正式機在跑）
    results.append(check("迴圈有 fast-first 分支且帶總開關",
                         "enabled=FAST_FIRST" in core_src))
    results.append(check("句子已收尾不搶（讓 tail-flush 清旗標）",
                         "not self._finish_pending\n                      and should_fast_first" in core_src))
    results.append(check("fast-first 也守畫格隊伍深度（不塞爆出口）",
                         core_src.count("can_generate_video_chunk(") >= 3))
    results.append(check("生成端只推真聲音那幾格（墊零不推）",
                         "trim_frames_to_valid=todo[4]" in core_src
                         and "frames = frames[:keep]" in core_src))
    results.append(check("出手次數進健康帳（長期 0＝這刀沒在工作）",
                         '"fast_first_count"' in core_src))

    failed = results.count(False)
    if failed:
        print(f"\n❌ {failed} 項未過")
        return 1
    print("\n聲嘴對錶：守門全過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
