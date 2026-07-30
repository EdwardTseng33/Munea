# -*- coding: utf-8 -*-
"""假人考場 · 全自動假人（2026-07-30 · 7/30 災難教訓「沒蓋到真語音路的驗證不算驗證」的產物）

不用瀏覽器、不用麥克風：這支程式自己就是一個「會講話的假人」——
用電話級水管（WebRTC）撥進橋、照真實節奏播一段真人錄音當嘴巴、
一邊錄下她的聲音何時回來，自動算出三個體感數字：

  ① 接話延遲：假人講完最後一個字 → 她第一聲，幾毫秒（長輩體感的「她慢不慢」）
  ② 搶話偵測：假人還在講、她就出聲＝搶話（長輩最忌）
  ③ 講話中斷偵測：她講到一半超過 1.2 秒沒聲又續播＝破句（「卡」的量化）

用法：先起橋（bridge_server.py），再：
  python tools/webrtc-spike/fake_caller.py [wav 路徑]
之後接不同考題錄音（含中途停頓版、插話版）就是完整考場。
"""
import asyncio
import fractions
import json
import os
import sys
import time
import wave

import numpy as np
from aiohttp import ClientSession
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = os.environ.get("BRIDGE_URL", "http://localhost:8378")
DEFAULT_WAV = os.path.join(HERE, "..", "..", "web", "demo-assets", "voice-sample.wav")


class WavMouthTrack(AudioStreamTrack):
    """假人的嘴：照真實節奏（20ms 一格、48kHz）播 wav，播完換恆常安靜
    ——引擎要「聽到安靜」才會判定講完（7/30 深夜第二課）。"""

    def __init__(self, wav_path):
        super().__init__()
        with wave.open(wav_path, "rb") as w:
            rate, n = w.getframerate(), w.getnframes()
            pcm = np.frombuffer(w.readframes(n), dtype=np.int16)
            if w.getnchannels() == 2:
                pcm = pcm.reshape(-1, 2).mean(axis=1).astype(np.int16)
        # 重採樣到 48k（線性插值，假人用夠了）
        if rate != 48000:
            x = np.arange(len(pcm)) / rate
            xi = np.arange(0, x[-1], 1 / 48000)
            pcm = np.interp(xi, x, pcm).astype(np.int16)
        self.pcm = pcm
        self.pos = 0
        self._pts = 0
        self.speech_end_wall = None     # 假人「講完最後一個字」的牆鐘時間
        # 找到錄音實際的語音尾巴（去掉檔尾靜音）：從後往前找最後一段有能量的
        frames = pcm[: len(pcm) // 960 * 960].reshape(-1, 960)
        energy = np.abs(frames).mean(axis=1)
        loud = np.where(energy > 300)[0]
        self.speech_end_frame = int(loud[-1]) if loud.size else len(frames) - 1
        self.total_speech_s = (self.speech_end_frame * 960) / 48000
        self.timeline = []   # (牆鐘, 假人此格有沒有出聲)

    async def recv(self):
        from av import AudioFrame
        need = 960   # 20ms @48k
        chunk = self.pcm[self.pos:self.pos + need]
        if len(chunk) < need:
            chunk = np.concatenate([chunk, np.zeros(need - len(chunk), dtype=np.int16)])
        frame_idx = self.pos // need
        self.pos += need
        now = time.monotonic()
        if frame_idx == self.speech_end_frame and self.speech_end_wall is None:
            self.speech_end_wall = now
        # 牆鐘時間線：此刻假人有沒有在出聲（閱卷要用來分辨「搶話」vs「停頓後合法接話」）
        self.timeline.append((now, float(np.abs(chunk.astype(np.int32)).mean()) > 300))
        frame = AudioFrame(format="s16", layout="mono", samples=need)
        frame.planes[0].update(chunk.tobytes())
        frame.sample_rate = 48000
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, 48000)
        self._pts += need
        await asyncio.sleep(0.02)
        return frame


