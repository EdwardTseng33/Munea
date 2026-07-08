# -*- coding: utf-8 -*-
"""D2 串流核心探針：模擬聲音「即時」抵達，量三個關鍵數字
1. 開機到就緒（人物註冊）  2. 首塊→首批影格延遲  3. 每塊處理時間 vs 0.2s 即時預算
"""
import os, sys, time
import numpy as np
import librosa

ROOT = "/workspace/ditto-talkinghead"
sys.path.insert(0, ROOT); os.chdir(ROOT)
from stream_pipeline_online import StreamSDK

CFG = "./checkpoints/ditto_cfg/v0.4_hubert_cfg_trt_online.pkl"
DATA = "./checkpoints/ditto_trt_Ampere_Plus"
SRC = "/root/nening-real-female-full.jpg"
OUT = "/root/nening-stream.mp4"
WAV = "/root/nening-reply-1.wav"

t0 = time.time()
sdk = StreamSDK(CFG, DATA)
t1 = time.time()
sdk.setup(SRC, OUT)
t2 = time.time()
print(f"[T] 引擎載入 {t1-t0:.1f}s · 人物註冊 {t2-t1:.1f}s", flush=True)

audio, sr = librosa.load(WAV, sr=16000)
chunksize = (3, 5, 2)
audio = np.concatenate([np.zeros((chunksize[0]*640,), dtype=np.float32), audio], 0)
split_len = int(sum(chunksize)*0.04*16000) + 80
hop = chunksize[1]*640                      # 3200 樣本 = 0.2s
budget = hop/16000.0

lat = []
first_chunk_t = None
for i in range(0, len(audio), hop):
    chunk = audio[i:i+split_len]
    if len(chunk) < split_len:
        chunk = np.pad(chunk, (0, split_len-len(chunk)), mode="constant")
    c0 = time.time()
    if first_chunk_t is None:
        first_chunk_t = c0
    sdk.run_chunk(chunk, chunksize)
    lat.append(time.time()-c0)

t3 = time.time()
sdk.close()
t4 = time.time()

import statistics
n = len(lat)
print(f"[T] 塊數 {n} · 每塊預算 {budget*1000:.0f}ms", flush=True)
print(f"[T] run_chunk 平均 {statistics.mean(lat)*1000:.0f}ms · p95 {sorted(lat)[int(n*0.95)]*1000:.0f}ms · 最大 {max(lat)*1000:.0f}ms", flush=True)
print(f"[T] 即時判定：{'✅ 過（平均<200ms）' if statistics.mean(lat) < budget else '❌ 不過'}", flush=True)
print(f"[T] 餵完全部 {t3-first_chunk_t:.1f}s（音檔 {len(audio)/16000:.1f}s）· close 收尾 {t4-t3:.1f}s", flush=True)
os.system(f'ffmpeg -loglevel error -y -i "{sdk.tmp_output_path}" -i "{WAV}" -map 0:v -map 1:a -c:v copy -c:a aac "{OUT}"')
print("PROBE DONE", OUT, flush=True)
