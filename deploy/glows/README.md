# Glows.ai 台灣 4090 · FlashHead 臉引擎（2026-07-11 試車紀錄＋重建手冊）

## 2026-07-13 RTX 6000 Ada 48GB 實測定案

- 測試卡：GLOWS TW-07，Ubuntu 24.04 Docker NV580，RTX 6000 Ada 48GB，0.720 Credit/hr（NT$23.04/hr）。
- 同版環境：PyTorch 2.7.1+cu128、Flash Attention 2.8.0.post2、SoulX-FlashHead Lite；同一角色圖與 `poc-mandarin.wav`，每塊即時預算 960ms。
- eager 1 路：p50 257ms／p95 259ms；2 路：p95 543ms（43% 餘裕）；3 路：p95 826ms（僅14% 餘裕，不列正式安全值）；4 路：p95 1116ms（失敗）。
- compile 1 路：p95 240ms；3 路：p95 735ms（23% 餘裕，峰值18.9GB，**正式安全容量**）；4 路：p95 999ms（失敗，峰值25.3GB）。
- 結論：瓶頸是300W算力，不是48GB顯存。正式派卡以 **3 sessions/card** 計，容器必須先暖完才進 ready；全新冷編譯約106秒，已有磁碟快取後三路並行暖機約30秒。
- 成本：3人滿載約 NT$0.128／人／分鐘；與4090安全2人約 NT$0.131／人／分鐘幾乎相同，但單機容量多50%。
- 重建腳本已修：requirements 必須 `--ignore-installed blinker`；新版 Hugging Face CLI 改用 `hf download`；requirements 會把 torch 換成cu126，最後必須用 `+cu128 --force-reinstall` 校正。
- 併發碼錶：`deploy/glows/run-concurrent-bench.sh <路數> <塊數> eager|compile`。

## 一句話結論
台灣 4090 三關全過：**開機 1 分鐘**、**儲值制關機即停錶（有 SDK 可自動開關）**、
**「講話截斷＝顯卡不夠」實錘**（同程式同料：Modal L4 p95 905ms vs 這台 309ms，預算 960ms）。

## 2026-07-11 實測成績單（ins-wg9983mg · TW-03 · RTX 4090 24GB）
| 項目 | 數字 |
|---|---|
| Edward 家 → 機器 來回 | **8ms**（美國 RunPod 204ms） |
| eager 每塊 p50 / p95 / max | **305 / 309 / 321 ms**（餘裕 67.8%、3.15x 即時、78.8 FPS） |
| eager 長跑 120 塊（~2分鐘連續講）| p50 307 / p95 320 / max 327 —— 零累積、零惡化 |
| compile 每塊 p50 / p95 | 245 / 270 ms（更快，但每次開機多付 ~2 分鐘編譯稅 → **不用**） |
| 引擎開機（eager）| pipeline 3.6s + 底圖 0.3s + 暖跑 0.8s ≈ **5 秒內** |
| 權重下載 8.9GB | 85 秒 |
| 計費 | 0.49 Credit/hr；1 Credit=NT$32 → **NT$15.7/hr**、全天 NT$376、月 NT$11.3k |

## 重建 SOP（機器 Release 後隨時重來，約 5 分鐘）
1. 主控台 Create New → 映像選 **CUDA12.8 Torch2.7.1 Base**（img-gzq2xep6；py3.11+torch2.7.1+cu128 預裝）
   → 4090 TW-03/TW-04 → 不掛 Datadrive、不 Bind IP → Create（約 1 分鐘 Running）
2. Access → SSH Port 22 拿 `ssh -p <埠> root@tw-XX.access.glows.ai`
3. 上傳並跑 `install-flashhead.sh`（本目錄；含先鋒 6 雷防雷。⚠ flash-attn 用 **cp311** 版）
   ＋上傳角色底圖 `deploy/flashhead-poc/assets/a0*-inB-512.png` → `/root/char-a0*.png`
4. 通話服務：**兩個檔案都要上傳**——`deploy/runpod-avatar/flashhead_server.py` +
   `deploy/runpod-avatar/flashhead_engine_core.py`（2026-07-12 N 槽改造後拆成兩檔，
   只傳第一個會 ImportError 開機失敗）。跑 `python3 flashhead_server.py`（獨立版、
   機器無關）。預設單槽，行為跟改造前一字不差；測試卡要多槽時設
   `MUNEA_FH_SLOTS=3` 環境變數（未經真機驗證前，正式服務不要設這個變數）。
5. 驗收：`tools/face-acceptance/驗收-FlashHead同線.py <門牌>`

## 鑰匙
- SSH 私鑰：`deploy/glows/glows_ed25519`（已 gitignore；公鑰已登記在 Edward 帳號 Profile）
- 帳號：Edward（user_514f94b7）；SDK 通行碼之後接自動開關時再請 Edward 從 Profile 抄一次

## 已知眉角
- 「Stop & Release」＝整台退還、環境消失 → 要保環境先 Snapshot；或直接用本手冊 5 分鐘重建
- 重開後 SSH 埠號/門牌會變 → 自動化要先查 instance 資訊再指路（SDK GET /sdk/v1/instance）
- conda 環境在 `/root/miniconda3/envs/workenv`（py3.11）；`/root/workenv` 是空資料夾別踩
- 尖峰缺卡備援：TW-03 ↔ TW-04 ↔（最後）美國 RunPod 線
