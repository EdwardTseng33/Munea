# -*- coding: utf-8 -*-
"""沐寧 · 雲端寧寧通話服務 v0（D2b · 正式版雛形）

Ditto 串流引擎（TRT online）→ 把引擎最後一棒「寫入器」換成影格緩衝 → WebRTC 即時送進瀏覽器。
聲音從 /audio WebSocket 進來（瀏覽器把寧寧的聲音複製一份轉發），插話送 "reset"。

跑法（在 4090 pod 上）：
  export LD_LIBRARY_PATH=/opt/cudnn8-pkgs/nvidia/cudnn/lib:$LD_LIBRARY_PATH
  python -u avatar_cloud_server.py
門：8188（/offer /audio /health · CORS 全開、經 RunPod 代理）
"""
import os
import sys
import time
import json
import asyncio
import threading
import collections

import numpy as np
from aiohttp import web, WSMsgType
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

# 畫質：位元率預設太細、講話會糊（D1 本機同款修正）
import aiortc.codecs.h264 as _h264
_h264.MIN_BITRATE = 3_000_000
_h264.DEFAULT_BITRATE = 8_000_000
_h264.MAX_BITRATE = 12_000_000

ROOT = "/workspace/ditto-talkinghead"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from stream_pipeline_online import StreamSDK  # noqa: E402

CFG = "./checkpoints/ditto_cfg/v0.4_hubert_cfg_trt_online.pkl"
DATA = "./checkpoints/ditto_trt_Ampere_Plus"
SRC = os.environ.get("MUNEA_AVATAR_SRC", "/root/nening-real-female-full.jpg")
PORT = 8188
SR_IN, SR_ENG = 24000, 16000
CHUNKSIZE = (3, 5, 2)
SPLIT = int(sum(CHUNKSIZE) * 0.04 * 16000) + 80   # 6480 樣本/窗
HOP = CHUNKSIZE[1] * 640                           # 3200 樣本 = 0.2s

print("[init] loading ditto stream sdk ...", flush=True)
sdk = StreamSDK(CFG, DATA)
sdk.setup(SRC, "/root/_live_dummy.mp4")

class FrameSink:
    """引擎最後一棒：原本寫檔、改成「照順序排隊」的影格緩衝（配合進料節流＝順順地演）。"""
    def __init__(self):
        self.q = collections.deque(maxlen=75)   # 約 3 秒緩衝
        self.count = 0
        self.lock = threading.Lock()
    def __call__(self, frame, fmt="rgb"):
        with self.lock:
            self.q.append(frame)
            self.count += 1
    def pop(self):
        with self.lock:
            return self.q.popleft() if self.q else None
    def clear(self):
        with self.lock:
            self.q.clear()
    def close(self):
        pass

sink = FrameSink()
sdk.writer = sink
print("[init] writer 已接管 → 影格直送通話", flush=True)

