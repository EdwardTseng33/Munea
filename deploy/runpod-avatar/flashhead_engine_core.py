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
import os
import threading
import time

import numpy as np


SUPPORTED_FRAME_SIZES = (512, 640, 768)

# 句尾自動補刀門檻（秒）：輸入音訊靜默超過這個時間、且 acc 還壓著不滿一個
# chunk 的殘尾，就視同句尾 finish、補靜音照樣生成。
# 背景（2026-07-24 Edward 親測「句尾吞 1-2 字」根因）：browser relay 的
# 'finish' 通知只在整輪 turn_complete 才來，一輪內逐句 TTS 之間沒有通知，
# 每句尾最多 0.96s（1-2 個中文字）會滯留 acc 直到下一句音訊抵達才被硬併，
# 實測 16 round 只有 6 次 finish。0.45s < 0.8s round 邊界、又大於正常
# 串流抖動；TTS 中途真的停超過 0.45s 時只是多一格帶靜音尾的畫面，順序不亂。
TAIL_FLUSH_S = float(os.environ.get("MUNEA_FH_TAIL_FLUSH_S", "0.45"))
# 新起句首塊加速（2026-08-17 第二刀 · Edward「直到90分」）：
# 一輪的第一塊原本要攢滿 0.96 秒聲音才開工＝每逢停頓後嘴慢 0.6-1.5 秒的主因。
# 開了這刀：等 FAST_FIRST_WAIT_S 還攢不滿一塊、就先拿手上的真聲音墊零開工，
# 只推真聲音那幾格畫面（墊零的不推——推了會蓋掉下一塊的真嘴型）。
FAST_FIRST = os.environ.get("MUNEA_FH_FAST_FIRST", "1") == "1"
FAST_FIRST_WAIT_S = float(os.environ.get("MUNEA_FH_FAST_FIRST_WAIT_S", "0.25"))
FAST_FIRST_MIN_S = float(os.environ.get("MUNEA_FH_FAST_FIRST_MIN_S", "0.18"))


def should_fast_first(round_pending, acc_len, chunk_samples, waited_s,
                      enabled=True, wait_s=None, min_s=None, sr_eng=16000):
    """一輪的第一塊要不要提早開工（純函式、可單元測）。

    條件：這一輪還沒出過畫面（round_pending）、聲音攢了一些但不滿一塊、
    已經等超過 wait_s（給爆發式到達一個攢滿整塊的機會）、且至少有 min_s
    的真聲音（太短的嘴型沒意義、白花一次顯卡）。"""
    wait_s = FAST_FIRST_WAIT_S if wait_s is None else wait_s
    min_s = FAST_FIRST_MIN_S if min_s is None else min_s
    return (bool(enabled) and bool(round_pending)
            and 0 < acc_len < chunk_samples
            and waited_s >= wait_s
            and acc_len >= int(min_s * sr_eng))

# 畫面時間穩定器（2026-07-24 Edward 反映「待機時整個背景微閃爍」）。
# 根因：生成模型每 chunk 重畫整張圖（含背景），背景像素每次都有 1~3 階的
# 隨機微差，待機時特別明顯。做法：新畫面逐像素跟上一張輸出比，差異 <= AF_LO
# 的像素直接沿用上一張（背景完全靜止）；差異 >= AF_HI 的照常更新（眨眼、
# 嘴型差異大、不受影響）；中間區線性過渡、避免硬邊。因為是跟「上一張輸出」
# 比，緩慢真動作的差異會累積、一超過 AF_LO 就開始跟上，不會被永久凍住。
# 副作用是正向的：背景靜止後 WebRTC 編碼省下的位元集中給臉部、畫質更好。
# MUNEA_FH_ANTIFLICKER=0 可整個關掉（回到舊行為）。
ANTIFLICKER = os.environ.get("MUNEA_FH_ANTIFLICKER", "1") == "1"
# Production A/B on the same Voice phrases showed that 3/12 suppresses quiet
# phoneme motion together with flicker (only 1/3 mouth-onset gates passed).
# 1/8 retained the temporal stabilizer while all 3/3 quiet/normal phrases kept
# measurable mouth motion. These defaults mirror the deployed worker config.
ANTIFLICKER_LO = float(os.environ.get("MUNEA_FH_AF_LO", "1"))
ANTIFLICKER_HI = float(os.environ.get("MUNEA_FH_AF_HI", "8"))

# FlashHead's torch.Generator advances after every generated chunk, while
# reset_person_name() restores only the motion latent.  Without resetting the
# generator, an identical opening phoneme can receive a different first-chunk
# noise sequence depending on how many chunks earlier turns consumed; receiver
# evidence showed that occasionally producing a near-static first 720 ms.  A
# semantic turn should be reproducible, while chunks inside the turn must keep
# advancing normally.  Set a negative value only for a bounded rollback.
TURN_SEED = int(os.environ.get("MUNEA_FH_TURN_SEED", "42"))
# A second full 960 ms generation is too expensive for a realtime opening.
# Keep the experimental escape hatch, but ship it off.  Most importantly,
# never delete video frames without deleting the matching audio samples: that
# makes an onset metric look better while moving every following viseme onto
# the wrong phoneme.
FIRST_CHUNK_RETRY = os.environ.get("MUNEA_FH_FIRST_CHUNK_RETRY", "0") == "1"
FIRST_CHUNK_SPEECH_RMS = float(
    os.environ.get("MUNEA_FH_FIRST_CHUNK_SPEECH_RMS", "0.02")
)
FIRST_CHUNK_MOUTH_MOTION = float(
    os.environ.get("MUNEA_FH_FIRST_CHUNK_MOUTH_MOTION", "0.015")
)
FIRST_CHUNK_MAX_SKEW_MS = float(
    os.environ.get("MUNEA_FH_FIRST_CHUNK_MAX_SKEW_MS", "160")
)
FIRST_CHUNK_RETRY_CANDIDATES = max(
    1, min(3, int(os.environ.get("MUNEA_FH_FIRST_CHUNK_RETRY_CANDIDATES", "3")))
)


def pcm_rms(pcm):
    """Normalized RMS for float or PCM16 arrays without copying large turns."""
    values = np.asarray(pcm).reshape(-1)
    if not len(values):
        return 0.0
    work = values.astype(np.float32, copy=False)
    if values.dtype.kind in "iu":
        work = work / 32768.0
    return float(np.sqrt(np.mean(work * work)))


def mouth_motion_peak(frames):
    """Peak adjacent-frame motion in the production portrait mouth region."""
    values = np.asarray(frames)
    if values.ndim != 4 or len(values) < 2:
        return 0.0
    height, width = values.shape[1:3]
    mouth = values[
        :, int(height * 0.55):max(int(height * 0.72), int(height * 0.55) + 1),
        int(width * 0.33):max(int(width * 0.67), int(width * 0.33) + 1),
    ].astype(np.float32)
    adjacent = np.abs(np.diff(mouth, axis=0))
    return float(np.max(np.mean(adjacent, axis=(1, 2, 3))) / 255.0)


