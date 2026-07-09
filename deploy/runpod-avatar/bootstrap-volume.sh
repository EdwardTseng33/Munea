#!/usr/bin/env bash
# 沐寧 · 置物櫃裝機（2026-07-09 · 暫停/喚醒實測失敗後的替代路線）
# 概念：所有「裝過的東西」全放網路置物櫃（network volume，掛 /workspace）——
#       模型、Python 依賴（venv）、cuDNN8、服務程式、寧寧照。
#       之後喚醒＝開一張全新卡掛同一個置物櫃 → 直接 wake.sh 起服務、零重裝。
# 用法：podctl.py create --volume=<id> → scp 本檔+素材 → bash bootstrap-volume.sh
# 環境前提：runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04（torch 由映像提供、venv 共用）
set -euo pipefail

echo "== [1/6] 系統套件（⚠ 必先 update；這步不進置物櫃、喚醒時 wake.sh 會重跑 ~20s）=="
apt-get update -qq
apt-get install -y -qq ffmpeg libgl1 libgles2 libegl1 libopengl0 libglib2.0-0 > /dev/null

echo "== [2/6] venv（開在置物櫃上、共用映像的 torch）=="
cd /workspace
[ -d venv ] || python -m venv --system-site-packages venv
source venv/bin/activate

echo "== [3/6] 臉引擎 + numpy2 修正（都在置物櫃上）=="
[ -d ditto-talkinghead ] || git clone --depth 1 https://github.com/antgroup/ditto-talkinghead
sed -i 's/np\.atan2/np.arctan2/g' ditto-talkinghead/core/aux_models/mediapipe_landmark478.py

echo "== [4/6] Python 依賴（版本全釘死 · 裝進置物櫃 venv）=="
pip install -q --no-input numpy==1.26.4 librosa tqdm filetype imageio imageio-ffmpeg \
  opencv-python-headless scikit-image cython colored polygraphy soundfile mediapipe einops \
  aiohttp aiortc huggingface_hub 2>&1 | tail -1
pip install -q --no-input 'onnxruntime-gpu==1.18.1' 2>&1 | tail -1
pip install -q --no-input 'tensorrt==8.6.1.post1' 'cuda-python==12.4.0' 2>&1 | tail -1
[ -d /workspace/cudnn8-pkgs ] || pip install -q --no-input --target /workspace/cudnn8-pkgs nvidia-cudnn-cu12==8.9.7.29 2>&1 | tail -1

echo "== [5/6] 模型權重（只抓 4090 用得到的）=="
cd ditto-talkinghead
python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("digital-avatar/ditto-talkinghead", local_dir="./checkpoints",
                  allow_patterns=["ditto_cfg/*", "ditto_trt_Ampere_Plus/*"])
print("weights done")
PY

echo "== [6/6] 一鍵喚醒腳本（新卡掛櫃後只跑這支）=="
cat > /workspace/wake.sh <<'WAKE'
#!/usr/bin/env bash
# 全新卡 + 舊置物櫃 → 起臉服務（量測點：本腳本開跑→ /health ok）
set -e
# 現場編譯暫存放置物櫃（7/9 實測抓到：不放的話每次喚醒重編、多燒 30-60 秒）
mkdir -p /workspace/pyxbld && ln -sfn /workspace/pyxbld /root/.pyxbld
apt-get update -qq && apt-get install -y -qq ffmpeg libgl1 libgles2 libegl1 libopengl0 libglib2.0-0 > /dev/null
export MUNEA_AVATAR_SRC=/workspace/nening-real-female-full.jpg
export LD_LIBRARY_PATH=/workspace/cudnn8-pkgs/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}
cd /workspace/ditto-talkinghead
nohup /workspace/venv/bin/python -u /workspace/avatar_cloud_server.py > /root/avatar.log 2>&1 &
echo "WAKE LAUNCHED"
WAKE
chmod +x /workspace/wake.sh

echo "BOOTSTRAP-VOLUME DONE（置物櫃就緒：venv + 模型 + cuDNN8 + wake.sh）"
