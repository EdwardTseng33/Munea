# LiveAvatar 即時 45fps PoC · 一鍵重跑指南（2026-06-27 · 卡西法 CTO）

> keystone (b)+(c)：LiveAvatar 能不能真出 45fps + 冷啟動幾秒 + 一組資源服務一路的獨佔性。生動引擎整個立論。
> 給 Edward 在 RunPod 一步步照做用。

## 0 · 開跑前兩個改變策略的新情報（重要）
讀官方最新 README 發現兩條藍圖當時還沒納入的更新，**讓這 PoC 變便宜很多**：
1. **2026.1.20 v1.1**：FP8 量化 + 編譯優化 → **單張 80GB 卡就能跑即時**（官方原話「不需 5×H800 那種房價伺服器」）、速度平均 3 倍、單卡逼近 45fps。
2. 官方已釋出單卡腳本 `infinite_inference_single_gpu.sh`。
→ **策略＝先用 1 張 H100/H200（80GB）跑單卡即時，釘死「45fps + 冷啟動」**。單卡 ~$2-3/hr、比 5×H800（~$12.5/hr）省 4-5 倍、符合燒錢 Gate。
> 但書：5 卡的意義是把速度再推到穩定 45fps + production。單卡跑出接近 45 = 立論成立；單卡只到 25-30 = 穩定 45 需多卡、再決定要不要燒（見第 6 節）。

## 1 · 開 RunPod Pod（這次要大卡）
1. GPU 選 **H100（80GB）/ H200（141GB）**（H100 ~$2.5-4/hr）。⚠️ **一定 ≥80GB**——RTX 4090(24GB) 裝不下 14B（物理限制、藍圖 Q1 已算）。找不到 H800 沒關係，H100/H200 同 Hopper 架構、單卡 PoC 可推論。
2. 範本選 **CUDA 12.8 PyTorch**（跟 Ditto 相反、LiveAvatar 要 PyTorch 2.8 + CUDA 12.8 + FlashAttention 3）：`RunPod PyTorch 2.8.0`。
3. 磁碟 ≥ 120GB（模型很大）。
4. Deploy → Running → Connect。
> H800 在哪租：RunPod 以 H100/H200 為主、H800 是中國市場型號不一定有。單卡 PoC 用 H100 即可；要驗 production 真實 5×H800 再去 DataCrunch/阿里雲/火山引擎（後話）。

## 2 · 裝環境（比 Ditto 久）
**第 1 段 · 程式碼**
```bash
cd /workspace
git clone https://github.com/Alibaba-Quark/LiveAvatar && cd LiveAvatar
apt-get update && apt-get install -y ffmpeg git-lfs
git lfs install
```
**第 2 段 · PyTorch 2.8 + FlashAttention 3（Hopper 加速關鍵）**
```bash
pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
pip install flash_attn_3 --find-links https://windreamer.github.io/flash-attention3-wheels/cu128_torch280 --extra-index-url https://download.pytorch.org/whl/cu128
```
FA3 是 H100/H200/H800 專用加速、**影響能否到 45fps**、留意紅字。失敗退路：`pip install flash-attn==2.8.3 --no-build-isolation`（FA2、慢一點能跑）。
**第 3 段 · 其他套件**
```bash
pip install -r requirements.txt
pip install "huggingface_hub[cli]"
```
**第 4 段 · 模型（最久、很大）**
```bash
huggingface-cli download Wan-AI/Wan2.2-S2V-14B --local-dir ./ckpt/Wan2.2-S2V-14B
huggingface-cli download Quark-Vision/Live-Avatar --local-dir ./ckpt/LiveAvatar
ls -lh ckpt/Wan2.2-S2V-14B/ ; ls -lh ckpt/LiveAvatar/
```
要看到 `.safetensors` 大檔（base model 好幾 GB）。這步 10-30 分（看網速）、整份最久。

## 3 · 第一跑：單卡即時模式（量真 fps）
先關編譯求快出結果：
```bash
export ENABLE_COMPILE=false
export ENABLE_FP8=true
bash infinite_inference_single_gpu.sh
```
`ENABLE_COMPILE=false`（開編譯第一次要等很久、PoC 先關）；`ENABLE_FP8=true`（單卡裝得下+加速、畫質略降）。
**真 fps**＝進度訊息印的 fps。目標 ≥45；單卡+FP8+不編譯**誠實預期 25-40fps（沒到 45 正常）**。想衝滿 → `ENABLE_COMPILE=true` 重跑（第一次編譯等十幾分、之後快）。

