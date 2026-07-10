# -*- coding: utf-8 -*-
"""臉聲同線終驗（Ditto dev）：同一條 WebRTC 收「影像軌+聲音軌」，同一時鐘記錄，
量「聲音軌能量起點 vs 嘴巴動起點」＝真實臉聲差。灌真語音 6s（大坨倒、模擬 Gemini）。"""
import os, time, json, wave, asyncio
import numpy as np, requests, websockets
from PIL import Image
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

BASE = "https://edwardt0303--munea-nening-avatar-dev-nening-web.modal.run"
KEY = open(r"E:\Claude\Munea\deploy\.munea-app-key", encoding="utf-8").read().strip()
WAV = r"E:\Claude\Munea\engine\nening-reply-1.wav"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sameline")
os.makedirs(OUT, exist_ok=True)
ICE = [RTCIceServer(urls="stun:stun.l.google.com:19302"),
       RTCIceServer(urls=["turn:34.81.102.52:3478?transport=udp", "turn:34.81.102.52:3478?transport=tcp"],
                    username="muneaturn", credential="munea-turn-a7k2q")]
T0 = None
vframes = []   # (t, ndarray)
aframes = []   # (t, np.int16 array)
stop = {"v": False}

async def recv_video(tr):
    while not stop["v"]:
        try:
            fr = await asyncio.wait_for(tr.recv(), timeout=5)
        except Exception:
            continue
        vframes.append((time.monotonic() - T0, fr.to_ndarray(format="rgb24")))

async def recv_audio(tr):
    while not stop["v"]:
        try:
            fr = await asyncio.wait_for(tr.recv(), timeout=5)
        except Exception:
            continue
        arr = fr.to_ndarray()   # (channels, samples) or (1,n)
        aframes.append((time.monotonic() - T0, arr.astype(np.int16).flatten(), fr.sample_rate))

async def main():
    global T0
    pc = RTCPeerConnection(RTCConfiguration(iceServers=ICE))
    pc.addTransceiver("video", direction="recvonly")
    pc.addTransceiver("audio", direction="recvonly")
    tasks = []
    @pc.on("track")
    def on_track(tr):
        print("[t] track:", tr.kind, flush=True)
        tasks.append(asyncio.ensure_future(recv_video(tr) if tr.kind == "video" else recv_audio(tr)))
    off = await pc.createOffer(); await pc.setLocalDescription(off)
    for _ in range(60):
        if pc.iceGatheringState == "complete": break
        await asyncio.sleep(0.05)
    r = requests.post(f"{BASE}/offer", params={"key": KEY, "char": "寧寧"},
                      json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}, timeout=30)
    ans = r.json()
    if "error" in ans: print("offer error", ans); return
    await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type=ans["type"]))
    for _ in range(100):
        if pc.connectionState == "connected": break
        await asyncio.sleep(0.1)
    print("[t] connected", flush=True)
    T0 = time.monotonic()
    aud = await websockets.connect(BASE.replace("https", "wss") + "/audio?key=" + KEY, max_size=None)
    await asyncio.sleep(2.0)   # 2 秒待機基準
    w = wave.open(WAV, "rb"); sr = w.getframerate()
    t_speak = time.monotonic() - T0
    print(f"[t] === 大坨倒真語音起點 t={t_speak:.2f}s ===", flush=True)
    sent = 0
    while sent < int(6.0 * sr):
        raw = w.readframes(int(0.2 * sr))
        if not raw: break
        await aud.send(raw); sent += int(0.2 * sr)
        await asyncio.sleep(0.01)
    w.close()
    await asyncio.sleep(9.0)   # 讓 6 秒的話演完
    stop["v"] = True
    await aud.close(); await pc.close()

    # ── 聲音軌能量時間軸（每收包時刻的 RMS）──
    a_on = None
    for t, arr, _sr in aframes:
        if t >= t_speak and np.sqrt(np.mean((arr / 32768.0) ** 2)) > 0.02:
            a_on = t; break
    # ── 嘴巴動起點（y33-50% 區塊）──
    m_on = None
    prev = None
    for t, a in vframes:
        h, wd = a.shape[:2]
        m = a[int(h*0.33):int(h*0.50), int(wd*0.30):int(wd*0.70)].astype(np.int16)
        if prev is not None and prev.shape == m.shape and t >= t_speak:
            if float(np.mean(np.abs(m - prev))) > 2.0 and m_on is None:
                m_on = t
        prev = m
    print(f"[RESULT] 聲音軌開始出聲 t={a_on and round(a_on,2)}s · 嘴巴開始動 t={m_on and round(m_on,2)}s "
          f"· 臉聲差={round(m_on - a_on, 2) if (a_on and m_on) else '量不到'}s", flush=True)
    print(f"[t] 收到影像格 {len(vframes)}、聲音包 {len(aframes)}", flush=True)
    # 存證：聲音軌存 wav、講話中段影格存 3 張
    if aframes:
        srr = aframes[0][2]
        pcm = np.concatenate([a for _, a, _ in aframes])
        ww = wave.open(os.path.join(OUT, "received.wav"), "wb")
        ww.setnchannels(1); ww.setsampwidth(2); ww.setframerate(srr)
        ww.writeframes(pcm.tobytes()); ww.close()
    saved = 0
    for t, a in vframes:
        if m_on and m_on + 0.5 <= t <= m_on + 2.0 and saved < 3:
            Image.fromarray(a).save(os.path.join(OUT, f"speak_{t:05.2f}s.png")); saved += 1
    print("[t] 存證於", OUT, flush=True)

asyncio.run(main())
