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
        self._wall0 = None   # 開播牆鐘（配速基準）

    def speak_again(self, pcm48k):
        """插話考：她講話講到一半，假人再開口。牆鐘記在真正播出的那格。"""
        self.extra = np.asarray(pcm48k, dtype=np.int16)
        self.extra_pos = 0
        self.interrupt_wall = None   # 第一格播出時蓋章

    async def recv(self):
        from av import AudioFrame
        need = 960   # 20ms @48k
        chunk = self.pcm[self.pos:self.pos + need]
        if len(chunk) < need and getattr(self, "extra", None) is not None:
            if self.interrupt_wall is None:
                self.interrupt_wall = time.monotonic()
            chunk = self.extra[self.extra_pos:self.extra_pos + need]
            self.extra_pos += need
            if self.extra_pos >= len(self.extra):
                self.extra = None
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
        # 牆鐘校準配速（2026-07-30 深夜真兇）：每格固定睡 0.02 在 Windows 上實際睡 31ms
        # （鬧鐘最小刻度 15.6ms）→ 嘴巴只有 0.64 倍速、考場所有時間數字灌水 1.5 倍。
        # 改成對「開播牆鐘＋已播樣本數」校準：睡過頭，下一格自動少睡補回來。
        if self._wall0 is None:
            self._wall0 = time.monotonic()
        target = self._wall0 + self._pts / 48000.0
        wait = target - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        return frame


async def run_exam(wav_path, listen_s=40, interrupt=False):
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
    interrupt_result = None
    if interrupt:
        # 等她接話 → 讓她講 1.2 秒 → 假人插一句 2.5 秒的話 → 量她多快閉嘴
        # 期限以「假人真正講完那一刻」起算——播放牆鐘比音檔長度慢（每格 sleep 有零頭），
        # 用 t0+音檔長 當期限會差點錯過她的接話（第一次插話考就這樣考砸的）
        her_started = None
        while time.monotonic() < t0 + 120:
            await asyncio.sleep(0.05)
            e = mouth.speech_end_wall
            if e and time.monotonic() > e + 15:
                break   # 講完 15 秒她都沒接話，放棄
            if e and any(on and t > e for t, on in her_audio[-10:]):
                her_started = next(t for t, on in her_audio if on and t > e)
                break
        if her_started:
            await asyncio.sleep(1.2)
            clip = mouth.pcm[:int(48000 * 2.5)]
            mouth.speak_again(clip)
            await asyncio.sleep(6)
            iw = mouth.interrupt_wall
            if iw:
                # 插話開始後，她最後一次出聲（之後靜 ≥1 秒算真的閉嘴）
                voiced = [t for t, on in her_audio if on and t > iw]
                stop_ms = None
                for t in voiced:
                    if not any(iw < u <= t + 1.0 and u > t for u, on in her_audio if on):
                        stop_ms = round((t - iw) * 1000); break
                if stop_ms is None and voiced:
                    stop_ms = round((voiced[-1] - iw) * 1000)
                interrupt_result = {"stop_ms": stop_ms, "her_started": True}
            else:
                interrupt_result = {"stop_ms": None, "her_started": True}
        else:
            interrupt_result = {"stop_ms": None, "her_started": False}
    await asyncio.sleep(listen_s if not interrupt else 8)
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
    # （插話模式：打斷之後的空檔是我們造成的、不算她破句）
    iw_cut = getattr(mouth, "interrupt_wall", None) or 1e18
    gaps = []
    tail = [(a, b) for a, b in her_segs if end < a < iw_cut]
    for (a1, b1), (a2, b2) in zip(tail, tail[1:]):
        if a2 - b1 > 1.2:
            gaps.append(round((a2 - b1) * 1000))
    print(f"📋 假人考場成績（{os.path.basename(wav_path)}·假人講了 {mouth.total_speech_s:.1f} 秒）")
    print(f"  ① 接話延遲：{reply_ms} ms" if reply_ms else "  ① 接話延遲：她沒接話 ❌")
    print(f"  ② 搶話：{'❌ ' + str(len(barge)) + ' 次（開口前假人才靜音 ' + str(barge) + ' ms）' if barge else '✅ 沒有'}"
          + (f"（另有 {len(pause_reply)} 次停頓後合法接話）" if pause_reply else ""))
    print(f"  ③ 破句：{'❌ ' + str(gaps) + ' ms' if gaps else '✅ 沒有'}")
    if interrupt_result is not None:
        if not interrupt_result["her_started"]:
            print("  ④ 插話考：她一直沒接話、考不成 ⚠")
        elif interrupt_result["stop_ms"] is None:
            print("  ④ 插話考：插話後她完全沒再出聲（可能已講完）⚠ 換長答題重考")
        else:
            ok = interrupt_result["stop_ms"] < 1500
            print(f"  ④ 插話後她 {interrupt_result['stop_ms']} ms 閉嘴讓人 {'✅' if ok else '❌（>1.5s 太慢）'}")
    return {"reply_ms": reply_ms, "barge": len(barge), "pause_reply": len(pause_reply), "gaps": gaps}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    wav = args[0] if args else os.path.abspath(DEFAULT_WAV)
    asyncio.run(run_exam(wav, interrupt=("--interrupt" in sys.argv)))
