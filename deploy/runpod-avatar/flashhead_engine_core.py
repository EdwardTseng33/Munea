# -*- coding: utf-8 -*-
"""Munea FlashHead call engine core (N-slot version, 2026-07-12 Calcifer).

Implements docs/多人併發容量架構-2026-07-12.md section 3.1: split the original
single global instance into an N-slot array. Each slot owns its own pipeline,
feeder, FrameSink, AudioOutBuffer and character state. This file holds the
reusable pieces: Slot / FrameSink / AudioOutBuffer / Feeder / SlotPool.

Design choice: this file has ZERO heavy dependencies (no torch / fastapi /
aiortc / cv2 imports at module scope -- only stdlib + numpy). That means it
can be unit tested on a dev machine with no GPU and no service stack
installed (see scripts/test_flashhead_multislot.py, which drives it with
fake pipeline functions). Everything that actually touches the GPU
(get_pipeline / get_audio_embedding / run_pipeline) is dependency-injected
from the caller (flashhead_server.py); this module never imports those.

DEPLOY NOTE (important): flashhead_server.py now imports from this module.
When copying files to GLOWS/RunPod, ship BOTH files together -- shipping
only flashhead_server.py will ImportError at boot. deploy/glows/README.md
and deploy/runpod-avatar/README.md have been updated with this reminder.

MUNEA_FH_SLOTS compatibility rule: when the env var is unset (or set to 1),
behavior must match the pre-refactor single-instance server byte-for-byte --
every field name, the 429 logic, reset timing, and the stale-pc self-heal
check are ported line-by-line from the original single-instance
flashhead_server.py, not rewritten from scratch.
"""
import collections
import threading
import time

import numpy as np


SUPPORTED_FRAME_SIZES = (512, 640, 768)


