#!/bin/bash
# Munea FlashHead @ Glows.ai TW 4090 — 裝機 v2（用預裝 conda workenv：py3.11 + torch2.7.1+cu128 已在）
set -x
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq libgl1 libglib2.0-0 ffmpeg >/dev/null 2>&1

E=/root/miniconda3/envs/workenv/bin
cd /root/SoulX-FlashHead || exit 1

echo "=== [1/5] requirements（雷1 mediapipe / 雷2 nccl 已修；不動預裝 torch）==="
sed -i 's/mediapipe==0.10.9/mediapipe>=0.10.13/' requirements.txt
sed -i '/nvidia-nccl-cu12/d' requirements.txt
$E/pip install -r requirements.txt

echo "=== [2/5] ninja + flash-attn 預編譯 cp311（雷4 完整檔名）==="
$E/pip install ninja
W=flash_attn-2.8.0.post2+cu12torch2.7cxx11abiTRUE-cp311-cp311-linux_x86_64.whl
wget -q "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.0.post2/$W" -O "/root/$W"
$E/pip install "/root/$W"

echo "=== [3/5] torch cu128 校正（雷3 保險絲；若沒被動過等於空跑）==="
$E/pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128 --no-deps

echo "=== [4/5] 服務層零件 ==="
$E/pip install fastapi aiortc aiohttp av "huggingface_hub[cli]" soundfile uvicorn

echo "=== [5/5] 自檢 ==="
$E/python - <<'EOF'
import torch
print("TORCH_CHECK", torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0))
import flash_attn
print("FLASH_ATTN_CHECK", flash_attn.__version__)
import mediapipe, cv2
print("MP_CV_CHECK", mediapipe.__version__, cv2.__version__)
EOF
echo "PIP_ZONE_DONE"

echo "=== 權重下載（輕量版＋聽聲零件）==="
date +%s > /root/t_w_start
$E/huggingface-cli download Soul-AILab/SoulX-FlashHead-1_3B --local-dir /models/soulx-flashhead-1.3b --exclude "Model_Pro/*"
$E/huggingface-cli download facebook/wav2vec2-base-960h --local-dir /models/wav2vec2-base-960h
date +%s > /root/t_w_end
echo "ALL_DONE"
