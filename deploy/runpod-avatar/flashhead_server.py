# -*- coding: utf-8 -*-
"""沐寧 · FlashHead 通話服務 · 獨立版（RunPod / Glows / 任何有 4090 的機器直接跑）

2026-07-11 主蘇菲：從 flashhead_modal_dev.py 拆出 Modal 包裝的移植版——
引擎邏輯（Feeder / FrameSink / AudioOutBuffer / 臉聲同線雙軌 / 換角色互斥鎖 /
看門狗 / 量測儀表）一行不動照搬，只把 modal.App/@app.cls/@modal.enter/@modal.asgi_app
換成「開機直接 load → uvicorn 常駐」。

2026-07-12 卡西法：單例 → N 槽改造（照 docs/多人併發容量架構-2026-07-12.md §3.1）。
引擎邏輯本體（Feeder/FrameSink/AudioOutBuffer/SlotPool/健康快照數學）搬進同目錄的
flashhead_engine_core.py（零重量依賴，可本機單元測試），這份檔案現在只負責：
GPU pipeline 的 N 槽載入 + FastAPI 路由怎麼把 session 綁到哪一槽。

**部署提醒（重要）**：這份檔案現在 import 同目錄的 flashhead_engine_core.py——
scp 上機器時「兩個檔案要一起傳」，只傳這支會在開機時 ImportError。

**MUNEA_FH_SLOTS 相容性鐵律**：環境變數沒設（預設 1）＝跟改造前的單例版行為
一字不差——429 邏輯、/health capacity 欄位、reset 時機、stale-pc 自癒判斷，
全部逐行對照原始單例版移植，不是重寫。只有在測試卡上設
`MUNEA_FH_SLOTS=3` 才會真的啟用多槽（現役 GLOWS 機器沒設這個變數，
這次改動對它是零風險——沒設變數＝跟改之前一模一樣）。

跑法（機器上要先照 runpod_install.sh / glows_install2.sh 裝好）：
  MUNEA_APP_KEY=<通行碼> python3.12 flashhead_server.py          # 門牌 8188
  MUNEA_FH_SLOTS=3 MUNEA_APP_KEY=<通行碼> python3.12 flashhead_server.py   # 測試卡開 3 槽
  （RunPod: https://<podId>-8188.proxy.runpod.net 就是對外 https 入口，WS 同線）

模式：eager（不開 torch.compile）——2026-07-11 Glows TW 4090 實測 eager 每塊
p50 305ms / p95 309ms（預算 960ms、餘裕 67.8%），且開機 5 秒內；compile 只快
60ms 但每次開機要多付 ~2 分鐘熱身稅，4090 上不划算（台灣機碼錶數據見協作看板）。
"""
import asyncio
import base64
import collections
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from fractions import Fraction

import numpy as np

FH_REPO = os.path.expanduser(os.environ.get("MUNEA_FH_REPO", "/root/SoulX-FlashHead"))
sys.path.insert(0, FH_REPO)
os.chdir(FH_REPO)

import torch

# 模式開關（2026-07-11 Edward 真機驗收抓到：實戰載客時 eager 每塊 0.68s、餘裕僅 27%、畫面斷糧 468 次＝嘴定格。
# 常駐機開機稅只付一次 → 渦輪(compile)划算：MUNEA_FH_COMPILE=1 開、熱身約 2 分鐘、穩態快 ~20%）
import flash_head.src.pipeline.flash_head_pipeline as _fhp_mod
_COMPILE = os.environ.get("MUNEA_FH_COMPILE", "0") == "1"
_fhp_mod.COMPILE_MODEL = _COMPILE
_fhp_mod.COMPILE_VAE = _COMPILE
# N-way batching surgery phase 1 / option B (2026-07-23, calcifer). See
# deploy/flashhead-patches/README.md for the patch itself (gates 8 device-wide
# torch.cuda.synchronize() debug barriers inside generate()) and the
# external-override convention this mirrors (same pattern as COMPILE_MODEL /
# COMPILE_VAE right above). Default keeps every barrier firing -- byte-for-
# byte pre-patch behavior when MUNEA_FH_PROFILE_SYNC is unset. Harmless no-op
# if the patch was not applied to this checkout (PROFILE_SYNC just becomes an
# unused module attribute; generate() still calls torch.cuda.synchronize()
# directly, matching pre-patch behavior in that case too).
_fhp_mod.PROFILE_SYNC = os.environ.get("MUNEA_FH_PROFILE_SYNC", "1") == "1"

from flash_head.inference import (get_audio_embedding, get_base_data,
                                  get_infer_params, get_pipeline, run_pipeline)

