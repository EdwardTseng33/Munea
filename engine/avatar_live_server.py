# -*- coding: utf-8 -*-
"""沐寧 · 擬真 live avatar 服務（產品第 3 層 · 規劃路線 demo 版）

架構＝6/3 已驗證的 voice-poc-stream PoC（GPU 即時對嘴 → WebRTC → 瀏覽器），兩處按產品需求換裝：
  1. 臉：Voice Path 測試臉 → 寧寧（web/avatars/nening-real-female-full.jpg 靜態照）
  2. 聲音：錄好的 wav 循環 → 「聊聊」即時語音（瀏覽器把寧寧的聲音原樣轉發進來、邊講邊生成）

跑法：E:/voice-poc/.venv/Scripts/python.exe engine/avatar_live_server.py
  - 需要 voice-poc 環境（torch cu121 + aiortc + Wav2Lip repo/models，路徑見下方常數）
  - :8188/offer  = 影像連線握手（WebRTC）
  - :8188/audio  = 聲音入口（WebSocket：binary=寧寧語音 PCM16@24kHz、文字 "reset"=用戶插話清空）

節奏設計：
  - 影像每幀推進 80/FPS 格聲譜（跟真實時間走），聲音先到就排隊、不會讓嘴巴超前聲音
  - 沒聲音（接通前/講完/被插話）→ 回傳原照片＝自然待機，零 GPU
"""
import os, sys, time, json, asyncio
import numpy as np, cv2, torch
from aiohttp import web, WSMsgType

WAV2LIP = r"E:/voice-poc/repo/Wav2Lip"
sys.path.insert(0, WAV2LIP); os.chdir(WAV2LIP)
import audio as w2l_audio
from models import Wav2Lip
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

# 畫質修正①：影像傳輸的位元率預設 1Mbps 太細——嘴一動整張被壓糊/馬賽克。
# 區網 demo 頻寬夠，直接拉高（下限也墊高、防自動降到糊掉）。
import aiortc.codecs.h264 as _h264
_h264.MIN_BITRATE = 3_000_000
_h264.DEFAULT_BITRATE = 8_000_000
_h264.MAX_BITRATE = 12_000_000

FACE_IMG = r"E:/Claude/Munea/web/avatars/nening-real-female-full.jpg"
CKPT     = r"E:/voice-poc/models/wav2lip_gan.pth"
PORT     = 8188
device = "cuda"; img_size = 96; mel_step = 16; MICROBATCH = 2
FPS = 30.0                     # 跟影像實際節奏一致（aiortc 30fps）；每幀吃 80/FPS 格聲譜
MEL_PER_FRAME = 80.0 / FPS
START_DELAY_FRAMES = 6         # 聲音剛到先等 ~0.24s 再開嘴（配合瀏覽器播放緩衝、嘴不超前聲音）
SR_IN, SR_MEL = 24000, 16000   # 進來 24k（Gemini 原生）→ 內部 16k（Wav2Lip 訓練規格）

