# -*- coding: utf-8 -*-
"""沐寧 · 寧寧雲端臉引擎（Modal 快照秒醒 · 正式通話服務 v1 · 2026-07-09）

7/9 早實測定案：快照喚醒 8–10 秒（6 輪零失敗）→ 主力開關機制。
本檔＝完整通話服務上雲：WebRTC 影像 ＋ /audio 聲音接口 ＋ /health 預醒探針。
沿用 RunPod 排雷全集（版本釘死、cuDNN8 獨立、numpy2 修正、進料節流、位元率調升）。

用法：
  modal deploy -m nening_modal          # 蓋映像＋上線（網址見輸出）
  modal run -m nening_modal::seed_models# 首次：模型進雲端櫃
  python probe_wake.py                  # 快照喚醒掐錶（診斷用）
App 端：localStorage['munea.avatarUrl'] 指到本服務網址（預設已內建）。
"""
import os

import modal

app = modal.App("munea-nening-avatar")

vol = modal.Volume.from_name("munea-ditto-models", create_if_missing=True)

# 薄門通行碼（正式上線 · 7/9 Edward 拍板）：App 自動帶、用戶無感；擋「拿網址直接來撥」的陌生流量。
# 部署時從本機 deploy/.munea-app-key 讀（gitignore）；檔不存在＝不啟用門（其他機器照常部署）。
_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".munea-app-key")
APP_KEY = ""
try:
    APP_KEY = open(_KEY_FILE, encoding="utf-8").read().strip()
except Exception:
    pass

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libgles2", "libegl1", "libopengl0", "libglib2.0-0")
    .pip_install("torch==2.4.0")
    .pip_install(
        "numpy==1.26.4", "librosa", "tqdm", "filetype", "imageio", "imageio-ffmpeg",
        "opencv-python-headless", "scikit-image", "cython", "colored", "polygraphy",
        "soundfile", "mediapipe", "einops", "aiohttp", "aiortc", "huggingface_hub",
    )
    .pip_install("onnxruntime-gpu==1.18.1")
    .pip_install("tensorrt==8.6.1.post1", "cuda-python==12.4.0")
    .run_commands(
        "pip install --target /opt/cudnn8-pkgs nvidia-cudnn-cu12==8.9.7.29",
        "git clone --depth 1 https://github.com/antgroup/ditto-talkinghead /root/ditto-talkinghead",
        "sed -i 's/np\\.atan2/np.arctan2/g' /root/ditto-talkinghead/core/aux_models/mediapipe_landmark478.py",
    )
    # ↓ 疊在頂層（不動上面的大層）：編譯工具＋預編 Cython 拼圖＋通話服務零件（7/9 排雷）
    .apt_install("build-essential", "clang")
    .run_commands(
        "cd /root/ditto-talkinghead && python -c \"import sys; sys.path.insert(0,'.'); "
        "import numpy, pyximport; pyximport.install(setup_args={'include_dirs': numpy.get_include()}); "
        "from core.utils.blend import blend; print('blend precompiled')\" || echo 'precompile skipped (runtime will compile)'",
    )
    .pip_install("fastapi")
    .env({"LD_LIBRARY_PATH": "/opt/cudnn8-pkgs/nvidia/cudnn/lib", "MUNEA_APP_KEY": APP_KEY})
    .add_local_file(r"E:\Claude\Munea\web\avatars\nening-real-female-full.jpg",
                    "/root/nening-real-female-full.jpg")
    # 六角色底圖（7/9 Edward「6 個角色都要會動」）——底圖跟 App 聊聊頁同一張
    .add_local_file(r"E:\Claude\Munea\web\avatars\ahong-tall.jpg", "/root/char-ahong.jpg")
    .add_local_file(r"E:\Claude\Munea\web\avatars\xiaoyun-2d-tall.jpg", "/root/char-xiaoyun.jpg")
    .add_local_file(r"E:\Claude\Munea\web\avatars\ayuan-2d-tall.jpg", "/root/char-ayuan.jpg")
    .add_local_file(r"E:\Claude\Munea\web\avatars\mimi-tall.jpg", "/root/char-mimi.jpg")
    .add_local_file(r"E:\Claude\Munea\web\avatars\wangcai-tall.jpg", "/root/char-wangcai.jpg")
)

# 角色 → 底圖（key 跟語音橋 ?char= 同一套中文名；App 聊聊頁同圖）
CHAR_SRC = {
    "寧寧": "/root/nening-real-female-full.jpg",
    "阿宏": "/root/char-ahong.jpg",
    "小昀": "/root/char-xiaoyun.jpg",
    "阿原": "/root/char-ayuan.jpg",
    "咪咪": "/root/char-mimi.jpg",
    "旺財": "/root/char-wangcai.jpg",
}


@app.function(image=image, volumes={"/models": vol}, timeout=3600)
def seed_models():
    """首次執行：模型權重下載進 Modal 置物櫃（之後所有容器共用、不重下）。"""
    from huggingface_hub import snapshot_download
    snapshot_download("digital-avatar/ditto-talkinghead", local_dir="/models/checkpoints",
                      allow_patterns=["ditto_cfg/*", "ditto_trt_Ampere_Plus/*"])
    vol.commit()
    return "models seeded"


