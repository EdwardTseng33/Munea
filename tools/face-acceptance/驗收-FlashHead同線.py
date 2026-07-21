# -*- coding: utf-8 -*-
"""FlashHead 臉聲同線終驗：驗解析度、影音雙軌、嘴聲差與句尾完整度。"""
import argparse, os, time, wave, asyncio
from urllib.parse import quote
import numpy as np, requests, websockets
from PIL import Image
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

PARSER = argparse.ArgumentParser()
PARSER.add_argument("base", nargs="?", default="https://edwardt0303--munea-flashhead-avatar-dev-flashhead-web.modal.run")
PARSER.add_argument("char", nargs="?", default="a05")
PARSER.add_argument("duration", nargs="?", type=float, default=6.0)
PARSER.add_argument("--expect-size", type=int, choices=(512, 640, 768))
PARSER.add_argument("--key-file", default=r"E:\Claude\Munea\deploy\.munea-app-key")
PARSER.add_argument("--demo-password")
PARSER.add_argument("--wav", default=r"E:\Claude\Munea\engine\nening-reply-1.wav")
PARSER.add_argument("--out")
ARGS = PARSER.parse_args()

BASE = ARGS.base.rstrip("/")
CHAR = ARGS.char
DURATION_S = ARGS.duration
if ARGS.demo_password:
    _session_response = requests.post(
        BASE + "/demo/session", json={"password": ARGS.demo_password}, timeout=30
    )
    _session_response.raise_for_status()
    KEY = str(_session_response.json().get("token") or "")
    if not KEY:
        raise RuntimeError("demo session did not return a token")
    AUTH_PARAM = "token"
else:
    KEY = open(ARGS.key_file, encoding="utf-8").read().strip()
    AUTH_PARAM = "key"
WAV = ARGS.wav
OUT = ARGS.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "sameline_fh")
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
        if T0 is None:   # 2026-07-11：T0 還沒定錨（connected 前）先跳過，防 None 相減把收格任務炸死
            continue
        vframes.append((time.monotonic() - T0, fr.to_ndarray(format="rgb24")))