def parse_frame_size(value):
    """Validate the square model frame size before any GPU work starts."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        raise ValueError("MUNEA_FH_FRAME_SIZE must be an integer")
    if size not in SUPPORTED_FRAME_SIZES or size % 32:
        raise ValueError("MUNEA_FH_FRAME_SIZE must be one of 512, 640, 768")
    return size


# ---------------------------------------------------------------------------
# FrameSink / AudioOutBuffer -- copied verbatim from the single-instance file
# (old flashhead_server.py lines 94-223). Logic untouched, only relocated;
# each Slot owns one instance so they can never cross-talk.
# ---------------------------------------------------------------------------
class FrameSink:
    """Stable playback queue (pure FIFO, trimmed only when backed up)."""
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

    def depth(self):
        with self.lock:
            return len(self.q)


class AudioOutBuffer:
    """語音出線緩衝（20ms 幀、underrun 儀表、首批資料到達後預緩衝）。

    prebuffer_s 從建構子傳入（原本是模組層級常數 AUDIO_PREBUFFER_S=0.5）——
    第一批資料尚未到達前維持 hold；資料到達後才開始倒數，讓這段時間真的
    累積成播放存貨，而不是把模型生成時間誤算成預緩衝。
    """
    def __init__(self, sample_rate, prebuffer_s=0.5):
        self.sample_rate = sample_rate
        self.prebuffer_s = prebuffer_s
        self.default_prebuffer_s = prebuffer_s
        self.next_prebuffer_s = prebuffer_s
        self.last_prebuffer_s = prebuffer_s
        self.frame_samples = int(sample_rate * 0.02)
        self.lock = threading.Lock()
        self.buf = np.zeros(0, dtype=np.int16)
        self.underrun_count = 0
        self.underrun_gap_ms = collections.deque(maxlen=50)
        self.last_push_ts = 0.0
        self.depth_samples = 0
        self.hold_until_ts = float("inf")
        self._awaiting_first_push = True
        self.playout_generation = 0

    def push(self, pcm_int16):
        with self.lock:
            if len(pcm_int16) and self._awaiting_first_push:
                delay = self.next_prebuffer_s
                self.last_prebuffer_s = delay
                self.next_prebuffer_s = self.default_prebuffer_s
                self.hold_until_ts = time.time() + delay
                self._awaiting_first_push = False
                self.playout_generation += 1
            self.buf = np.concatenate([self.buf, pcm_int16])
            self.last_push_ts = time.time()
            self.depth_samples = len(self.buf)

    def clear(self):
        with self.lock:
            self.buf = np.zeros(0, dtype=np.int16)
            self.depth_samples = 0
            self.hold_until_ts = float("inf")
            self._awaiting_first_push = True
            self.next_prebuffer_s = self.default_prebuffer_s

    def arm_prebuffer(self, seconds):
        """Use a one-shot playout delay for the next PCM turn only."""
        with self.lock:
            self.next_prebuffer_s = max(0.0, float(seconds))

    def playout_held(self):
        """True while audio and video must stay on their shared start gate."""
        with self.lock:
            return time.time() < self.hold_until_ts

    def playout_marker(self):
        """Return the current turn id and its shared A/V release timestamp."""
        with self.lock:
            return self.playout_generation, self.hold_until_ts

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


# ---------------------------------------------------------------------------
# Slot —— 取代舊版全域單例的「outer」角色。每個 Slot 各自持有一份 pipeline、
# feeder、sink、audio_out、角色狀態；串線隔離＝「每個 session 綁定唯一一個
# Slot 物件」天生成立，不必額外寫路由表去對映哪路音頻該去哪裡（3.2 節測項 3）。
# ---------------------------------------------------------------------------
class Slot:
    def __init__(self, index):
        self.index = index
        # ---- load() 階段填（GPU 重活：pipeline 實例、底圖註冊）----
        self.pipeline = None
        self.char = None
        self.char_lock = threading.Lock()
        self.sample_rate = None
        self.tgt_fps = None
        self.frame_num = None
        self.motion_frames_num = None
        self.slice_len = None
        self.cached_audio_duration = None
        self.chunk_samples = None
        self.audio_end_idx = None
        self.audio_start_idx = None
        self.audio_dq = None
        self.frame_height = None
        self.frame_width = None
        self.load_report = {}
        # ---- wake() 階段填（每次容器/程序甦醒都跑）----
        self.poster = None
        self.pcs = set()
        self.pc_created = {}
        self.sink = None
        self.audio_out = None
        self.feeder = None
        self.SYNC_BUFFER_MS = 350
        self.round_count = 0
        self.round_start_ts = 0.0
        self.round_latencies = collections.deque(maxlen=20)
        self.last_gen_compute_ms = None
        self.gen_compute_ms_hist = collections.deque(maxlen=100)
        # ---- 准入/佔用（SlotPool 管）----
        self.active_session = None
        self.active_pc = None
        self.active_created = 0.0
        # ---- 故障隔離（2026-07-12 新補，對應設計文件 3.2 節測項 5）----
        self.healthy = True
        self.fault_count = 0
        self.last_fault = None


def switch_slot_char(slot, char, char_src_map, get_base_data_fn, load_poster_fn):
    """換角色，鎖只綁該 slot（不像舊版全域鎖）——這正是「串線隔離」的一部分：
    切換 A 槽的角色，B 槽完全不受影響（連鎖都不用鎖，因為狀態物件本來就分開）。
    純函式、可注入假的 get_base_data_fn/load_poster_fn 單元測試，不需要真 GPU。
    """
    if not char or char == slot.char:
        return True
    if char not in char_src_map:
        return False
    with slot.char_lock:
        if char == slot.char:
            return True
        prev = slot.char
        try:
            if slot.feeder is not None:
                slot.feeder.reset()
            get_base_data_fn(slot.pipeline, cond_image_path_or_dir=char_src_map[char],
                              base_seed=42, use_face_crop=False)
            slot.char = char
            slot.poster = load_poster_fn(char_src_map[char])
            return True
        except Exception:
            try:
                get_base_data_fn(slot.pipeline, cond_image_path_or_dir=char_src_map[prev],
                                  base_seed=42, use_face_crop=False)
                slot.char = prev
            except Exception:
                pass
            return False


# ---------------------------------------------------------------------------
# Feeder —— 逐行照抄單例版的節奏/緩衝/世代號邏輯（那些是踩過真機雷才調出來的
# 參數，這裡刻意不改動任何門檻值），差別只有兩點：
#   1. 原本閉包捕捉的 outer 換成建構子傳入的 slot（狀態隔離）
#   2. get_audio_embedding / run_pipeline 兩支 GPU 函式改依賴注入（可塞假函式測試）
# 加了故障隔離：_gen_chunk 抓例外，不再讓一路的 pipeline 炸裂悄悄弄壞資料或
# 讓那條線悶不吭聲空轉——連續故障超過門檻標 unhealthy 並呼叫 on_unhealthy。
# ---------------------------------------------------------------------------
class Feeder:
    def __init__(self, slot, get_audio_embedding, run_pipeline, sr_in=24000, sr_eng=16000,
                 max_ahead_s=1.5, sharpen=False, fault_streak_limit=3, on_unhealthy=None,
                 auto_start=True):
        self.slot = slot
        self.get_audio_embedding = get_audio_embedding
        self.run_pipeline = run_pipeline
        self.sr_in = sr_in
        self.sr_eng = sr_eng
        self.max_ahead_s = max_ahead_s
        self.sharpen = sharpen
        self.fault_streak_limit = fault_streak_limit
        self.on_unhealthy = on_unhealthy

        self.lock = threading.Lock()
        self.acc = np.zeros(0, dtype=np.float32)
        # The lip-sync model consumes 16 kHz audio, but listeners should hear
        # Gemini's original 24 kHz stream. Keep both buffers aligned so model
        # resampling never becomes the audible output path.
        self.acc_out = np.zeros(0, dtype=np.float32)
        self.consumed = 0
        self.t0 = None
        self.last_in = 0.0
        self._idle_due = 0.0
        self._idle_on = False
        self._round_pending = False
        self._finish_pending = False
        # 世代號——每次 reset() +1。GPU 上跑到一半的舊塊完成時比對世代號，
        # 變了就整塊丟棄，不讓上一輪聲畫漏進新一輪（治「掛斷重撥她一接通就
        # 繼續講上一段」「插話後又冒半句舊話」）。
        self._epoch = 0
        self._fault_streak = 0

        if auto_start:
            threading.Thread(target=self._loop, daemon=True).start()

    def push24k(self, pcm_bytes):
        x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        n_out = int(len(x) * self.sr_eng / self.sr_in)
        if n_out <= 0:
            return
        xq = np.interp(np.linspace(0, 1, n_out, endpoint=False),
                        np.linspace(0, 1, len(x), endpoint=False), x).astype(np.float32)
        with self.lock:
            now = time.time()
            if self.t0 is None or (now - self.last_in) > 0.8:
                self.t0 = now
                self.consumed = 0
                self.slot.round_count += 1
                self.slot.round_start_ts = now
                self._round_pending = True
                print("[round] slot" + str(self.slot.index) + " #" + str(self.slot.round_count)
                      + " start (acc keep " + str(len(self.acc)) + " samples)", flush=True)
            self.acc = np.concatenate([self.acc, xq])
            self.acc_out = np.concatenate([self.acc_out, x])
            self.last_in = now

    def reset(self):
        with self.lock:
            self.acc = np.zeros(0, dtype=np.float32)
            self.acc_out = np.zeros(0, dtype=np.float32)
            self.t0 = None
            self.consumed = 0
            self._epoch += 1
            self._finish_pending = False
            if self.slot.audio_dq is not None:
                self.slot.audio_dq.extend([0.0] * self.slot.audio_dq.maxlen)
        if self.slot.sink is not None:
            self.slot.sink.clear()
        if self.slot.audio_out is not None:
            self.slot.audio_out.clear()
        print("[feeder] slot" + str(self.slot.index) + " reset(turn boundary) epoch="
              + str(self._epoch), flush=True)

    def finish(self):
        with self.lock:
            self._finish_pending = bool(len(self.acc))
            partial_samples = len(self.acc)
        if self._finish_pending:
            print("[feeder] slot" + str(self.slot.index) + " finish requested partial_samples="
                  + str(partial_samples), flush=True)

    def _on_fault(self, exc):
        self._fault_streak += 1
        self.slot.fault_count += 1
        self.slot.last_fault = repr(exc)
        print("[feeder] slot" + str(self.slot.index) + " gen_chunk error (" + repr(exc)
              + ") streak=" + str(self._fault_streak), flush=True)
        if self._fault_streak >= self.fault_streak_limit:
            self.slot.healthy = False
            print("[feeder] slot" + str(self.slot.index) + " marked UNHEALTHY after "
                  + str(self._fault_streak) + " consecutive faults", flush=True)
            if self.on_unhealthy is not None:
                try:
                    self.on_unhealthy(self.slot)
                except Exception as cb_err:
                    print("[feeder] slot" + str(self.slot.index)
                          + " on_unhealthy callback error: " + repr(cb_err), flush=True)

    def _gen_chunk(self, chunk_16k, valid_samples=None, output_pcm=None):
        t_chunk_ready = time.time()
        with self.lock:
            chunk_epoch = self._epoch
            self.slot.audio_dq.extend(chunk_16k.tolist())
            arr = np.array(self.slot.audio_dq)
        try:
            emb = self.get_audio_embedding(self.slot.pipeline, arr,
                                            self.slot.audio_start_idx, self.slot.audio_end_idx)
            with self.slot.char_lock:
                video = self.run_pipeline(self.slot.pipeline, emb)
        except Exception as e:
            # 故障隔離核心：這一路的 pipeline 炸了，不讓例外往上炸穿整個 feeder
            # 執行緒（更不會波及其他槽的 pipeline/thread，本來就是獨立物件）。
            # 這塊音畫直接丟棄，不推進 sink/audio_out（不留半殘資料）。
            self._on_fault(e)
            return
        self._fault_streak = 0
        video = video[self.slot.motion_frames_num:]
        frames = video.cpu().numpy().astype(np.uint8)
        if self.sharpen:
            import cv2 as _cv2
            for _i in range(frames.shape[0]):
                _f = frames[_i]
                _blur = _cv2.GaussianBlur(_f, (0, 0), 1.8)
                frames[_i] = _cv2.addWeighted(_f, 1.5, _blur, -0.5, 0)
        t_frames_ready = time.time()
        self.slot.last_gen_compute_ms = round((t_frames_ready - t_chunk_ready) * 1000, 1)
        self.slot.gen_compute_ms_hist.append(self.slot.last_gen_compute_ms)
        with self.lock:
            if self._epoch != chunk_epoch:
                print("[feeder] slot" + str(self.slot.index) + " stale chunk dropped (epoch "
                      + str(chunk_epoch) + " -> " + str(self._epoch) + ")", flush=True)
                return
        self.slot.sink.push_many(frames, t_frames_ready, self.slot.tgt_fps)
        if valid_samples is None:
            valid_samples = len(chunk_16k)
        if output_pcm is None:
            output_samples = int(round(valid_samples * self.sr_in / self.sr_eng))
            if output_samples > 0 and valid_samples > 0:
                output_pcm = np.interp(
                    np.linspace(0, 1, output_samples, endpoint=False),
                    np.linspace(0, 1, valid_samples, endpoint=False),
                    chunk_16k[:valid_samples],
                ).astype(np.float32)
            else:
                output_pcm = np.zeros(0, dtype=np.float32)
        pcm_out = np.clip(output_pcm * 32768.0, -32768, 32767).astype(np.int16)
        self.slot.audio_out.push(pcm_out)
        if self._round_pending:
            self._round_pending = False
            lat_ms = round((t_frames_ready - self.slot.round_start_ts) * 1000, 1)
            self.slot.round_latencies.append(lat_ms)
            print("[round] slot" + str(self.slot.index) + " #" + str(self.slot.round_count)
                  + " first-frame-latency " + str(lat_ms) + "ms", flush=True)

    def _loop(self):
        cs = self.slot.chunk_samples
        while True:
            todo = None
            with self.lock:
                if len(self.acc) >= cs and self.t0 is not None:
                    ahead_s = self.slot.audio_out.depth_samples / self.slot.audio_out.sample_rate
                    if ahead_s < self.max_ahead_s:
                        output_samples = min(len(self.acc_out), int(round(cs * self.sr_in / self.sr_eng)))
                        todo = (self.acc[:cs].copy(), cs, self.acc_out[:output_samples].copy())
                        self.acc = self.acc[cs:]
                        self.acc_out = self.acc_out[output_samples:]
                        self.consumed += cs
                elif self._finish_pending and 0 < len(self.acc) < cs:
                    valid = len(self.acc)
                    padded = np.zeros(cs, dtype=np.float32)
                    padded[:valid] = self.acc
                    output_samples = min(len(self.acc_out), int(round(valid * self.sr_in / self.sr_eng)))
                    output_pcm = self.acc_out[:output_samples].copy()
                    self.acc = np.zeros(0, dtype=np.float32)
                    self.acc_out = self.acc_out[output_samples:]
                    self._finish_pending = False
                    self.consumed += valid
                    todo = (padded, valid, output_pcm)
            if todo is not None:
                if self._idle_on:
                    self._idle_on = False
                    self.slot.sink.clear()
                    self.slot.audio_out.clear()
                    print("[feeder] slot" + str(self.slot.index)
                          + " real audio arrived, stop idle feed", flush=True)
                self._gen_chunk(todo[0], todo[1], todo[2])
                continue
            now = time.time()
            with self.lock:
                real_silent = ((now - self.last_in) > 1.0 and len(self.acc) < cs
                                and self.slot.audio_out.depth_samples == 0
                                and self.slot.sink.depth() == 0)
            has_conn = any(pc.connectionState in ("new", "connecting", "connected")
                           for pc in self.slot.pcs)
            if has_conn and real_silent and now >= self._idle_due and self.slot.healthy:
                if not self._idle_on:
                    self._idle_on = True
                    print("[feeder] slot" + str(self.slot.index)
                          + " real silence, connection alive, start idle feed", flush=True)
                self._gen_chunk(np.zeros(cs, dtype=np.float32))
                self._idle_due = now + cs / self.sr_eng
            else:
                time.sleep(0.02)


# ---------------------------------------------------------------------------
# SlotPool —— N 槽准入簿：找空槽 / 滿了擋 / 釋放 / stale-pc 自癒回收。
# 純邏輯、不含任何 asyncio/threading 鎖——呼叫端（flashhead_server.py）自己包
# 一層 asyncio.Lock（沿用單例版 admission_lock 的既有模式），這裡才能在完全
# 沒有 asyncio 的本機單元測試裡直接呼叫驗證。
# ---------------------------------------------------------------------------
class SlotPool:
    def __init__(self, slots):
        self.slots = list(slots)

    def limit(self):
        return len(self.slots)

    def active_count(self):
        return sum(1 for s in self.slots if s.active_session is not None)

    def admit(self, session_id, preferred_index=None):
        # Durable Call Control reserves a concrete 1-based slot before the App
        # reaches this worker. Honor that reservation instead of taking any
        # free slot, otherwise the database and GPU could disagree.
        if preferred_index is not None:
            try:
                slot = self.slots[int(preferred_index)]
            except (TypeError, ValueError, IndexError):
                return None
            if slot.healthy and slot.active_session is None:
                return self._claim(slot, session_id)
            pc = slot.active_pc
            if pc is not None and getattr(pc, "connectionState", None) in ("closed", "failed"):
                return self._claim(slot, session_id)
            return None
        # 先找完全空的槽（本機內槽序無關緊要；跨機器的 fullest-first 打包
        # 是 gateway 的活，不是這裡）
        for slot in self.slots:
            if slot.healthy and slot.active_session is None:
                return self._claim(slot, session_id)
        # 找不到空槽 → 找「pc 早就斷了但還沒被 watchdog 釋放」的槽回收
        # （逐行對照單例版 stale-pc 自癒邏輯：pc is None 一律視為忙碌中，
        # 不可回收——這條分支跟舊版 429 判斷完全一致）
        for slot in self.slots:
            if not slot.healthy:
                continue
            pc = slot.active_pc
            if pc is not None and getattr(pc, "connectionState", None) in ("closed", "failed"):
                return self._claim(slot, session_id)
        return None

    def _claim(self, slot, session_id):
        slot.active_session = session_id
        slot.active_pc = None
        slot.active_created = time.time()
        return slot

    def slot_for_session(self, session_id):
        if not session_id:
            return None
        for slot in self.slots:
            if slot.active_session == session_id:
                return slot
        return None

    def release(self, session_id, pc=None):
        slot = self.slot_for_session(session_id)
        if slot is None:
            return None
        if pc is not None and slot.active_pc is not pc:
            return None
        slot.active_session = None
        slot.active_pc = None
        slot.active_created = 0.0
        return slot

    def force_release_slot(self, slot):
        """故障隔離用：slot 被判 unhealthy 時強制清空占用（不管 pc 物件比對）。"""
        slot.active_session = None
        slot.active_pc = None
        slot.active_created = 0.0

    def snapshot(self):
        active = self.active_count()
        limit = self.limit()
        return {"limit": limit, "active": active, "available": active < limit}


# ---------------------------------------------------------------------------
# health_snapshot —— /health 單槽欄位計算，逐行對照單例版原本寫在路由函式裡
# 的算法（median/p95/headroom），搬出來純函式化才能在本機不裝 fastapi 也測
# 數學算對不對。
# ---------------------------------------------------------------------------
def health_snapshot(slot, wake_ts=None):
    import statistics as _stats
    budget_ms = round(slot.slice_len / slot.tgt_fps * 1000, 1) if slot.slice_len else None
    hist = list(slot.gen_compute_ms_hist)
    gen_p50 = round(_stats.median(hist), 1) if hist else None
    gen_p95 = None
    if hist:
        srt = sorted(hist)
        gen_p95 = round(srt[max(0, int(len(srt) * 0.95) - 1)], 1)
    ao = slot.audio_out
    sink = slot.sink
    return {
        "frames": sink.count if sink else 0,
        "output_resolution": {
            "width": slot.frame_width,
            "height": slot.frame_height,
        },
        "load": slot.load_report,
        "round_count": slot.round_count,
        "round_latencies_ms": list(slot.round_latencies),
        "uptime_s": round(time.time() - (wake_ts if wake_ts else time.time()), 1),
        "sink_depth": len(sink.q) if sink else 0,
        "latency_ms": {
            "gen_compute_B": slot.last_gen_compute_ms,
            "sink_pop_C": sink.last_pop_latency_ms if sink else None,
            "chunk_budget_ms": budget_ms,
            "sync_buffer_reserved_ms": slot.SYNC_BUFFER_MS,
        },
        "gen_compute_ms_rolling": {
            "p50": gen_p50, "p95": gen_p95, "budget_ms": budget_ms,
            "n_samples": len(hist),
            "headroom_p95_pct": (round((1 - gen_p95 / budget_ms) * 100, 1)
                                  if (gen_p95 and budget_ms) else None),
        },
        "audio_underrun": {
            "count": ao.underrun_count if ao else 0,
            "recent_gap_ms": list(ao.underrun_gap_ms)[-10:] if ao else [],
            "buffer_depth_ms": round(ao.depth_samples / ao.sample_rate * 1000, 1) if ao else 0,
            "prebuffer_s": ao.default_prebuffer_s if ao else None,
            "last_prebuffer_s": ao.last_prebuffer_s if ao else None,
            "next_prebuffer_s": ao.next_prebuffer_s if ao else None,
        },
        "video_underrun": {"count": sink.underrun_count if sink else 0},
    }


def slot_summary(slot, wake_ts=None):
    """N>1 時 /health 的 slots 陣列每格摘要——health_snapshot 加上占用/健康欄位。"""
    body = health_snapshot(slot, wake_ts)
    body.update({
        "index": slot.index,
        "char": slot.char,
        "active": slot.active_session is not None,
        "healthy": slot.healthy,
        "fault_count": slot.fault_count,
        "last_fault": slot.last_fault,
    })
    return body