def prepare_output_frames(frames, output_size=None, sharpen=False, cv2mod=None):
    """Upscale model frames for transport without changing model resolution.

    FlashHead 512 retains the livelier motion profile seen in production, but
    sending that square directly makes the App enlarge it to 1080 CSS pixels.
    A bounded Lanczos resize plus a mild unsharp pass improves transport detail
    without asking the diffusion model to infer at 640 again.
    """
    values = np.asarray(frames)
    if values.ndim != 4 or not len(values):
        return values
    size = int(output_size or values.shape[2])
    if size <= 0:
        return values
    if cv2mod is None:
        import cv2 as cv2mod
    needs_resize = values.shape[1] != size or values.shape[2] != size
    if not needs_resize and not sharpen:
        return values
    prepared = np.empty((len(values), size, size, values.shape[3]), dtype=np.uint8)
    for index, frame in enumerate(values):
        current = frame
        if needs_resize:
            current = cv2mod.resize(current, (size, size), interpolation=cv2mod.INTER_LANCZOS4)
        if sharpen:
            blurred = cv2mod.GaussianBlur(current, (0, 0), 1.0)
            current = cv2mod.addWeighted(current, 1.28, blurred, -0.28, 0)
        prepared[index] = current
    return prepared


def first_chunk_av_skew_ms(frames, pcm, fps=25):
    """Measure model-local audio-to-mouth onset skew for one generated chunk."""
    values = np.asarray(frames)
    audio = np.asarray(pcm).reshape(-1)
    if values.ndim != 4 or len(values) < 2 or not len(audio):
        return None
    work = audio.astype(np.float32, copy=False)
    if audio.dtype.kind in "iu":
        work = work / 32768.0
    samples_per_frame = max(1, int(round(len(work) / len(values))))
    audio_onset = None
    for index in range(len(values)):
        part = work[index * samples_per_frame:(index + 1) * samples_per_frame]
        if len(part) and float(np.sqrt(np.mean(part * part))) >= FIRST_CHUNK_SPEECH_RMS:
            audio_onset = index
            break
    if audio_onset is None:
        return None

    height, width = values.shape[1:3]
    mouth = values[
        :, int(height * 0.55):max(int(height * 0.72), int(height * 0.55) + 1),
        int(width * 0.33):max(int(width * 0.67), int(width * 0.33) + 1),
    ].astype(np.float32)
    motion = np.mean(np.abs(np.diff(mouth, axis=0)), axis=(1, 2, 3)) / 255.0
    mouth_onset = next(
        (index + 1 for index, value in enumerate(motion)
         if index + 1 >= audio_onset and float(value) >= FIRST_CHUNK_MOUTH_MOTION),
        None,
    )
    if mouth_onset is None:
        return float("inf")
    return round((mouth_onset - audio_onset) * 1000.0 / max(1, float(fps)), 1)


def select_first_chunk_candidate(candidates):
    """Choose the earliest credible mouth onset, then strongest motion."""
    usable = [item for item in candidates if item and len(item) >= 3]
    if not usable:
        return None, None, 0.0

    def rank(item):
        _frames, skew_ms, motion = item
        finite = skew_ms is not None and np.isfinite(skew_ms)
        return (
            0 if finite else 1,
            float(skew_ms) if finite else float("inf"),
            -float(motion or 0.0),
        )

    return min(usable, key=rank)


def first_chunk_requires_retry(skew_ms):
    """Retry only when no credible mouth onset exists.

    A second GPU generation adds roughly 600 ms and makes first speech feel
    stuck, so it is reserved for a non-finite measurement.  Finite late motion
    is reported for model tuning and preserved byte-for-byte; it must never be
    hidden by deleting video-only content.
    """
    return skew_ms is not None and not np.isfinite(skew_ms)


def should_apply_antiflicker(emit_audio):
    """Background stabilization is safe only for video-only idle chunks.

    Speech frames must preserve even quiet phoneme motion.  Production A/V
    evidence caught a full 8.3-second audible response whose small mouth
    changes were flattened by the same pixel hold intended for idle
    background flicker.  Keep the stabilizer's reference frame updated during
    speech, but never filter speech pixels.
    """
    return ANTIFLICKER and not emit_audio


def stabilize_frame(prev, cur, cv2mod):
    """單張時間穩定：跟上一張輸出 prev 比，回傳處理後的 cur。

    三分法：差異(三通道取最大) <= AF_LO 的像素沿用 prev（背景微雜訊凍住）、
    >= AF_HI 照常更新（眨眼嘴型不受影響）、中間窄帶線性混合避免硬邊。
    對真動作用「取最大」是刻意保守——寧可放行、不誤凍。緩慢真動作因為是
    跟「上一張輸出」比，差異會累積、一超過 AF_LO 就開始跟上、不會永久凍住。
    cv2mod 傳 None 走純 numpy 備援；兩條路徑輸出必須完全一致（有單元測試）。
    """
    if cv2mod is not None:
        d3 = cv2mod.absdiff(cur, prev)
        c0, c1, c2 = cv2mod.split(d3)
        d = cv2mod.max(cv2mod.max(c0, c1), c2)
        hold = cv2mod.compare(d, ANTIFLICKER_LO, cv2mod.CMP_LE)
        cv2mod.copyTo(prev, hold, cur)
    else:
        delta = cur.astype(np.int16)
        delta -= prev
        np.abs(delta, out=delta)
        d = delta.max(axis=2)
        cur = np.where((d <= ANTIFLICKER_LO)[:, :, None], prev, cur)
    mid = (d > ANTIFLICKER_LO) & (d < ANTIFLICKER_HI)
    if mid.any():
        w = ((d[mid].astype(np.float32) - ANTIFLICKER_LO)
             / (ANTIFLICKER_HI - ANTIFLICKER_LO))[:, None]
        cur[mid] = (prev[mid].astype(np.float32) * (1.0 - w)
                    + cur[mid].astype(np.float32) * w + 0.5).astype(np.uint8)
    return cur


