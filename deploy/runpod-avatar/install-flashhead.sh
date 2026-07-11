#!/bin/bash
# Munea FlashHead @ RunPod US 4090（備援線）— 裝機（py3.12 + torch2.7.1+cu128 預裝、照先鋒 6 雷配方）
set -x
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq libgl1 libglib2.0-0 git wget ffmpeg >/dev/null 2>&1

PY=python3.12
PIP=pip3
cd /root

echo "=== [1/5] clone SoulX-FlashHead ==="
git clone --depth 1 https://github.com/Soul-AILab/SoulX-FlashHead.git || true
cd /root/SoulX-FlashHead || exit 1

echo "=== [2/5] requirements（雷1 mediapipe / 雷2 nccl 已修；不動預裝 torch）==="
sed -i 's/mediapipe==0.10.9/mediapipe>=0.10.13/' requirements.txt
sed -i '/nvidia-nccl-cu12/d' requirements.txt
$PIP install -r requirements.txt

echo "=== [3/5] ninja + flash-attn 預編譯 cp312（雷4 完整檔名）==="
$PIP install ninja
W=flash_attn-2.8.0.post2+cu12torch2.7cxx11abiTRUE-cp312-cp312-linux_x86_64.whl
wget -q "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.0.post2/$W" -O "/root/$W"
$PIP install "/root/$W"
$PIP install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128 --no-deps

echo "=== [4/5] 服務層零件 ==="
$PIP install fastapi aiortc aiohttp av "huggingface_hub[cli]" soundfile uvicorn

echo "=== [5/5] 自檢 ==="
$PY - <<'EOF'
import torch
print("TORCH_CHECK", torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0))
import flash_attn
print("FLASH_ATTN_CHECK", flash_attn.__version__)
import mediapipe, cv2
print("MP_CV_CHECK", mediapipe.__version__, cv2.__version__)
EOF
echo "PIP_ZONE_DONE"

echo "=== 權重下載 ==="
mkdir -p /models
huggingface-cli download Soul-AILab/SoulX-FlashHead-1_3B --local-dir /models/soulx-flashhead-1.3b --exclude "Model_Pro/*"
huggingface-cli download facebook/wav2vec2-base-960h --local-dir /models/wav2vec2-base-960h
echo "ALL_DONE"
