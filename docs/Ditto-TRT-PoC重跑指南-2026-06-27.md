# Ditto TensorRT 25fps 即時 PoC · 一鍵重跑指南（2026-06-27 · 卡西法 CTO）

> keystone (a)：Ditto TRT 路能不能在一張 RTX 4090 上跑出 ≥25fps + 首幀 ≤1.5s + 串流邊生邊播。
> 這是「即時聊天臉」整個立論的物理門檻。上次 PyTorch 路只跑 12fps（半即時），TRT 版理論快 2-4 倍、預期到即時。
> 給 Edward 在 RunPod 一步步照做用。每步都寫了「會看到什麼」跟「卡住怎麼辦」。

## 0 · 開跑前先懂一件事（為什麼上次 TRT 編不過）
上次 `tensorrt==8.6.1` 裝不上，**不是 tensorrt 壞，是 RunPod 範本選太新**。
- 上次範本 CUDA **12.8** → 對 8.6.1 太新、編不過。
- Ditto 官方環境（environment.yaml）：**PyTorch 2.5.1 + CUDA 12.1 + tensorrt 8.6.1**，預編 `.engine` 就是這版導出的。
- **核心策略＝環境降回 CUDA 12.1**，讓 8.6.1 直接裝得上、預編 engine 直接載入。不要找更新的 tensorrt（反方向撞牆）。

## 1 · 開 RunPod Pod（關鍵在選對範本）
1. RunPod → Deploy → GPU 選 **RTX 4090**（$0.69/hr、24GB）。
2. 範本選 **CUDA 12.1 系列** PyTorch：首選 `RunPod PyTorch 2.4.0`（CUDA 12.1）或任何標 **cuda 12.1** 的。⚠️ 不要選 12.8/12.6。
3. 磁碟 ≥ 40GB。
4. Deploy → Running → Connect → Jupyter/Web Terminal。
> 確認範本對：Terminal 貼 `nvcc --version`，看到 `release 12.1` 才對；看到 12.4/12.6/12.8 → 砍 Pod 重選。

## 2 · 裝環境 + 抓模型（一段段貼）
**第 1 段 · 程式碼 + 系統工具**
```bash
cd /workspace
git clone https://github.com/antgroup/ditto-talkinghead && cd ditto-talkinghead
apt-get update -y && apt-get install -y git-lfs ffmpeg libgl1 libgles2 libegl1 libglib2.0-0 libxrender1 libsm6 libxext6
git lfs install
```
**第 2 段 · TensorRT 8.6.1 + 套件（這次重點）**
```bash
pip install tensorrt==8.6.1 tensorrt-bindings==8.6.1 tensorrt-libs==8.6.1
pip install librosa tqdm filetype imageio opencv_python_headless scikit-image cython cuda-python imageio-ffmpeg colored polygraphy "numpy==2.0.1" onnxruntime mediapipe einops
```
看到 `Successfully installed tensorrt-8.6.1` 即過。這是上次卡關處——在 12.1 範本上應順順裝完。
**第 3 段 · 模型（含 TRT 預編 engine）**
```bash
git clone https://huggingface.co/digital-avatar/ditto-talkinghead checkpoints
cd checkpoints && git lfs pull && cd ..
ls -lh checkpoints/ditto_trt_Ampere_Plus/
```
要看到一排 `.engine`（幾十 MB~幾百 MB、不是幾 KB）。都幾 KB → lfs 沒拉成功、重跑 `cd checkpoints && git lfs pull && cd ..`。

## 3 · 第一跑：TRT 離線模式測「真 fps」
```bash
time python inference.py \
  --data_root "./checkpoints/ditto_trt_Ampere_Plus" \
  --cfg_pkl "./checkpoints/ditto_cfg/v0.4_hubert_cfg_trt.pkl" \
  --audio_path "./example/audio.wav" \
  --source_path "./example/image.png" \
  --output_path "./tmp/result_trt.mp4"
```
進度條的 **`it/s` 就是真 fps**（上次 PyTorch 是 11.81 it/s≈12fps、TRT 應明顯變大）。⚠️ 別用「總格數÷time 總耗時」算（time 含模型載入幾秒、會被拖低），看進度條 `it/s`。