## 4 · 第二跑：量冷啟動秒數（keystone c）
```bash
time bash infinite_inference_single_gpu.sh
```
冷啟動 ≈ 從按 enter（t0）到螢幕第一次印「正在生成/第一格 fps」（t1）的時間。⚠️ 第一次含「模型從硬碟讀進 GPU」會久（可能 30-90 秒）。**真正決定體驗的是「模型已在 GPU、idle 睡著→喚醒出第一格」那種冷啟動**——這用單純腳本量不準、需卡西法補「常駐服務+喚醒計時」測試碼（標**半自動需補腳本**）。PoC 先求量級：第一次完整載入幾秒 → 已能粗答「10 秒等級還是 90 秒等級」、足以決定藍圖 B.2 容錯走哪層。

## 5 · 第三跑（選配）：驗「一組資源只服務一路」
生成跑著時、另開 Terminal：
```bash
watch -n 1 nvidia-smi
```
看 GPU-Util 幾乎打滿（90-100%）+ VRAM 吃滿 → 一張卡跑一路就吃滿算力 → 「per-session 獨佔」假設成立（藍圖成本結構）。多卡獨佔性要真 5 卡才驗、PoC 不需要。

## 6 · 最可能卡的步驟 + 解/退路
| 卡點 | 症狀 | 解/退路 |
|---|---|---|
| ①模型下載慢/斷 | huggingface-cli 卡住 | 重跑同行（續傳）、耐心等 |
| ②FA3 裝不上 | 第 2 段紅字 | 退 FA2：`pip install flash-attn==2.8.3 --no-build-isolation`（fps 低一點能跑）|
| ③VRAM 爆(OOM) | `CUDA out of memory` | 確認 `ENABLE_FP8=true`；調小 `size`(降解析度)；還爆換 H200(141GB)|
| ④單卡 fps 上不去 | 卡 20-30 | 開 `ENABLE_COMPILE=true` 重跑（編譯後快、第一次等十幾分）|
| ⑤Modal 綁多卡 | （production 問題、PoC 不遇）| 藍圖風險(e)、PoC 用單卡不碰、production 退路=自管 instance+controller |
| ⑥真要驗 5×H800 | RunPod 沒 H800 現貨 | 單卡過了再說、真要去 DataCrunch/阿里雲/火山引擎（~$12-15/hr）。**先別燒** |

## 7 · 過/不過判準
| 指標 | 目標 | 看 |
|---|---|---|
| 真 fps(單卡 FP8) | 不編譯 ≥25 / 編譯後逼近 45 = 過 | 生成 fps |
| 冷啟動量級 | 知道「10 秒級」or「90 秒級」= 達成 | t1−t0 + time |
| 獨佔性 | 單卡 GPU-Util 打滿、塞不下第二路 = 證明 | nvidia-smi |
| 畫質 | 臉自然、對嘴 OK、明顯比 Ditto 生動 = 過 | 人工看 |
- 🟢 GO：編譯後 fps 摸 40-45、冷啟動 idle 藏得住量級(≤20s)、畫質明顯比 Ditto → keystone (b)(c) 釘死、生動引擎可投基建、**且單卡就跑得動=成本比藍圖樂觀**。
- 🟡 有條件 GO：單卡只 25-35、要 5 卡才穩 45 → 立論成立但成本回藍圖原估(5 卡~NT$200/人)、維持尊榮版有額度策略。要不要燒 5 卡驗 production 由 Edward 拍。
- 🔴 NO-GO：單卡跑不出/冷啟動 >60s 藏不住/畫質沒比 Ditto 好到值得 → 退「LiveAvatar 只做離線預生特殊片段（生日/歡迎）、生動降為奢侈片段非即時」（成本極低、產品照樣上）。

## 8 · 花多久/多少錢/會知道什麼
- **1.5-3 小時**（裝環境~20+抓大模型 10-30 是大頭+不編譯跑~15+編譯版+20+量冷啟動+看片）。
- **約 NT$200-300**（H100 ~$3/hr×2-3hr）；加編譯版+NT$100。⚠️ **跑完記得關 Pod**（H100 一小時 NT$100、忘關持續燒）。
- 跑完知道：① 單卡真 fps（回答「45 是不是只能多卡」）② 冷啟動量級（決定切換容錯哪層）③ 獨佔性 ④ 生動畫質比 Ditto 好多少 → 直接決定**生動引擎 GO/有條件 GO(要 5 卡走尊榮)/NO-GO(降級離線預生)**。兩引擎裡風險最高最貴最該先釘死那條。

*LiveAvatar PoC 指南 v1 · 2026-06-27 · 卡西法（讀官方最新 README）· 核心策略：用官方新釋出單卡 FP8 路徑先驗、比 5×H800 省 4-5 倍。*
