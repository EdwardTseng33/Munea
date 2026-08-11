# -*- coding: utf-8 -*-
"""FlashHead N-slot 本機 smoke test（2026-07-12 卡西法）。

不需要真 GPU、不裝 torch/fastapi/aiortc——deploy/runpod-avatar/flashhead_engine_core.py
本來就零重量依賴，這裡直接 import 真的引擎邏輯（不是重寫一份假的），拿假的
get_audio_embedding/run_pipeline 函式當「假顯卡」驗證：
  1. admission 找空槽 / 滿了擋 / 釋放 / stale-pc 自癒回收
  2. 串線隔離：兩槽同時餵不同音訊，彼此輸出完全不混
  3. 故障隔離：一槽的 pipeline 連續拋錯，不炸整個 process、也不波及另一槽
  4. 換角色（switch_slot_char）互不影響
  5. health_snapshot 的 p50/p95/headroom 數學

跟 scripts/test_flashhead_idle_contract.py 走同一種本機測試風格（純腳本、assert，
main() 印 PASS），沒有 pytest 依賴也能跑：
  python scripts/test_flashhead_multislot.py
"""
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "runpod-avatar"))

import flashhead_engine_core as fec  # noqa: E402


TGT_FPS = 25
MOTION_FRAMES = 2
SLICE_LEN = 24
FRAME_NUM = SLICE_LEN + MOTION_FRAMES
SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CACHED_AUDIO_DURATION = 8
CHUNK_SAMPLES = SLICE_LEN * SAMPLE_RATE // TGT_FPS


class FakeTensor:
    """假的 torch tensor：只需要 [] 切片、.cpu().numpy() 兩個原本程式碼會呼叫的介面。"""
    def __init__(self, arr):
        self.arr = arr

    def __getitem__(self, sl):
        return FakeTensor(self.arr[sl])

    def cpu(self):
        return self

    def numpy(self):
        return self.arr


def make_slot(index, tag):
    """組一個「假裝已經 load() 完成」的 Slot——不呼叫真的 GPU 函式，
    手動填進跟 flashhead_server.py._load_slot 一樣形狀的欄位。"""
    slot = fec.Slot(index)
    slot.pipeline = {"tag": tag}   # 假 pipeline：只是個可以被 mock 函式辨識的標記物件
    slot.char = "a05"
    slot.sample_rate = SAMPLE_RATE
    slot.tgt_fps = TGT_FPS
    slot.frame_num = FRAME_NUM
    slot.motion_frames_num = MOTION_FRAMES
    slot.slice_len = SLICE_LEN
    slot.cached_audio_duration = CACHED_AUDIO_DURATION
    slot.chunk_samples = CHUNK_SAMPLES
    slot.audio_end_idx = CACHED_AUDIO_DURATION * TGT_FPS
    slot.audio_start_idx = slot.audio_end_idx - FRAME_NUM
    cached_len_sum = SAMPLE_RATE * CACHED_AUDIO_DURATION
    import collections
    slot.audio_dq = collections.deque([0.0] * cached_len_sum, maxlen=cached_len_sum)
    slot.load_report = {"chunk_samples": CHUNK_SAMPLES, "chunk_budget_ms": 960.0}
    slot.poster = np.zeros((4, 4, 3), dtype=np.uint8)
    slot.pcs = set()
    slot.pc_created = {}
    slot.sink = fec.FrameSink(TGT_FPS)
    slot.audio_out = fec.AudioOutBuffer(OUTPUT_SAMPLE_RATE, prebuffer_s=0.0)  # 測試不等暖身墊窗
    return slot


def make_mock_pipeline_fns(tag_marker):
    """回傳 (get_audio_embedding, run_pipeline) 假函式——video 輸出裡編碼「這是哪個
    pipeline（tag）生的」，讓串線隔離測試可以直接檢查有沒有混到別槽的資料。"""
    def get_audio_embedding(pipeline, arr, start_idx, end_idx):
        return {"pipeline_tag": pipeline["tag"], "arr_sum": float(np.sum(arr))}

    def run_pipeline(pipeline, emb):
        # 用 pipeline tag 當像素值，方便斷言「這一塊是不是我這槽生的」
        marker = tag_marker[pipeline["tag"]]
        video = np.full((FRAME_NUM, 2, 2, 3), marker, dtype=np.uint8)
        return FakeTensor(video)

    return get_audio_embedding, run_pipeline


def test_admission_find_free_and_full():
    slots = [make_slot(i, "s%d" % i) for i in range(2)]
    pool = fec.SlotPool(slots)
    assert pool.snapshot() == {"limit": 2, "active": 0, "available": True}

    s1 = pool.admit("session-A")
    assert s1 is slots[0]
    assert pool.snapshot()["active"] == 1

    s2 = pool.admit("session-B")
    assert s2 is slots[1]
    assert pool.snapshot() == {"limit": 2, "active": 2, "available": False}

    # 滿了 → 擋（回 None，路由層據此回 429，跟改造前單例版邏輯一致）
    s3 = pool.admit("session-C")
    assert s3 is None, "pool full must reject new admission"
    print("test_admission_find_free_and_full: PASS")