# ---------- 聲音進料（持續串流、跨句不重啟引擎） ----------
class Feeder:
    """進料節流（D1 同款教訓）：Google 的聲音整坨倒進來，但嘴要照「真實時間」演——
    每 0.2 秒最多吃一塊，跟用戶「正在聽到的位置」對齊，臉才會順順地講而不是快轉定格。"""
    def __init__(self):
        self.lock = threading.Lock()
        self.acc = np.zeros(CHUNKSIZE[0] * 640, dtype=np.float32)  # 開頭墊靜音（官方餵法）
        self.pos = 0
        self.t0 = None          # 這一句開始「被聽到」的牆上時間
        self.last_in = 0.0
        threading.Thread(target=self._loop, daemon=True).start()
    def push24k(self, pcm_bytes):
        x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        n_out = int(len(x) * SR_ENG / SR_IN)
        if n_out <= 0:
            return
        xq = np.interp(np.linspace(0, 1, n_out, endpoint=False),
                       np.linspace(0, 1, len(x), endpoint=False), x).astype(np.float32)
        with self.lock:
            now = time.time()
            prefix = CHUNKSIZE[0] * 640
            if self.t0 is None or (now - self.last_in) > 0.8:
                # 新的一句：重新對錶（讓「目前吃到的位置」對齊「現在+播放緩衝」）
                self.t0 = now + 0.25 - max(0, self.pos - prefix) / SR_ENG
            self.acc = np.concatenate([self.acc, xq])
            self.last_in = now
    def reset(self):
        with self.lock:
            self.acc = np.zeros(CHUNKSIZE[0] * 640, dtype=np.float32)
            self.pos = 0
            self.t0 = None
        sink.clear()
        print("[feeder] reset(插話)", flush=True)
    def _loop(self):
        prefix = CHUNKSIZE[0] * 640
        while True:
            todo = None
            with self.lock:
                ready = len(self.acc) >= self.pos + SPLIT
                if ready and self.t0 is not None:
                    # 節流：這一塊對應的「聽到時間」還沒到就等
                    due = self.t0 + max(0, self.pos - prefix) / SR_ENG
                    if time.time() >= due:
                        todo = self.acc[self.pos:self.pos + SPLIT].copy()
                        self.pos += HOP
                        if self.pos > 60 * SR_ENG:      # 記憶體帽：保留最近一段
                            cut = self.pos - 5 * SR_ENG
                            self.acc = self.acc[cut:]
                            self.pos -= cut
                            self.t0 += cut / SR_ENG
            if todo is not None:
                t0 = time.time()
                sdk.run_chunk(todo, CHUNKSIZE)
                dt = (time.time() - t0) * 1000
                if sink.count % 100 == 0:
                    print(f"[feeder] chunk {dt:.0f}ms frames={sink.count} qlen={len(sink.q)}", flush=True)
            else:
                time.sleep(0.01)

feeder = Feeder()

# ---------- WebRTC 影像軌 ----------
import cv2
_poster = cv2.cvtColor(cv2.imread(SRC), cv2.COLOR_BGR2RGB)
_scale = 960.0 / _poster.shape[0]
_poster = cv2.resize(_poster, (int(_poster.shape[1] * _scale), 960))

class NeningTrack(VideoStreamTrack):
    kind = "video"
    def __init__(self):
        super().__init__()
        self.last = _poster
        self.sent = 0
    async def recv(self):
        pts, tb = await self.next_timestamp()
        fr = sink.pop()          # 照順序一格一格演；沒新格就停在上一格
        if fr is not None:
            self.last = fr
        self.sent += 1
        if self.sent % 250 == 0:
            print(f"[track] sent={self.sent} engine_frames={sink.count}", flush=True)
        vf = VideoFrame.from_ndarray(self.last, format="rgb24")
        vf.pts = pts
        vf.time_base = tb
        return vf

# ---------- HTTP / WS ----------
pcs = set()

def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

async def offer(request):
    if request.method == "OPTIONS":
        return _cors(web.Response())
    p = await request.json()
    pc = RTCPeerConnection()
    pcs.add(pc)
    pc.addTrack(NeningTrack())
    await pc.setRemoteDescription(RTCSessionDescription(sdp=p["sdp"], type=p["type"]))
    ans = await pc.createAnswer()
    await pc.setLocalDescription(ans)
    return _cors(web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}))

async def audio_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print("[audio] connected", flush=True)
    async for msg in ws:
        if msg.type == WSMsgType.BINARY:
            feeder.push24k(msg.data)
        elif msg.type == WSMsgType.TEXT and msg.data == "reset":
            feeder.reset()
    print("[audio] closed", flush=True)
    return ws

async def health(request):
    return _cors(web.json_response({"ok": True, "engine": "ditto-online-trt", "frames": sink.count}))

async def on_shutdown(app):
    await asyncio.gather(*[pc.close() for pc in pcs])

app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_route("*", "/offer", offer)
app.router.add_get("/audio", audio_ws)
app.router.add_get("/health", health)
if __name__ == "__main__":
    print(f"[server] 寧寧雲端通話服務 on :{PORT}", flush=True)
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)