SNAPSHOT_KEY = "v2-call"  # 改這個字串＝作廢舊快照重拍

SR_IN, SR_ENG = 24000, 16000
CHUNKSIZE = (3, 5, 2)
SPLIT = int(sum(CHUNKSIZE) * 0.04 * 16000) + 80   # 6480 樣本/窗
HOP = CHUNKSIZE[1] * 640                           # 3200 樣本 = 0.2s


@app.cls(
    image=image,
    gpu="l4",                        # 7/9 實測：L4 跑我們的引擎穩定 19–32ms/塊、預算 200ms 內
    volumes={"/models": vol},
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
    scaledown_window=120,            # 通話結束 2 分鐘沒人用→睡（快照喚醒 8–10 秒）
    timeout=3600,                    # 允許長通話
)
@modal.concurrent(max_inputs=20)     # 同一容器同時受理 offer + 聲音接口 + 探針（不排隊）
class Nening:

    # ---------- 睡前（拍進快照）：重活全做完 ----------
    @modal.enter(snap=True)
    def load(self):
        import os
        import sys
        import time
        import numpy as np

        t0 = time.time()
        sys.path.insert(0, "/root/ditto-talkinghead")
        os.chdir("/root/ditto-talkinghead")
        from stream_pipeline_online import StreamSDK

        self.sdk = StreamSDK("/models/checkpoints/ditto_cfg/v0.4_hubert_cfg_trt_online.pkl",
                             "/models/checkpoints/ditto_trt_Ampere_Plus")
        t1 = time.time()
        self.sdk.setup("/root/nening-real-female-full.jpg", "/root/_live_dummy.mp4")
        t2 = time.time()

        # 影格出口：照順序排隊的緩衝（引擎最後一棒、原本寫檔）
        import collections
        import threading

        cls = self

        class FrameSink:
            def __init__(self):
                self.q = collections.deque(maxlen=75)
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

        self.sink = FrameSink()
        self.sdk.writer = self.sink
        self.char = "寧寧"
        self.char_lock = threading.Lock()

        # 暖跑一塊 0.2s 靜音（觸發所有懶載入、快照拍「全熟」狀態）
        self.sdk.run_chunk(np.zeros(SPLIT, dtype=np.float32), CHUNKSIZE)
        t3 = time.time()
        self.load_report = {"sdk_init_s": round(t1 - t0, 1), "setup_s": round(t2 - t1, 1),
                            "warm_chunk_s": round(t3 - t2, 1), "total_load_s": round(t3 - t0, 1),
                            "snapshot_key": SNAPSHOT_KEY}
        print("[load]", self.load_report, flush=True)

    # ---------- 醒來後（每次快照喚醒都跑）：起進料執行緒＋通話零件 ----------
    @modal.enter(snap=False)
    def wake(self):
        import threading
        import time
        import numpy as np

        # 畫質：位元率預設太細、講話會糊（D1 排雷同款）
        import aiortc.codecs.h264 as _h264
        _h264.MIN_BITRATE = 3_000_000
        _h264.DEFAULT_BITRATE = 8_000_000
        _h264.MAX_BITRATE = 12_000_000

        import cv2

        def _load_poster(path):
            p = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
            s = 960.0 / p.shape[0]
            return cv2.resize(p, (int(p.shape[1] * s), 960))

        self._load_poster = _load_poster
        self.poster = _load_poster(CHAR_SRC[self.char])
        self.pcs = set()

        sdk, sink = self.sdk, self.sink

        class Feeder:
            """進料節流（D1 教訓）：聲音整坨進來、嘴要照真實時間演——
            每 0.2 秒吃一塊、跟「用戶正聽到的位置」對齊，臉才順順地講不快轉。"""
            def __init__(self):
                self.lock = threading.Lock()
                self.acc = np.zeros(CHUNKSIZE[0] * 640, dtype=np.float32)
                self.pos = 0
                self.t0 = None
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
                        self.t0 = now + 0.12 - max(0, self.pos - prefix) / SR_ENG   # 對嘴緩衝 0.25→0.12：嘴提早約 130ms、更貼聲音（Edward 2026-07-10）
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
                            due = self.t0 + max(0, self.pos - prefix) / SR_ENG
                            if time.time() >= due:
                                todo = self.acc[self.pos:self.pos + SPLIT].copy()
                                self.pos += HOP
                                if self.pos > 60 * SR_ENG:
                                    cut = self.pos - 5 * SR_ENG
                                    self.acc = self.acc[cut:]
                                    self.pos -= cut
                                    self.t0 += cut / SR_ENG
                    if todo is not None:
                        sdk.run_chunk(todo, CHUNKSIZE)
                    else:
                        time.sleep(0.01)

        self.feeder = Feeder()
        print("[wake] feeder 上工、通話零件就緒", flush=True)

    # ---------- 換角色（六角色 · 7/9）：換底圖重註冊、約 1–2 秒；失敗回舊角色 ----------
    def _switch(self, char):
        import numpy as np
        if not char or char == self.char:
            return True
        if char not in CHAR_SRC:
            return False
        with self.char_lock:
            if char == self.char:
                return True
            prev = self.char
            try:
                self.feeder.reset()
                self.sdk.setup(CHAR_SRC[char], "/root/_live_dummy.mp4")
                self.sdk.writer = self.sink          # setup 會換掉出口、要把影格緩衝接回來
                self.sdk.run_chunk(np.zeros(SPLIT, dtype=np.float32), CHUNKSIZE)  # 暖跑
                self.char = char
                self.poster = self._load_poster(CHAR_SRC[char])
                print(f"[char] {prev} → {char} ok", flush=True)
                return True
            except Exception as e:
                print(f"[char] {char} 不吃這顆引擎（{e}）→ 回 {prev}", flush=True)
                try:
                    self.sdk.setup(CHAR_SRC[prev], "/root/_live_dummy.mp4")
                    self.sdk.writer = self.sink
                    self.char = prev
                except Exception:
                    pass
                return False

    # ---------- 對外：通話服務（網頁接口） ----------
    @modal.asgi_app()
    def web(self):
        import time
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
        from av import VideoFrame
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware

        api = FastAPI()
        api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        outer = self

        import os as _os
        _gate = _os.environ.get("MUNEA_APP_KEY", "").strip()

        def _pass(request_key):
            return (not _gate) or (request_key == _gate)

        class NeningTrack(VideoStreamTrack):
            kind = "video"
            def __init__(self):
                super().__init__()
                self.last = outer.poster
                self._active_ts = 0.0
            async def recv(self):
                pts, tb = await self.next_timestamp()
                fr = outer.sink.pop()
                now = time.time()
                if fr is not None:
                    self.last = fr
                    self._active_ts = now
                elif self._active_ts and (now - self._active_ts) > 0.35:
                    # 講完 0.35 秒沒新畫面 → 回「閉嘴的待機靜態」，不要卡在最後一格開著嘴像當機（Edward 2026-07-10）
                    self.last = outer.poster
                    self._active_ts = 0.0
                vf = VideoFrame.from_ndarray(self.last, format="rgb24")
                vf.pts = pts
                vf.time_base = tb
                return vf

        @api.get("/health")
        def health(key: str = ""):
            if not _pass(key):
                return {"ok": False, "error": "key required"}
            return {"ok": True, "engine": "ditto-online-trt-modal", "frames": outer.sink.count,
                    "load": outer.load_report}

        @api.post("/offer")
        async def offer(payload: dict, key: str = "", char: str = ""):
            if not _pass(key):
                return {"error": "key required"}
            if char and not outer._switch(char):
                return {"error": "char not supported"}   # App 收到會自動退回 2D 動畫、照樣會動
            pc = RTCPeerConnection(RTCConfiguration(
                iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]))
            outer.pcs.add(pc)
            pc.addTrack(NeningTrack())
            await pc.setRemoteDescription(RTCSessionDescription(sdp=payload["sdp"], type=payload["type"]))
            ans = await pc.createAnswer()
            await pc.setLocalDescription(ans)
            # 等我方連線候選收集完（伺服器端 trickle 關閉、answer 帶滿候選）
            import asyncio
            for _ in range(60):
                if pc.iceGatheringState == "complete":
                    break
                await asyncio.sleep(0.05)
            return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

        @api.websocket("/audio")
        async def audio_ws(ws: WebSocket, key: str = ""):
            if not _pass(key):
                await ws.close(code=4403)
                return
            await ws.accept()
            print("[audio] connected", flush=True)
            try:
                while True:
                    msg = await ws.receive()
                    if msg.get("bytes") is not None:
                        outer.feeder.push24k(msg["bytes"])
                    elif msg.get("text") == "reset":
                        outer.feeder.reset()
                    elif msg.get("type") == "websocket.disconnect":
                        break
            except WebSocketDisconnect:
                pass
            print("[audio] closed", flush=True)

        return api

    # ---------- 診斷探針（掐錶／巡檢／六角色測試用） ----------
    @modal.method()
    def probe(self, char: str = ""):
        import time
        import numpy as np
        if char:
            t_sw = time.time()
            ok = self._switch(char)
            sw_s = round(time.time() - t_sw, 1)
            if not ok:
                return {"char": char, "supported": False, "switch_s": sw_s}
        t0 = time.time()
        before = self.sink.count
        for _ in range(5):
            self.sdk.run_chunk(np.zeros(SPLIT, dtype=np.float32), CHUNKSIZE)
        dt = time.time() - t0
        time.sleep(1.0)
        return {"char": self.char, "supported": True, "load_report": self.load_report,
                "chunk_ms": round(dt / 5 * 1000), "frames_delta": self.sink.count - before, "ready": True}
