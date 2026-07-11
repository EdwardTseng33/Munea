# Glows.ai 台灣 4090 · FlashHead 臉引擎（2026-07-11 試車紀錄＋重建手冊）

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
4. 通話服務：跑 `deploy/runpod-avatar/flashhead_server.py`（獨立版、機器無關）
5. 驗收：`tools/face-acceptance/驗收-FlashHead同線.py <門牌>`

## 鑰匙
- SSH 私鑰：`deploy/glows/glows_ed25519`（已 gitignore；公鑰已登記在 Edward 帳號 Profile）
- 帳號：Edward（user_514f94b7）；SDK 通行碼之後接自動開關時再請 Edward 從 Profile 抄一次

## 已知眉角
- 「Stop & Release」＝整台退還、環境消失 → 要保環境先 Snapshot；或直接用本手冊 5 分鐘重建
- 重開後 SSH 埠號/門牌會變 → 自動化要先查 instance 資訊再指路（SDK GET /sdk/v1/instance）
- conda 環境在 `/root/miniconda3/envs/workenv`（py3.11）；`/root/workenv` 是空資料夾別踩
- 尖峰缺卡備援：TW-03 ↔ TW-04 ↔（最後）美國 RunPod 線