from flashhead_engine_core import (AudioOutBuffer, Feeder, FrameSink, Slot, SlotPool,
                                    env_flag_enabled, health_snapshot,
                                    make_slot_stream_run_pipeline, parse_frame_size,
                                    slot_summary, switch_slot_char)

# ===== 正式線 / 展示間分家（2026-07-21）=====
# a05/a06 = 正式 App 的臉，條件圖必須是「原生正方形裁切」（a05 貼 y=190、a06 貼 y=209），
# 與 web/src/styles.css 的 .fh-overlay 貼合數字綁在一起，任一邊單獨改就會出現
# 頭被壓扁／頭框上移／領口疊影（2026-07-20 正是這樣中的）。
# a05d/a06d = B2B 展示間專用實驗格，換裁切／換解析度都不影響正式線。
CHAR_SRC = {
    "a05": os.environ.get("MUNEA_FH_CHAR_A05", "/root/char-a05B.png"),
    "a06": os.environ.get("MUNEA_FH_CHAR_A06", "/root/char-a06B.png"),
    "a05d": os.environ.get("MUNEA_FH_CHAR_A05D", "/root/char-a05B-demo.png"),
    "a06d": os.environ.get("MUNEA_FH_CHAR_A06D", "/root/char-a06B-demo.png"),
}
DEFAULT_CHAR = "a05"

# 與 deploy/modal-avatar/flashhead_modal_dev.py 同一份表——備援機接手時臉不可以換個樣子。
# scripts/test-avatar-render-contract.py 會比對兩支引擎與 App，任一邊漂掉就擋下。
_PROD_SQUARE = {"width": 640, "height": 640}
_DEMO_FILL = {"width": 512, "height": 512}
_CANVAS = {"width": 1080, "height": 1920}
AVATAR_RENDER_CONTRACTS = {
    "a05": {"version": "app-flashhead-square-v1", "lane": "prod", "canvas": _CANVAS,
            "source_crop": {"x": 0, "y": 190, "width": 1080, "height": 1080},
            "model_input": _PROD_SQUARE, "fit": "fill"},
    "a06": {"version": "app-flashhead-square-v1", "lane": "prod", "canvas": _CANVAS,
            "source_crop": {"x": 0, "y": 209, "width": 1080, "height": 1080},
            "model_input": _PROD_SQUARE, "fit": "fill"},
    "a05d": {"version": "demo-flashhead-portrait-v1", "lane": "demo", "canvas": _CANVAS,
             "source_crop": {"x": 0, "y": 140, "width": 1080, "height": 1440},
             "model_input": _DEMO_FILL, "fit": "fill"},
    "a06d": {"version": "demo-flashhead-portrait-v1", "lane": "demo", "canvas": _CANVAS,
             "source_crop": {"x": 0, "y": 140, "width": 1080, "height": 1440},
             "model_input": _DEMO_FILL, "fit": "fill"},
}


def avatar_render_contract(char):
    return AVATAR_RENDER_CONTRACTS.get(char) or AVATAR_RENDER_CONTRACTS[DEFAULT_CHAR]
MODEL_ROOT = os.path.expanduser(os.environ.get("MUNEA_FH_MODEL_ROOT", "/models"))
CKPT_DIR = os.environ.get(
    "MUNEA_FH_CKPT_DIR", os.path.join(MODEL_ROOT, "soulx-flashhead-1.3b")
)
WAV2VEC_DIR = os.environ.get(
    "MUNEA_FH_WAV2VEC_DIR", os.path.join(MODEL_ROOT, "wav2vec2-base-960h")
)

