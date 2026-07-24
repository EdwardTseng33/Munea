# Glows.ai 台灣 4090 · FlashHead 臉引擎（2026-07-11 試車紀錄＋重建手冊）

## 2026-07-23 合批手術階段 2 · 多程序部署（同卡 A/B 實測定案）

**今晚同卡 A/B 實測（RunPod 4090、640 渦輪、21 塊）**：3 條 thread 在同一 process 內 p95=1920ms（-100%），同一顆卡改成 3 個獨立 OS process（各自 1 slot）p95=1183ms（-23%，GPU 真的吃到 100%/412W）——**GIL 序列化才是「3 路變超慢」的真病灶，不是階段 1（方案 B）猜測的 CUDA sync 屏障**（那條路也量過：3 thread + 方案 B 拔屏障 p95=1964ms，比不拔還略慢、判定無效，見 `deploy/flashhead-patches/README.md` 的誠實紀錄；方案 B 程式碼保留在 repo 裡，預設關、無害，留作日後計時診斷用）。

**新增元件（都在 `deploy/runpod-avatar/`，跟 `flashhead_server.py` 同一批要上傳的檔案）**：

| 檔案 | 用途 |
|---|---|
| `start-vocaframe.sh` | 多程序啟動器。`MUNEA_FH_PROCS` 未設/設 1 時完全委派給既有 `start-flashhead.sh`，一字不差；設 >1 時開 N 個 `flashhead_server.py` process（各自 `MUNEA_FH_SLOTS=1`、各自埠號 `MUNEA_FACE_PORT+1..+N`、各自 `MUNEA_WORKER_ID` 尾碼 `-p0/-p1/...`）+ 1 個 `flashhead_router.py`。支援 `--dry-run`（或 `MUNEA_FH_DRY_RUN=1`）只印計畫、不真的啟動，方便部署前預覽。 |
| `flashhead_router.py` | 前置分流器（aiohttp），只在 `MUNEA_FH_PROCS>1` 時由啟動器一併起，監聽原本對外的 `MUNEA_FACE_PORT` 不變，依請求裡的 call token（`worker_id` 欄位）把 `/offer`／`/audio`／`/switch`／`/demo/session` 轉給對應的 backend process，`/health` 會 fan-out 聚合成一份跟現行多槽 `/health` 同形狀的 `slots` 陣列。 |
| `flashhead_router_core.py` | 路由決策純邏輯（零重依賴，不 import aiohttp），可離線單元測試——見 `scripts/test_flashhead_router_core.py`（已接進 `test:launch`）。 |

**為什麼需要一個分流器**：Glows 目前一台機器只映射一個對外 http 埠，N 個獨立 process 各自綁不同內部埠號時，只有分流器綁的那個埠是外面連得到的；分流器再依 call token 裡的 `worker_id`（Durable Call Control 核發、`flashhead_server.py` 既有的 `_decode_call_token` 機制本來就會帶這個欄位）轉發給正確的 backend process。路由層只「偷看」token payload 決定轉去哪，不驗證簽章——真正的權限驗證維持在被轉發到的那個 process 裡各自做一次，跟現行完全一樣，路由猜錯的後果最多是白轉一次、被目標 process 的簽章驗證擋下，不會弱化安全性。

**部署步驟草稿（正式線 Glows 卡切雙/三程序，待 Edward/主對話蘇菲離峰時段驗）**：

