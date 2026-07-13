# -*- coding: utf-8 -*-
# FlashHead 4090 產能碼錶（照 flashhead_modal_dev.py 正式跑法逐塊生成）
# 用法: python bench_fh.py eager|compile [wav路徑] [最多塊數]
import collections
import os
import sys
import time

MODE = sys.argv[1] if len(sys.argv) > 1 else "eager"
WAV = sys.argv[2] if len(sys.argv) > 2 else "/root/poc-mandarin.wav"
MAXC = int(sys.argv[3]) if len(sys.argv) > 3 else 40
CHAR = os.environ.get("MUNEA_FH_BENCH_CHAR", "/root/char-a05B.png")
EXPECT_SIZE = int(os.environ.get("MUNEA_FH_BENCH_SIZE", "0") or 0)

sys.path.insert(0, "/root/SoulX-FlashHead")
os.chdir("/root/SoulX-FlashHead")

import numpy as np
import torch

import flash_head.src.pipeline.flash_head_pipeline as _fhp
_fhp.COMPILE_MODEL = (MODE == "compile")
_fhp.COMPILE_VAE = (MODE == "compile")

import flash_head.inference as _fh_inference
if EXPECT_SIZE:
    _fh_inference.infer_params["height"] = EXPECT_SIZE
    _fh_inference.infer_params["width"] = EXPECT_SIZE

from flash_head.inference import (get_audio_embedding, get_base_data,
                                  get_infer_params, get_pipeline, run_pipeline)

t0 = time.time()
pipeline = get_pipeline(world_size=1, ckpt_dir="/models/soulx-flashhead-1.3b",
                        wav2vec_dir="/models/wav2vec2-base-960h", model_type="lite")
t1 = time.time()
get_base_data(pipeline, cond_image_path_or_dir=CHAR,
              base_seed=42, use_face_crop=False)
t2 = time.time()

ip = get_infer_params()
sr, fps = ip["sample_rate"], ip["tgt_fps"]
fn, mfn = ip["frame_num"], ip["motion_frames_num"]
slice_len = fn - mfn
chunk = slice_len * sr // fps
cad = ip["cached_audio_duration"]
end_idx = cad * fps
start_idx = end_idx - fn
dq = collections.deque([0.0] * (sr * cad), maxlen=sr * cad)

import soundfile as sf
wav, wsr = sf.read(WAV, dtype="float32")
if wav.ndim > 1:
    wav = wav.mean(1)
if wsr != sr:
    xi = np.linspace(0, 1, int(len(wav) * sr / wsr))
    wav = np.interp(xi, np.linspace(0, 1, len(wav)), wav).astype("float32")

times = []
output_shapes = set()
pos = 0
n = min(len(wav) // chunk, MAXC)
first_chunk_s = None
for i in range(n):
    seg = wav[pos:pos + chunk]
    pos += chunk
    tc0 = time.time()
    dq.extend(seg.tolist())
    arr = np.array(dq)
    emb = get_audio_embedding(pipeline, arr, start_idx, end_idx)
    video = run_pipeline(pipeline, emb)
    torch.cuda.synchronize()
    shape = tuple(int(v) for v in video.shape[-3:])
    output_shapes.add(shape)
    if EXPECT_SIZE and shape[:2] != (EXPECT_SIZE, EXPECT_SIZE):
        raise RuntimeError(f"expected {EXPECT_SIZE}x{EXPECT_SIZE}, got {shape}")
    dt = (time.time() - tc0) * 1000
    times.append(dt)
    if i == 0:
        first_chunk_s = round(dt / 1000, 1)
    print(f"chunk {i:02d}: {dt:.0f} ms", flush=True)

budget = slice_len / fps * 1000
ts = sorted(times[2:]) if len(times) > 4 else sorted(times)
p50 = ts[len(ts) // 2]
p95 = ts[max(0, int(len(ts) * 0.95) - 1)]
gpu = torch.cuda.get_device_name(0)
print("RESULT", {
    "mode": MODE, "gpu": gpu, "wav": os.path.basename(WAV),
    "char": os.path.basename(CHAR), "output_shapes": sorted(output_shapes),
    "load_s": round(t1 - t0, 1), "base_s": round(t2 - t1, 1),
    "first_chunk_s": first_chunk_s, "chunks": len(times),
    "budget_ms": round(budget, 1),
    "p50_ms": round(p50, 1), "p95_ms": round(p95, 1), "max_ms": round(max(ts), 1),
    "realtime_x": round(budget / p50, 2),
    "fps_effective": round(slice_len / (p50 / 1000), 1),
    "headroom_pct": round((budget - p95) / budget * 100, 1),
}, flush=True)
