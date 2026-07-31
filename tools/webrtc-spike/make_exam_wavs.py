# -*- coding: utf-8 -*-
"""假人考場 · 考題產生器（2026-07-30）

拿一段真人錄音、在句子中間插「喘口氣」停頓，產出搶話考題：
每個停頓的**有效靜音**（天然＋補插）剛好 0.6 秒——低於正式線 0.8 秒收音窗，
及格標準＝她一次都不准跳進來。

第一版教訓：0.6 秒直接插在「最安靜的點」會跟前後天然靜音連成 1.2-1.5 秒、
超過門檻＝她接話變合法、考題自己不及格。二版先量天然靜音、只補差額。

用法：python tools/webrtc-spike/make_exam_wavs.py [來源wav] [輸出wav]
"""
import os
import sys
import wave

import numpy as np

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "web", "demo-assets", "voice-sample.wav"))
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "exam-pause.wav")
    with wave.open(src, "rb") as w:
        rate, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        pcm = np.frombuffer(w.readframes(n), dtype=np.int16)
        if ch == 2:
            pcm = pcm.reshape(-1, 2).mean(axis=1).astype(np.int16)
    win = rate // 50   # 20ms
    frames = pcm[: len(pcm) // win * win].reshape(-1, win)
    on = np.abs(frames).mean(axis=1) > 300
    runs, start = [], None
    for i, v in enumerate(on):
        if not v and start is None:
            start = i
        if v and start is not None:
            runs.append((start, i - start)); start = None
    mid = [(s, d) for s, d in runs if 0.2 * len(frames) < s < 0.8 * len(frames)]
    picks, chosen = [], []
    for s, d in sorted(mid, key=lambda x: -x[1]):
        t = s * 0.02
        if d * 0.02 < 0.5 and all(abs(t - c) > 3.0 for c in chosen):
            picks.append((s, d)); chosen.append(t)
        if len(picks) == 3:
            break
    picks.sort()
    parts, last = [], 0
    for s, d in picks:
        cut = (s + d // 2) * win
        pad = np.zeros(int(rate * 0.6) - d * win, dtype=np.int16)
        parts += [pcm[last:cut], pad]; last = cut
    parts.append(pcm[last:])
    out = np.concatenate(parts)
    with wave.open(dst, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(out.tobytes())
    print(f"考題已生：{dst}·插點(原始秒)={[round(s*0.02,1) for s,_ in picks]}·總長 {len(out)/rate:.1f}s")

if __name__ == "__main__":
    main()