def parse_frame_size(value):
    """Validate the square model frame size before any GPU work starts."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        raise ValueError("MUNEA_FH_FRAME_SIZE must be an integer")
    if size not in SUPPORTED_FRAME_SIZES or size % 32:
        raise ValueError("MUNEA_FH_FRAME_SIZE must be one of 512, 640, 768")
    return size


def env_flag_enabled(value):
    """Shared default-off parsing rule for the N-way batching surgery switches
    (MUNEA_FH_SLOT_STREAM today; MUNEA_FH_BATCHING once phase 2 lands). Kept
    here (zero heavy deps) so the parsing rule itself is unit-testable without
    a GPU/torch/fastapi install -- see scripts/test_flashhead_slot_stream.py.

    Convention: only the literal string "1" enables the switch. Unset, "0",
    "" or anything else disables it -- current behavior must never change
    unless a session explicitly opts in (same rule as MUNEA_FH_SLOTS in
    docs/多人併發容量架構-2026-07-12.md and the 2026-07-23 batching-surgery
    design doc's compatibility rules).
    """
    return value == "1"


# ---------------------------------------------------------------------------
# FrameSink / AudioOutBuffer -- copied verbatim from the single-instance file
# (old flashhead_server.py lines 94-223). Logic untouched, only relocated;
# each Slot owns one instance so they can never cross-talk.
# ---------------------------------------------------------------------------
class FrameSink:
    """Playback queue with an audio-clock outlet (2026-08-13 聲嘴對錶).

    Edward 8/13 實機儀器抓到的結構病：畫格出口原本是「不看時間的傳送帶」
    （先到先播、每秒固定張數），聲音卻照自己的鐘走——兩邊只是碰巧對上。
    顯卡某一塊算慢 0.6-1.5 秒，那一段嘴型就整段遲到照播（量到 45 秒的
    遲到畫格、追齊機制 0 次觸發），受端看到 0.5-1.3 秒的「嘴慢尖峰」。

    對錶規則（聲音永遠是主時鐘、聲音永遠不等畫面）：
      - 每格畫面帶著「這格對應的聲音位置」入隊（idle 畫格沒有聲音＝不帶錶）
      - 出口每次取格先對錶：這格的聲音**還沒播到**（早到超過 LEAD）＝先不播、
        維持上一格；這格的聲音**早就播過**（遲到超過 LAG）＝整段丟掉追到現在
      - 沒掛錶（audio_pos_fn 未設）＝行為與舊版逐位元相同（傳送帶）
    """

    # 允許畫面領先聲音的幅度（FlashHead 設計上嘴會微微先動）；再早就先扣住
    AV_LEAD_S = 0.28
    # 允許畫面落後聲音的幅度；再晚整段丟掉、嘴直接跳回「現在」
    AV_LAG_S = 0.16

    def __init__(self, tgt_fps):
        self.tgt_fps = tgt_fps
        self.target_depth = max(1, int(round(tgt_fps * 1.5)))
        self.max_depth = max(self.target_depth + 1, int(round(tgt_fps * 2.0)))
        self.q = collections.deque(maxlen=int(round(tgt_fps * 12)))
        self.count = 0
        self.lock = threading.Lock()
        self.last_pop_latency_ms = None
        self.underrun_count = 0
        self.trim_events = 0
        self.trim_frames = 0
        # 聲音錶：wake() 時綁 audio_out.played_pos_s；沒綁＝舊行為
        self.audio_pos_fn = None
        # 對錶儀表（進 health_snapshot.video_sync）
        self.av_resync_events = 0
        self.av_resync_frames = 0
        self.av_hold_events = 0
        self.last_av_offset_ms = None

    def push_many(self, frames, chunk_gen_ts, tgt_fps, start_audio_pos=None):
        with self.lock:
            n = frames.shape[0]
            fps = float(tgt_fps or self.tgt_fps or 1)
            for i in range(n):
                pos = (None if start_audio_pos is None
                       else float(start_audio_pos) + i / fps)
                self.q.append((frames[i], pos))
                self.count += 1
            if len(self.q) > self.max_depth:
                drop_n = len(self.q) - self.target_depth
                for _ in range(drop_n):
                    self.q.popleft()
                self.trim_events += 1
                self.trim_frames += drop_n

    def pop(self):
        with self.lock:
            depth = len(self.q)
            self.last_pop_latency_ms = round(depth / self.tgt_fps * 1000, 1)
            if not self.q:
                self.underrun_count += 1
                return None
            frame, pos = self.q[0]
            played = None
            if pos is not None and self.audio_pos_fn is not None:
                try:
                    played = self.audio_pos_fn()
                except Exception:
                    played = None
            if played is not None:
                offset = pos - float(played)
                self.last_av_offset_ms = round(offset * 1000, 1)
                if offset > self.AV_LEAD_S:
                    # 這格的聲音還沒播到：先扣住（recv 端維持上一格），聲音不等畫面
                    self.av_hold_events += 1
                    return None
                if offset < -self.AV_LAG_S:
                    # 這格的聲音早播完了：把遲到的整段丟掉、追到「現在」
                    dropped = 0
                    while self.q:
                        head_frame, head_pos = self.q[0]
                        if head_pos is None or (head_pos - float(played)) >= -0.02:
                            break
                        self.q.popleft()
                        dropped += 1
                    self.av_resync_events += 1
                    self.av_resync_frames += dropped
                    if not self.q:
                        self.underrun_count += 1
                        return None
                    frame, pos = self.q[0]
            self.q.popleft()
            return frame

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
    def __init__(self, sample_rate, prebuffer_s=0.5, adaptive_min_s=None,
                 adaptive_max_s=None):
        self.sample_rate = sample_rate
        self.prebuffer_s = prebuffer_s
        self.default_prebuffer_s = prebuffer_s
        adaptive_min = prebuffer_s if adaptive_min_s is None else float(adaptive_min_s)
        adaptive_max = prebuffer_s if adaptive_max_s is None else float(adaptive_max_s)
        self.adaptive_min_s = max(0.0, min(adaptive_min, adaptive_max))
        self.adaptive_max_s = max(self.adaptive_min_s, adaptive_max)
        self.adaptive_prebuffer_s = self.adaptive_min_s
        self.adaptive_target_s = self.adaptive_prebuffer_s
        self.next_prebuffer_s = self.adaptive_prebuffer_s
        self.last_prebuffer_s = self.adaptive_prebuffer_s
        self.generation_compute_ms = collections.deque(maxlen=20)
        self.generation_budget_ms = None
        self.generation_p95_ms = None
        self.frame_samples = int(sample_rate * 0.02)
        self.lock = threading.Lock()
        self.buf = np.zeros(0, dtype=np.int16)
        self.underrun_count = 0
        self.underrun_gap_ms = collections.deque(maxlen=50)
        self._underrun_started_ts = None
        self.last_push_ts = 0.0
        self.depth_samples = 0
        # Counts only PCM frames actually handed to WebRTC. Held/underrun
        # zeroes are excluded so lip catch-up follows the audible timeline.
        self.played_samples = 0
        self.hold_until_ts = float("inf")
        self._awaiting_first_push = True
        self._turn_complete = False
        self._one_shot_prebuffer = False
        self._turn_underrun_seen = False
        self.stable_turns = 0

    def _raise_adaptive_prebuffer_locked(self, seconds):
        if self.adaptive_max_s <= self.adaptive_min_s:
            return
        self.adaptive_prebuffer_s = min(
            self.adaptive_max_s,
            max(self.adaptive_prebuffer_s, self.adaptive_prebuffer_s + float(seconds)),
        )
        if self._awaiting_first_push and not self._one_shot_prebuffer:
            self.next_prebuffer_s = self.adaptive_prebuffer_s

    def observe_generation(self, compute_ms, budget_ms):
        """Record GPU headroom without charging every turn a speculative wait.

        Compute p95 remains operational evidence, but only a real mid-turn
        starvation may raise the next turn's 200-350 ms prebuffer.  This avoids
        turning one slow/cold chunk into a fixed latency tax on every sentence.
        """
        if compute_ms is None or budget_ms is None or budget_ms <= 0:
            return
        with self.lock:
            self.generation_compute_ms.append(max(0.0, float(compute_ms)))
            self.generation_budget_ms = float(budget_ms)
            ordered = sorted(self.generation_compute_ms)
            # Match health_snapshot's operational p95: with a short rolling
            # window, do not let one cold-compile maximum dominate every
            # subsequent turn. Real starvation still takes the separate
            # immediate +50ms path in push().
            p95_index = max(0, int(len(ordered) * 0.95) - 1)
            self.generation_p95_ms = ordered[p95_index]

    def _queue_locked(self, pcm_int16):
        now = time.time()
        if len(pcm_int16) and self._underrun_started_ts is not None:
            gap_ms = round((now - self._underrun_started_ts) * 1000, 1)
            self.underrun_gap_ms.append(gap_ms)
            self._underrun_started_ts = None
            # Only observed starvation raises the next-turn cushion.
            self._turn_underrun_seen = True
            self.stable_turns = 0
            self._raise_adaptive_prebuffer_locked(0.05)
        self.buf = np.concatenate([self.buf, pcm_int16])
        self.last_push_ts = now
        self.depth_samples = len(self.buf)

    def queue(self, pcm_int16):
        """Queue original Voice PCM immediately, without waiting for lip rendering.

        Playout remains held until ``release_playout`` sees the first rendered
        video chunk. GPU variance may then freeze video, but it can no longer
        starve the audible PCM queue every model chunk.
        """
        with self.lock:
            self._queue_locked(np.asarray(pcm_int16, dtype=np.int16).reshape(-1))

    def release_playout(self):
        """Open the shared audio/video start gate after first video is ready."""
        with self.lock:
            if len(self.buf) and self._awaiting_first_push:
                now = time.time()
                delay = self.next_prebuffer_s
                self.last_prebuffer_s = delay
                self.next_prebuffer_s = self.adaptive_prebuffer_s
                self._one_shot_prebuffer = False
                self.hold_until_ts = now + delay
                self._awaiting_first_push = False

    def push(self, pcm_int16):
        """Backward-compatible queue-and-release path for local callers/tests."""
        with self.lock:
            self._queue_locked(np.asarray(pcm_int16, dtype=np.int16).reshape(-1))
            if len(self.buf) and self._awaiting_first_push:
                now = time.time()
                delay = self.next_prebuffer_s
                self.last_prebuffer_s = delay
                self.next_prebuffer_s = self.adaptive_prebuffer_s
                self._one_shot_prebuffer = False
                self.hold_until_ts = now + delay
                self._awaiting_first_push = False

    def clear(self):
        with self.lock:
            self.buf = np.zeros(0, dtype=np.int16)
            self.depth_samples = 0
            self.played_samples = 0
            self.hold_until_ts = float("inf")
            self._awaiting_first_push = True
            self._turn_complete = False
            self._turn_underrun_seen = False
            self._one_shot_prebuffer = False
            self._underrun_started_ts = None
            self.next_prebuffer_s = self.adaptive_prebuffer_s

    def arm_prebuffer(self, seconds):
        """Use a one-shot playout delay for the next PCM turn only."""
        with self.lock:
            self.next_prebuffer_s = max(0.0, float(seconds))
            self._one_shot_prebuffer = True

    def mark_input_complete(self):
        """Stop treating the natural end of a response as buffer starvation."""
        with self.lock:
            if self._turn_underrun_seen:
                self.stable_turns = 0
            else:
                self.stable_turns += 1
                if self.stable_turns >= 3 and self.adaptive_prebuffer_s > self.adaptive_min_s:
                    self.adaptive_prebuffer_s = max(
                        self.adaptive_min_s, self.adaptive_prebuffer_s - 0.05
                    )
                    self.adaptive_target_s = self.adaptive_prebuffer_s
                    self.stable_turns = 0
            if self._awaiting_first_push and not self._one_shot_prebuffer:
                self.next_prebuffer_s = self.adaptive_prebuffer_s
            self._turn_complete = True
            self._underrun_started_ts = None

    def played_pos_s(self):
        """聲音錶讀數：真正交給 WebRTC 的樣本數換算成秒（靜音補零不計）。"""
        with self.lock:
            return self.played_samples / max(1, self.sample_rate)

    def playout_held(self):
        """True while audio and video must stay on their shared start gate."""
        with self.lock:
            return time.time() < self.hold_until_ts

    def video_playout_held(self, lead_s=0.0):
        """Apply a bounded signed video offset to the shared turn gate.

        Positive values open video before audio; negative values hold video
        after audio.  The first rendered chunk still arms the single
        authoritative turn gate and an empty turn remains held forever.
        """
        lead = max(-0.35, min(0.35, float(lead_s or 0.0)))
        with self.lock:
            return time.time() < self.hold_until_ts - lead

    def pop_frame(self):
        with self.lock:
            if time.time() < self.hold_until_ts:
                return np.zeros(self.frame_samples, dtype=np.int16)
            if len(self.buf) >= self.frame_samples:
                chunk = self.buf[:self.frame_samples]
                self.buf = self.buf[self.frame_samples:]
                self.depth_samples = len(self.buf)
                self.played_samples += len(chunk)
                return chunk
            if not self._turn_complete and self._underrun_started_ts is None:
                self.underrun_count += 1
                self._underrun_started_ts = time.time()
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
        self.model_frame_height = None
        self.model_frame_width = None
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
        # N-way batching surgery phase 1 / option B (2026-07-23): only set to a
        # real torch.cuda.Stream() by flashhead_server.py when MUNEA_FH_SLOT_STREAM
        # is on; stays None otherwise (default, matches pre-patch behavior).
        # This module never imports torch itself -- see make_slot_stream_run_pipeline
        # below for how the stream actually gets used.
        self.cuda_stream = None
        self.SYNC_BUFFER_MS = 350
        self.round_count = 0
        self.round_start_ts = 0.0
        self.round_latencies = collections.deque(maxlen=20)
        self.last_gen_compute_ms = None
        self.gen_compute_ms_hist = collections.deque(maxlen=100)
        self.video_catchup_events = 0
        self.video_catchup_frames = 0
        self.video_late_events = 0
        self.video_late_frames = 0
        # FlashHead carries the final motion latent into the next generation
        # chunk.  That continuity is correct inside one assistant utterance,
        # but a new semantic turn must start from the character reference or
        # it can inherit a closed/static mouth from the previous answer.
        self.motion_reset_count = 0
        self.motion_reset_failures = 0
        self.turn_seed_reset_count = 0
        self.first_chunk_retry_count = 0
        self.first_chunk_retry_failures = 0
        self.first_chunk_align_events = 0
        self.first_chunk_align_frames = 0
        # Real speech must invalidate any idle GPU work that is still in flight.
        # Expose this count so the production gate can prove that the race was
        # handled instead of inferring it from negative first-frame timings.
        self.idle_invalidation_count = 0
        # WebRTC audio sender scheduling is separate from PCM availability.
        # A busy event loop can wake the 20 ms sender late even while audio_out
        # still has plenty of buffered PCM. Track that independently so an RTP
        # playout hole cannot hide behind audio_underrun=0.
        self.audio_sender_rebase_count = 0
        self.audio_sender_max_late_ms = 0.0
        self.audio_sender_recent_late_ms = collections.deque(maxlen=20)
        # ---- 准入/佔用（SlotPool 管）----
        self.active_session = None
        self.active_pc = None
        self.active_created = 0.0
        # ---- 故障隔離（2026-07-12 新補，對應設計文件 3.2 節測項 5）----
        self.healthy = True
        self.fault_count = 0
        self.last_fault = None
        # 新起句首塊加速的出手次數（health 曝光；長期 0 ＝這刀沒在工作）
        self.fast_first_count = 0


def lip_catchup_frame_count(audio_played_s, queued_video_s, timeline_start_s,
                            frame_count, fps, keep_frames=2):
    """Return how many already-expired lip frames may be skipped safely.

    Audio remains the master clock. The final ``keep_frames`` are retained so
    a slow GPU produces a short mouth freeze/catch-up instead of an empty video
    queue or delaying audible PCM.
    """
    if not frame_count or not fps or timeline_start_s is None:
        return 0
    expired_s = max(0.0, float(audio_played_s) + float(queued_video_s)
                    - float(timeline_start_s))
    expired_frames = int(expired_s * float(fps))
    return min(max(0, int(frame_count) - max(1, int(keep_frames))), expired_frames)


def can_generate_video_chunk(depth_frames, fps, chunk_frames, max_ahead_s):
    """Reserve queue room for a whole model chunk before rendering it.

    FlashHead produces one sizeable frame batch at a time.  Checking only the
    current queue depth can therefore pass at 1.49 seconds and immediately push
    another ~0.96 seconds into a 1.5-second queue.  The sink then has no choice
    but to trim lip frames.  Gate on the post-push depth so content is paced,
    never deleted.
    """
    rate = max(1.0, float(fps))
    current_s = max(0.0, float(depth_frames)) / rate
    chunk_s = max(0.0, float(chunk_frames)) / rate
    return current_s <= max(0.0, float(max_ahead_s) - chunk_s)


def pace_audio_sender_clock(started, next_pts, sample_rate, now,
                            rebase_after_s=0.04):
    """Keep late WebRTC audio frames paced instead of sending a catch-up burst.

    aiortc asks ``recv`` for one media frame at a time. If the event loop wakes
    100 ms late, retaining the original wall-clock anchor makes the next five
    20 ms frames return immediately. Receivers can discard that burst as late
    RTP, creating an audible hole even though PCM never underruns. Move only
    the wall-clock anchor forward; RTP PTS and every audio sample stay intact.
    """
    if not sample_rate:
        return started, 0.0, False
    target = float(started) + float(next_pts) / float(sample_rate)
    late_s = max(0.0, float(now) - target)
    if late_s <= float(rebase_after_s):
        return started, round(late_s * 1000, 1), False
    return float(started) + late_s, round(late_s * 1000, 1), True


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
                # get_base_data_fn below already replaces the character and
                # resets its motion latent.  Avoid reacquiring char_lock from
                # Feeder.reset while this switch already owns it.
                slot.feeder.reset(reset_pipeline_motion=False)
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
                 auto_start=True, output_size=None, output_sharpen=False):
        self.slot = slot
        self.get_audio_embedding = get_audio_embedding
        self.run_pipeline = run_pipeline
        self.sr_in = sr_in
        self.sr_eng = sr_eng
        self.max_ahead_s = max_ahead_s
        self.sharpen = sharpen
        self.output_size = int(output_size) if output_size else None
        self.output_sharpen = bool(output_sharpen)
        self.fault_streak_limit = fault_streak_limit
        self.on_unhealthy = on_unhealthy

        self.lock = threading.Lock()
        self.acc = np.zeros(0, dtype=np.float32)
        # The lip-sync model consumes 16 kHz audio, but listeners should hear
        # Gemini's original 24 kHz stream. Keep both buffers aligned so model
        # resampling never becomes the audible output path.
        self.acc_out = np.zeros(0, dtype=np.float32)
        self.consumed = 0
        self.timeline_base_s = 0.0
        self.t0 = None
        self.last_in = 0.0
        self._idle_due = 0.0
        self._idle_on = False
        self._round_pending = False
        self._finish_pending = False
        self._complete_pending = False
        # 每次真 PCM 進來都推進；待機 GPU 工作用它確認計算期間沒有真語音抵達。
        # 否則晚完成的待機畫格會插到新一輪嘴型前面，造成首句嘴慢甚至完全沒動。
        self._real_input_seq = 0
        # 世代號——每次 reset() +1。GPU 上跑到一半的舊塊完成時比對世代號，
        # 變了就整塊丟棄，不讓上一輪聲畫漏進新一輪（治「掛斷重撥她一接通就
        # 繼續講上一段」「插話後又冒半句舊話」）。
        self._epoch = 0
        self._fault_streak = 0
        # 時間穩定器狀態：上一張「實際輸出」的畫面（reset/換角色時清空，
        # 否則會拿舊角色/舊一輪的畫面當基準、產生一瞬間的鬼影混合）。
        self._prev_frame = None

        if auto_start:
            threading.Thread(target=self._loop, daemon=True).start()

    def push24k(self, pcm_bytes):
        pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16).copy()
        # Audible PCM takes the direct ingress path. Lip generation consumes a
        # resampled copy, but never becomes the clock that feeds the speaker.
        self.slot.audio_out.queue(pcm_int16)
        x = pcm_int16.astype(np.float32) / 32768.0
        n_out = int(len(x) * self.sr_eng / self.sr_in)
        if n_out <= 0:
            return
        xq = np.interp(np.linspace(0, 1, n_out, endpoint=False),
                        np.linspace(0, 1, len(x), endpoint=False), x).astype(np.float32)
        stop_idle = False
        with self.lock:
            now = time.time()
            self._real_input_seq += 1
            if self._idle_on:
                # 讓已在 GPU 上的待機工作以 epoch 判定作廢；只清畫面，不碰已排入的
                # 原始 PCM／共同播放時鐘。真嘴型完成前仍由 poster 保持畫面。
                self._idle_on = False
                self._epoch += 1
                self._prev_frame = None
                # Do not clear audio_dq here. The embedding model indexes a
                # fixed-length history window; shortening it while an idle
                # chunk is in flight makes the next embedding index past the
                # array and poisons the CUDA context. The zero-valued idle
                # history is the required neutral pre-roll for real speech.
                self.slot.idle_invalidation_count += 1
                stop_idle = True
            if self.t0 is None or (now - self.last_in) > 0.8:
                self.t0 = now
                self.consumed = 0
                # A pause starts a new model round, not a new audible turn.
                # Anchor the round after PCM queued before this push so its
                # first lip frame keeps the full-turn playback timeline.
                with self.slot.audio_out.lock:
                    queued_before_push = max(
                        0,
                        self.slot.audio_out.depth_samples - len(pcm_int16),
                    )
                    self.timeline_base_s = (
                        self.slot.audio_out.played_samples + queued_before_push
                    ) / max(1, self.slot.audio_out.sample_rate)
                self.slot.round_count += 1
                self.slot.round_start_ts = now
                self._round_pending = True
                print("[round] slot" + str(self.slot.index) + " #" + str(self.slot.round_count)
                      + " start (acc keep " + str(len(self.acc)) + " samples)", flush=True)
            self.acc = np.concatenate([self.acc, xq])
            self.acc_out = np.concatenate([self.acc_out, x])
            self.last_in = now
        if stop_idle and self.slot.sink is not None:
            self.slot.sink.clear()
            print("[feeder] slot" + str(self.slot.index)
                  + " real audio invalidated in-flight idle frames", flush=True)

    def reset(self, reset_pipeline_motion=True):
        with self.lock:
            self.acc = np.zeros(0, dtype=np.float32)
            self.acc_out = np.zeros(0, dtype=np.float32)
            self.t0 = None
            self.consumed = 0
            self.timeline_base_s = 0.0
            self._epoch += 1
            self._finish_pending = False
            self._complete_pending = False
            self._prev_frame = None
            if self.slot.audio_dq is not None:
                self.slot.audio_dq.extend([0.0] * self.slot.audio_dq.maxlen)
        if self.slot.sink is not None:
            self.slot.sink.clear()
        if self.slot.audio_out is not None:
            self.slot.audio_out.clear()
        motion_reset = False
        if reset_pipeline_motion:
            try:
                reset_fn = getattr(self.slot.pipeline, "reset_person_name", None)
                if callable(reset_fn):
                    # An older GPU chunk may still be updating
                    # latent_motion_frames.  Epoch invalidates its output;
                    # char_lock then waits for it to finish before restoring
                    # the neutral per-character motion seed for the new turn.
                    with self.slot.char_lock:
                        reset_fn(getattr(self.slot.pipeline, "person_name", None))
                        generator = getattr(self.slot.pipeline, "generator", None)
                        reseed_fn = getattr(generator, "manual_seed", None)
                        if TURN_SEED >= 0 and callable(reseed_fn):
                            reseed_fn(TURN_SEED)
                            self.slot.turn_seed_reset_count += 1
                    self.slot.motion_reset_count += 1
                    motion_reset = True
            except Exception as exc:
                # Preserve audible service even if a third-party model build
                # lacks a compatible reset implementation.  Surface the
                # failure for the production gate instead of silently
                # poisoning subsequent lip turns.
                self.slot.motion_reset_failures += 1
                self.slot.last_fault = "motion reset: " + repr(exc)
                print("[feeder] slot" + str(self.slot.index)
                      + " motion reset failed: " + repr(exc), flush=True)
        print("[feeder] slot" + str(self.slot.index) + " reset(turn boundary) epoch="
              + str(self._epoch) + " motion=" + str(motion_reset), flush=True)

    def finish(self):
        with self.lock:
            self._finish_pending = bool(len(self.acc))
            # Audible PCM is queued at ingress now, so input completion no
            # longer depends on the last lip-render chunk finishing. Waiting
            # for GPU tail work here mislabels natural end silence as an audio
            # underrun even though the captured waveform is continuous.
            self._complete_pending = False
            partial_samples = len(self.acc)
        self.slot.audio_out.mark_input_complete()
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

    def _stabilize(self, frames, chunk_epoch, apply_filter=True):
        """時間穩定器：逐張跟上一張輸出比，幾乎沒變的像素沿用上一張。

        cv2 快路徑實測 768² 約 3.5-4.7ms/張（26 張一包約 0.1s、佔 0.96s
        chunk 預算一成）；cv2 缺席時走純 numpy 備援（慢 4 倍、僅測試環境）。
        像素數學在模組層 stabilize_frame()，兩條路徑輸出完全一致、可單元測。
        """
        try:
            import cv2 as cv2mod
        except ImportError:
            cv2mod = None
        prev = self._prev_frame
        if apply_filter:
            for i in range(frames.shape[0]):
                cur = frames[i]
                if prev is not None and prev.shape == cur.shape:
                    cur = stabilize_frame(prev, cur, cv2mod)
                    frames[i] = cur
                prev = cur
        elif len(frames):
            # Speech uses the unfiltered model frames, while the last frame is
            # still remembered so the next idle chunk does not jump back to a
            # stale pre-speech reference.
            prev = frames[-1]
        # 只有世代號沒變才更新基準——reset()/換角色後不可拿舊世代的畫面當基準
        with self.lock:
            if self._epoch == chunk_epoch and prev is not None:
                self._prev_frame = prev.copy()
        return frames

    def _gen_chunk(self, chunk_16k, valid_samples=None, output_pcm=None,
                   emit_audio=True, timeline_start_s=None, idle_input_seq=None,
                   trim_frames_to_valid=False):
        t_chunk_ready = time.time()
        with self.lock:
            if idle_input_seq is not None and self._real_input_seq != idle_input_seq:
                return
            chunk_epoch = self._epoch
            first_round_chunk = bool(
                emit_audio and self._round_pending
                and self.slot.round_start_ts <= t_chunk_ready
            )
            self.slot.audio_dq.extend(chunk_16k.tolist())
            arr = np.array(self.slot.audio_dq)
        try:
            emb = self.get_audio_embedding(self.slot.pipeline, arr,
                                            self.slot.audio_start_idx, self.slot.audio_end_idx)
            with self.slot.char_lock:
                video = self.run_pipeline(self.slot.pipeline, emb)
                frames = video[self.slot.motion_frames_num:].cpu().numpy().astype(np.uint8)
                if first_round_chunk:
                    input_pcm = output_pcm if output_pcm is not None else chunk_16k
                    initial_skew = first_chunk_av_skew_ms(
                        frames, input_pcm, self.slot.tgt_fps,
                    )
                    candidates = [(frames, initial_skew, mouth_motion_peak(frames))]
                    retry_supported = (
                        FIRST_CHUNK_RETRY and TURN_SEED >= 0
                        and first_chunk_requires_retry(initial_skew)
                    )
                    reset_fn = getattr(self.slot.pipeline, "reset_person_name", None)
                    generator = getattr(self.slot.pipeline, "generator", None)
                    reseed_fn = getattr(generator, "manual_seed", None)
                    final_skew = initial_skew
                    attempts = 0
                    while (retry_supported and callable(reset_fn) and callable(reseed_fn)
                           and attempts < FIRST_CHUNK_RETRY_CANDIDATES - 1):
                        attempts += 1
                        reset_fn(getattr(self.slot.pipeline, "person_name", None))
                        reseed_fn(TURN_SEED + attempts)
                        retry_video = self.run_pipeline(self.slot.pipeline, emb)
                        frames = retry_video[self.slot.motion_frames_num:].cpu().numpy().astype(np.uint8)
                        final_skew = first_chunk_av_skew_ms(
                            frames, input_pcm, self.slot.tgt_fps,
                        )
                        candidates.append((frames, final_skew, mouth_motion_peak(frames)))
                        self.slot.first_chunk_retry_count += 1
                        if final_skew is not None and final_skew <= FIRST_CHUNK_MAX_SKEW_MS:
                            break
                    if attempts:
                        frames, final_skew, _final_motion = select_first_chunk_candidate(candidates)
                        if final_skew is None or final_skew > FIRST_CHUNK_MAX_SKEW_MS:
                            self.slot.first_chunk_retry_failures += 1
                        print("[mouth-quality] slot" + str(self.slot.index)
                              + " first chunk retry skew=" + str(initial_skew)
                              + "ms -> " + str(final_skew) + "ms"
                              + " attempts=" + str(attempts), flush=True)
                    print("[mouth-quality] slot" + str(self.slot.index)
                          + " first chunk preserved frames=" + str(len(frames))
                          + " skew=" + str(final_skew) + "ms",
                          flush=True)
        except Exception as e:
            # 故障隔離核心：這一路的 pipeline 炸了，不讓例外往上炸穿整個 feeder
            # 執行緒（更不會波及其他槽的 pipeline/thread，本來就是獨立物件）。
            # 這塊音畫直接丟棄，不推進 sink/audio_out（不留半殘資料）。
            self._on_fault(e)
            return
        self._fault_streak = 0
        frames = prepare_output_frames(
            frames,
            output_size=self.output_size,
            sharpen=self.output_sharpen,
        )
        if self.sharpen:
            import cv2 as _cv2
            for _i in range(frames.shape[0]):
                _f = frames[_i]
                _blur = _cv2.GaussianBlur(_f, (0, 0), 1.8)
                frames[_i] = _cv2.addWeighted(_f, 1.5, _blur, -0.5, 0)
        t_frames_ready = time.time()
        self.slot.last_gen_compute_ms = round((t_frames_ready - t_chunk_ready) * 1000, 1)
        self.slot.gen_compute_ms_hist.append(self.slot.last_gen_compute_ms)
        budget_ms = (round(self.slot.slice_len / self.slot.tgt_fps * 1000, 1)
                     if self.slot.slice_len and self.slot.tgt_fps else None)
        self.slot.audio_out.observe_generation(self.slot.last_gen_compute_ms, budget_ms)
        with self.lock:
            if self._epoch != chunk_epoch:
                print("[feeder] slot" + str(self.slot.index) + " stale chunk dropped (epoch "
                      + str(chunk_epoch) + " -> " + str(self._epoch) + ")", flush=True)
                return
            if idle_input_seq is not None and self._real_input_seq != idle_input_seq:
                print("[feeder] slot" + str(self.slot.index)
                      + " stale idle chunk dropped (real input arrived)", flush=True)
                return
        chunk_frames_cut = 0
        if emit_audio and timeline_start_s is not None and len(frames):
            queued_video_s = self.slot.sink.depth() / max(1, self.slot.tgt_fps)
            audio_played_s = (self.slot.audio_out.played_samples
                              / max(1, self.slot.audio_out.sample_rate))
            drop_count = lip_catchup_frame_count(
                audio_played_s,
                queued_video_s,
                timeline_start_s,
                len(frames),
                self.slot.tgt_fps,
            )
            if drop_count:
                # 生成端不刪畫格（Codex 8/12 的教訓：在這裡刪＝後面每個嘴型都對到
                # 錯的字）。只記帳曝光排程債；真正的還債改在出口端做——每格帶著
                # 「這格對應的聲音位置」，出口照錶丟過期的（帶錶丟＝不會對錯字）。
                self.slot.video_late_events += 1
                self.slot.video_late_frames += drop_count
                print("[video-sync] slot" + str(self.slot.index)
                      + " late_frames=" + str(drop_count) + " preserved"
                      + " audio=" + str(round(audio_played_s, 3)) + "s"
                      + " queued=" + str(round(queued_video_s, 3)) + "s"
                      + " source=" + str(round(timeline_start_s, 3)) + "s",
                      flush=True)
        if (trim_frames_to_valid and valid_samples is not None
                and len(frames) and self.slot.tgt_fps):
            # 新起句首塊：墊零那段的畫面不推——推了會佔住隊伍、蓋掉下一塊的真嘴型
            keep = max(1, int(round(valid_samples / max(1, self.sr_eng) * self.slot.tgt_fps)))
            if keep < len(frames):
                frames = frames[:keep]
        if ANTIFLICKER:
            frames = self._stabilize(
                frames, chunk_epoch,
                apply_filter=should_apply_antiflicker(emit_audio),
            )
        # Keep the final generation check and queue insertion atomic with
        # push24k's epoch bump + sink.clear(). Otherwise real input can arrive
        # after the check but before this push and stale idle frames still win.
        with self.lock:
            if self._epoch != chunk_epoch:
                print("[feeder] slot" + str(self.slot.index)
                      + " stale chunk dropped before sink push", flush=True)
                return
            if idle_input_seq is not None and self._real_input_seq != idle_input_seq:
                print("[feeder] slot" + str(self.slot.index)
                      + " stale idle chunk dropped before sink push", flush=True)
                return
            chunk_audio_pos = None
            if emit_audio and timeline_start_s is not None:
                # lip_catchup 若剪掉開頭 drop_count 格，剩下畫格的錶要跟著往後撥
                chunk_audio_pos = (float(timeline_start_s)
                                   + chunk_frames_cut / max(1, self.slot.tgt_fps))
            self.slot.sink.push_many(frames, t_frames_ready, self.slot.tgt_fps,
                                     start_audio_pos=chunk_audio_pos)
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
        if emit_audio:
            self.slot.audio_out.release_playout()
        round_marker = None
        if emit_audio:
            with self.lock:
                # PCM ingress may begin a newer semantic round while this older
                # GPU chunk is between frames-ready and metric recording. An
                # older chunk must not consume that newer marker (the old code
                # produced impossible negative first-frame latency). Leave it
                # pending for the first chunk that actually started after the
                # marker instead.
                if self._round_pending and self.slot.round_start_ts <= t_chunk_ready:
                    round_marker = (self.slot.round_count, self.slot.round_start_ts)
                    self._round_pending = False
        if round_marker is not None:
            round_no, round_start_ts = round_marker
            lat_ms = round((t_frames_ready - round_start_ts) * 1000, 1)
            self.slot.round_latencies.append(lat_ms)
            print("[round] slot" + str(self.slot.index) + " #" + str(round_no)
                  + " first-frame-latency " + str(lat_ms) + "ms", flush=True)

    def _loop(self):
        cs = self.slot.chunk_samples
        while True:
            todo = None
            complete_now = False
            idle_input_seq = None
            with self.lock:
                if len(self.acc) >= cs and self.t0 is not None:
                    # The audio queue now holds ingress PCM before GPU work.
                    # Reserve room for the entire next model chunk. Checking
                    # only current depth lets one large push overflow the sink,
                    # which deletes mouth content and creates long-call drift.
                    depth_frames = self.slot.sink.depth()
                    if can_generate_video_chunk(
                            depth_frames, self.slot.tgt_fps,
                            self.slot.slice_len, self.max_ahead_s):
                        output_samples = min(len(self.acc_out), int(round(cs * self.sr_in / self.sr_eng)))
                        timeline_start_s = (self.timeline_base_s
                                            + self.consumed / max(1, self.sr_eng))
                        todo = (self.acc[:cs].copy(), cs,
                                self.acc_out[:output_samples].copy(), timeline_start_s, False)
                        self.acc = self.acc[cs:]
                        self.acc_out = self.acc_out[output_samples:]
                        self.consumed += cs
                elif (not self._finish_pending
                      and should_fast_first(
                          self._round_pending, len(self.acc), cs,
                          (time.time() - self.slot.round_start_ts)
                          if self.slot.round_start_ts else 0.0,
                          enabled=FAST_FIRST, sr_eng=self.sr_eng)
                      and can_generate_video_chunk(
                          self.slot.sink.depth(), self.slot.tgt_fps,
                          self.slot.slice_len, self.max_ahead_s)):
                    # 新起句首塊加速：真聲音墊零先開工、只推真聲音那幾格
                    # （句子已收尾交給 tail-flush——它會立刻出手並清旗標）
                    valid = len(self.acc)
                    padded = np.zeros(cs, dtype=np.float32)
                    padded[:valid] = self.acc
                    output_samples = min(len(self.acc_out), int(round(valid * self.sr_in / self.sr_eng)))
                    output_pcm = self.acc_out[:output_samples].copy()
                    self.acc = np.zeros(0, dtype=np.float32)
                    self.acc_out = self.acc_out[output_samples:]
                    timeline_start_s = (self.timeline_base_s
                                        + self.consumed / max(1, self.sr_eng))
                    self.consumed += valid
                    self.slot.fast_first_count += 1
                    print("[feeder] slot" + str(self.slot.index)
                          + " fast-first flush valid=" + str(valid), flush=True)
                    todo = (padded, valid, output_pcm, timeline_start_s, True)
                elif 0 < len(self.acc) < cs and (
                        self._finish_pending
                        or (self.t0 is not None
                            and (time.time() - self.last_in) > TAIL_FLUSH_S)):
                    valid = len(self.acc)
                    if not self._finish_pending:
                        print("[feeder] slot" + str(self.slot.index)
                              + " tail auto-flush valid=" + str(valid), flush=True)
                    padded = np.zeros(cs, dtype=np.float32)
                    padded[:valid] = self.acc
                    output_samples = min(len(self.acc_out), int(round(valid * self.sr_in / self.sr_eng)))
                    output_pcm = self.acc_out[:output_samples].copy()
                    self.acc = np.zeros(0, dtype=np.float32)
                    self.acc_out = self.acc_out[output_samples:]
                    self._finish_pending = False
                    timeline_start_s = (self.timeline_base_s
                                        + self.consumed / max(1, self.sr_eng))
                    self.consumed += valid
                    todo = (padded, valid, output_pcm, timeline_start_s, False)
                if todo is None and self._complete_pending and len(self.acc) == 0:
                    self._complete_pending = False
                    complete_now = True
            if complete_now:
                # "finish" means no more input will arrive, not that every
                # queued/model chunk has already reached playout. Mark the turn
                # complete only after this feeder has produced its final chunk;
                # otherwise a real mid-turn underrun is hidden as natural tail
                # silence and the adaptive prebuffer never learns from it.
                self.slot.audio_out.mark_input_complete()
            if todo is not None:
                if self._idle_on:
                    self._idle_on = False
                    self.slot.sink.clear()
                    print("[feeder] slot" + str(self.slot.index)
                          + " real audio arrived, stop idle feed", flush=True)
                self._gen_chunk(todo[0], todo[1], todo[2], timeline_start_s=todo[3],
                                trim_frames_to_valid=todo[4])
                continue
            now = time.time()
            with self.lock:
                real_silent = ((now - self.last_in) > 1.0 and len(self.acc) < cs
                                and self.slot.audio_out.depth_samples == 0
                                and self.slot.sink.depth() == 0)
                if real_silent:
                    idle_input_seq = self._real_input_seq
            has_conn = any(pc.connectionState in ("new", "connecting", "connected")
                           for pc in self.slot.pcs)
            if has_conn and real_silent and now >= self._idle_due and self.slot.healthy:
                idle_started = False
                with self.lock:
                    idle_still_valid = (self._real_input_seq == idle_input_seq
                                        and (time.time() - self.last_in) > 1.0
                                        and len(self.acc) < cs)
                    if idle_still_valid and not self._idle_on:
                        self._idle_on = True
                        idle_started = True
                if not idle_still_valid:
                    continue
                if idle_started:
                    print("[feeder] slot" + str(self.slot.index)
                          + " real silence, connection alive, start idle feed", flush=True)
                # WebRTC already emits zero PCM while speech is absent. Queueing
                # another 960 ms of generated silence here makes the next real
                # phrase clear/re-arm the audio buffer and inserts a new
                # 200-350 ms start gate inside one conversational turn. Idle
                # generation is video-only; real PCM keeps one continuous clock.
                self._gen_chunk(
                    np.zeros(cs, dtype=np.float32), emit_audio=False,
                    idle_input_seq=idle_input_seq,
                )
                self._idle_due = now + cs / self.sr_eng
            else:
                time.sleep(0.02)


# ---------------------------------------------------------------------------
# make_slot_stream_run_pipeline —— N-way batching surgery phase 1 / option B
# (2026-07-23, see docs/research/合批手術-設計方案-2026-07-23.md section 2).
#
# All three slots' Feeder threads live in the SAME process / SAME CUDA
# context. Without an explicit per-slot stream, their GPU work all lands on
# the shared default stream, and deploy/flashhead-patches/0001-gate-profile-
# sync.patch's 8 device-wide torch.cuda.synchronize() barriers (now gated by
# MUNEA_FH_PROFILE_SYNC) make each slot's generate() call wait for whatever
# the OTHER slots queued too -- see the design doc section 1.2 for the full
# root-cause writeup.
#
# This wraps a slot's run_pipeline callable so its GPU work is issued on a
# dedicated stream instead, then hands the finished tensor back to the
# caller's current stream via wait_stream() -- a GPU-side, non-blocking
# dependency, NOT another host-blocking torch.cuda.synchronize() (that would
# just reintroduce a barrier and defeat the whole point). torch_module is
# dependency-injected (this file stays free of a module-level `import torch`)
# so the wiring itself is unit-testable with a fake torch stand-in -- see
# scripts/test_flashhead_slot_stream.py.
# ---------------------------------------------------------------------------
def make_slot_stream_run_pipeline(run_pipeline_fn, stream, torch_module):
    def _run_on_slot_stream(pipeline, audio_embedding):
        with torch_module.cuda.stream(stream):
            result = run_pipeline_fn(pipeline, audio_embedding)
        torch_module.cuda.current_stream().wait_stream(stream)
        return result
    return _run_on_slot_stream


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
    round_latencies = list(slot.round_latencies)
    return {
        "frames": sink.count if sink else 0,
        "output_resolution": {
            "width": slot.frame_width,
            "height": slot.frame_height,
        },
        "load": slot.load_report,
        "round_count": slot.round_count,
        "round_latencies_ms": round_latencies,
        "round_latency_integrity": {
            "negative_count": sum(1 for value in round_latencies if value < 0),
            "min_ms": min(round_latencies) if round_latencies else None,
        },
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
            "adaptive_prebuffer_s": round(ao.adaptive_prebuffer_s, 3) if ao else None,
            "adaptive_target_s": round(ao.adaptive_target_s, 3) if ao else None,
            "adaptive_min_s": ao.adaptive_min_s if ao else None,
            "adaptive_max_s": ao.adaptive_max_s if ao else None,
            "generation_p95_ms": (round(ao.generation_p95_ms, 1)
                                    if ao and ao.generation_p95_ms is not None else None),
        },
        "audio_sender": {
            "rebase_count": slot.audio_sender_rebase_count,
            "max_late_ms": round(slot.audio_sender_max_late_ms, 1),
            "recent_late_ms": list(slot.audio_sender_recent_late_ms),
        },
        "video_underrun": {"count": sink.underrun_count if sink else 0},
        "video_queue_trim": {
            "events": sink.trim_events if sink else 0,
            "frames": sink.trim_frames if sink else 0,
        },
        "video_sync": {
            "catchup_events": slot.video_catchup_events,
            "catchup_frames": slot.video_catchup_frames,
            "late_events": slot.video_late_events,
            "late_frames": slot.video_late_frames,
            "idle_invalidations": slot.idle_invalidation_count,
            "audio_played_ms": (round(ao.played_samples / ao.sample_rate * 1000, 1)
                                if ao else 0),
            # 聲嘴對錶（2026-08-13）：出口丟了幾段遲到畫格、扣住幾次早到畫格、
            # 最後一次量到的畫-聲差。av_resync_frames 長期為 0 ＝對錶沒在工作。
            "av_resync_events": sink.av_resync_events if sink else 0,
            "av_resync_frames": sink.av_resync_frames if sink else 0,
            "av_hold_events": sink.av_hold_events if sink else 0,
            "fast_first_count": slot.fast_first_count,
            "last_av_offset_ms": sink.last_av_offset_ms if sink else None,
        },
        "model_turn_state": {
            "motion_resets": slot.motion_reset_count,
            "motion_reset_failures": slot.motion_reset_failures,
            "seed": TURN_SEED if TURN_SEED >= 0 else None,
            "seed_resets": slot.turn_seed_reset_count,
            "first_chunk_retries": slot.first_chunk_retry_count,
            "first_chunk_retry_failures": slot.first_chunk_retry_failures,
            "first_chunk_align_events": slot.first_chunk_align_events,
            "first_chunk_align_frames": slot.first_chunk_align_frames,
        },
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