SR_IN, SR_ENG = 24000, 16000
# 2026-07-11 斷續根治（官方體檢：零起播緩衝→斷糧）：開口前先墊 0.5s、生成允許往前衝到 1.5s 存貨。
# 原理：4090 生成比即時快~1.9倍，拔掉「卡即時節奏」的閘門後會自動囤到上限、形成抖動緩衝墊；
# 偶爾一塊做慢也不會見底（斷糧）。代價＝首句慢約 0.5s（一次性、非累積），換整段不再斷斷續續。
AUDIO_PREBUFFER_S = max(0.2, float(os.environ.get("MUNEA_FH_AUDIO_PREBUFFER_S", "0.5")))
OPENING_PREBUFFER_S = max(
    AUDIO_PREBUFFER_S,
    float(os.environ.get("MUNEA_FH_OPENING_PREBUFFER_S", "1.0")),
)
MAX_AHEAD_S = 1.5          # 生成往前衝的存貨上限（超過就等播放消化、不無限囤積致延遲膨脹）
# 2026-07-11 臉銳化：unsharp mask（Edward 看過覺得「不太行」、要真 1024 而非銳化假利）→ 預設關。
# 程式留著、MUNEA_FH_SHARPEN=1 可再開；正解走真 1024（Pro 模型/超解析），見下方研究。
FH_SHARPEN = os.environ.get("MUNEA_FH_SHARPEN", "0") == "1"
FRAME_SIZE = parse_frame_size(os.environ.get("MUNEA_FH_FRAME_SIZE", "512"))
# N-way batching surgery phase 1 / option B (2026-07-23): give each slot its
# own CUDA stream instead of sharing the default stream with the other two.
# Default off -- matches pre-patch behavior byte-for-byte (see
# deploy/flashhead-patches/README.md). Pairs with MUNEA_FH_PROFILE_SYNC=0
# above; turning this on alone has little effect because the vendored
# generate() barriers (when still firing) are device-wide, not per-stream.
SLOT_STREAM = env_flag_enabled(os.environ.get("MUNEA_FH_SLOT_STREAM", "0"))
# SoulX defaults to 512 in infer_params.yaml. Changing only the source image
# does not change inference resolution, so apply the launch decision here.
import flash_head.inference as _fh_inference
_fh_inference.infer_params["height"] = FRAME_SIZE
_fh_inference.infer_params["width"] = FRAME_SIZE
PORT = int(os.environ.get("MUNEA_FACE_PORT", "8188"))
# 2026-07-12 N 槽改造：沒設＝1（跟改造前單例行為一字不差）。只有測試卡明確設
# MUNEA_FH_SLOTS=3 才會真的多槽——這是本輪任務的核心相容性鐵律。
N_SLOTS = max(1, int(os.environ.get("MUNEA_FH_SLOTS", "1")))


# 2026-07-23 時鐘誤差容忍：GPU 租賃主機的時鐘由機房控制、容器內無權校時（tw-06 實測快 4 分 17 秒），
# 主機時鐘偏快會把 90 秒壽命的正牌通話證全部當過期拒收（換卡當天全通話陣亡的根因）。
# 容忍只放寬「過期」判定方向（吃得下主機快 MUNEA_CALL_TOKEN_CLOCK_LEEWAY 秒）；簽章/worker 綁定照舊全驗。
CALL_TOKEN_CLOCK_LEEWAY_S = max(0, int(os.environ.get("MUNEA_CALL_TOKEN_CLOCK_LEEWAY", "330")))


def _decode_call_token(token, secret, expected_worker):
    if not token or not secret:
        return None
    try:
        encoded, supplied = token.split(".", 1)
        expected = base64.urlsafe_b64encode(
            hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        ).rstrip(b"=").decode("ascii")
        if not hmac.compare_digest(supplied, expected):
            return None
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw)
        if int(payload.get("exp") or 0) + CALL_TOKEN_CLOCK_LEEWAY_S < int(time.time()):
            return None
        if expected_worker and payload.get("worker_id") != expected_worker:
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _post_json(url, body, bearer, timeout=10):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + bearer},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


