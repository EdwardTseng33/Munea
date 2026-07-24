#!/bin/bash
# Munea FlashHead @ Glows.ai TW GPU — 從官方空白映像重建
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq libgl1 libglib2.0-0 ffmpeg >/dev/null 2>&1

E=/root/miniconda3/envs/workenv/bin
# 2026-07-23 calcifer: pin the checkout to a known commit (matches the
# runpod-avatar install script) so deploy/flashhead-patches/*.patch always
# has a stable base to apply against -- "git clone --depth 1" alone only
# grabs whatever the upstream default branch tip happens to be that day.
FLASHHEAD_COMMIT="${MUNEA_FH_COMMIT:-9bc03de06bb0de82cd6bc477804512ae06144bf2}"
if [[ ! -d /root/SoulX-FlashHead/.git ]]; then
  git clone --depth 1 https://github.com/Soul-AILab/SoulX-FlashHead.git /root/SoulX-FlashHead
fi
cd /root/SoulX-FlashHead || exit 1
git fetch --depth 1 origin "$FLASHHEAD_COMMIT"
git checkout --detach "$FLASHHEAD_COMMIT"

echo "=== apply Munea patches (see deploy/flashhead-patches/README.md) ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MUNEA_FH_PATCHES_DIR="${MUNEA_FH_PATCHES_DIR:-$SCRIPT_DIR/../flashhead-patches}"
if [[ -d "$MUNEA_FH_PATCHES_DIR" ]]; then
  for p in "$MUNEA_FH_PATCHES_DIR"/*.patch; do
    [[ -e "$p" ]] || continue
    if git apply --check "$p" 2>/dev/null; then
      echo "  applying $(basename "$p")"
      git apply "$p"
    elif git apply -R --check "$p" 2>/dev/null; then
      echo "  $(basename "$p") already applied -- skipping (idempotent rerun)"
    else
      echo "  ERROR: $(basename "$p") does not apply and is not already applied (upstream commit $FLASHHEAD_COMMIT may have drifted) -- aborting"
      exit 1
    fi
  done
else
  echo "  MUNEA_FH_PATCHES_DIR ($MUNEA_FH_PATCHES_DIR) not found -- skipping. Upload deploy/flashhead-patches alongside this script to enable MUNEA_FH_PROFILE_SYNC / MUNEA_FH_SLOT_STREAM."
fi

echo "=== [1/5] requirements（雷1 mediapipe / 雷2 nccl 已修；不動預裝 torch）==="
sed -i 's/mediapipe==0.10.9/mediapipe>=0.10.13/' requirements.txt
sed -i '/nvidia-nccl-cu12/d' requirements.txt
$E/pip install --ignore-installed blinker -r requirements.txt
# GLOWS base image can retain old conda scipy extensions after pip's uninstall.
# Remove the package directory before reinstalling so imports cannot mix builds.
$E/pip uninstall -y scipy || true
rm -rf /root/miniconda3/envs/workenv/lib/python3.11/site-packages/scipy \
  /root/miniconda3/envs/workenv/lib/python3.11/site-packages/scipy-*.dist-info
$E/pip install --no-cache-dir scipy==1.17.1
$E/pip uninstall -y psutil || true
rm -rf /root/miniconda3/envs/workenv/lib/python3.11/site-packages/psutil \
  /root/miniconda3/envs/workenv/lib/python3.11/site-packages/psutil-*.dist-info
$E/pip install --no-cache-dir psutil
$E/pip uninstall -y transformers || true
rm -rf /root/miniconda3/envs/workenv/lib/python3.11/site-packages/transformers \
  /root/miniconda3/envs/workenv/lib/python3.11/site-packages/transformers-*.dist-info
$E/pip install --no-cache-dir transformers==4.57.3

echo "=== [2/5] ninja + flash-attn 預編譯 cp311（雷4 完整檔名）==="
$E/pip install ninja
W=flash_attn-2.8.0.post2+cu12torch2.7cxx11abiTRUE-cp311-cp311-linux_x86_64.whl
wget -q "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.0.post2/$W" -O "/root/$W"
$E/pip install "/root/$W"

echo "=== [3/5] torch cu128 校正（雷3 保險絲；若沒被動過等於空跑）==="
$E/pip install --force-reinstall torch==2.7.1+cu128 torchvision==0.22.1+cu128 --index-url https://download.pytorch.org/whl/cu128 --no-deps

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
$E/hf download Soul-AILab/SoulX-FlashHead-1_3B --local-dir /models/soulx-flashhead-1.3b --exclude "Model_Pro/*"
$E/hf download facebook/wav2vec2-base-960h --local-dir /models/wav2vec2-base-960h
date +%s > /root/t_w_end
echo "ALL_DONE"
