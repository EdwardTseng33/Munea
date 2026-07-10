# -*- coding: utf-8 -*-
"""FlashHead L4+torch.compile experiment (2026-07-11 calcifer).

Goal: measure whether torch.compile brings L4 chunk p95 headroom to >=32%.
Threshold: p95<=650ms -> L4+compile is the answer; p95>700ms -> switch to RunPod 4090.

Independent from flashhead_modal_dev.py (different App name) - does not touch prod/dev.
Deliberately NO enable_memory_snapshot / experimental_options (that combo with compile
broke memory snapshot creation last time and burned $0.70 in retries).
"""
import os
import time

import modal

app = modal.App("munea-flashhead-compile-exp")

vol = modal.Volume.from_name("soulx-flashhead-models", create_if_missing=False)
cache_vol = modal.Volume.from_name("flashhead-inductor-cache-exp", create_if_missing=True)

FLASH_ATTN_WHL = "flash_attn-2.8.0.post2+cu12torch2.7cxx11abiTRUE-cp312-cp312-linux_x86_64.whl"
FLASH_ATTN_URL = "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.0.post2/" + FLASH_ATTN_WHL

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
    .add_local_file(r"E:\Claude\Munea\deploy\flashhead-poc\assets\a05-inB-512.png", "/root/char-a05B.png")
)

CHAR_SRC = {"a05": "/root/char-a05B.png"}
DEFAULT_CHAR = "a05"



@app.cls(
    image=image,
    gpu="l4",
    volumes={"/models": vol, "/inductor_cache": cache_vol},
    timeout=3600,
    max_containers=1,
    region="ap-northeast",
    scaledown_window=120,
)
class FlashHeadCompileExp:

    @modal.enter()
    def load(self):
        import collections
        import sys
        import threading

        import numpy as np
        import torch

        os.makedirs("/inductor_cache/inductor", exist_ok=True)
        os.makedirs("/inductor_cache/triton", exist_ok=True)
        os.environ["TORCHINDUCTOR_CACHE_DIR"] = "/inductor_cache/inductor"
        os.environ["TRITON_CACHE_DIR"] = "/inductor_cache/triton"

        t0 = time.time()
        sys.path.insert(0, "/root/SoulX-FlashHead")
        os.chdir("/root/SoulX-FlashHead")
        from flash_head.inference import (get_audio_embedding, get_base_data,
                                           get_infer_params, get_pipeline, run_pipeline)
        self._get_audio_embedding = get_audio_embedding
        self._run_pipeline = run_pipeline

        import flash_head.src.pipeline.flash_head_pipeline as _fhp_mod
        print("[compile-exp] library default COMPILE_MODEL=", _fhp_mod.COMPILE_MODEL,
              "COMPILE_VAE=", _fhp_mod.COMPILE_VAE, flush=True)
        _fhp_mod.COMPILE_MODEL = True
        _fhp_mod.COMPILE_VAE = True

        self.pipeline = get_pipeline(world_size=1, ckpt_dir="/models/soulx-flashhead-1.3b",
                                     wav2vec_dir="/models/wav2vec2-base-960h", model_type="lite")
        t1 = time.time()
        print("[compile-exp] pipeline construct+compile-wrap =", round(t1 - t0, 1), "s", flush=True)

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

        warm_times = []
        for i in range(3):
            silence = np.zeros(self.chunk_samples, dtype=np.float32)
            tw0 = time.time()
            self.audio_dq.extend(silence.tolist())
            arr = np.array(self.audio_dq)
            emb = get_audio_embedding(self.pipeline, arr, self.audio_start_idx, self.audio_end_idx)
            video = run_pipeline(self.pipeline, emb)
            torch.cuda.synchronize()
            wt = round(time.time() - tw0, 2)
            warm_times.append(wt)
            print("[compile-exp] warm chunk#" + str(i) + " = " + str(wt) + "s", flush=True)
        t3 = time.time()

        self.load_report = {
            "pipeline_construct_s": round(t1 - t0, 1),
            "base_data_s": round(t2 - t1, 2),
            "warm_chunk_s": warm_times,
            "total_load_s": round(t3 - t0, 1),
            "chunk_samples": self.chunk_samples,
            "slice_len_frames": self.slice_len,
            "chunk_budget_ms": round(self.slice_len / self.tgt_fps * 1000, 1),
            "compile_on": True,
            "inductor_cache_dir": os.environ.get("TORCHINDUCTOR_CACHE_DIR"),
        }
        print("[compile-exp load]", self.load_report, flush=True)
        cache_vol.commit()

    @modal.method()
    def probe(self, n: int = 12):
        import statistics

        import numpy as np
        import torch

        cs = self.chunk_samples
        times = []
        for _ in range(n):
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

        if p95 * 1000 <= 650:
            verdict = "PASS: L4+compile is viable (cheap + keeps Modal auto-sleep)"
        elif p95 * 1000 > 700:
            verdict = "FAIL: give up on L4+compile, switch to RunPod 4090 dedicated"
        else:
            verdict = "BORDERLINE (650-700ms), needs manual review"

        result = {
            "load_report": self.load_report,
            "chunk_times_ms": [round(t * 1000, 1) for t in times],
            "chunk_p50_ms": round(p50 * 1000, 1),
            "chunk_p95_ms": round(p95 * 1000, 1),
            "chunk_budget_ms": round(budget_s * 1000, 1),
            "realtime_multiple": round(budget_s / p50, 2),
            "headroom_p95_pct": round((1 - p95 / budget_s) * 100, 1),
            "vram_allocated_mb": vram_mb,
            "verdict": verdict,
        }
        print("[compile-exp probe]", result, flush=True)
        return result
