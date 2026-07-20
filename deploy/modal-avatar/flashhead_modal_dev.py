# -*- coding: utf-8 -*-
"""沐寧 · FlashHead 雲端臉引擎試作版（Modal 快照秒醒 · 2026-07-10）

跟現役 munea-nening-avatar[-dev]（Ditto 引擎）完全並行、互不影響：
- 不同 Modal App 名（munea-flashhead-avatar-dev）
- 不同置物櫃（soulx-flashhead-models，早先 5/22 探索時已下載好權重、這次直接掛用不必重抓）
- 不動現役任何檔案/服務

引擎＝SoulX-FlashHead-1_3B Lite（7/10 RunPod 兩輪 PoC 已驗證：穩態 96FPS/3.8x 即時於 4090、
4.3 分鐘長講零漂移、Edward 看片驗收通過 B 版裁切框）。這版把它包成常駐通話服務骨架，
照抄 nening_modal_dev.py 的形狀：暖管線 + Modal 記憶體/GPU 快照 + WebRTC 影像出 +
/health /offer /audio 接口 + MUNEA_APP_KEY 門禁。

裝機雷防（RunPod 兩輪踩過、這裡直接照修，不重踩）：
1. mediapipe==0.10.9 在 py3.12 無 wheel，放寬到 >=0.10.13（我們固定不開 use_face_crop，
   舊版 API mediapipe.solutions 有沒有都不影響，輸入圖已是預裁好的 512x512）
2. requirements.txt 釘的 nvidia-nccl-cu12==2.27.3 跟 torch 自帶的 2.26.2 衝突，直接砍掉該行
3. pip 解依賴時會把 cu128 torch 換成 PyPI 預設 cu126 版（xformers==0.0.31 的 torch==2.7.1
   精確 pin 觸發），全部裝完後最後一步用 --no-deps 強制校正回 cu128
4. flash-attn 用官方 GitHub release 預編譯 wheel，下載時保留完整檔名，不然 pip 認不得
5. requirements.txt 同時裝 opencv-python + opencv-python-headless + opencv-contrib-python，
   非 headless 版需要 libGL.so.1（Modal debian_slim 沒有）——先 apt_install libgl1 libglib2.0-0
   （這條 RunPod 沒踩到是因為那邊的基礎映像本來就帶；Modal debian_slim 精簡、必須自己補）
6. 【關鍵】torch.compile(COMPILE_MODEL/COMPILE_VAE) 在 L4 首塊冷編譯要 1010 秒(16.8分鐘、
   比 4090 的 170 秒慢近 6 倍)，且 Modal GPU 記憶體快照對編譯後的 CUDA graph 狀態存不進去
   （"Failed creating Function memory snapshot"、會無限重試、每次重試都重付一次 17 分鐘
   的代價——實測燒了約 US$0.70 才發現）。修法：在 get_pipeline() 之前 monkey-patch
   flash_head.src.pipeline.flash_head_pipeline.COMPILE_MODEL/COMPILE_VAE = False，
   改 eager 模式——load 從 1129 秒降到 36 秒、快照也真的建成功了（"Snapshot created.
   Restoring Function from memory snapshot."）。代價：穩態每塊變慢（eager ~0.77s vs
   compile 模式 4090 上約 0.25s），但 L4 eager 模式仍在 960ms 預算內（p95 787.8ms、
   realtime_multiple 1.23x）——用比較慢但穩定可預測的路線，換掉快但會炸的路線。

用法：
  modal deploy -m flashhead_modal_dev     # 蓋映像加上線
  python probe_flashhead.py               # 快照喚醒/穩態耗時/換角色耗時 掐錶
App 端/測試網頁：疊圖合成在客戶端做，伺服器只吐 512x512 原尺寸影格。
"""
import os

import modal

app = modal.App("munea-flashhead-avatar-dev")

vol = modal.Volume.from_name("soulx-flashhead-models", create_if_missing=False)

_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".munea-app-key")
APP_KEY = ""
try:
    APP_KEY = open(_KEY_FILE, encoding="utf-8").read().strip()
except Exception:
    pass