# ---------- 載寧寧 + 模型（一次） ----------
print("[init] loading nening + wav2lip ...", flush=True)
_img = cv2.imread(FACE_IMG)
_scale = 960.0 / _img.shape[0]
FRAME = cv2.resize(_img, (int(_img.shape[1] * _scale), 960))
import face_detection
_det = face_detection.FaceAlignment(face_detection.LandmarksType._2D, flip_input=False, device=device)
_rect = _det.get_detections_for_batch(np.array([FRAME]))[0]
del _det; torch.cuda.empty_cache()
Y1 = max(0, _rect[1]); Y2 = min(FRAME.shape[0], _rect[3] + 10)
X1 = max(0, _rect[0]); X2 = min(FRAME.shape[1], _rect[2])
FACE96 = cv2.resize(FRAME[Y1:Y2, X1:X2], (img_size, img_size))
# 畫質修正②：生成結果「只貼下半臉＋邊緣羽化」——眼睛/額頭永遠是原圖、接縫看不見
PATCH_W, PATCH_H = X2 - X1, Y2 - Y1
_m = np.zeros((PATCH_H, PATCH_W), np.float32)
_e = max(6, PATCH_W // 12)
cv2.rectangle(_m, (_e, int(PATCH_H * 0.52)), (PATCH_W - _e, PATCH_H - 3), 1.0, -1)
_m = cv2.GaussianBlur(_m, (0, 0), _e / 2.0)
BLEND_MASK = _m[..., None]                     # (H,W,1) 0=原圖 1=生成
ORIG_PATCH = FRAME[Y1:Y2, X1:X2].astype(np.float32)
model = Wav2Lip(); _ck = torch.load(CKPT, map_location=device)
model.load_state_dict({k.replace("module.", ""): v for k, v in _ck["state_dict"].items()})
model = model.to(device).eval()
# 暖機
_fb = np.asarray([FACE96] * MICROBATCH, dtype=np.float32) / 255.0
_mk = _fb.copy(); _mk[:, img_size // 2:] = 0
_fb = np.concatenate((_mk, _fb), axis=3)
_it = torch.from_numpy(np.transpose(_fb, (0, 3, 1, 2))).float().to(device)
_mt = torch.zeros((MICROBATCH, 1, 80, mel_step)).float().to(device)
for _ in range(3):
    with torch.no_grad():
        _ = model(_mt, _it)
torch.cuda.synchronize()
print(f"[init] ready. frame={FRAME.shape[1]}x{FRAME.shape[0]} face=({X1},{Y1})-({X2},{Y2})", flush=True)

# ---------- 聲音 → 聲譜（滑動累積、跨段連續） ----------
HOP, NFFT = 200, 800
CTX = NFFT - HOP        # 左側銜接樣本（避免每段接縫）
LEAD = 0.30             # 瀏覽器播放緩衝＋影像編碼延遲的對時提前量（秒）
GAP_NEW_UTTER = 0.8     # 靜默超過這秒數又來新聲音＝新的一句、重新對時

import collections

class MelStream:
    """聲音進、聲譜出。設計重點（正式版同款）：
    - feed() 在主迴圈只丟進佇列（零成本、不噎住影像）；聲譜在工作執行緒才算
    - 嘴型用「牆上時鐘」對時：現在該講到哪、就生哪一段的嘴——卡頓自動復原、不快轉
    """
    def __init__(self):
        self.raw = collections.deque()
        self.reset()
    def reset(self):
        self.raw.clear()
        self.pcm_tail = np.zeros(0, dtype=np.float32)
        self.mel = np.zeros((80, 0), dtype=np.float32)
        self.t0 = None          # 這一句開始講的牆上時間
        self.last_in = 0.0
    def feed(self, data):       # 主迴圈：只排隊
        self.raw.append(data)
    def _exhausted(self):
        if self.t0 is None:
            return True
        tgt = (time.time() - self.t0 - LEAD) * 80.0
        return tgt + mel_step >= self.mel.shape[1]
    def _drain(self):           # 工作執行緒：重採樣＋算聲譜
        now = time.time()
        if self.raw and self.t0 is not None and (now - self.last_in) > GAP_NEW_UTTER and self._exhausted():
            self.pcm_tail = np.zeros(0, dtype=np.float32)   # 新的一句：清舊聲譜、重新對時
            self.mel = np.zeros((80, 0), dtype=np.float32)
            self.t0 = None
        got = False
        while self.raw:
            f = _resample_24k_to_16k(self.raw.popleft())
            buf = np.concatenate([self.pcm_tail, f])
            usable = (len(buf) - CTX) // HOP * HOP
            if usable >= HOP:
                seg = buf[: CTX + usable]
                m = w2l_audio.melspectrogram(seg)           # 含左側銜接 → 掐頭
                skip = CTX // HOP
                self.mel = np.concatenate([self.mel, m[:, skip: skip + usable // HOP]], axis=1)
                self.pcm_tail = buf[usable:]
            else:
                self.pcm_tail = buf
            got = True
        if got:
            if self.t0 is None:
                self.t0 = time.time()
                print(f"[utter] start mel_lead={LEAD}s", flush=True)
            self.last_in = time.time()
        if self.mel.shape[1] > 90 * 80:                     # 超長獨白保險絲
            self.reset()
    def windows_now(self, n):
        """工作執行緒：照牆上時鐘拿「現在該講」的 n 幀聲譜窗；沒得講回 None＝待機。"""
        self._drain()
        if self.t0 is None:
            return None
        tgt = (time.time() - self.t0 - LEAD) * 80.0
        if tgt < 0:
            return None
        if int(tgt + (n - 1) * MEL_PER_FRAME) + mel_step > self.mel.shape[1]:
            return None
        return [self.mel[:, int(tgt + k * MEL_PER_FRAME): int(tgt + k * MEL_PER_FRAME) + mel_step] for k in range(n)]

mels = MelStream()

def _resample_24k_to_16k(i16_bytes):
    x = np.frombuffer(i16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    n_out = int(len(x) * SR_MEL / SR_IN)
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    xp = np.linspace(0.0, 1.0, len(x), endpoint=False)
    xq = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(xq, xp, x).astype(np.float32)

# ---------- GPU 生成 ----------
def gen_frames(mel_windows):
    fb = np.asarray([FACE96] * len(mel_windows), dtype=np.float32) / 255.0
    mk = fb.copy(); mk[:, img_size // 2:] = 0
    fb = np.concatenate((mk, fb), axis=3)
    it = torch.from_numpy(np.transpose(fb, (0, 3, 1, 2))).float().to(device)
    mt = torch.from_numpy(np.asarray(mel_windows, dtype=np.float32)).float().unsqueeze(1).to(device)
    with torch.no_grad():
        pred = model(mt, it)
    pred = (pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.0)
    outs = []
    for p in pred:
        fr = FRAME.copy()
        gen = cv2.resize(p.astype(np.uint8), (PATCH_W, PATCH_H)).astype(np.float32)
        fr[Y1:Y2, X1:X2] = (ORIG_PATCH * (1.0 - BLEND_MASK) + gen * BLEND_MASK).astype(np.uint8)
        outs.append(fr)
    return outs

def worker_step():
    """工作執行緒一站式：收聲音→算聲譜→（有得講就）生成對嘴幀。主迴圈零重活。"""
    wins = mels.windows_now(MICROBATCH)
    if wins is None:
        return None
    return gen_frames(wins)

class NeningTrack(VideoStreamTrack):
    kind = "video"
    def __init__(self):
        super().__init__()
        self.buf = []; self.count = 0; self.t0 = time.time(); self.live = 0
    async def recv(self):
        pts, time_base = await self.next_timestamp()
        if not self.buf:
            frames = await asyncio.get_event_loop().run_in_executor(None, worker_step)
            if frames:
                self.buf = frames; self.live += len(frames)
        fr = self.buf.pop(0) if self.buf else FRAME     # 沒聲音＝原照片待機
        self.count += 1
        if self.count % 120 == 0:
            print(f"[stream] frames={self.count} live_lip={self.live} eff_fps={round(self.count/(time.time()-self.t0),1)} "
                  f"mel_avail={mels.mel.shape[1]}", flush=True)
        vf = VideoFrame.from_ndarray(fr, format="bgr24")
        vf.pts = pts; vf.time_base = time_base
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
    params = await request.json()
    od = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection(); pcs.add(pc)
    pc.addTrack(NeningTrack())
    await pc.setRemoteDescription(od)
    ans = await pc.createAnswer(); await pc.setLocalDescription(ans)
    return _cors(web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}))

async def audio_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    print("[audio] connected", flush=True)
    mels.reset()
    async for msg in ws:
        if msg.type == WSMsgType.BINARY:
            mels.feed(msg.data)                          # 只排隊、不算——重活在工作執行緒
        elif msg.type == WSMsgType.TEXT and msg.data == "reset":
            print("[audio] reset(interrupt)", flush=True)
            mels.reset()                                 # 用戶插話：清空、回待機
    print("[audio] closed", flush=True)
    mels.reset()
    return ws

async def health(request):
    return _cors(web.json_response({"ok": True, "face": "寧寧", "engine": "wav2lip-live"}))

async def on_shutdown(app):
    await asyncio.gather(*[pc.close() for pc in pcs]); pcs.clear()

app = web.Application()
app.on_shutdown.append(on_shutdown)
app.router.add_route("*", "/offer", offer)
app.router.add_get("/audio", audio_ws)
app.router.add_get("/health", health)
if __name__ == "__main__":
    print(f"[server] 寧寧 live avatar on :{PORT}  (/offer /audio /health)", flush=True)
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)