1. 上傳 `flashhead_server.py`／`flashhead_engine_core.py`／`flashhead_router.py`／`flashhead_router_core.py`／`start-vocaframe.sh` 五個檔案（缺任何一個，`MUNEA_FH_PROCS>1` 時 `start-vocaframe.sh` 會在啟動 router 前主動擋下並印錯誤訊息，不會半殘啟動）。
2. `runtime.env` 加一行 `MUNEA_FH_PROCS=2`（先從 2 開始、確認穩定再考慮 3——今晚 2 process 實測 p95=787ms、18% 餘裕已經達標，3 process 才會逼近 GPU 硬體極限的 23% 缺口）。
3. 先跑 `bash start-vocaframe.sh --dry-run` 確認印出的埠號／`worker_id` 計畫符合預期，再拿掉 `--dry-run` 真的啟動。
4. 驗收：`curl <門牌>/health` 應該回報 `capacity.limit=2`（或設定的 N）且 `slots` 陣列有 N 筆各自的 `worker_id`；`tools/face-acceptance/驗收-FlashHead同線.py` 跑過（會走 `/offer`，實際驗證分流有沒有把請求正確送到某一個 backend process）。
5. 資料庫端（待 Edward/主對話蘇菲確認）：`gpu_workers` 表要幫這張卡新增 N 筆 worker 列，`worker_id` 依序是 `<既有worker_id>-p0`／`-p1`／...，`url` 全部填同一個對外門牌（分流器會處理內部轉發），`capacity` 每筆都填 1（不是 N——現在是「N 個各自 capacity=1 的獨立 worker」模型，不是「1 個 worker capacity=N」）。
6. 觀察至少一輪離峰時段的真實通話（不只是 `/health` 探測），確認 `/audio` WebSocket 全程沒有中途斷線、嘴聲同步正常，再擴大流量占比。
7. 回退路徑：`runtime.env` 拿掉 `MUNEA_FH_PROCS`（或設回 1）+ 重跑 `start-vocaframe.sh`，立刻退回現行單程序行為；`gpu_workers` 的 N 筆列改回 `status='draining'` 讓現有通話跑完、不再派新的。

**已知限制（誠實記錄，非本輪範圍）**：demo 模式（`/demo/session`）固定路由到 process 0，多程序不會幫 demo 流量分攤負載（demo token 只在核發它的那個 process 記憶體裡驗證得過，這是既有單程序時代就有的設計、不是這輪新增的限制）；`/switch` 端點沿用既有 0-based `slot` 參數，跟 call token 裡 1-based 的 `slot_id` 語意不同，保留給人工操作用、不是給 App 呼叫的端點。


## 2026-07-13 RTX 6000 Ada 48GB 實測定案

- 測試卡：GLOWS TW-07，Ubuntu 24.04 Docker NV580，RTX 6000 Ada 48GB，0.720 Credit/hr（NT$23.04/hr）。
- 同版環境：PyTorch 2.7.1+cu128、Flash Attention 2.8.0.post2、SoulX-FlashHead Lite；同一角色圖與 `poc-mandarin.wav`，每塊即時預算 960ms。
- eager 1 路：p50 257ms／p95 259ms；2 路：p95 543ms（43% 餘裕）；3 路：p95 826ms（僅14% 餘裕，不列正式安全值）；4 路：p95 1116ms（失敗）。
- compile 1 路：p95 240ms；3 路：p95 735ms（23% 餘裕，峰值18.9GB，**正式安全容量**）；4 路：p95 999ms（失敗，峰值25.3GB）。
- 結論：瓶頸是300W算力，不是48GB顯存。正式派卡以 **3 sessions/card** 計，容器必須先暖完才進 ready；全新冷編譯約106秒，已有磁碟快取後三路並行暖機約30秒。
- 成本：3人滿載約 NT$0.128／人／分鐘；與4090安全2人約 NT$0.131／人／分鐘幾乎相同，但單機容量多50%。
- 重建腳本已修：requirements 必須 `--ignore-installed blinker`；新版 Hugging Face CLI 改用 `hf download`；requirements 會把 torch 換成cu126，最後必須用 `+cu128 --force-reinstall` 校正。
- 併發碼錶：`deploy/glows/run-concurrent-bench.sh <路數> <塊數> eager|compile`。

## 2026-07-13 RTX 4090 24GB／真768實測定案

- 測試卡：GLOWS控制台區域TW-03（SSH access endpoint為tw-06）；a05／a06推論、服務健康與WebRTC實收皆確認768×768。
- 官方預設仍鎖512，必須同步改`flash_head.inference.infer_params`的height／width；只上傳768底圖仍會輸出512。
- 單路：eager p95約627–649ms；compile離線p95約588ms。正式服務compile兩角色共16塊p95約759ms，20.9%餘裕，僅勉強跨過20%門檻。
- 多路：eager 2路p95約1.35s；compile 2路不穩且最差1.19s；compile 3路約1.61–1.79s、峰值23.9GB。**4090真768容量鎖1人／卡。**
- WebRTC雖收得到影音雙軌，但嘴比聲音早0.78–0.88s，服務有大量underrun；修共同時間軸／緩衝前不能切正式線。
- 測試instance `ins-5y4knd6r`已於2026-07-13 12:41（台北）Stop & Release；清單顯示本輪累計0.430 Credit，依1 Credit約NT$32估算約NT$13.76。

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
