#!/bin/bash
# Munea FlashHead @ RunPod CUDA 12.8 — 4090／5090 共用裝機配方
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq libgl1 libglib2.0-0 git wget ffmpeg >/dev/null 2>&1

PY=python3.12
PIP=pip3
FLASHHEAD_COMMIT="${MUNEA_FH_COMMIT:-9bc03de06bb0de82cd6bc477804512ae06144bf2}"
cd /root

echo "=== [1/5] clone SoulX-FlashHead ==="
git clone --depth 1 https://github.com/Soul-AILab/SoulX-FlashHead.git || true
cd /root/SoulX-FlashHead || exit 1
git fetch --depth 1 origin "$FLASHHEAD_COMMIT"
git checkout --detach "$FLASHHEAD_COMMIT"

echo "=== [2/5] requirements（雷1 mediapipe / 雷2 nccl 已修；不動預裝 torch）==="
sed -i 's/mediapipe==0.10.9/mediapipe>=0.10.13/' requirements.txt
sed -i '/nvidia-nccl-cu12/d' requirements.txt
$PIP install --ignore-installed blinker -r requirements.txt

echo "=== [3/5] 清除模板殘留 torch，再裝 cu128 + flash-attn ==="
SITE="$($PY -c 'import site; print(site.getsitepackages()[0])')"
$PIP uninstall -y torch torchvision torchaudio || true
rm -rf "$SITE/torch" "$SITE/functorch" "$SITE/torchgen" \
  "$SITE"/torch-*.dist-info "$SITE/torchvision" "$SITE"/torchvision-*.dist-info \
  "$SITE/torchaudio" "$SITE"/torchaudio-*.dist-info
$PIP install torch==2.7.1+cu128 torchvision==0.22.1+cu128 torchaudio==2.7.1+cu128 \
  --index-url https://download.pytorch.org/whl/cu128
$PIP install ninja
W=flash_attn-2.8.0.post2+cu12torch2.7cxx11abiTRUE-cp312-cp312-linux_x86_64.whl
wget -q "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.0.post2/$W" -O "/root/$W"
$PIP install "/root/$W"

echo "=== [4/5] 服務層零件 ==="
$PIP install --ignore-installed cryptography pyOpenSSL aiortc aiohttp
$PIP install fastapi av "huggingface_hub[cli]" soundfile uvicorn

echo "=== [5/5] 自檢 ==="
$PY - <<'EOF'
import torch
print("TORCH_CHECK", torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0))
import torch._inductor.compile_fx
print("INDUCTOR_CHECK", "ok")
import flash_attn
print("FLASH_ATTN_CHECK", flash_attn.__version__)
import mediapipe, cv2
print("MP_CV_CHECK", mediapipe.__version__, cv2.__version__)
EOF
echo "PIP_ZONE_DONE"

echo "=== 權重下載 ==="
unset HF_HUB_ENABLE_HF_TRANSFER
mkdir -p /models
hf download Soul-AILab/SoulX-FlashHead-1_3B --local-dir /models/soulx-flashhead-1.3b --exclude "Model_Pro/*"
hf download facebook/wav2vec2-base-960h --local-dir /models/wav2vec2-base-960h
echo "ALL_DONE"