## 4 · 第二跑：串流線上模式測「首幀延遲 + 邊生邊播」
把 cfg 換 **online 版**（檔名多 `_online`）：
```bash
time python inference.py \
  --data_root "./checkpoints/ditto_trt_Ampere_Plus" \
  --cfg_pkl "./checkpoints/ditto_cfg/v0.4_hubert_cfg_trt_online.pkl" \
  --audio_path "./example/audio.wav" \
  --source_path "./example/image.png" \
  --output_path "./tmp/result_online.mp4"
```
online＝把音切小塊邊餵邊生（真實對話運作方式）。同看 `it/s`。
**首幀延遲（白話）**：腳本整段跑完才存檔、不直接印首幀。PoC 先用替代判斷：online `it/s ≥ 25` = 生得比播得快、首幀落可接受範圍（理論 ~0.6s）。要精準值 → 叫卡西法補一段加計時器的 `inference_timed.py`（標**半自動需補腳本**）。

## 5 · 看臉（速度只是一半）
Jupyter 下載 `tmp/result_trt.mp4` 自己播，看：① 對嘴同步 ② 自然無鬼影抖動 ③ TRT(fp16) 畫質有沒比 PyTorch 掉（理論肉眼難分）。

## 6 · 最可能卡的步驟 + 怎麼解
| 卡點 | 症狀 | 解 |
|---|---|---|
| ①範本選錯⚠️最常見 | nvcc 顯 12.4/12.6/12.8 | 砍 Pod 重選 12.1、別硬跑 |
| ②tensorrt 裝不上 | 第 2 段紅字 | 先確認範本 12.1；仍失敗用官方 conda：`conda env create -f environment.yaml && conda activate ditto`（最穩、多花 10-15 分）|
| ③engine 載入報錯 | `version mismatch`/plugin 紅字 | 自己重編：`python scripts/cvt_onnx_to_trt.py --onnx_dir "./checkpoints/ditto_onnx" --trt_dir "./checkpoints/ditto_trt_custom"`、inference 的 `--data_root` 改 custom（多 ~10 分、保證對你的卡）。**整份最可能要動手的退路。** |
| ④lfs 沒拉大檔 | `.engine` 都幾 KB | 重跑 `git lfs pull` |
| ⑤缺 .so 圖形庫 | `libGLESv2` cannot open | 第 1 段 apt-get 已含；仍缺把庫名貼給卡西法補 |

## 7 · 過/不過判準
| 指標 | 目標 | 看 |
|---|---|---|
| 真 fps（看 online 那次）| **≥25** = 過 | 進度條 `it/s` |
| 首幀延遲 | ≤1.5s = 過 | online `it/s≥25` 即達標（精準需補腳本）|
| 串流邊生邊播 | online `it/s` 持平 ≥25 不掉 = 過 | 同上 |
| 畫質 | 臉自然、對嘴 OK = 過 | 人工看 |
- 🟢 GO：online `it/s≥25`+畫質 OK → 即時聊臉立論成立、keystone (a) 釘死。
- 🟡 有條件 GO：`it/s` 18-24 → 再調一輪（解析度/batch/更強卡）。
- 🔴 NO-GO：online `it/s` 明顯 <18 拉不上 → 退「純語音+靜態臉、看臉才生片段」混合。

## 8 · 花多久/多少錢/會知道什麼
- **30-45 分鐘**（裝環境~15+抓模型~10+兩跑~10+看片）；撞退路③+15 分。
- **不到 NT$25**（4090 $0.69/hr×~1hr）。
- 跑完知道：Ditto TRT 在 4090 真 fps 幾、串流順不順、畫質有沒掉 → 直接決定**標準引擎整條線 GO 或走退路**（兩引擎裡服務所有人那條的命脈）。

*Ditto TRT PoC 指南 v1 · 2026-06-27 · 卡西法（讀官方 README+environment.yaml+inference.py 源碼）· 核心修正：環境降回 CUDA 12.1。*