async def run_exam(wav_path, listen_s=40):
    mouth = WavMouthTrack(wav_path)
    pc = RTCPeerConnection()
    pc.addTrack(mouth)

    her_audio = []   # (牆鐘, 這 20ms 格有沒有聲音)

    @pc.on("track")
    def on_track(track):
        async def ear():
            while True:
                try:
                    frame = await track.recv()
                except Exception:
                    return
                arr = frame.to_ndarray().reshape(-1).astype(np.int32)
                her_audio.append((time.monotonic(), float(np.abs(arr).mean()) > 60))
        asyncio.ensure_future(ear())

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    async with ClientSession() as http:
        async with http.post(BRIDGE + "/offer", json={
                "sdp": pc.localDescription.sdp, "type": pc.localDescription.type}) as r:
            answer = await r.json()
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

    t0 = time.monotonic()
    await asyncio.sleep(mouth.total_speech_s + listen_s)
    await pc.close()

    # ── 閱卷（2026-07-30 二版·停頓感知）──
    # 第一輪教訓：錄音裡有 >0.8 秒的自然停頓，她在那種停頓後開口＝合法接話
    # （真人也會被接話），不能全算搶話。只有「假人真的還在講（靜音不足 SILENCE_S）
    # 她就出聲」才算搶話。
    SILENCE_S = float(os.environ.get("EXAM_SILENCE_S", "0.8"))   # 跟橋的收音節奏同步
    end = mouth.speech_end_wall
    if not end:
        print("⚠ 假人沒把話講完（音檔異常）"); return
    # 她的聲音整併成「段」（間隔 <0.3 秒視為同一段），別再用 20ms 碎格嚇人
    her_segs = []
    for t, on in her_audio:
        if not on:
            continue
        if her_segs and t - her_segs[-1][1] < 0.3:
            her_segs[-1][1] = t
        else:
            her_segs.append([t, t])
    # ① 接話延遲：講完後她第一次出聲
    after = [a for a, b in her_segs if a > end]
    reply_ms = round((after[0] - end) * 1000) if after else None
    # ② 搶話 vs 停頓接話：看她每段開口時，假人已靜音多久
    def fake_silent_for(t):
        talked = [w for w, on in mouth.timeline if on and w <= t]
        return (t - talked[-1]) if talked else 99.0
    def blamed_pause_s(t):
        """她開口時假人若在講，她多半是在反應「更早那個停頓」（聲音生成要 1-2 秒、
        傳回來時錄音已續播）。回溯 4 秒內最近一個 ≥0.35s 的假人靜音段，回它的長度；
        沒有就回 0＝真搶話。"""
        sil = fake_silent_for(t)
        if sil > 0.05:
            return sil
        runs, run_start = [], None
        for w, on in mouth.timeline:
            if w > t: break
            if not on and run_start is None: run_start = w
            if on and run_start is not None:
                runs.append((run_start, w - run_start)); run_start = None
        recent = [(st, d) for st, d in runs if d >= 0.35 and t - (st + d) <= 4.0]
        return recent[-1][1] if recent else 0.0
    barge, pause_reply = [], []
    for a, b in her_segs:
        if not ((t0 + 1.5) < a < end):
            continue
        sil = blamed_pause_s(a)
        (pause_reply if sil >= SILENCE_S else barge).append(round(sil * 1000))
    # ③ 破句：講完後她的回覆段之間 >1.2 秒的斷口
    gaps = []
    tail = [(a, b) for a, b in her_segs if a > end]
    for (a1, b1), (a2, b2) in zip(tail, tail[1:]):
        if a2 - b1 > 1.2:
            gaps.append(round((a2 - b1) * 1000))
    print(f"📋 假人考場成績（{os.path.basename(wav_path)}·假人講了 {mouth.total_speech_s:.1f} 秒）")
    print(f"  ① 接話延遲：{reply_ms} ms" if reply_ms else "  ① 接話延遲：她沒接話 ❌")
    print(f"  ② 搶話：{'❌ ' + str(len(barge)) + ' 次（開口前假人才靜音 ' + str(barge) + ' ms）' if barge else '✅ 沒有'}"
          + (f"（另有 {len(pause_reply)} 次停頓後合法接話）" if pause_reply else ""))
    print(f"  ③ 破句：{'❌ ' + str(gaps) + ' ms' if gaps else '✅ 沒有'}")
    return {"reply_ms": reply_ms, "barge": len(barge), "pause_reply": len(pause_reply), "gaps": gaps}


if __name__ == "__main__":
    wav = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(DEFAULT_WAV)
    asyncio.run(run_exam(wav))