class FlashHead:
    """跟 Modal 版同名同構——load() 一次、wake() 一次、web() 產出 FastAPI app。
    2026-07-12 起內部是 N 槽陣列（self.slots），N=1 時對外行為跟改造前單例版
    完全相同（欄位名稱、429 邏輯、reset 時機一字不差）。"""

    def load(self):
        t0 = time.time()
        self._get_base_data = get_base_data
        self._get_audio_embedding = get_audio_embedding
        self._run_pipeline = run_pipeline

        self.slots = [Slot(i) for i in range(N_SLOTS)]
        for slot in self.slots:
            self._load_slot(slot)

        # 頂層彙總（給人看的 log／未來 ops 用；/health 的 "load" 欄位用 slot[0].load_report，
        # 跟改造前單例版欄位形狀一字不差，不是這個彙總——見 health() 路由）
        self.load_report = {
            "slots": N_SLOTS,
            "per_slot": [s.load_report for s in self.slots],
            "total_load_s": round(time.time() - t0, 1),
            "host": "standalone-" + os.uname().nodename,
        }
        print("[load]", self.load_report, flush=True)

    def _load_slot(self, slot):
        t0 = time.time()
        slot.pipeline = get_pipeline(world_size=1, ckpt_dir=CKPT_DIR,
                                     wav2vec_dir=WAV2VEC_DIR, model_type="lite")
        t1 = time.time()

        slot.char = DEFAULT_CHAR
        get_base_data(slot.pipeline, cond_image_path_or_dir=CHAR_SRC[slot.char],
                      base_seed=42, use_face_crop=False)
        t2 = time.time()

        ip = get_infer_params()
        slot.sample_rate = ip["sample_rate"]
        slot.tgt_fps = ip["tgt_fps"]
        slot.frame_num = ip["frame_num"]
        slot.motion_frames_num = ip["motion_frames_num"]
        slot.slice_len = slot.frame_num - slot.motion_frames_num
        slot.cached_audio_duration = ip["cached_audio_duration"]
        slot.chunk_samples = slot.slice_len * slot.sample_rate // slot.tgt_fps
        slot.audio_end_idx = slot.cached_audio_duration * slot.tgt_fps
        slot.audio_start_idx = slot.audio_end_idx - slot.frame_num
        cached_len_sum = slot.sample_rate * slot.cached_audio_duration
        slot.audio_dq = collections.deque([0.0] * cached_len_sum, maxlen=cached_len_sum)

        warm_times = []
        for _ in range(2):
            silence = np.zeros(slot.chunk_samples, dtype=np.float32)
            tw0 = time.time()
            slot.audio_dq.extend(silence.tolist())
            arr = np.array(slot.audio_dq)
            emb = get_audio_embedding(slot.pipeline, arr, slot.audio_start_idx, slot.audio_end_idx)
            video = run_pipeline(slot.pipeline, emb)
            torch.cuda.synchronize()
            warm_times.append(round(time.time() - tw0, 2))
        frame_shape = tuple(int(v) for v in video.shape[-3:])
        if len(frame_shape) != 3 or frame_shape[0] != FRAME_SIZE or frame_shape[1] != FRAME_SIZE:
            raise RuntimeError("FlashHead generated " + str(frame_shape)
                               + " but MUNEA_FH_FRAME_SIZE=" + str(FRAME_SIZE))
        slot.frame_height, slot.frame_width = frame_shape[0], frame_shape[1]
        t3 = time.time()

        slot.load_report = {
            "pipeline_load_s": round(t1 - t0, 1),
            "base_data_s": round(t2 - t1, 2),
            "warm_chunk_s": warm_times,
            "total_load_s": round(t3 - t0, 1),
            "chunk_samples": slot.chunk_samples,
            "slice_len_frames": slot.slice_len,
            "chunk_budget_ms": round(slot.slice_len / slot.tgt_fps * 1000, 1),
            "output_resolution": {"width": slot.frame_width, "height": slot.frame_height},
            "host": "standalone-" + os.uname().nodename,
        }
        print("[load] slot" + str(slot.index), slot.load_report, flush=True)

    def wake(self):
        import aiortc.codecs.h264 as _h264
        _h264.MIN_BITRATE = 3_000_000
        _h264.DEFAULT_BITRATE = 8_000_000
        _h264.MAX_BITRATE = 12_000_000

        self.wake_ts = time.time()

        import cv2

        def _load_poster(path):
            raw = cv2.imread(path)
            if raw is None:
                raise FileNotFoundError("avatar source not found: " + path)
            p = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
            return cv2.resize(p, (FRAME_SIZE, FRAME_SIZE))

        self._load_poster = _load_poster
        self.pool = SlotPool(self.slots)
        for slot in self.slots:
            self._wake_slot(slot)
        print("[wake] " + str(len(self.slots))
              + " slot(s) ready, audio+video co-release, call components ready", flush=True)

    def _wake_slot(self, slot):
        slot.poster = self._load_poster(CHAR_SRC[slot.char])
        slot.pcs = set()
        slot.pc_created = {}
        slot.round_count = 0
        slot.round_start_ts = 0.0
        slot.round_latencies = collections.deque(maxlen=20)
        slot.last_gen_compute_ms = None
        slot.gen_compute_ms_hist = collections.deque(maxlen=100)
        # Lip-sync inference stays at 16 kHz; WebRTC carries the untouched
        # 24 kHz Gemini audio for clearer speech and less resampling noise.
        slot.audio_out = AudioOutBuffer(SR_IN, prebuffer_s=AUDIO_PREBUFFER_S)
        slot.sink = FrameSink(slot.tgt_fps)
        slot.SYNC_BUFFER_MS = 350
        run_pipeline_for_slot = self._run_pipeline
        if SLOT_STREAM:
            # Give this slot its own stream instead of sharing the default one
            # with the other slots -- see make_slot_stream_run_pipeline's
            # docstring in flashhead_engine_core.py for why it uses
            # wait_stream() and not another blocking synchronize().
            slot.cuda_stream = torch.cuda.Stream()
            run_pipeline_for_slot = make_slot_stream_run_pipeline(
                self._run_pipeline, slot.cuda_stream, torch)
        else:
            slot.cuda_stream = None
        slot.feeder = Feeder(slot, self._get_audio_embedding, run_pipeline_for_slot,
                             sr_in=SR_IN, sr_eng=SR_ENG, max_ahead_s=MAX_AHEAD_S,
                             sharpen=FH_SHARPEN, on_unhealthy=self._on_slot_unhealthy)

    def _on_slot_unhealthy(self, slot):
        """故障隔離：一槽連續出錯超過門檻時呼叫——強制把它從准入池釋放，
        不讓新使用者被配到壞掉的槽，也不讓舊使用者卡在悶死的連線上不自知。"""
        session = slot.active_session
        if getattr(self, "pool", None) is not None:
            self.pool.force_release_slot(slot)
        print("[capacity] slot" + str(slot.index) + " marked unhealthy, force-released session="
              + (session[:8] if session else "None"), flush=True)

    def _switch(self, slot, char):
        ok = switch_slot_char(slot, char, CHAR_SRC, self._get_base_data, self._load_poster)
        if ok:
            print("[char] slot" + str(slot.index) + " -> " + slot.char + " ok", flush=True)
        else:
            print("[char] slot" + str(slot.index) + " switch to " + str(char) + " failed", flush=True)
        return ok

    def web(self):
        from aiortc import (MediaStreamError, MediaStreamTrack, RTCConfiguration, RTCIceServer,
                            RTCPeerConnection, RTCSessionDescription, VideoStreamTrack)
        from aiortc.mediastreams import VIDEO_CLOCK_RATE, VIDEO_TIME_BASE
        from av import AudioFrame, VideoFrame
        from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
        from fastapi.responses import JSONResponse
        from fastapi.middleware.cors import CORSMiddleware

        api = FastAPI()
        worker_origins = [x.strip() for x in os.environ.get(
            "MUNEA_WORKER_CORS_ORIGINS",
            "capacitor://localhost,ionic://localhost,http://localhost,https://localhost,https://munea-b2b.vercel.app",
        ).split(",") if x.strip()]
        api.add_middleware(
            CORSMiddleware, allow_origins=worker_origins,
            allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
        )
        outer = self
        admission_lock = asyncio.Lock()

        _gate = os.environ.get("MUNEA_APP_KEY", "").strip()
        _token_secret = os.environ.get("MUNEA_CALL_TOKEN_SECRET", "").strip()
        _worker_id = os.environ.get("MUNEA_WORKER_ID", "").strip()
        _call_control = os.environ.get("MUNEA_CALL_CONTROL_URL", "").strip().rstrip("/")
        _control_token = os.environ.get("MUNEA_GATEWAY_ADMIN_KEY", "").strip()
        _worker_heartbeat_seconds = max(
            10, int(os.environ.get("MUNEA_WORKER_HEARTBEAT_SECONDS", "30"))
        )
        _allow_legacy = os.environ.get("MUNEA_ALLOW_LEGACY_APP_KEY", "1") == "1"
        _demo_password_sha256 = os.environ.get("MUNEA_DEMO_PASSWORD_SHA256", "").strip().lower()
        _demo_token_ttl = max(60, min(900, int(os.environ.get("MUNEA_DEMO_TOKEN_TTL", "300"))))
        _demo_tokens = {}
        _demo_attempts = {}
        _session_control = {}

        def _pass(request_key):
            return (not _gate and not _demo_password_sha256) or (request_key == _gate)

        def _demo_token_payload(token):
            now = int(time.time())
            expired = [value for value, payload in _demo_tokens.items()
                       if int(payload.get("exp") or 0) < now]
            for value in expired:
                _demo_tokens.pop(value, None)
            payload = _demo_tokens.get(token or "")
            if not payload or int(payload.get("exp") or 0) < now:
                return None
            return payload

        def _authorize(request_key, token):
            demo_payload = _demo_token_payload(token)
            if demo_payload is not None:
                return demo_payload
            if _token_secret:
                payload = _decode_call_token(token, _token_secret, _worker_id)
                if payload is not None:
                    return payload
                if not (_allow_legacy and _pass(request_key)):
                    return False
                return None
            if _demo_password_sha256:
                return False
            return None if _pass(request_key) else False

        async def _control_ready(control):
            if not (control and _call_control and _control_token):
                return
            body = {
                "call_id": control["call_id"],
                "lease_version": int(control["lease_version"]),
                "component": "avatar",
                "event_id": "avatar-ready:" + control["call_id"] + ":" + str(control["lease_version"]),
            }
            try:
                await asyncio.to_thread(
                    _post_json, _call_control + "/v1/internal/calls/ready", body, _control_token
                )
            except Exception as exc:
                print("[call-control] avatar ready callback failed: " + str(exc), flush=True)

        async def _control_release(control, reason):
            if not (control and _call_control and _control_token):
                return
            call_id = str(control["call_id"])
            version = int(control["lease_version"])
            body = {
                "lease_version": version,
                "event_id": "avatar-release:" + call_id + ":" + str(version),
                "reason": reason,
            }
            try:
                await asyncio.to_thread(
                    _post_json,
                    _call_control + "/v1/internal/calls/" + call_id + "/release",
                    body,
                    _control_token,
                )
            except Exception as exc:
                print("[call-control] avatar release callback failed: " + str(exc), flush=True)

        async def _worker_heartbeat_loop():
            if not (_worker_id and _call_control and _control_token):
                print("[call-control] worker heartbeat disabled (configuration incomplete)",
                      flush=True)
                return
            endpoint = (
                _call_control + "/v1/internal/workers/" + _worker_id + "/health"
            )
            while True:
                try:
                    active = int(outer.pool.snapshot().get("active", 0))
                    await asyncio.to_thread(
                        _post_json,
                        endpoint,
                        {"healthy": True, "active": active},
                        _control_token,
                    )
                except Exception as exc:
                    print("[call-control] worker heartbeat failed: " + str(exc), flush=True)
                await asyncio.sleep(_worker_heartbeat_seconds)

        async def _release_session(session_id, pc=None, reason="avatar_disconnected"):
            async with admission_lock:
                slot = outer.pool.release(session_id, pc)
            if slot is None:
                return
            control = _session_control.pop(session_id, None)
            try:
                slot.feeder.reset()
            except Exception as e:
                print("[capacity] release reset failed (slot" + str(slot.index) + "): "
                      + str(e), flush=True)
            print("[capacity] released session " + session_id[:8] + " (slot" + str(slot.index) + ")",
                  flush=True)
            await _control_release(control, reason)

        class FlashHeadTrack(VideoStreamTrack):
            kind = "video"
            def __init__(self, slot):
                super().__init__()
                self.slot = slot
                self.last = slot.poster
                self._active_ts = 0.0
                self._ptime = 1.0 / slot.tgt_fps
            async def next_timestamp(self):
                if self.readyState != "live":
                    raise MediaStreamError()
                if hasattr(self, "_timestamp"):
                    self._timestamp += int(self._ptime * VIDEO_CLOCK_RATE)
                    wait = self._start + (self._timestamp / VIDEO_CLOCK_RATE) - time.time()
                    if wait > 0:
                        await asyncio.sleep(wait)
                else:
                    self._start = time.time()
                    self._timestamp = 0
                return self._timestamp, VIDEO_TIME_BASE
            async def recv(self):
                pts, tb = await self.next_timestamp()
                # AudioOutBuffer owns the shared start gate. Keep the poster on
                # screen without consuming generated frames until audio has a
                # real prebuffer, then release both tracks on the same clock.
                if self.slot.audio_out.playout_held():
                    fr = None
                    self.last = self.slot.poster
                    self._active_ts = 0.0
                else:
                    fr = self.slot.sink.pop()
                now = time.time()
                if fr is not None:
                    self.last = fr
                    self._active_ts = now
                elif self._active_ts and (now - self._active_ts) > 0.35:
                    self.last = self.slot.poster
                    self._active_ts = 0.0
                vf = VideoFrame.from_ndarray(self.last, format="rgb24")
                vf.pts = pts
                vf.time_base = tb
                return vf

        class FlashHeadAudioTrack(MediaStreamTrack):
            kind = "audio"
            def __init__(self, slot):
                super().__init__()
                self.slot = slot
                self._next_pts = 0
                self._started = None
            async def recv(self):
                sr = self.slot.audio_out.sample_rate
                if self._started is None:
                    self._started = time.time()
                target_t = self._started + self._next_pts / sr
                now = time.time()
                if target_t > now:
                    await asyncio.sleep(target_t - now)
                chunk = self.slot.audio_out.pop_frame()
                frame = AudioFrame(format="s16", layout="mono", samples=len(chunk))
                frame.sample_rate = sr
                frame.pts = self._next_pts
                frame.time_base = Fraction(1, sr)
                frame.planes[0].update(chunk.astype("<i2").tobytes())
                self._next_pts += len(chunk)
                return frame

        @api.post("/demo/session")
        async def demo_session(payload: dict, request: Request):
            if not _demo_password_sha256:
                return JSONResponse(status_code=404, content={"error": "demo disabled"})
            now = int(time.time())
            client = request.client.host if request.client else "unknown"
            recent = [stamp for stamp in _demo_attempts.get(client, []) if stamp > now - 300]
            if len(recent) >= 10:
                return JSONResponse(status_code=429, content={"error": "too many attempts"})
            supplied = str(payload.get("password") or "").replace(" ", "").lower()
            digest = hashlib.sha256(supplied.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(digest, _demo_password_sha256):
                recent.append(now)
                _demo_attempts[client] = recent
                await asyncio.sleep(0.25)
                return JSONResponse(status_code=401, content={"error": "password"})
            _demo_attempts.pop(client, None)
            token = secrets.token_urlsafe(32)
            exp = now + _demo_token_ttl
            _demo_tokens[token] = {
                "demo": True,
                "call_id": "demo-" + secrets.token_hex(8),
                "lease_version": 1,
                "slot_id": 1,
                "exp": exp,
            }
            return {"token": token, "expiresIn": _demo_token_ttl}

        @api.get("/health")
        def health(key: str = "", token: str = ""):
            if _authorize(key, token) is False:
                return JSONResponse(status_code=403, content={"ok": False, "error": "token required"})
            snap = outer.pool.snapshot()
            primary = outer.slots[0]
            body = health_snapshot(primary, outer.wake_ts)
            body.update({"ok": True, "engine": "flashhead-lite-standalone", "char": primary.char,
                         "avatar_render_contract": avatar_render_contract(primary.char),
                         "capacity": snap})
            if len(outer.slots) > 1:
                body["slots"] = [slot_summary(s, outer.wake_ts) for s in outer.slots]
            return body

        @api.post("/diag")
        async def diag(payload: dict, key: str = "", token: str = ""):
            if _authorize(key, token) is False:
                return JSONResponse(status_code=403, content={"error": "token required"})
            import json as _json
            uptime_s = round(time.time() - getattr(outer, "wake_ts", time.time()), 1)
            body = _json.dumps(payload, ensure_ascii=False, default=str)
            if len(body) > 12000:
                body = body[:12000] + "...(truncated)"
            print("=" * 70, flush=True)
            print("[DIAG] client-reported connection diagnostic  server_uptime_s=" + str(uptime_s),
                  flush=True)
            print("[DIAG] " + body, flush=True)
            print("=" * 70, flush=True)
            return {"ok": True, "received": True, "server_uptime_s": uptime_s}

        @api.post("/offer")
        async def offer(payload: dict, key: str = "", char: str = "", token: str = ""):
            control = _authorize(key, token)
            if control is False:
                return JSONResponse(status_code=403, content={"error": "valid call token required"})
            import uuid
            session_id = uuid.uuid4().hex
            preferred_index = None
            if control:
                preferred_index = int(control.get("slot_id") or 0) - 1
            async with admission_lock:
                slot = outer.pool.admit(session_id, preferred_index=preferred_index)
            if slot is None:
                return JSONResponse(status_code=429, content={
                    "error": "avatar capacity full", "code": "capacity_full",
                    "retryAfter": 5,
                })
            if control:
                _session_control[session_id] = control
            if char and not outer._switch(slot, char):
                await _release_session(session_id, reason="avatar_character_failed")
                return {"error": "char not supported"}
            # 2026-07-11 主蘇菲：新通話開線＝把上一通的殘留全部倒掉（音頻緩衝+畫格佇列+進料狀態）。
            # 不倒＝Edward 實測「掛斷再撥、她一接通就繼續播上一段的話」——殘留聲音直接漏進新通話。
            try:
                slot.feeder.reset()
                slot.audio_out.arm_prebuffer(OPENING_PREBUFFER_S)
            except Exception as _e:
                print("[offer] pre-call reset failed (slot" + str(slot.index) + "): "
                      + str(_e), flush=True)
            try:
                ice_servers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]
                turn_urls = (control or {}).get("turn_urls") or []
                turn_username = (control or {}).get("turn_username") or ""
                turn_credential = (control or {}).get("turn_credential") or ""
                if not turn_urls:
                    turn_urls = [x.strip() for x in os.environ.get("MUNEA_TURN_URLS", "").split(",") if x.strip()]
                    turn_username = os.environ.get("MUNEA_TURN_USERNAME", "").strip()
                    turn_credential = os.environ.get("MUNEA_TURN_CREDENTIAL", "").strip()
                if turn_urls and turn_username and turn_credential:
                    ice_servers.append(RTCIceServer(
                        urls=turn_urls, username=turn_username, credential=turn_credential
                    ))
                pc = RTCPeerConnection(RTCConfiguration(iceServers=ice_servers))
            except Exception:
                await _release_session(session_id, reason="avatar_pc_create_failed")
                raise
            async with admission_lock:
                if slot.active_session == session_id:
                    slot.active_pc = pc
            slot.pcs.add(pc)
            slot.pc_created[id(pc)] = time.time()

            pc_tag = str(id(pc))[-5:]
            ready_reported = {"done": False}

            @pc.on("connectionstatechange")
            async def _on_conn_state_change():
                age_s = round(time.time() - slot.pc_created.get(id(pc), time.time()), 1)
                print("[offer] slot" + str(slot.index) + " pc#" + pc_tag + " -> "
                      + pc.connectionState + " (age " + str(age_s) + "s)", flush=True)
                if pc.connectionState == "connected" and not ready_reported["done"]:
                    ready_reported["done"] = True
                    await _control_ready(control)
                if pc.connectionState in ("closed", "failed"):
                    slot.pcs.discard(pc)
                    slot.pc_created.pop(id(pc), None)
                    await _release_session(session_id, pc)

            pc.addTrack(FlashHeadTrack(slot))
            pc.addTrack(FlashHeadAudioTrack(slot))
            try:
                await pc.setRemoteDescription(RTCSessionDescription(sdp=payload["sdp"], type=payload["type"]))
                ans = await pc.createAnswer()
                await pc.setLocalDescription(ans)
                for _ in range(60):
                    if pc.iceGatheringState == "complete":
                        break
                    await asyncio.sleep(0.05)
                return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type,
                        "session": session_id}
            except Exception:
                slot.pcs.discard(pc)
                slot.pc_created.pop(id(pc), None)
                try:
                    await pc.close()
                finally:
                    await _release_session(session_id, pc, reason="avatar_offer_failed")
                raise

        @api.on_event("startup")
        async def _start_background_tasks():
            async def _loop():
                while True:
                    await asyncio.sleep(10)
                    now = time.time()
                    for slot in outer.slots:
                        stale = [p for p in list(slot.pcs)
                                 if p.connectionState != "connected"
                                 and now - slot.pc_created.get(id(p), now) > 30]
                        for p in stale:
                            print("[watchdog] slot" + str(slot.index) + " closing stale pc state="
                                  + p.connectionState, flush=True)
                            try:
                                await p.close()
                            except Exception as e:
                                print("[watchdog] close err " + str(e), flush=True)
                            slot.pcs.discard(p)
                            slot.pc_created.pop(id(p), None)
                            if slot.active_pc is p:
                                await _release_session(slot.active_session, p, reason="avatar_watchdog_reaped")
            asyncio.create_task(_loop())
            asyncio.create_task(_worker_heartbeat_loop())

        @api.post("/switch")
        async def switch_char(key: str = "", char: str = "", slot: int = 0,
                              token: str = ""):
            if _authorize(key, token) is False:
                return JSONResponse(status_code=403, content={"error": "token required"})
            if not char:
                return {"error": "char required"}
            if slot < 0 or slot >= len(outer.slots):
                return {"error": "slot out of range"}
            t0 = time.time()
            target = outer.slots[slot]
            ok = outer._switch(target, char)
            return {"ok": ok, "char": target.char, "slot": target.index,
                    "switch_s": round(time.time() - t0, 3)}

        @api.websocket("/audio")
        async def audio_ws(ws: WebSocket, key: str = "", session: str = "", token: str = ""):
            control = _authorize(key, token)
            if control is False:
                await ws.close(code=4403)
                return
            # Transition support: builds before v1.27 don't send the session id.
            # 只在單槽（N=1，改造前唯一情境）時保留這個相容路徑——多槽是這輪新加的能力，
            # 舊版客戶端從沒遇過多槽伺服器，不需要在 N>1 時猜哪一槽。
            if not session and len(outer.slots) == 1 and outer.slots[0].active_session:
                session = outer.slots[0].active_session
            slot = outer.pool.slot_for_session(session) if session else None
            if slot is None:
                await ws.close(code=4409, reason="invalid avatar session")
                return
            expected = _session_control.get(session)
            if expected and (not control or control.get("call_id") != expected.get("call_id")):
                await ws.close(code=4403, reason="call token mismatch")
                return
            await ws.accept()
            print("[audio] connected session=" + session[:8] + " slot" + str(slot.index), flush=True)
            try:
                while True:
                    msg = await ws.receive()
                    if msg.get("bytes") is not None:
                        slot.feeder.push24k(msg["bytes"])
                    elif msg.get("text") == "reset":
                        slot.feeder.reset()
                    elif msg.get("text") == "finish":
                        slot.feeder.finish()
                    elif msg.get("type") == "websocket.disconnect":
                        break
            except WebSocketDisconnect:
                pass
            print("[audio] closed session=" + session[:8] + " slot" + str(slot.index), flush=True)

        return api


if __name__ == "__main__":
    import uvicorn
    fh = FlashHead()
    fh.load()
    fh.wake()
    app = fh.web()
    print("[main] serving on 0.0.0.0:" + str(PORT) + " slots=" + str(N_SLOTS), flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