def test_admission_release_and_reclaim():
    slots = [make_slot(0, "s0")]
    pool = fec.SlotPool(slots)
    pool.admit("session-A")
    assert pool.snapshot()["active"] == 1

    released = pool.release("session-A")
    assert released is slots[0]
    assert pool.snapshot() == {"limit": 1, "active": 0, "available": True}

    # 釋放後可以再 admit（單槽場景，等同改造前單例版「掛斷後下一位可進來」）
    s = pool.admit("session-B")
    assert s is slots[0]
    print("test_admission_release_and_reclaim: PASS")


def test_admission_honors_durable_preferred_slot():
    slots = [make_slot(i, "s%d" % i) for i in range(3)]
    pool = fec.SlotPool(slots)
    picked = pool.admit("call-slot-3", preferred_index=2)
    assert picked is slots[2]
    assert slots[0].active_session is None and slots[1].active_session is None
    assert pool.admit("duplicate-slot-3", preferred_index=2) is None
    assert pool.admit("invalid-slot", preferred_index=99) is None
    print("test_admission_honors_durable_preferred_slot: PASS")


def test_admission_stale_pc_self_heal():
    """逐行對照舊版：pc.connectionState in (closed, failed) 時才可回收；
    pc is None（還在交握中）視為忙碌，不可回收——這條分支決定 429 或放行。"""
    class FakePC:
        def __init__(self, state):
            self.connectionState = state

    slots = [make_slot(0, "s0")]
    pool = fec.SlotPool(slots)
    slot = pool.admit("session-A")
    assert slot is not None

    # pc 還沒建立（active_pc is None）→ 視為忙碌，第二個人必須被拒絕
    assert pool.admit("session-B") is None, "pc is None must be treated as busy, not reclaimable"

    # pc 已經 closed → 可以回收給下一位
    slot.active_pc = FakePC("closed")
    reclaimed = pool.admit("session-C")
    assert reclaimed is slot
    assert slot.active_session == "session-C"
    print("test_admission_stale_pc_self_heal: PASS")


def test_health_n1_shape_matches_capacity_contract():
    """N=1 時 /health 的 capacity 欄位必須跟改造前單例版「一字不差」。"""
    slot = make_slot(0, "s0")
    pool = fec.SlotPool([slot])
    snap = pool.snapshot()
    assert snap == {"limit": 1, "active": 0, "available": True}
    pool.admit("session-A")
    snap = pool.snapshot()
    assert snap == {"limit": 1, "active": 1, "available": False}
    print("test_health_n1_shape_matches_capacity_contract: PASS")


def _drain_all(feeder, n_max=50):
    """測試用：不啟動背景 thread（auto_start=False），手動把 feeder.acc 裡累積的音訊
    一塊一塊 drain 掉（模擬 _loop() 該做的事），這樣測試才是同步、確定性的。"""
    cs = feeder.slot.chunk_samples
    n = 0
    while len(feeder.acc) >= cs and n < n_max:
        with feeder.lock:
            chunk = feeder.acc[:cs].copy()
            output_samples = min(len(feeder.acc_out), int(round(cs * feeder.sr_in / feeder.sr_eng)))
            output_pcm = feeder.acc_out[:output_samples].copy()
            feeder.acc = feeder.acc[cs:]
            feeder.acc_out = feeder.acc_out[output_samples:]
            feeder.consumed += cs
        feeder._gen_chunk(chunk, cs, output_pcm)
        n += 1
    return n