FLASH_ATTN_WHL = "flash_attn-2.8.0.post2+cu12torch2.7cxx11abiTRUE-cp312-cp312-linux_x86_64.whl"
FLASH_ATTN_URL = "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.0.post2/" + FLASH_ATTN_WHL
CHAR_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "wget", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.7.1", "torchvision==0.22.1",
                 index_url="https://download.pytorch.org/whl/cu128")
    .run_commands(
        "git clone --depth 1 https://github.com/Soul-AILab/SoulX-FlashHead.git /root/SoulX-FlashHead",
        "cd /root/SoulX-FlashHead && "
        "sed -i 's/mediapipe==0.10.9/mediapipe>=0.10.13/' requirements.txt && "
        "sed -i '/nvidia-nccl-cu12/d' requirements.txt && "
        "pip install --ignore-installed -r requirements.txt",
        "pip install ninja",
        "wget -q " + FLASH_ATTN_URL + " -O /root/" + FLASH_ATTN_WHL + " && pip install /root/" + FLASH_ATTN_WHL,
    )
    .pip_install("torch==2.7.1", "torchvision==0.22.1",
                 index_url="https://download.pytorch.org/whl/cu128", extra_options="--no-deps")
    .pip_install("fastapi", "aiortc", "aiohttp", "av")
    .env({"MUNEA_APP_KEY": APP_KEY})
    # v2 crops come from the same bg-a05/bg-a06 portraits shipped in the App.
    # Source box: x=0, y=140, w=1080, h=1440, resized to 512x512 for FlashHead.
    .add_local_file(os.path.join(CHAR_ASSET_DIR, "a05-inB-512-v2.png"), "/root/char-a05B.png")
    .add_local_file(os.path.join(CHAR_ASSET_DIR, "a06-inB-512-v2.png"), "/root/char-a06B.png")
)

CHAR_SRC = {
    "a05": "/root/char-a05B.png",
    "a06": "/root/char-a06B.png",
}
DEFAULT_CHAR = "a05"

SNAPSHOT_KEY = "v2-flashhead-eager"  # v1 用 compile 模式、Modal GPU 快照失敗(CUDA graph 存不進去)；v2 改 eager

SR_IN, SR_ENG = 24000, 16000
# 2026-07-11 卡西法：Edward「語音卡卡」止血方案(a)——每輪開口前先讓 AudioOutBuffer 墊 0.3 秒
# 緩衝才開始真的放音，免費、代價=開口再慢一點。誠實記：延後發作不是根治，量到的漂移速率
# (~14ms/秒通話)換算大概多撐~20秒才會復發同頻率斷糧。
AUDIO_PREBUFFER_S = 0.3


