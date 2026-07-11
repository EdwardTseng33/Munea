# -*- coding: utf-8 -*-
"""沐寧 · FlashHead 通話服務 · 獨立版（RunPod / Glows / 任何有 4090 的機器直接跑）

2026-07-11 主蘇菲：從 flashhead_modal_dev.py 拆出 Modal 包裝的移植版——
引擎邏輯（Feeder / FrameSink / AudioOutBuffer / 臉聲同線雙軌 / 換角色互斥鎖 /
看門狗 / 量測儀表）一行不動照搬，只把 modal.App/@app.cls/@modal.enter/@modal.asgi_app
換成「開機直接 load → uvicorn 常駐」。

跑法（機器上要先照 runpod_install.sh / glows_install2.sh 裝好）：
  MUNEA_APP_KEY=<通行碼> python3.12 flashhead_server.py          # 門牌 8188
  （RunPod: https://<podId>-8188.proxy.runpod.net 就是對外 https 入口，WS 同線）

模式：eager（不開 torch.compile）——2026-07-11 Glows TW 4090 實測 eager 每塊
p50 305ms / p95 309ms（預算 960ms、餘裕 67.8%），且開機 5 秒內；compile 只快
60ms 但每次開機要多付 ~2 分鐘熱身稅，4090 上不划算（台灣機碼錶數據見協作看板）。
"""
import asyncio
import collections
import os
import sys
import threading
import time
from fractions import Fraction

import numpy as np

sys.path.insert(0, "/root/SoulX-FlashHead")
os.chdir("/root/SoulX-FlashHead")

import torch

# 模式開關（2026-07-11 Edward 真機驗收抓到：實戰載客時 eager 每塊 0.68s、餘裕僅 27%、畫面斷糧 468 次＝嘴定格。
# 常駐機開機稅只付一次 → 渦輪(compile)划算：MUNEA_FH_COMPILE=1 開、熱身約 2 分鐘、穩態快 ~20%）
import flash_head.src.pipeline.flash_head_pipeline as _fhp_mod
_COMPILE = os.environ.get("MUNEA_FH_COMPILE", "0") == "1"
_fhp_mod.COMPILE_MODEL = _COMPILE
_fhp_mod.COMPILE_VAE = _COMPILE

from flash_head.inference import (get_audio_embedding, get_base_data,
                                  get_infer_params, get_pipeline, run_pipeline)

CHAR_SRC = {
    "a05": "/root/char-a05B.png",
    "a06": "/root/char-a06B.png",
}
DEFAULT_CHAR = "a05"
CKPT_DIR = "/models/soulx-flashhead-1.3b"
WAV2VEC_DIR = "/models/wav2vec2-base-960h"

SR_IN, SR_ENG = 24000, 16000
AUDIO_PREBUFFER_S = 0.3   # 止血方案(a)：開口前先墊 0.3s 緩衝（4090 餘裕大、保留當保險）
PORT = int(os.environ.get("MUNEA_FACE_PORT", "8188"))