async def recv_audio(tr):
    while not stop["v"]:
        try:
            fr = await asyncio.wait_for(tr.recv(), timeout=5)
        except Exception:
            continue
        if T0 is None:   # 同上護欄
            continue
        arr = fr.to_ndarray()
        channels = len(fr.layout.channels)
        if channels > 1:
            # PyAV may return planar (channels, samples) or packed
            # (1, samples * channels). Downmix instead of flattening packed
            # stereo into a fake double-length mono stream.
            if arr.ndim == 2 and arr.shape[0] == channels:
                mono = arr.astype(np.float32).mean(axis=0)
            else:
                mono = arr.reshape(-1, channels).astype(np.float32).mean(axis=1)
            arr = np.clip(mono, -32768, 32767).astype(np.int16)
        else:
            arr = arr.astype(np.int16).reshape(-1)
        aframes.append((time.monotonic() - T0, arr, fr.sample_rate))

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
    r = requests.post(f"{BASE}/offer", params={AUTH_PARAM: KEY, "char": CHAR},
                      json={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}, timeout=30)
    ans = r.json()
    if "error" in ans: print("offer error", ans); return
    session = ans.get("session", "")
    if not session:
        raise RuntimeError("avatar offer missing session id")
    await pc.setRemoteDescription(RTCSessionDescription(sdp=ans["sdp"], type=ans["type"]))
    for _ in range(100):
        if pc.connectionState == "connected": break
        await asyncio.sleep(0.1)
    print("[t] connected", flush=True)
    T0 = time.monotonic()
    _ws_base = BASE.replace("https://", "wss://").replace("http://", "ws://")   # https→wss、http(SSH通道)→ws
    aud = await websockets.connect(
        _ws_base + "/audio?" + AUTH_PARAM + "=" + quote(KEY) + "&session=" + quote(session),
        max_size=None,
    )
    await asyncio.sleep(2.0)   # 2 秒待機基準
    w = wave.open(WAV, "rb"); sr = w.getframerate()
    t_speak = time.monotonic() - T0
    print(f"[t] === 大坨倒真語音起點 t={t_speak:.2f}s ===", flush=True)
    sent = 0
    while sent < int(DURATION_S * sr):
        raw = w.readframes(int(0.2 * sr))
        if not raw: break
        await aud.send(raw); sent += int(0.2 * sr)
        await asyncio.sleep(0.01)
    w.close()
    await aud.send("finish")   # 明確要求服務補算最後不足一個模型 chunk 的句尾
    await asyncio.sleep(max(4.0, DURATION_S + 3.0))   # 讓整句與最後補算塊演完
    stop["v"] = True
    await aud.close(); await pc.close()

    if not vframes:
        raise RuntimeError("沒有收到任何WebRTC影像格")
    received_sizes = sorted({(a.shape[1], a.shape[0]) for _, a in vframes})
    print("[VIDEO] 收到解析度", received_sizes, flush=True)
    if len(received_sizes) != 1:
        raise RuntimeError("同一通話內影像解析度跳動: " + repr(received_sizes))
    if ARGS.expect_size and received_sizes[0] != (ARGS.expect_size, ARGS.expect_size):
        raise RuntimeError("預期 " + str(ARGS.expect_size) + "x" + str(ARGS.expect_size)
                           + "，實收 " + str(received_sizes[0][0]) + "x"
                           + str(received_sizes[0][1]))

    # ── 聲音軌能量時間軸（每收包時刻的 RMS）──
    a_on = None
    for t, arr, _sr in aframes:
        if t >= t_speak and np.sqrt(np.mean((arr / 32768.0) ** 2)) > 0.02:
            a_on = t; break
    # ── 嘴巴動起點（y33-50% 區塊）──
    m_on = None
    mouth_motion = []
    prev = None
    for t, a in vframes:
        h, wd = a.shape[:2]
        m = a[int(h*0.33):int(h*0.50), int(wd*0.30):int(wd*0.70)].astype(np.int16)
        if prev is not None and prev.shape == m.shape and t >= t_speak:
            score = float(np.mean(np.abs(m - prev)))
            mouth_motion.append((t, score))
            if score > 2.0 and m_on is None:
                m_on = t
        prev = m

    # A single poster/idle transition can move enough pixels to trip the old
    # first-frame detector even though the mouth is visibly still. Require
    # sustained motion in at least 5 of the next 8 frames before calling it
    # speech motion; retain the raw first transition for diagnostics.
    m_on_sustained = None
    for i, (t, _) in enumerate(mouth_motion):
        window = [score for wt, score in mouth_motion[i:i + 8] if wt - t <= 0.45]
        if len(window) >= 5 and sum(score > 2.0 for score in window) >= 5:
            m_on_sustained = t
            break
    measured_mouth_on = m_on_sustained or m_on
    print(f"[RESULT] 聲音軌開始出聲 t={a_on and round(a_on,2)}s"
          f" · 嘴巴持續動 t={m_on_sustained and round(m_on_sustained,2)}s"
          f" · 首次畫面變化 t={m_on and round(m_on,2)}s"
          f" · 臉聲差={round(measured_mouth_on - a_on, 2) if (a_on and measured_mouth_on) else '量不到'}s",
          flush=True)
    print(f"[t] 收到影像格 {len(vframes)}、聲音包 {len(aframes)}"
          f"、解析度 {received_sizes[0][0]}x{received_sizes[0][1]}", flush=True)
    # 存證：聲音軌存 wav、講話中段影格存 3 張
    if aframes:
        srr = aframes[0][2]
        pcm = np.concatenate([a for _, a, _ in aframes])
        ww = wave.open(os.path.join(OUT, "received.wav"), "wb")
        ww.setnchannels(1); ww.setsampwidth(2); ww.setframerate(srr)
        ww.writeframes(pcm.tobytes()); ww.close()
    saved = 0
    evidence_anchor = a_on or measured_mouth_on
    for t, a in vframes:
        if evidence_anchor and evidence_anchor - 0.3 <= t <= evidence_anchor + 1.2 and saved < 6:
            Image.fromarray(a).save(os.path.join(OUT, f"speak_{t:05.2f}s.png")); saved += 1
    print("[t] 存證於", OUT, flush=True)

asyncio.run(main())
