#!/usr/bin/env bash
# 沐寧 · 4090 一鍵裝機（D1 2026-07-08 實戰驗證版——所有排雷已固化）
# 用法：開卡（podctl.py create）→ scp 本檔+素材上去 → bash bootstrap.sh
# 環境前提：runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04
set -euo pipefail

echo "== [1/6] 系統套件（⚠ 必先 update、否則靜默裝失敗）=="
apt-get update -qq
apt-get install -y -qq ffmpeg libgl1 libgles2 libegl1 libopengl0 libglib2.0-0 > /dev/null

echo "== [2/6] 臉引擎（Ditto · Apache-2.0）=="
mkdir -p /workspace && cd /workspace
[ -d ditto-talkinghead ] || git clone --depth 1 https://github.com/antgroup/ditto-talkinghead
cd ditto-talkinghead
# numpy 2 相容修正（np.atan2 改名）
sed -i 's/np\.atan2/np.arctan2/g' core/aux_models/mediapipe_landmark478.py

echo "== [3/6] Python 依賴（版本全釘死、D1 排雷結論）=="
pip install -q --no-input "huggingface_hub[cli]" numpy==1.26.4 librosa tqdm filetype imageio imageio-ffmpeg \
  opencv-python-headless scikit-image cython colored polygraphy soundfile mediapipe einops 2>&1 | tail -1
pip uninstall -q -y onnxruntime onnxruntime-gpu 2>/dev/null || true
pip install -q --no-input 'onnxruntime-gpu==1.18.1' 2>&1 | tail -1   # CUDA12 相容版
pip install -q --no-input 'tensorrt==8.6.1.post1' 'cuda-python==12.4.0' 2>&1 | tail -1
# TRT8 要 cuDNN8、torch 用 9——裝到獨立資料夾、跑臉引擎時才掛（不動 torch）
pip install -q --no-input --target /opt/cudnn8-pkgs nvidia-cudnn-cu12==8.9.7.29 2>&1 | tail -1

echo "== [4/6] 模型權重（PyTorch 版 + 4090 可用的 TRT 加速版 + 設定檔）=="
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("digital-avatar/ditto-talkinghead", local_dir="./checkpoints",
                  allow_patterns=["ditto_cfg/*", "ditto_pytorch/*", "ditto_trt_Ampere_Plus/*"])
print("weights done")
PY

echo "== [5/6] 煙霧測試指令（手動跑）=="
cat <<'TXT'
  離線（基礎）：python inference.py --data_root ./checkpoints/ditto_pytorch \
    --cfg_pkl ./checkpoints/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl \
    --audio_path <wav> --source_path <寧寧照> --output_path /root/out.mp4
  離線（加速 · 29.4s 音檔實測 26s 完成＝1.1x 即時）：
    LD_LIBRARY_PATH=/opt/cudnn8-pkgs/nvidia/cudnn/lib:$LD_LIBRARY_PATH \
    python inference.py --data_root ./checkpoints/ditto_trt_Ampere_Plus \
    --cfg_pkl ./checkpoints/ditto_cfg/v0.4_hubert_cfg_trt.pkl \
    --audio_path <wav> --source_path <寧寧照> --output_path /root/out.mp4
  串流（D2 目標）：cfg 用 v0.4_hubert_cfg_trt_online.pkl + stream_pipeline_online.py
TXT

echo "== [6/6] 完成 =="
echo "BOOTSTRAP DONE（D3 待辦：把本腳本烘成自訂 docker 映像＝冷啟動從 ~12 分縮到 ~1 分）"