@app.cls(
    image=image,
    gpu="l4",                         # 7/10 卡西法二測仍鎖：L40S 需先設付款方式，維持 L4 為主路
    volumes={"/models": vol},
    scaledown_window=480,              # 7/11 卡西法：240->480，真機測試常連續重試、避免每次都重冷啟(冷啟遇GPU吃緊可能等數分鐘)
    timeout=3600,
    max_containers=1,
    region="ap-northeast",
)
# 2026-07-12 卡西法（緊急修正，照 docs/多人併發容量架構-2026-07-12.md §8 標「緊急」）：
# max_inputs=20 是「兩人同時打進同一容器互看臉/聲音混疊」bug 的根源——這支 Modal 測試版
# 目前還是單例邏輯（沒有像 flashhead_server.py 那樣做 N 槽陣列改造），container 內部
# 只有一份全域 pipeline/sink/audio_out，max_inputs=20 等於允許 20 個 HTTP 請求同時擠進
# 同一顆引擎共用那一份狀態。改 max_inputs=1（配 max_containers=1，一容器一路）先安全止血；
# 若之後把 §3 的 N 槽陣列也搬進這支 Modal 版，才配合放寬成 max_inputs=N。
@modal.concurrent(max_inputs=1)
class FlashHead:

    # ---------- 睡前(拍進快照)：重活全做完，含觸發 torch.compile 的暖跑 ----------
    @modal.enter()   # 這輪不啟用記憶體快照，load 跟 wake 都是每次開容器就跑
    def load(self):
        import collections
        import sys
        import threading
        import time

        import numpy as np
        import torch

        t0 = time.time()
        sys.path.insert(0, "/root/SoulX-FlashHead")
        os.chdir("/root/SoulX-FlashHead")
        from flash_head.inference import get_audio_embedding, get_base_data, get_infer_params, get_pipeline, run_pipeline
        self._get_base_data = get_base_data
        self._get_audio_embedding = get_audio_embedding
        self._run_pipeline = run_pipeline

        # L4 實測：torch.compile 首塊冷編譯要 1010 秒(16.8分鐘)、Modal GPU 記憶體快照對編譯後的
        # CUDA graph 狀態存不進去(Failed creating Function memory snapshot)——關掉 compile 改
        # eager 模式：換掉一次性巨額編譯稅、也讓快照有機會真的吃得下(這才是秒醒的關鍵)
        import flash_head.src.pipeline.flash_head_pipeline as _fhp_mod
        _fhp_mod.COMPILE_MODEL = False
        _fhp_mod.COMPILE_VAE = False

        self.pipeline = get_pipeline(world_size=1, ckpt_dir="/models/soulx-flashhead-1.3b",
                                     wav2vec_dir="/models/wav2vec2-base-960h", model_type="lite")
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
            """穩定播放佇列（2026-07-11 卡西法重寫，解 Edward 7/11 二測回報「動態很卡、斷斷續續」）：
            舊版每塊 24 幀一次到貨後，pop(stale_after_s=0.2) 把「生成完成時刻往回推」超過 0.2 秒的
            幀全部當過期丟掉——每塊 24 幀只有最後~5 幀(0.2s*25fps)算新鮮，等於每 0.96 秒只播 5 幀、
            肉眼看是規律性跳格。這版改純 FIFO 穩定佇列：正常情況下生成速率(~25fps)跟播放拉幀速率
            (FlashHeadTrack 已改用內容原生 fps 恆速拉、不是 aiortc 預設 30fps)打平，佇列只當緩衝墊
            吸收生成節奏的小抖動；只有真的塞車（佇列衝過 max_depth，約 2 塊）才從頭修剪回
            target_depth（約 1.5 塊），防止長通話累積延遲——不是每塊都丟。
            deque 另設 maxlen 當硬安全網，防任何未知 bug 造成無界成長。"""
            def __init__(self, tgt_fps):
                self.tgt_fps = tgt_fps
                self.target_depth = max(1, int(round(tgt_fps * 1.5)))   # ~36幀 @25fps
                self.max_depth = max(self.target_depth + 1, int(round(tgt_fps * 2.0)))  # ~48幀，超過才修剪
                self.q = collections.deque(maxlen=int(round(tgt_fps * 12)))  # 硬安全網~12秒份
                self.count = 0
                self.lock = threading.Lock()
                self.last_pop_latency_ms = None
                self.underrun_count = 0   # 2026-07-11 卡西法：pop()拿不到幀(佇列見底)的累計次數
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
                        self.underrun_count += 1   # 2026-07-11 卡西法：視訊斷幀次數(佇列見底、只能重播上一幀)
                        return None
                    return self.q.popleft()
            def clear(self):
                with self.lock:
                    self.q.clear()

        self.sink = FrameSink(self.tgt_fps)
        # 預留聲音延遲緩衝介面(下一棒接 Gemini Live 語音鏈時用)：聲音要等到有對應時間戳的
        # 畫面才放行播放，容許 SYNC_BUFFER_MS 內的落後——這裡先留常數與說明，真正的雙流對時
        # 邏輯要等語音鏈接上才能寫(現在沒有真的語音時間戳可以比對)。
        self.SYNC_BUFFER_MS = 350
        self.last_gen_compute_ms = None    # 段 B：塊備妥 -> 影格生出，Feeder._gen_chunk 會更新

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
            "snapshot_key": SNAPSHOT_KEY,
        }
        print("[load]", self.load_report, flush=True)

    # ---------- 醒來後(每次快照喚醒都跑)：起進料執行緒加通話零件 ----------
    @modal.enter(snap=False)
    def wake(self):
        import collections
        import threading
        import time

        import numpy as np

        import aiortc.codecs.h264 as _h264
        _h264.MIN_BITRATE = 3_000_000
        _h264.DEFAULT_BITRATE = 8_000_000
        _h264.MAX_BITRATE = 12_000_000

        self.wake_ts = time.time()   # 7/11 卡西法：容器這輪甦醒的牆鐘時間，/health /diag 拿來算 uptime_s
                                       # （冷啟/GPU排隊耗時肉眼可查、不用每次翻log猜這通是不是撞到冷啟窗）

        import cv2

        def _load_poster(path):
            p = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
            return cv2.resize(p, (512, 512))

        self._load_poster = _load_poster
        self.poster = _load_poster(CHAR_SRC[self.char])
        self.pcs = set()
        self.pc_created = {}   # id(pc) -> 建線時間戳，餵給 watchdog 判斷卡住太久的連線(7/10 真機測試失敗後補)
        outer = self

        get_audio_embedding = self._get_audio_embedding
        run_pipeline = self._run_pipeline
        sink = self.sink

        outer.round_count = 0
        outer.round_start_ts = 0.0
        outer.round_latencies = collections.deque(maxlen=20)
        outer.last_gen_compute_ms = None
        # 2026-07-11 卡西法：每塊生成耗時滾動視窗(供算 p50/p95)——L4 eager 模式餘裕只有~23%
        # (0.77s/0.96s budget)，要看尖峰有沒有吃穿預算(這是「臉卡頓」跟「語音斷糧」共同上游疑犯)
        outer.gen_compute_ms_hist = collections.deque(maxlen=100)

        class AudioOutBuffer:
            """2026-07-11 卡西法：Edward「語音卡卡」量測儀表——pop_frame()每 20ms 被
            FlashHeadAudioTrack.recv() 拉一次，拿不到整幀時只能回靜音，這就是聽感上的
            「斷斷續續」。underrun_count 累計次數；underrun_gap_ms 記每次事件發生時「距上次
            push() 過了幾ms」——如果數字一直貼近 chunk_budget_ms(~960ms)，代表規律卡在塊
            邊界(生成端跟不上，不是隨機網路問題)；depth_samples 換算 ms 供 /health 看目前
            buffer 存量(正常應該在 0~960ms 之間穩定擺動，長期趨近 0 = 快斷糧的前兆)。

            止血方案(a)（2026-07-11 卡西法・Edward拍板今晚上）：AUDIO_PREBUFFER_S——每次
            clear()(=turn boundary，下一輪聲音要開始前)先讓 buffer 暗自累積 0.3 秒才開始真的
            放音，用起手多等一點點換取撐過短暫的生成端速度抖動。誠實記：這是延後發作、不是
            根治——量到的漂移速率(~14ms/秒通話)換算，大概多撐~20秒才會復發同頻率斷糧，短回合
            有感、長回合治標不治本(正式修法看今晚 L4+compile 實驗結果，不行就 RunPod 4090 常駐)。
            hold 期間刻意不消耗 buf(讓它繼續累積)、也不計進 underrun_count(這是刻意安靜，不是斷糧)。"""
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
                        return np.zeros(self.frame_samples, dtype=np.int16)   # 暖身墊窗：刻意安靜、buf繼續攢
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
                        self.t0 = now
                        self.acc = np.zeros(0, dtype=np.float32)
                        self.consumed = 0
                        outer.round_count += 1
                        outer.round_start_ts = now
                        self._round_pending = True
                        print("[round] #" + str(outer.round_count) + " start", flush=True)
                    self.acc = np.concatenate([self.acc, xq])
                    self.last_in = now

            def reset(self):
                with self.lock:
                    self.acc = np.zeros(0, dtype=np.float32)
                    self.t0 = None
                    self.consumed = 0
                sink.clear()
                outer.audio_out.clear()
                print("[feeder] reset(turn boundary)", flush=True)

            def _gen_chunk(self, chunk_16k):
                t_chunk_ready = time.time()
                outer.audio_dq.extend(chunk_16k.tolist())
                arr = np.array(outer.audio_dq)
                emb = get_audio_embedding(outer.pipeline, arr, outer.audio_start_idx, outer.audio_end_idx)
                with outer.char_lock:
                    video = run_pipeline(outer.pipeline, emb)
                video = video[outer.motion_frames_num:]
                frames = video.cpu().numpy().astype(np.uint8)
                t_frames_ready = time.time()
                outer.last_gen_compute_ms = round((t_frames_ready - t_chunk_ready) * 1000, 1)
                outer.gen_compute_ms_hist.append(outer.last_gen_compute_ms)
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

    # ---------- 換角色：換底圖重註冊(get_base_data)；失敗回舊角色 ----------
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

    # ---------- 對外：通話服務(網頁接口，形狀照抄 nening) ----------
    @modal.asgi_app()
    def web(self):
        import asyncio
        import time
        from fractions import Fraction

        import numpy as np
        from aiortc import (MediaStreamError, MediaStreamTrack, RTCConfiguration, RTCIceServer,
                            RTCPeerConnection, RTCSessionDescription, VideoStreamTrack)
        from aiortc.mediastreams import VIDEO_CLOCK_RATE, VIDEO_TIME_BASE
        from av import AudioFrame, VideoFrame
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware

        api = FastAPI()
        api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        outer = self

        import os as _os
        _gate = _os.environ.get("MUNEA_APP_KEY", "").strip()

        def _pass(request_key):
            return (not _gate) or (request_key == _gate)

        class FlashHeadTrack(VideoStreamTrack):
            kind = "video"
            def __init__(self):
                super().__init__()
                self.last = outer.poster
                self._active_ts = 0.0
                # 2026-07-11 卡西法：內容原生就是 outer.tgt_fps(通常25)、aiortc VideoStreamTrack 預設卻是
                # 30fps——沿用預設會讓 recv() 抽幀速率長期快過生成速率，佇列反覆見底，跟舊版「丟過期幀」
                # 政策疊加變成規律性頓挫。改覆寫 next_timestamp() 用內容原生 fps 恆速拉，供需速率打平。
                self._ptime = 1.0 / outer.tgt_fps
            async def next_timestamp(self):
                # 抄 aiortc.mediastreams.VideoStreamTrack.next_timestamp()，只把寫死的 30fps 換成內容原生 fps
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
            # 跟 FlashHeadTrack 共用同一條 RTCPeerConnection：瀏覽器原生對嘴(視訊通話本來就這樣做)
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
            return {"ok": True, "engine": "flashhead-lite-modal", "char": outer.char,
                    "frames": outer.sink.count, "load": outer.load_report,
                    "round_count": outer.round_count,
                    "round_latencies_ms": list(outer.round_latencies),
                    "uptime_s": round(time.time() - getattr(outer, "wake_ts", time.time()), 1),
                    "sink_depth": len(outer.sink.q),
                    "latency_ms": {
                        "gen_compute_B": outer.last_gen_compute_ms,     # 段B: 塊備妥->影格生出
                        "sink_pop_C": outer.sink.last_pop_latency_ms,   # 段C: 影格生出->被WebRTC取用
                        "chunk_budget_ms": budget_ms,
                        "sync_buffer_reserved_ms": outer.SYNC_BUFFER_MS,
                    },
                    # 2026-07-11 卡西法：Edward「語音卡卡」量測儀表——三支計數器
                    "gen_compute_ms_rolling": {
                        "p50": gen_p50, "p95": gen_p95, "budget_ms": budget_ms,
                        "n_samples": len(hist), "headroom_p95_pct":
                            (round((1 - gen_p95 / budget_ms) * 100, 1) if gen_p95 else None),
                    },
                    "audio_underrun": {
                        "count": ao.underrun_count,
                        "recent_gap_ms": list(ao.underrun_gap_ms)[-10:],   # 貼近 chunk_budget_ms 代表卡在塊邊界
                        "buffer_depth_ms": round(ao.depth_samples / ao.sample_rate * 1000, 1),
                        "prebuffer_s": AUDIO_PREBUFFER_S,   # 止血方案(a)目前設定值
                    },
                    "video_underrun": {
                        "count": outer.sink.underrun_count,
                    }}

        # ---------- 診斷回傳（2026-07-11 卡西法）：client端連線失敗時自動把 debug log + ICE candidate/
        # getStats() 現場 POST 回這裡，Edward 不用截圖，我們直接看 `modal app logs` 就有完整現場 ----------
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
            pc = RTCPeerConnection(RTCConfiguration(iceServers=[
                RTCIceServer(urls="stun:stun.l.google.com:19302"),
                # 7/11 卡西法補：server 端原本只有 STUN、relay 只靠 client 單邊——兩端都帶 TURN 是
                # WebRTC 正規做法，對稱型 NAT 等更難連的網路環境兩端都能找到relay配對
                RTCIceServer(urls=["turn:34.81.102.52:3478?transport=udp", "turn:34.81.102.52:3478?transport=tcp"],
                             username="muneaturn", credential="munea-turn-a7k2q"),
            ]))
            outer.pcs.add(pc)
            outer.pc_created[id(pc)] = time.time()

            pc_tag = str(id(pc))[-5:]  # 短 id，log 裡跟 offer/close 對得起來

            @pc.on("connectionstatechange")
            async def _on_conn_state_change():
                # 7/11 卡西法補：兩次真機測試(7/10 首測 ICE 卡2分鐘失敗、7/11 二測)server log
                # 都查不到 pc 有沒有到過 connected——原本只印 closed/failed，"connected" 從沒印過。
                # 全狀態都印，下次測試才能分清「根本沒連上」vs「連上了但client已經放棄」。
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

        # ---------- 看門狗：ICE 卡在 connecting 太久的連線自動關掉（7/10 真機測試失敗後補）----------
        # 背景：server log 證實過一條 pc 卡在 connecting 逾 2 分鐘才變 failed，這段期間 Feeder 的
        # idle 分支會一直當「有人在線」持續生成待機影格燒 GPU 時間——不是無限卡死，但沒必要陪它等 2 分鐘，
        # 30 秒還沒 connected 就直接關掉，讓容器可以照常在真的沒人用時歸零。
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

        # ---------- 對外：換角色（不必重開 WebRTC，7/10 手機真機測試輪加）----------
        # /offer?char= 只在「建線那一刻」能換角色；通話中途想換角色（不掛斷）就靠這支——
        # 直接呼叫既有 _switch()，換的是共享狀態（outer.char/outer.poster/outer.sink），
        # FlashHeadTrack/FlashHeadAudioTrack 下一格自然讀到新角色，不必碰 pc/track。
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

    # ---------- 診斷探針(掐錶/巡檢用)：喚醒/穩態每塊耗時 p50 p95/換角色耗時/VRAM ----------
    @modal.method()
    def probe(self, char: str = ""):
        import statistics
        import time

        import numpy as np
        import torch

        sw_s = None
        if char:
            t_sw = time.time()
            ok = self._switch(char)
            sw_s = round(time.time() - t_sw, 3)
            if not ok:
                return {"char": char, "supported": False, "switch_s": sw_s}

        cs = self.chunk_samples
        times = []
        for _ in range(8):
            t0 = time.time()
            self.audio_dq.extend(np.zeros(cs, dtype=np.float32).tolist())
            arr = np.array(self.audio_dq)
            emb = self._get_audio_embedding(self.pipeline, arr, self.audio_start_idx, self.audio_end_idx)
            with self.char_lock:
                video = self._run_pipeline(self.pipeline, emb)
            torch.cuda.synchronize()
            times.append(time.time() - t0)

        p50 = statistics.median(times)
        srt = sorted(times)
        p95 = srt[max(0, int(len(srt) * 0.95) - 1)]
        budget_s = self.slice_len / self.tgt_fps
        vram_mb = round(torch.cuda.memory_allocated() / 1024 / 1024, 1) if torch.cuda.is_available() else None

        return {
            "char": self.char, "supported": True, "switch_s": sw_s,
            "load_report": self.load_report,
            "chunk_times_ms": [round(t * 1000, 1) for t in times],
            "chunk_p50_ms": round(p50 * 1000, 1),
            "chunk_p95_ms": round(p95 * 1000, 1),
            "chunk_budget_ms": round(budget_s * 1000, 1),
            "realtime_multiple": round(budget_s / p50, 2),
            "hits_realtime_25fps": bool(p95 < budget_s),
            "vram_allocated_mb": vram_mb,
        }