def test_cross_slot_isolation():
    """串線隔離核心測試：2 槽各自餵不同音訊，槽 A 的 sink/audio_out 絕不能出現
    槽 B 的資料（正是 Modal max_inputs=20 那個「互看臉」bug 的正面回歸測試）。"""
    slot_a = make_slot(0, "sA")
    slot_b = make_slot(1, "sB")
    tag_marker = {"sA": 11, "sB": 222}
    emb_fn, run_fn = make_mock_pipeline_fns(tag_marker)

    feeder_a = fec.Feeder(slot_a, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
    feeder_b = fec.Feeder(slot_b, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
    slot_a.feeder = feeder_a
    slot_b.feeder = feeder_b

    # 各塞 2 塊份量的音訊進各自 feeder
    pcm_a = (np.ones(CHUNK_SAMPLES * 2, dtype=np.float32) * 0.1 * 32768).astype(np.int16).tobytes()
    pcm_b = (np.ones(CHUNK_SAMPLES * 2, dtype=np.float32) * -0.1 * 32768).astype(np.int16).tobytes()
    # push24k 的取樣率轉換用 sr_in=24000 -> sr_eng=16000，這裡兩個 feeder 建構時
    # sr_in/sr_eng 用預設 24000/16000，塞 24k 規格的 bytes 進去換算成 16k
    feeder_a.push24k(pcm_a)
    feeder_b.push24k(pcm_b)

    n_a = _drain_all(feeder_a)
    n_b = _drain_all(feeder_b)
    assert n_a >= 1 and n_b >= 1, "both slots should have generated at least one chunk"

    # 槽 A 的畫面像素值只能是 marker 11，絕不能出現槽 B 的 222
    frame_a = slot_a.sink.pop()
    frame_b = slot_b.sink.pop()
    assert frame_a is not None and frame_b is not None
    assert np.all(frame_a == 11), "slot A frame must only contain slot A's marker"
    assert np.all(frame_b == 222), "slot B frame must only contain slot B's marker"
    assert not np.any(frame_a == 222), "slot A must never see slot B's data"
    assert not np.any(frame_b == 11), "slot B must never see slot A's data"

    # audio_out 也要各自獨立（互不共用 buffer 物件）
    assert slot_a.audio_out is not slot_b.audio_out
    assert slot_a.sink is not slot_b.sink
    print("test_cross_slot_isolation: PASS")


def test_audible_output_keeps_original_24k_samples():
    slot = make_slot(0, "s0")
    emb_fn, run_fn = make_mock_pipeline_fns({"s0": 42})
    feeder = fec.Feeder(slot, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
    original = (np.sin(np.linspace(0, 20 * np.pi, 40000)) * 12000).astype(np.int16)

    feeder.push24k(original.tobytes())
    expected_total = len(original)
    assert slot.audio_out.depth_samples == expected_total
    assert np.array_equal(slot.audio_out.buf, original)
    assert _drain_all(feeder, n_max=1) == 1

    assert slot.audio_out.sample_rate == OUTPUT_SAMPLE_RATE
    assert slot.audio_out.depth_samples == expected_total, "rendering must not duplicate or consume PCM"
    assert np.array_equal(slot.audio_out.buf, original)
    print("test_audible_output_keeps_original_24k_samples: PASS")


def test_audio_ingress_waits_for_video_once_then_stays_continuous():
    original_time = fec.time.time
    clock = [300.0]
    fec.time.time = lambda: clock[0]
    try:
        slot = make_slot(0, "s0")
        slot.audio_out = fec.AudioOutBuffer(OUTPUT_SAMPLE_RATE, prebuffer_s=0.2)
        emb_fn, run_fn = make_mock_pipeline_fns({"s0": 42})
        feeder = fec.Feeder(slot, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
        pcm = np.arange(OUTPUT_SAMPLE_RATE * 2, dtype=np.int16)
        feeder.push24k(pcm.tobytes())

        assert slot.audio_out.playout_held() is True
        before = slot.audio_out.depth_samples
        assert np.count_nonzero(slot.audio_out.pop_frame()) == 0
        assert slot.audio_out.depth_samples == before

        assert _drain_all(feeder, n_max=1) == 1
        assert slot.audio_out.playout_held() is True
        clock[0] += slot.audio_out.last_prebuffer_s
        first = slot.audio_out.pop_frame()
        assert np.array_equal(first, pcm[:slot.audio_out.frame_samples])
        assert slot.audio_out.played_samples == slot.audio_out.frame_samples
        assert slot.audio_out.underrun_count == 0
        slot.audio_out.clear()
        assert slot.audio_out.played_samples == 0
    finally:
        fec.time.time = original_time
    print("test_audio_ingress_waits_for_video_once_then_stays_continuous: PASS")


def test_real_audio_invalidates_inflight_idle_frames():
    """待機 GPU 還在跑時真語音抵達，晚到的待機畫格不得插在嘴型前面。"""
    slot = make_slot(0, "s0")
    feeder_holder = {}
    real_pcm = np.full(2400, 1200, dtype=np.int16)

    def emb_fn(pipeline, arr, start_idx, end_idx):
        return {"pipeline_tag": pipeline["tag"]}

    def run_fn(pipeline, emb):
        feeder_holder["feeder"].push24k(real_pcm.tobytes())
        video = np.full((FRAME_NUM, 2, 2, 3), 77, dtype=np.uint8)
        return FakeTensor(video)

    feeder = fec.Feeder(slot, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
    feeder_holder["feeder"] = feeder
    slot.feeder = feeder
    feeder._idle_on = True
    idle_seq = feeder._real_input_seq

    feeder._gen_chunk(
        np.zeros(CHUNK_SAMPLES, dtype=np.float32),
        emit_audio=False,
        idle_input_seq=idle_seq,
    )

    assert slot.sink.depth() == 0, "late idle frames must be discarded after real PCM arrives"
    assert slot.audio_out.depth_samples == len(real_pcm), "real PCM must remain queued"
    assert len(slot.audio_dq) == slot.audio_dq.maxlen, (
        "real input must preserve the model's fixed-length embedding context"
    )
    assert feeder._round_pending is True, "idle work must not consume the real turn first-frame marker"
    assert slot.idle_invalidation_count == 1, "health gate must expose the handled idle/real race"
    print("test_real_audio_invalidates_inflight_idle_frames: PASS")


def test_lip_catchup_skips_only_expired_frames():
    assert fec.lip_catchup_frame_count(0.0, 0.0, 0.0, 24, 25) == 0
    assert fec.lip_catchup_frame_count(1.0, 0.2, 0.4, 24, 25) == 20
    assert fec.lip_catchup_frame_count(10.0, 0.0, 0.0, 8, 25) == 6
    assert fec.lip_catchup_frame_count(1.0, 0.0, None, 8, 25) == 0
    print("test_lip_catchup_skips_only_expired_frames: PASS")


def test_lip_timeline_survives_mid_turn_pause():
    original_time = fec.time.time
    clock = [500.0]
    fec.time.time = lambda: clock[0]
    try:
        slot = make_slot(0, "s0")
        emb_fn, run_fn = make_mock_pipeline_fns({"s0": 42})
        feeder = fec.Feeder(slot, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
        pcm = np.arange(OUTPUT_SAMPLE_RATE // 10, dtype=np.int16)
        feeder.push24k(pcm.tobytes())
        assert feeder.timeline_base_s == 0.0

        with slot.audio_out.lock:
            slot.audio_out.buf = np.zeros(0, dtype=np.int16)
            slot.audio_out.depth_samples = 0
            slot.audio_out.played_samples = len(pcm)
        clock[0] += 1.0
        feeder.push24k(pcm.tobytes())
        assert round(feeder.timeline_base_s, 3) == 0.1
    finally:
        fec.time.time = original_time
    print("test_lip_timeline_survives_mid_turn_pause: PASS")


def test_new_round_marker_waits_for_its_own_gpu_chunk():
    """An older GPU chunk must not consume a marker created after it started."""
    original_time = fec.time.time
    clock = [100.0]
    fec.time.time = lambda: clock[0]
    try:
        slot = make_slot(0, "s0")
        emb_fn, run_fn = make_mock_pipeline_fns({"s0": 42})
        feeder = fec.Feeder(slot, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
        base_sink = slot.sink

        class MarkerInterleavingSink:
            def depth(self):
                return base_sink.depth()

            def push_many(self, frames, ready_ts=None, fps=None):
                base_sink.push_many(frames, ready_ts, fps)
                # Simulate PCM ingress starting round 2 after this old chunk's
                # t_frames_ready was captured but before its metric is recorded.
                feeder._round_pending = True
                slot.round_count = 2
                slot.round_start_ts = 101.0

        slot.sink = MarkerInterleavingSink()
        feeder._round_pending = True
        slot.round_count = 1
        slot.round_start_ts = 99.0
        feeder._gen_chunk(np.zeros(CHUNK_SAMPLES, dtype=np.float32), emit_audio=True)
        assert list(slot.round_latencies) == [], "old chunk must not emit a negative latency"
        assert feeder._round_pending is True, "newer marker must remain pending"

        slot.sink = base_sink
        clock[0] = 101.5
        feeder._gen_chunk(np.zeros(CHUNK_SAMPLES, dtype=np.float32), emit_audio=True)
        assert list(slot.round_latencies) == [500.0]
        assert feeder._round_pending is False
    finally:
        fec.time.time = original_time
    print("test_new_round_marker_waits_for_its_own_gpu_chunk: PASS")


def test_audio_finish_does_not_count_natural_tail_as_underrun():
    slot = make_slot(0, "s0")
    emb_fn, run_fn = make_mock_pipeline_fns({"s0": 42})
    feeder = fec.Feeder(slot, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
    pcm = np.arange(slot.audio_out.frame_samples, dtype=np.int16)
    feeder.push24k(pcm.tobytes())
    slot.audio_out.release_playout()
    feeder.finish()
    assert np.array_equal(slot.audio_out.pop_frame(), pcm)
    slot.audio_out.pop_frame()
    assert slot.audio_out.underrun_count == 0
    assert slot.audio_out._turn_complete is True
    print("test_audio_finish_does_not_count_natural_tail_as_underrun: PASS")


def test_audio_prebuffer_starts_when_first_pcm_arrives():
    """模型計算時間不能偷吃預緩衝；第一批 PCM 到達後才開始共同起播倒數。"""
    original_time = fec.time.time
    clock = [100.0]
    fec.time.time = lambda: clock[0]
    try:
        audio = fec.AudioOutBuffer(OUTPUT_SAMPLE_RATE, prebuffer_s=0.5)
        assert audio.playout_held() is True

        clock[0] = 103.0
        pcm = np.arange(audio.frame_samples, dtype=np.int16)
        audio.push(pcm)
        assert audio.hold_until_ts == 103.5
        assert audio.playout_held() is True

        before = audio.depth_samples
        clock[0] = 103.49
        assert np.count_nonzero(audio.pop_frame()) == 0
        assert audio.depth_samples == before, "prebuffer must not consume queued PCM"

        clock[0] = 103.5
        assert np.array_equal(audio.pop_frame(), pcm)
        audio.clear()
        assert audio.playout_held() is True, "each real turn must re-arm the shared gate"

        audio.arm_prebuffer(1.0)
        clock[0] = 104.0
        audio.push(pcm)
        assert audio.hold_until_ts == 105.0
        assert audio.last_prebuffer_s == 1.0
        audio.clear()
        clock[0] = 106.0
        audio.push(pcm)
        assert audio.hold_until_ts == 106.5, "opening delay must be one-shot"
        assert audio.last_prebuffer_s == 0.5
    finally:
        fec.time.time = original_time
    print("test_audio_prebuffer_starts_when_first_pcm_arrives: PASS")


def test_audio_prebuffer_adapts_without_counting_natural_silence():
    """Only real starvation raises 200-350 ms; stable turns decay it."""
    original_time = fec.time.time
    clock = [200.0]
    fec.time.time = lambda: clock[0]
    try:
        audio = fec.AudioOutBuffer(
            OUTPUT_SAMPLE_RATE,
            prebuffer_s=0.2,
            adaptive_min_s=0.2,
            adaptive_max_s=0.35,
        )
        pcm = np.arange(audio.frame_samples, dtype=np.int16)

        for compute_ms in (450.0, 470.0, 480.0):
            audio.observe_generation(compute_ms, 960.0)
        audio.push(pcm)
        assert audio.last_prebuffer_s == 0.2

        clock[0] = 200.2
        assert np.array_equal(audio.pop_frame(), pcm)
        clock[0] = 200.22
        audio.pop_frame()
        audio.pop_frame()
        assert audio.underrun_count == 1, "one starvation gap must be one event, not 20ms ticks"

        clock[0] = 200.30
        audio.push(pcm)
        assert list(audio.underrun_gap_ms)[-1] == 80.0
        assert round(audio.adaptive_prebuffer_s, 2) == 0.25

        audio.mark_input_complete()
        audio.pop_frame()
        audio.pop_frame()
        assert audio.underrun_count == 1, "natural response-end silence is not an underrun"

        audio.clear()
        for compute_ms in (900.0, 910.0, 920.0):
            audio.observe_generation(compute_ms, 960.0)
        audio.push(pcm)
        assert audio.last_prebuffer_s == 0.25, "slow compute alone must not add fixed wait"

        # Three genuinely stable turns remove the one underrun increment.
        for _ in range(3):
            audio.mark_input_complete()
            audio.clear()
            audio.push(pcm)
        assert audio.adaptive_prebuffer_s == 0.2

        audio.clear()
        audio.arm_prebuffer(0.6)
        audio.push(pcm)
        assert audio.last_prebuffer_s == 0.6, "opening one-shot must override adaptation"

        cold_start = fec.AudioOutBuffer(
            OUTPUT_SAMPLE_RATE,
            prebuffer_s=0.7,
            adaptive_min_s=0.2,
            adaptive_max_s=0.35,
        )
        for compute_ms in (1152.8, 465.0, 430.0, 440.0, 471.3, 450.0, 455.0, 460.0, 468.0):
            cold_start.observe_generation(compute_ms, 960.0)
        assert cold_start.generation_p95_ms == 471.3
        assert cold_start.adaptive_prebuffer_s == 0.2, (
            "one cold-start maximum must not erase the steady-state latency gain"
        )
    finally:
        fec.time.time = original_time
    print("test_audio_prebuffer_adapts_without_counting_natural_silence: PASS")


def test_fault_isolation_one_slot_does_not_crash_others():
    """故障隔離：槽 A 的 pipeline 連續拋錯 -> 標 unhealthy、觸發 on_unhealthy 回調、
    但不拋例外炸掉呼叫者，且完全不影響槽 B（獨立物件，槽 B 的 feeder/sink 正常運作）。"""
    slot_a = make_slot(0, "sA")
    slot_b = make_slot(1, "sB")

    def broken_get_audio_embedding(pipeline, arr, start_idx, end_idx):
        raise RuntimeError("simulated OOM on slot " + pipeline["tag"])

    def broken_run_pipeline(pipeline, emb):
        raise AssertionError("should never reach run_pipeline if embedding already broken")

    ok_marker = {"sB": 77}
    ok_emb_fn, ok_run_fn = make_mock_pipeline_fns(ok_marker)

    unhealthy_calls = []
    feeder_a = fec.Feeder(slot_a, broken_get_audio_embedding, broken_run_pipeline,
                          sr_eng=SAMPLE_RATE, fault_streak_limit=3,
                          on_unhealthy=lambda s: unhealthy_calls.append(s.index),
                          auto_start=False)
    feeder_b = fec.Feeder(slot_b, ok_emb_fn, ok_run_fn, sr_eng=SAMPLE_RATE, auto_start=False)
    slot_a.feeder = feeder_a
    slot_b.feeder = feeder_b

    pcm_a = (np.ones(CHUNK_SAMPLES * 5, dtype=np.float32) * 0.1 * 32768).astype(np.int16).tobytes()
    pcm_b = (np.ones(CHUNK_SAMPLES * 2, dtype=np.float32) * 0.1 * 32768).astype(np.int16).tobytes()
    feeder_a.push24k(pcm_a)
    feeder_b.push24k(pcm_b)

    # drain 槽 A：每塊都拋錯，_gen_chunk 內部要吞掉例外，不能往外炸
    n_a = _drain_all(feeder_a, n_max=5)
    assert n_a >= 3, "should have attempted enough chunks to trip the fault streak"
    assert slot_a.healthy is False, "slot A must be marked unhealthy after repeated faults"
    assert slot_a.fault_count >= 3
    assert unhealthy_calls == [0], "on_unhealthy callback must fire exactly for slot A"
    # 壞掉的槽不該有任何畫面被推進 sink（寧可沒畫面，也不留半殘資料）
    assert slot_a.sink.count == 0

    # 槽 B 完全不受影響：正常生成、frame 資料正確
    n_b = _drain_all(feeder_b)
    assert n_b >= 1
    frame_b = slot_b.sink.pop()
    assert frame_b is not None and np.all(frame_b == 77)
    assert slot_b.healthy is True
    assert slot_b.fault_count == 0
    print("test_fault_isolation_one_slot_does_not_crash_others: PASS")


def test_switch_slot_char_isolation():
    """換角色互斥鎖只綁該 slot：切 A 槽角色不動 B 槽；失敗要 revert 回原角色；
    不支援的角色回 False、不留副作用。"""
    slot_a = make_slot(0, "sA")
    slot_b = make_slot(1, "sB")
    char_src_map = {"a05": "/fake/a05.png", "a06": "/fake/a06.png"}

    calls = []

    def get_base_data_fn(pipeline, cond_image_path_or_dir, base_seed, use_face_crop):
        calls.append((pipeline["tag"], cond_image_path_or_dir))

    def load_poster_fn(path):
        return np.array([[path]])

    ok = fec.switch_slot_char(slot_a, "a06", char_src_map, get_base_data_fn, load_poster_fn)
    assert ok is True
    assert slot_a.char == "a06"
    assert slot_b.char == "a05", "switching slot A must not touch slot B"
    assert calls == [("sA", "/fake/a06.png")]

    # 不支援的角色 -> False，且不改動狀態
    ok2 = fec.switch_slot_char(slot_a, "does-not-exist", char_src_map, get_base_data_fn, load_poster_fn)
    assert ok2 is False
    assert slot_a.char == "a06", "unsupported char must not change slot state"

    # get_base_data 失敗 -> revert 回原角色
    def failing_get_base_data(pipeline, cond_image_path_or_dir, base_seed, use_face_crop):
        # switch target(a05)呼叫要失敗、revert 回原角色(a06)呼叫要成功——
        # 這樣才驗得到「switch 失敗必須 revert 回原角色」這條路徑
        if cond_image_path_or_dir == char_src_map["a06"]:
            calls.append(("revert", cond_image_path_or_dir))
            return
        raise RuntimeError("simulated switch failure")

    ok3 = fec.switch_slot_char(slot_a, "a05", char_src_map, failing_get_base_data, load_poster_fn)
    assert ok3 is False
    assert slot_a.char == "a06", "failed switch must revert to previous char"
    print("test_switch_slot_char_isolation: PASS")


def test_health_snapshot_math():
    slot = make_slot(0, "sA")
    slot.slice_len = 24
    slot.tgt_fps = 25   # budget_ms = 24/25*1000 = 960.0
    for ms in [300.0, 310.0, 320.0, 900.0, 305.0]:
        slot.gen_compute_ms_hist.append(ms)
    slot.last_gen_compute_ms = 305.0
    slot.frame_width = 768
    slot.frame_height = 768
    slot.round_count = 3
    slot.round_latencies.extend([480.0, 520.0])
    slot.idle_invalidation_count = 2
    body = fec.health_snapshot(slot, wake_ts=time.time() - 10)
    assert body["gen_compute_ms_rolling"]["budget_ms"] == 960.0
    assert body["gen_compute_ms_rolling"]["n_samples"] == 5
    assert body["gen_compute_ms_rolling"]["p50"] == 310.0
    # p95 of [300,305,310,320,900] sorted -> idx = max(0, int(5*0.95)-1) = max(0,3) = 3 -> 320.0
    assert body["gen_compute_ms_rolling"]["p95"] == 320.0
    expect_headroom = round((1 - 320.0 / 960.0) * 100, 1)
    assert body["gen_compute_ms_rolling"]["headroom_p95_pct"] == expect_headroom
    assert 9.9 <= body["uptime_s"] <= 10.5
    assert body["round_count"] == 3
    assert body["round_latency_integrity"] == {
        "negative_count": 0,
        "min_ms": 480.0,
    }
    assert body["frames"] == 0
    assert body["output_resolution"] == {"width": 768, "height": 768}
    assert body["video_underrun"]["count"] == 0
    assert body["audio_sender"] == {
        "rebase_count": 0,
        "max_late_ms": 0.0,
        "recent_late_ms": [],
    }
    assert body["video_sync"] == {
        "catchup_events": 0,
        "catchup_frames": 0,
        "idle_invalidations": 2,
        "audio_played_ms": 0.0,
    }
    assert body["model_turn_state"] == {
        "motion_resets": 0,
        "motion_reset_failures": 0,
        "seed": 42,
        "seed_resets": 0,
        "first_chunk_retries": 0,
        "first_chunk_retry_failures": 0,
    }
    print("test_health_snapshot_math: PASS")


def test_audio_sender_late_wakeup_rebases_without_skipping_pts():
    started = 10.0
    sample_rate = 24000
    next_pts = 4800
    target = started + next_pts / sample_rate

    unchanged, late_ms, rebased = fec.pace_audio_sender_clock(
        started, next_pts, sample_rate, target + 0.02
    )
    assert unchanged == started and late_ms == 20.0 and not rebased

    adjusted, late_ms, rebased = fec.pace_audio_sender_clock(
        started, next_pts, sample_rate, target + 0.10
    )
    assert rebased and late_ms == 100.0
    assert round(adjusted + next_pts / sample_rate, 6) == round(target + 0.10, 6)
    # PTS remains next_pts; only the wall-clock anchor moves, so the next 20 ms
    # frame is paced 20 ms later instead of being returned immediately.
    assert round(adjusted + (next_pts + 480) / sample_rate, 6) == round(target + 0.12, 6)
    print("test_audio_sender_late_wakeup_rebases_without_skipping_pts: PASS")


def test_frame_size_contract():
    for value in ("512", 640, "768"):
        assert fec.parse_frame_size(value) == int(value)
    for value in (None, "720", 800, "large"):
        try:
            fec.parse_frame_size(value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid frame size must fail: " + repr(value))
    print("test_frame_size_contract: PASS")


def test_force_release_slot_used_by_unhealthy_path():
    """驗 SlotPool.force_release_slot：不管 pc 物件比對，直接清空占用
    （flashhead_server.py._on_slot_unhealthy 會呼叫這支，讓壞掉的槽立刻可以
    被跳過、不會一直卡著一個「看起來占用中但其實壞掉」的假席位）。"""
    class FakePC:
        connectionState = "connected"

    slot = make_slot(0, "sA")
    pool = fec.SlotPool([slot])
    pool.admit("session-A")
    slot.active_pc = FakePC()
    slot.healthy = False   # 模擬故障隔離判定
    pool.force_release_slot(slot)
    assert slot.active_session is None
    assert slot.active_pc is None
    # 槽被標 unhealthy，即使已釋放，admit() 也不該再把新使用者配進來
    assert pool.admit("session-B") is None, "unhealthy slot must stay excluded from admission"
    print("test_force_release_slot_used_by_unhealthy_path: PASS")


def test_antiflicker_freezes_static_background_keeps_motion():
    """時間穩定器（2026-07-24 待機背景微閃爍修正）：
    1. 背景 ±2 階微雜訊 -> 凍住（輸出跟第一張完全一致）
    2. 真動作（0<->200 大幅變化）-> 照常通過、不被凍
    3. reset() 清基準 -> 下一張原樣通過、不跟舊一輪畫面混合"""
    slot = make_slot(0, "s0")
    emb_fn, run_fn = make_mock_pipeline_fns({"s0": 42})
    feeder = fec.Feeder(slot, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)

    rng = np.random.default_rng(7)
    base = np.full((8, 8, 3), 120, dtype=np.uint8)
    n = 6
    frames = np.zeros((n, 8, 8, 3), dtype=np.uint8)
    for i in range(n):
        # Keep the synthetic background inside ANTIFLICKER_LO. The old -2..2
        # range could differ by four levels between adjacent frames, which is
        # deliberately blended (not frozen) by the production filter and made
        # this assertion fail deterministically under the real 1/8 defaults.
        noise = rng.integers(-1, 1, size=(8, 8, 3))
        frames[i] = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        # 「嘴巴」那格做真動作：0 <-> 200 交替（差異遠超 AF_HI，必須通過）
        frames[i, 6, 6] = 200 if i % 2 == 0 else 0

    out = feeder._stabilize(frames.copy(), feeder._epoch)

    bg = np.ones((8, 8), dtype=bool)
    bg[6, 6] = False
    for i in range(1, n):
        assert np.array_equal(out[i][bg], out[0][bg]), \
            "frame %d: static background noise must be frozen" % i
    mouth = [int(out[i][6, 6, 0]) for i in range(n)]
    assert max(mouth) > 150 and min(mouth) < 50, "real motion must pass through"

    feeder.reset()
    assert feeder._prev_frame is None, "reset must clear the stabilizer baseline"
    fresh = np.full((1, 8, 8, 3), 10, dtype=np.uint8)
    out2 = feeder._stabilize(fresh.copy(), feeder._epoch)
    assert np.array_equal(out2[0], fresh[0]), "first frame after reset must pass unchanged"

    # cv2 快路徑與 numpy 備援必須輸出完全一致（含中間混合帶）
    try:
        import cv2
    except ImportError:
        cv2 = None
    if cv2 is not None:
        prev = rng.integers(0, 255, size=(32, 32, 3)).astype(np.uint8)
        # 差異值刻意覆蓋 0..30：涵蓋凍住帶 / 混合帶 / 放行帶
        cur = np.clip(prev.astype(np.int16)
                      + rng.integers(-30, 31, size=(32, 32, 3)), 0, 255).astype(np.uint8)
        got_np = fec.stabilize_frame(prev.copy(), cur.copy(), None)
        got_cv = fec.stabilize_frame(prev.copy(), cur.copy(), cv2)
        assert np.array_equal(got_np, got_cv), "cv2 and numpy paths must agree exactly"
    print("test_antiflicker_freezes_static_background_keeps_motion: PASS")


def test_turn_reset_restores_model_motion_seed_once():
    """A new assistant turn resets model motion; character switching does not deadlock."""
    slot = make_slot(0, "s0")

    class MotionPipeline:
        def __init__(self):
            self.person_name = "munea"
            self.calls = []
            self.generator = self
            self.seeds = []

        def reset_person_name(self, person_name=None):
            self.calls.append(person_name)

        def manual_seed(self, seed):
            self.seeds.append(seed)

    pipeline = MotionPipeline()
    slot.pipeline = pipeline
    emb_fn, run_fn = make_mock_pipeline_fns({"s0": 42})
    feeder = fec.Feeder(slot, emb_fn, run_fn, sr_eng=SAMPLE_RATE, auto_start=False)

    feeder.reset()
    assert pipeline.calls == ["munea"]
    assert pipeline.seeds == [42]
    assert slot.motion_reset_count == 1
    assert slot.turn_seed_reset_count == 1
    assert slot.motion_reset_failures == 0

    feeder.reset(reset_pipeline_motion=False)
    assert pipeline.calls == ["munea"], "character switch owns the model reset"
    assert pipeline.seeds == [42], "character switch owns the generator reset"
    assert slot.motion_reset_count == 1
    assert slot.turn_seed_reset_count == 1
    print("test_turn_reset_restores_model_motion_seed_once: PASS")


def test_first_chunk_quality_metrics_detect_static_speech():
    quiet = np.zeros(2400, dtype=np.int16)
    speech = np.full(2400, 5000, dtype=np.int16)
    assert fec.pcm_rms(quiet) == 0.0
    assert fec.pcm_rms(speech) > fec.FIRST_CHUNK_SPEECH_RMS

    frames = np.zeros((4, 100, 100, 3), dtype=np.uint8)
    assert fec.mouth_motion_peak(frames) == 0.0
    assert fec.first_chunk_av_skew_ms(frames, speech, fps=25) == float("inf")
    frames[1, 60:65, 45:55] = 255
    assert fec.mouth_motion_peak(frames) > fec.FIRST_CHUNK_MOUTH_MOTION
    assert fec.first_chunk_av_skew_ms(frames, speech, fps=25) == 40.0
    print("test_first_chunk_quality_metrics_detect_static_speech: PASS")


def test_retry_prebuffer_is_bounded_and_stricter_than_steady_state():
    assert 0.27 < fec.FIRST_CHUNK_RETRY_PREBUFFER_S <= 0.5
    assert fec.FIRST_CHUNK_MOUTH_MOTION >= 0.015
    print("test_retry_prebuffer_is_bounded_and_stricter_than_steady_state: PASS")


def main():
    test_admission_find_free_and_full()
    test_admission_release_and_reclaim()
    test_admission_honors_durable_preferred_slot()
    test_admission_stale_pc_self_heal()
    test_health_n1_shape_matches_capacity_contract()
    test_cross_slot_isolation()
    test_audible_output_keeps_original_24k_samples()
    test_audio_ingress_waits_for_video_once_then_stays_continuous()
    test_real_audio_invalidates_inflight_idle_frames()
    test_lip_catchup_skips_only_expired_frames()
    test_lip_timeline_survives_mid_turn_pause()
    test_new_round_marker_waits_for_its_own_gpu_chunk()
    test_audio_finish_does_not_count_natural_tail_as_underrun()
    test_audio_prebuffer_starts_when_first_pcm_arrives()
    test_audio_prebuffer_adapts_without_counting_natural_silence()
    test_fault_isolation_one_slot_does_not_crash_others()
    test_switch_slot_char_isolation()
    test_health_snapshot_math()
    test_audio_sender_late_wakeup_rebases_without_skipping_pts()
    test_frame_size_contract()
    test_force_release_slot_used_by_unhealthy_path()
    test_antiflicker_freezes_static_background_keeps_motion()
    test_turn_reset_restores_model_motion_seed_once()
test_first_chunk_quality_metrics_detect_static_speech()
test_retry_prebuffer_is_bounded_and_stricter_than_steady_state()
print("FlashHead multi-slot smoke test: ALL PASS")


if __name__ == "__main__":
    main()
