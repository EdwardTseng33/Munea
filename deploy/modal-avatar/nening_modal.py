# -*- coding: utf-8 -*-
"""沐寧 · 寧寧臉引擎上 Modal（快照秒醒 PoC · 2026-07-09）

目的：量「全睡 → 臉引擎就緒」在 GPU 記憶體快照下能壓到幾秒（對照鈴響窗 1–6 秒）。
沿用 RunPod 排雷結論：版本全釘死、cuDNN8 獨立資料夾、numpy2 修正、TRT Ampere_Plus 引擎。

用法：
  modal deploy -m nening_modal        # 建映像 + 部署（快照要部署版才會啟用）
  modal run nening_modal::seed_models # 首次：模型權重下載進雲端置物櫃
  python probe_wake.py                # 掐錶：冷喚醒 → 就緒
"""
import modal

app = modal.App("munea-nening-avatar")

vol = modal.Volume.from_name("munea-ditto-models", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libgles2", "libegl1", "libopengl0", "libglib2.0-0")
    .pip_install("torch==2.4.0")
    .pip_install(
        "numpy==1.26.4", "librosa", "tqdm", "filetype", "imageio", "imageio-ffmpeg",
        "opencv-python-headless", "scikit-image", "cython", "colored", "polygraphy",
        "soundfile", "mediapipe", "einops", "aiohttp", "aiortc", "huggingface_hub",
    )
    .pip_install("onnxruntime-gpu==1.18.1")
    .pip_install("tensorrt==8.6.1.post1", "cuda-python==12.4.0")
    .run_commands(
        "pip install --target /opt/cudnn8-pkgs nvidia-cudnn-cu12==8.9.7.29",
        "git clone --depth 1 https://github.com/antgroup/ditto-talkinghead /root/ditto-talkinghead",
        "sed -i 's/np\\.atan2/np.arctan2/g' /root/ditto-talkinghead/core/aux_models/mediapipe_landmark478.py",
    )
    .env({"LD_LIBRARY_PATH": "/opt/cudnn8-pkgs/nvidia/cudnn/lib"})
    .add_local_file(r"E:\Claude\Munea\web\avatars\nening-real-female-full.jpg",
                    "/root/nening-real-female-full.jpg")
)


@app.function(image=image, volumes={"/models": vol}, timeout=3600)
def seed_models():
    """首次執行：模型權重下載進 Modal 置物櫃（之後所有容器共用、不重下）。"""
    from huggingface_hub import snapshot_download
    snapshot_download("digital-avatar/ditto-talkinghead", local_dir="/models/checkpoints",
                      allow_patterns=["ditto_cfg/*", "ditto_trt_Ampere_Plus/*"])
    vol.commit()
    return "models seeded"


SNAPSHOT_KEY = "v1"  # 改這個字串＝作廢舊快照重拍


@app.cls(
    image=image,
    gpu="l40s",                      # Ada 世代、跟 4090 同代（TRT 引擎相容）
    volumes={"/models": vol},
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
    scaledown_window=40,             # 沒人用 40 秒就睡（PoC 用短、量冷喚醒方便）
    timeout=600,
)
class Nening:
    @modal.enter(snap=True)
    def load(self):
        """重活全做在這：TRT 引擎載入 + 寧寧照註冊 + 暖跑一塊。快照拍在這之後。"""
        import os
        import sys
        import time
        import numpy as np

        t0 = time.time()
        sys.path.insert(0, "/root/ditto-talkinghead")
        os.chdir("/root/ditto-talkinghead")
        from stream_pipeline_online import StreamSDK

        self.sdk = StreamSDK("/models/checkpoints/ditto_cfg/v0.4_hubert_cfg_trt_online.pkl",
                             "/models/checkpoints/ditto_trt_Ampere_Plus")
        t1 = time.time()
        self.sdk.setup("/root/nening-real-female-full.jpg", "/root/_live_dummy.mp4")
        t2 = time.time()

        # 影格出口改成計數器（正式版=WebRTC 直送；PoC 只要證明引擎活著在產格）
        cls = self

        class Sink:
            def __call__(self, frame, fmt="rgb"):
                cls.frames += 1
            def close(self):
                pass

        self.frames = 0
        self.sdk.writer = Sink()

        # 暖跑一塊 0.2s 靜音（觸發所有懶載入、快照才是「全熟」狀態）
        chunk = np.zeros(6480, dtype=np.float32)
        self.sdk.run_chunk(chunk, (3, 5, 2))
        t3 = time.time()
        self.load_report = {"sdk_init_s": round(t1 - t0, 1), "setup_s": round(t2 - t1, 1),
                            "warm_chunk_s": round(t3 - t2, 1), "total_load_s": round(t3 - t0, 1),
                            "snapshot_key": SNAPSHOT_KEY}
        print("[load]", self.load_report, flush=True)

    @modal.method()
    def probe(self):
        """喚醒後健康探針：真的跑 5 塊音訊、回報引擎速度與影格數。"""
        import time
        import numpy as np
        t0 = time.time()
        before = self.frames
        for _ in range(5):
            self.sdk.run_chunk(np.zeros(6480, dtype=np.float32), (3, 5, 2))
        dt = time.time() - t0
        time.sleep(1.0)  # 等管線把格吐完
        return {"load_report": self.load_report, "chunk_ms": round(dt / 5 * 1000),
                "frames_delta": self.frames - before, "ready": True}
