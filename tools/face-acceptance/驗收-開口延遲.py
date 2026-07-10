# -*- coding: utf-8 -*-
"""量「開場延遲」：先待機 N 秒堆積壓，再送真語音，抓「嘴巴區塊」第一次明顯動的時間點。
delay = 嘴動 onset − 送真語音起點。只測分身臉。char 可切。"""
import os, sys, time, json, wave, asyncio
import numpy as np, requests, websockets
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

CHAR = sys.argv[1] if len(sys.argv) > 1 else "寧寧"
IDLE_PRE = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0   # 送真語音前先待機幾秒（堆積壓）
BASE = "https://edwardt0303--munea-nening-avatar-dev-nening-web.modal.run"
KEY = open(r"E:\Claude\Munea\deploy\.munea-app-key", encoding="utf-8").read().strip()
WAV = r"E:\Claude\Munea\engine\nening-reply-1.wav"
ICE = [RTCIceServer(urls="stun:stun.l.google.com:19302"),
       RTCIceServer(urls=["turn:34.81.102.52:3478?transport=udp", "turn:34.81.102.52:3478?transport=tcp"],
                    username="muneaturn", credential="munea-turn-a7k2q")]
frames = []   # (t_rel, ndarray)
stop = {"v": False}
T0 = None

async def recv_track(track):
    while not stop["v"]:
        try:
            fr = await asyncio.wait_for(track.recv(), timeout=5)
        except asyncio.TimeoutError:
            continue
        frames.append((time.monotonic() - T0, fr.to_ndarray(format="rgb24")))

async def main():
    global T0
    pc = RTCPeerConnection(RTCConfiguration(iceServers=ICE))
    pc.addTransceiver("video", direction="recvonly")
    @pc.on("track")
    def on_track(track):
        asyncio.ensure_future(recv_track(track))
    offer = await pc.createOffer(); await pc.setLocalDescription(offer)
    for _ in range(60):
        if pc.iceGatheringState == "complete": break
        await asyncio.sleep(0.05)
    r = requests.post(f"{BASE}/offer", params={"key": KEY, "char": CHAR},
                      json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}, timeout=30)
    ans = r.json()
    if "error" in ans:
        print("offer error", ans); return
    await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type=ans["type"]))
    for _ in range(100):
        if pc.connectionState == "connected": break
        await asyncio.sleep(0.1)
    T0 = time.monotonic()
    # 開一條 audio ws，但先不送 → 讓臉待機 IDLE_PRE 秒（堆積壓）
    aud = await websockets.connect(BASE.replace("https", "wss") + "/audio?key=" + KEY, max_size=None)
    print(f"[t] connected，待機 {IDLE_PRE}s 堆積壓中...", flush=True)
    await asyncio.sleep(IDLE_PRE)
    # 送真語音
    w = wave.open(WAV, "rb"); sr = w.getframerate(); assert sr == 24000
    chunk = int(0.2 * sr)
    t_speak = time.monotonic() - T0
    print(f"[t] === 送真語音起點 t={t_speak:.2f}s ===", flush=True)
    sent = 0
    while sent < int(6.0 * sr):
        raw = w.readframes(chunk)
        if not raw: break
        await aud.send(raw); sent += chunk
        await asyncio.sleep(0.2)
    w.close()
    await asyncio.sleep(1.0)
    stop["v"] = True
    await aud.close(); await pc.close()

    # 嘴巴區塊(中下段)逐格差異
    def mouth_diff(a, b):
        h, w2 = a.shape[:2]
        ra = a[int(h*0.55):int(h*0.85), int(w2*0.30):int(w2*0.70)].astype(np.int16)
        rb = b[int(h*0.55):int(h*0.85), int(w2*0.30):int(w2*0.70)].astype(np.int16)
        return float(np.mean(np.abs(ra - rb)))
    fs = sorted(frames, key=lambda x: x[0])
    # 待機期基準（送語音前 1 秒）算雜訊底
    base = [mouth_diff(fs[i-1][1], fs[i][1]) for i in range(1, len(fs)) if fs[i][0] < t_speak and fs[i][0] > t_speak-2]
    noise = (np.mean(base) + 3*np.std(base)) if base else 2.0
    thr = max(noise, 1.5)   # 超過待機雜訊 3 個標準差＝真的在動
    print(f"[t] 待機期嘴巴雜訊底 mean={np.mean(base) if base else 0:.2f} → 動作門檻 thr={thr:.2f}", flush=True)
    after = [(t - t_speak, mouth_diff(fs[i-1][1], fs[i][1])) for i, (t, a) in enumerate(fs) if i > 0 and t >= t_speak]
    # 送語音後前 3.5 秒的嘴巴變化時間軸
    print("[時間軸] 送語音後(秒):嘴巴變化量  ↓第一次穩定超過門檻＝嘴開始動", flush=True)
    line = "  ".join(f"{off:.1f}:{d:.1f}" for off, d in after if off <= 3.5)
    print("  " + line, flush=True)
    onset = next((off for off, d in after if d > thr), None)
    if onset is not None:
        print(f"[RESULT] char={CHAR} 待機{IDLE_PRE}s後 → 嘴第一次動延遲 = {onset:.2f}s（門檻 thr={thr:.2f}）", flush=True)
    else:
        print(f"[RESULT] char={CHAR} 送語音後嘴巴幾乎沒動（最大變化 {max([d for _,d in after]) if after else 0:.2f} < 門檻）", flush=True)
    print(f"[t] 總影格 {len(fs)}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