class FlashHead:
    """跟 Modal 版同名同構——load() 一次、wake() 一次、web() 產出 FastAPI app。"""

    def load(self):
        t0 = time.time()
        self._get_base_data = get_base_data
        self._get_audio_embedding = get_audio_embedding
        self._run_pipeline = run_pipeline

        self.pipeline = get_pipeline(world_size=1, ckpt_dir=CKPT_DIR,
                                     wav2vec_dir=WAV2VEC_DIR, model_type="lite")
        t1 = time.time()

        self.char = DEFAULT_CHAR
        get_base_data(self.pipeline, cond_image_path_or_dir=CHAR_SRC[self.char],
                      base_seed=42, use_face_crop=False)
        t2 = time.time()

        ip = get_infer_params()
        self.sample_rate = ip["sample_rate"]
        self.tgt_fps = ip["tgt_fps"]
        self.frame_num = ip["frame_num"]
        self.motion_frames_num = ip["motion_frames_num"]
        self.slice_len = self.frame_num - self.motion_frames_num
        self.cached_audio_duration = ip["cached_audio_duration"]
        self.chunk_samples = self.slice_len * self.sample_rate // self.tgt_fps
        self.audio_end_idx = self.cached_audio_duration * self.tgt_fps
        self.audio_start_idx = self.audio_end_idx - self.frame_num
        cached_len_sum = self.sample_rate * self.cached_audio_duration
        self.audio_dq = collections.deque([0.0] * cached_len_sum, maxlen=cached_len_sum)
        self.char_lock = threading.Lock()

        class FrameSink:
            """穩定播放佇列（照抄 Modal 版 7/11 卡西法重寫：純 FIFO ＋ 塞車才修剪）。"""
            def __init__(self, tgt_fps):
                self.tgt_fps = tgt_fps
                self.target_depth = max(1, int(round(tgt_fps * 1.5)))
                self.max_depth = max(self.target_depth + 1, int(round(tgt_fps * 2.0)))
                self.q = collections.deque(maxlen=int(round(tgt_fps * 12)))
                self.count = 0
                self.lock = threading.Lock()
                self.last_pop_latency_ms = None
                self.underrun_count = 0
            def push_many(self, frames, chunk_gen_ts, tgt_fps):
                with self.lock:
                    n = frames.shape[0]
                    for i in range(n):
                        self.q.append(frames[i])
                        self.count += 1
                    if len(self.q) > self.max_depth:
                        drop_n = len(self.q) - self.target_depth
                        for _ in range(drop_n):
                            self.q.popleft()
            def pop(self):
                with self.lock:
                    depth = len(self.q)
                    self.last_pop_latency_ms = round(depth / self.tgt_fps * 1000, 1)
                    if not self.q:
                        self.underrun_count += 1
                        return None
                    return self.q.popleft()
            def clear(self):
                with self.lock:
                    self.q.clear()

        self.sink = FrameSink(self.tgt_fps)
        self.SYNC_BUFFER_MS = 350
        self.last_gen_compute_ms = None

        warm_times = []
        for _ in range(2):
            silence = np.zeros(self.chunk_samples, dtype=np.float32)
            tw0 = time.time()
            self.audio_dq.extend(silence.tolist())
            arr = np.array(self.audio_dq)
            emb = get_audio_embedding(self.pipeline, arr, self.audio_start_idx, self.audio_end_idx)
            video = run_pipeline(self.pipeline, emb)
            torch.cuda.synchronize()
            warm_times.append(round(time.time() - tw0, 2))
        t3 = time.time()

        self.load_report = {
            "pipeline_load_s": round(t1 - t0, 1),
            "base_data_s": round(t2 - t1, 2),
            "warm_chunk_s": warm_times,
            "total_load_s": round(t3 - t0, 1),
            "chunk_samples": self.chunk_samples,
            "slice_len_frames": self.slice_len,
            "chunk_budget_ms": round(self.slice_len / self.tgt_fps * 1000, 1),
            "host": "standalone-" + os.uname().nodename,
        }
        print("[load]", self.load_report, flush=True)

    def wake(self):
        import aiortc.codecs.h264 as _h264
        _h264.MIN_BITRATE = 3_000_000
        _h264.DEFAULT_BITRATE = 8_000_000
        _h264.MAX_BITRATE = 12_000_000

        self.wake_ts = time.time()

        import cv2

        def _load_poster(path):
            p = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
            return cv2.resize(p, (512, 512))

        self._load_poster = _load_poster
        self.poster = _load_poster(CHAR_SRC[self.char])
        self.pcs = set()
        self.pc_created = {}
        outer = self

        get_audio_embedding_ = self._get_audio_embedding
        run_pipeline_ = self._run_pipeline
        sink = self.sink

        outer.round_count = 0
        outer.round_start_ts = 0.0
        outer.round_latencies = collections.deque(maxlen=20)
        outer.last_gen_compute_ms = None
        outer.gen_compute_ms_hist = collections.deque(maxlen=100)

        class AudioOutBuffer:
            """語音出線緩衝（照抄 Modal 版：20ms 幀、underrun 儀表、0.3s 暖身墊窗）。"""
            def __init__(self, sample_rate):
                self.sample_rate = sample_rate
                self.frame_samples = int(sample_rate * 0.02)
                self.lock = threading.Lock()
                self.buf = np.zeros(0, dtype=np.int16)
                self.underrun_count = 0
                self.underrun_gap_ms = collections.deque(maxlen=50)
                self.last_push_ts = 0.0
                self.depth_samples = 0
                self.hold_until_ts = time.time() + AUDIO_PREBUFFER_S
            def push(self, pcm_int16):
                with self.lock:
                    self.buf = np.concatenate([self.buf, pcm_int16])
                    self.last_push_ts = time.time()
                    self.depth_samples = len(self.buf)
            def clear(self):
                with self.lock:
                    self.buf = np.zeros(0, dtype=np.int16)
                    self.depth_samples = 0
                    self.hold_until_ts = time.time() + AUDIO_PREBUFFER_S
            def pop_frame(self):
                with self.lock:
                    if time.time() < self.hold_until_ts:
                        return np.zeros(self.frame_samples, dtype=np.int16)
                    if len(self.buf) >= self.frame_samples:
                        chunk = self.buf[:self.frame_samples]
                        self.buf = self.buf[self.frame_samples:]
                        self.depth_samples = len(self.buf)
                        return chunk
                    self.underrun_count += 1
                    if self.last_push_ts:
                        self.underrun_gap_ms.append(round((time.time() - self.last_push_ts) * 1000, 1))
                    self.depth_samples = len(self.buf)
                    return np.zeros(self.frame_samples, dtype=np.int16)

        outer.audio_out = AudioOutBuffer(SR_ENG)

        class Feeder:
            def __init__(self):
                self.lock = threading.Lock()
                self.acc = np.zeros(0, dtype=np.float32)
                self.consumed = 0
                self.t0 = None
                self.last_in = 0.0
                self._idle_due = 0.0
                self._idle_on = False
                self._round_pending = False
                # 2026-07-11 A案小刀1：世代號——每次 reset() +1。GPU 上跑到一半的舊塊
                # 完成時比對世代號，變了就整塊丟棄，不讓上一輪聲畫漏進新一輪
                # （治「掛斷重撥她一接通就繼續講上一段」「插話後又冒半句舊話」）。
                self._epoch = 0
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
                    if self.t0 is None or (now - self.last_in) > 0.8:
                        # 2026-07-11 A案小刀2：0.8s 到貨空窗只當「新一輪開口」計數＋重錨節奏鐘，
                        # 不再清 self.acc——舊碼在這裡把已到貨還沒消化的話整包丟掉＝「話講一半
                        # 跳掉／吃字」（語音腦是爆發式到貨，中途卡 0.8s 是常態）。已到貨的真話
                        # 一律留著讓 _loop 照節奏消化完；真正的 turn 邊界只認 ws "reset" 明確訊號。
                        # 節奏鐘重錨（t0/consumed 歸位）＝殘餘舊音從現在起接著新音連續放行，一格不丟。
                        self.t0 = now
                        self.consumed = 0
                        outer.round_count += 1
                        outer.round_start_ts = now
                        self._round_pending = True
                        print("[round] #" + str(outer.round_count) + " start (acc keep "
                              + str(len(self.acc)) + " samples)", flush=True)
                    self.acc = np.concatenate([self.acc, xq])
                    self.last_in = now

            def reset(self):
                with self.lock:
                    self.acc = np.zeros(0, dtype=np.float32)
                    self.t0 = None
                    self.consumed = 0
                    # 2026-07-11 A案小刀1：世代號 +1——在 GPU 上跑到一半的舊塊，跑完後
                    # 看到世代變了就自己丟棄（見 _gen_chunk 尾端比對），舊聲畫進不了新佇列。
                    self._epoch += 1
                    # 2026-07-11 A案小刀1：8 秒聲音記憶窗整個歸零重填（官方每輪 run 開始
                    # audio_dq 就是全零起步）。舊碼留著上一輪最後 0.36s 音尾，新一輪第一塊
                    # 的嘴型會被舊語音牽著走＝「下一輪開頭嘴亂動／像在接上一段」。
                    outer.audio_dq.extend([0.0] * outer.audio_dq.maxlen)
                sink.clear()
                outer.audio_out.clear()
                print("[feeder] reset(turn boundary) epoch=" + str(self._epoch), flush=True)

            def _gen_chunk(self, chunk_16k):
                t_chunk_ready = time.time()
                # 2026-07-11 A案小刀1：開跑前先記下世代號——跟 audio_dq 進料包在同一把鎖裡，
                # 這樣「reset 歸零記憶窗」和「這塊進料」一定分出先後：reset 在後＝整窗連這塊
                # 一起被歸零（塊尾端也會被丟）；reset 在前＝這塊帶新世代號正常走。
                with self.lock:
                    chunk_epoch = self._epoch
                    outer.audio_dq.extend(chunk_16k.tolist())
                    arr = np.array(outer.audio_dq)
                emb = get_audio_embedding_(outer.pipeline, arr, outer.audio_start_idx, outer.audio_end_idx)
                with outer.char_lock:
                    video = run_pipeline_(outer.pipeline, emb)
                video = video[outer.motion_frames_num:]
                frames = video.cpu().numpy().astype(np.uint8)
                t_frames_ready = time.time()
                outer.last_gen_compute_ms = round((t_frames_ready - t_chunk_ready) * 1000, 1)
                outer.gen_compute_ms_hist.append(outer.last_gen_compute_ms)
                # 2026-07-11 A案小刀1：入佇列前比對世代號——reset 期間在 GPU 上跑完的舊塊
                # 整塊丟棄（畫面＋聲音都不推），0.96s 舊聲畫再也污染不了剛清空的新一輪
                # （治「掛斷重撥繼續講上一段」「插話後她又冒出半句舊話」）。
                with self.lock:
                    if self._epoch != chunk_epoch:
                        print("[feeder] stale chunk dropped (epoch " + str(chunk_epoch)
                              + " -> " + str(self._epoch) + ")", flush=True)
                        return
                sink.push_many(frames, t_frames_ready, outer.tgt_fps)
                pcm16 = np.clip(chunk_16k * 32768.0, -32768, 32767).astype(np.int16)
                outer.audio_out.push(pcm16)
                if self._round_pending:
                    self._round_pending = False
                    lat_ms = round((t_frames_ready - outer.round_start_ts) * 1000, 1)
                    outer.round_latencies.append(lat_ms)
                    print("[round] #" + str(outer.round_count) + " first-frame-latency " + str(lat_ms) + "ms", flush=True)

            def _loop(self):
                cs = outer.chunk_samples
                while True:
                    todo = None
                    with self.lock:
                        if len(self.acc) >= cs and self.t0 is not None:
                            due = self.t0 + self.consumed / SR_ENG
                            if time.time() >= due:
                                todo = self.acc[:cs].copy()
                                self.acc = self.acc[cs:]
                                self.consumed += cs
                    if todo is not None:
                        if self._idle_on:
                            self._idle_on = False
                            sink.clear()
                            print("[feeder] real audio arrived, stop idle feed", flush=True)
                        self._gen_chunk(todo)
                        continue
                    now = time.time()
                    with self.lock:
                        real_silent = (now - self.last_in) > 1.0
                    has_conn = any(pc.connectionState in ("new", "connecting", "connected")
                                  for pc in outer.pcs)
                    if has_conn and real_silent and now >= self._idle_due:
                        if not self._idle_on:
                            self._idle_on = True
                            print("[feeder] real silence, connection alive, start idle feed", flush=True)
                        self._gen_chunk(np.zeros(cs, dtype=np.float32))
                        self._idle_due = now + cs / SR_ENG
                    else:
                        time.sleep(0.02)

        self.feeder = Feeder()
        print("[wake] feeder ready, audio+video co-release, call components ready", flush=True)

    def _switch(self, char):
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
                self._get_base_data(self.pipeline, cond_image_path_or_dir=CHAR_SRC[char],
                                    base_seed=42, use_face_crop=False)
                self.char = char
                self.poster = self._load_poster(CHAR_SRC[char])
                print(f"[char] {prev} -> {char} ok", flush=True)
                return True
            except Exception as e:
                print(f"[char] {char} switch failed ({e}) -> revert {prev}", flush=True)
                try:
                    self._get_base_data(self.pipeline, cond_image_path_or_dir=CHAR_SRC[prev],
                                        base_seed=42, use_face_crop=False)
                    self.char = prev
                except Exception:
                    pass
                return False

    def web(self):
        from aiortc import (MediaStreamError, MediaStreamTrack, RTCConfiguration, RTCIceServer,
                            RTCPeerConnection, RTCSessionDescription, VideoStreamTrack)
        from aiortc.mediastreams import VIDEO_CLOCK_RATE, VIDEO_TIME_BASE
        from av import AudioFrame, VideoFrame
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware

        api = FastAPI()
        api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        outer = self

        _gate = os.environ.get("MUNEA_APP_KEY", "").strip()

        def _pass(request_key):
            return (not _gate) or (request_key == _gate)

        class FlashHeadTrack(VideoStreamTrack):
            kind = "video"
            def __init__(self):
                super().__init__()
                self.last = outer.poster
                self._active_ts = 0.0
                self._ptime = 1.0 / outer.tgt_fps
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
                fr = outer.sink.pop()
                now = time.time()
                if fr is not None:
                    self.last = fr
                    self._active_ts = now
                elif self._active_ts and (now - self._active_ts) > 0.35:
                    self.last = outer.poster
                    self._active_ts = 0.0
                vf = VideoFrame.from_ndarray(self.last, format="rgb24")
                vf.pts = pts
                vf.time_base = tb
                return vf

        class FlashHeadAudioTrack(MediaStreamTrack):
            kind = "audio"
            def __init__(self):
                super().__init__()
                self._next_pts = 0
                self._started = None
            async def recv(self):
                sr = outer.audio_out.sample_rate
                if self._started is None:
                    self._started = time.time()
                target_t = self._started + self._next_pts / sr
                now = time.time()
                if target_t > now:
                    await asyncio.sleep(target_t - now)
                chunk = outer.audio_out.pop_frame()
                frame = AudioFrame(format="s16", layout="mono", samples=len(chunk))
                frame.sample_rate = sr
                frame.pts = self._next_pts
                frame.time_base = Fraction(1, sr)
                frame.planes[0].update(chunk.astype("<i2").tobytes())
                self._next_pts += len(chunk)
                return frame

        @api.get("/health")
        def health(key: str = ""):
            if not _pass(key):
                return {"ok": False, "error": "key required"}
            import statistics as _stats
            budget_ms = round(outer.slice_len / outer.tgt_fps * 1000, 1)
            hist = list(outer.gen_compute_ms_hist)
            gen_p50 = round(_stats.median(hist), 1) if hist else None
            gen_p95 = None
            if hist:
                srt = sorted(hist)
                gen_p95 = round(srt[max(0, int(len(srt) * 0.95) - 1)], 1)
            ao = outer.audio_out
            return {"ok": True, "engine": "flashhead-lite-standalone", "char": outer.char,
                    "frames": outer.sink.count, "load": outer.load_report,
                    "round_count": outer.round_count,
                    "round_latencies_ms": list(outer.round_latencies),
                    "uptime_s": round(time.time() - getattr(outer, "wake_ts", time.time()), 1),
                    "sink_depth": len(outer.sink.q),
                    "latency_ms": {
                        "gen_compute_B": outer.last_gen_compute_ms,
                        "sink_pop_C": outer.sink.last_pop_latency_ms,
                        "chunk_budget_ms": budget_ms,
                        "sync_buffer_reserved_ms": outer.SYNC_BUFFER_MS,
                    },
                    "gen_compute_ms_rolling": {
                        "p50": gen_p50, "p95": gen_p95, "budget_ms": budget_ms,
                        "n_samples": len(hist), "headroom_p95_pct":
                            (round((1 - gen_p95 / budget_ms) * 100, 1) if gen_p95 else None),
                    },
                    "audio_underrun": {
                        "count": ao.underrun_count,
                        "recent_gap_ms": list(ao.underrun_gap_ms)[-10:],
                        "buffer_depth_ms": round(ao.depth_samples / ao.sample_rate * 1000, 1),
                        "prebuffer_s": AUDIO_PREBUFFER_S,
                    },
                    "video_underrun": {
                        "count": outer.sink.underrun_count,
                    }}

        @api.post("/diag")
        async def diag(payload: dict, key: str = ""):
            if not _pass(key):
                return {"error": "key required"}
            import json as _json
            uptime_s = round(time.time() - getattr(outer, "wake_ts", time.time()), 1)
            body = _json.dumps(payload, ensure_ascii=False, default=str)
            if len(body) > 12000:
                body = body[:12000] + "...(truncated)"
            print("=" * 70, flush=True)
            print("[DIAG] client-reported connection diagnostic  server_uptime_s=" + str(uptime_s)
                  + " round_count=" + str(outer.round_count), flush=True)
            print("[DIAG] " + body, flush=True)
            print("=" * 70, flush=True)
            return {"ok": True, "received": True, "server_uptime_s": uptime_s}

        @api.post("/offer")
        async def offer(payload: dict, key: str = "", char: str = ""):
            if not _pass(key):
                return {"error": "key required"}
            if char and not outer._switch(char):
                return {"error": "char not supported"}
            # 2026-07-11 主蘇菲：新通話開線＝把上一通的殘留全部倒掉（音頻緩衝+畫格佇列+進料狀態）。
            # 不倒＝Edward 實測「掛斷再撥、她一接通就繼續播上一段的話」——殘留聲音直接漏進新通話。
            try:
                outer.feeder.reset()
            except Exception as _e:
                print(f"[offer] pre-call reset failed: {_e}", flush=True)
            pc = RTCPeerConnection(RTCConfiguration(iceServers=[
                RTCIceServer(urls="stun:stun.l.google.com:19302"),
                RTCIceServer(urls=["turn:34.81.102.52:3478?transport=udp", "turn:34.81.102.52:3478?transport=tcp"],
                             username="muneaturn", credential="munea-turn-a7k2q"),
            ]))
            outer.pcs.add(pc)
            outer.pc_created[id(pc)] = time.time()

            pc_tag = str(id(pc))[-5:]

            @pc.on("connectionstatechange")
            async def _on_conn_state_change():
                age_s = round(time.time() - outer.pc_created.get(id(pc), time.time()), 1)
                print(f"[offer] pc#{pc_tag} -> {pc.connectionState} (age {age_s}s)", flush=True)
                if pc.connectionState in ("closed", "failed"):
                    outer.pcs.discard(pc)
                    outer.pc_created.pop(id(pc), None)

            pc.addTrack(FlashHeadTrack())
            pc.addTrack(FlashHeadAudioTrack())
            await pc.setRemoteDescription(RTCSessionDescription(sdp=payload["sdp"], type=payload["type"]))
            ans = await pc.createAnswer()
            await pc.setLocalDescription(ans)
            for _ in range(60):
                if pc.iceGatheringState == "complete":
                    break
                await asyncio.sleep(0.05)
            return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

        @api.on_event("startup")
        async def _start_watchdog():
            async def _loop():
                while True:
                    await asyncio.sleep(10)
                    now = time.time()
                    stale = [p for p in list(outer.pcs)
                             if p.connectionState != "connected"
                             and now - outer.pc_created.get(id(p), now) > 30]
                    for p in stale:
                        print(f"[watchdog] closing stale pc state={p.connectionState}", flush=True)
                        try:
                            await p.close()
                        except Exception as e:
                            print(f"[watchdog] close err {e}", flush=True)
                        outer.pcs.discard(p)
                        outer.pc_created.pop(id(p), None)
            asyncio.create_task(_loop())

        @api.post("/switch")
        async def switch_char(key: str = "", char: str = ""):
            if not _pass(key):
                return {"error": "key required"}
            if not char:
                return {"error": "char required"}
            t0 = time.time()
            ok = outer._switch(char)
            return {"ok": ok, "char": outer.char, "switch_s": round(time.time() - t0, 3)}

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


if __name__ == "__main__":
    import uvicorn
    fh = FlashHead()
    fh.load()
    fh.wake()
    app = fh.web()
    print(f"[main] serving on 0.0.0.0:{PORT}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
