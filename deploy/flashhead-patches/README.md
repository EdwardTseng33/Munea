# FlashHead 上游 patch 目錄

`SoulX-FlashHead` 是整包 `git clone` 到每台 GPU 機器上的第三方副本（`deploy/glows/install-flashhead.sh`／`deploy/runpod-avatar/install-flashhead.sh`），不是 pip 套件、也不 vendor 進這個 repo。要改上游程式碼一律走「patch 檔 + 裝機腳本自動套用」，不手改機器上的檔案，理由見 `docs/research/合批手術-設計方案-2026-07-23.md` 第 3 節相容性鐵律第 4 條。

## 目錄慣例

- 檔名 `NNNN-描述.patch`，四碼流水號、只增不改（既有 patch 不回頭改內容，要調整就開新編號）。
- 每個 patch 都必須：① 對準 `MUNEA_FH_COMMIT`（目前 `9bc03de06bb0de82cd6bc477804512ae06144bf2`）純淨 checkout 套得上 ② 用 `git apply --check` 與 GNU `patch -p1 --dry-run` 都驗證過 ③ 產生方式全程 `core.autocrlf=false`（LF only），避免 Windows 開發機的 CRLF 污染patch 內容，導致 Linux GPU 機器上 apply 失敗。
- 裝機腳本套用順序：`git checkout --detach $MUNEA_FH_COMMIT` 之後、`pip install -r requirements.txt` 之前，依編號順序套用本目錄下所有 `*.patch`。

## 0001-gate-profile-sync.patch

**動哪個檔**：`flash_head/src/pipeline/flash_head_pipeline.py`（僅此一檔）。

**做什麼**：`FlashHeadPipeline.generate()` 原本有 8 處無條件 `torch.cuda.synchronize()`（denoise 迴圈內 2 處 × 4 步、VAE decode 前後、color correction 前後、motion frame encode 前後），全部只是為了緊接著的 wall-clock `print()` 計時，不是正確性需要——但這是全裝置屏障，Munea 的 N 槽服務把三個槽跑在同一個 process 的三條 Python thread 裡（共用一個 CUDA context），這些屏障會把其他槽當下排隊中的 kernel 也一起等，是「3 路變超慢」的主要病灶。完整分析見設計文件第 1.2 節第 ③ 點。

這支 patch 把 8 處呼叫全部換成 `_profile_sync()`（新增的小函式），並新增一個模組層級旗標 `PROFILE_SYNC`（預設 `True`，跟改動前行為一字不差）。

**開關方式**：跟這個檔案既有的 `COMPILE_MODEL`／`COMPILE_VAE` 外部覆寫慣例一致——patch 本身不去讀 `os.environ`，而是由 `flashhead_server.py` import 這個模組後，把 `MUNEA_FH_PROFILE_SYNC` 環境變數的值指派給 `PROFILE_SYNC`（`_fhp_mod.PROFILE_SYNC = ...`，緊接著現有 `_fhp_mod.COMPILE_MODEL = _COMPILE` 那幾行之後）。

| 環境變數 | 未設 / 其他值 | `MUNEA_FH_PROFILE_SYNC=0` |
|---|---|---|
| 行為 | `PROFILE_SYNC=True`，8 處屏障全部照舊觸發，跟改動前一字不差 | `PROFILE_SYNC=False`，8 處屏障全部跳過；緊接著的 `print()` 計時行還是會印，但不再代表真正 GPU-drained 的時間 |

**為什麼安全**：denoise 迴圈跟 VAE decode/encode 的資料相依鏈完全靠 CUDA stream 本身排序，不靠這些 host-side barrier 保正確性——這些 sync 拔掉後，運算結果不會變、只是不再每一步都停下來等全裝置排隊做完。零損驗證計畫見設計文件第 4 節（`MUNEA_FH_PROFILE_SYNC=0` 目標是位元級輸出不變）。

**單獨開這個旗標的效果有限**：`torch.cuda.synchronize()` 是全裝置等待、不分 stream；如果三個槽的 kernel 都還在同一條 default stream 上（`MUNEA_FH_SLOT_STREAM` 沒開），拔掉這些屏障後 GPU 排程器本來就會照 stream 上的順序執行，效果會比「兩個開關都開」小。要驗證方案 B 的完整效果，實驗卡上請同時設 `MUNEA_FH_PROFILE_SYNC=0` 與 `MUNEA_FH_SLOT_STREAM=1`（見下方「每槽獨立 CUDA stream」段）。

## 每槽獨立 CUDA stream（不是 patch，是我方程式碼）

跟上面的 patch搭配、但這塊改動在 Munea 自己的 `deploy/runpod-avatar/flashhead_engine_core.py`／`flashhead_server.py`，不是上游 vendored 檔案，所以沒有另立 patch 檔：

- `flashhead_engine_core.py` 新增 `make_slot_stream_run_pipeline(run_pipeline_fn, stream, torch_module)`——依賴注入 `torch_module`（不在這個零重依賴模組內 import torch），把 `run_pipeline` 包成「在 `stream` 上跑、跑完用 `wait_stream` 把結果非阻塞地交回呼叫端目前的 stream」，不是再加一個全裝置 `synchronize()`（那樣就白拔了上面那 8 個屏障）。
- `flashhead_server.py` 新增 `MUNEA_FH_SLOT_STREAM` 環境變數（預設 `0`，不建立額外 stream，跟現行行為一致）；`=1` 時 `_wake_slot()` 幫每個槽建立一條 `torch.cuda.Stream()`，並用上面的 wrapper 包住該槽的 `run_pipeline`。

## 套用驗證（本機、無 GPU）

`scripts/test_flashhead_patch_integrity.py`——不需要網路、不需要 clone 上游 repo，純靜態檢查這個目錄下每個 patch 檔的結構（合法 unified diff、只動預期檔案、LF only、8 個屏障呼叫點的移除/新增數量對得上）。跑法：

```
python scripts/test_flashhead_patch_integrity.py
```

若要做「真的套進 commit 9bc03de 純淨 checkout」這種需要網路的複驗（今晚 session 已手動跑過兩次、`git apply --check` 與 `patch -p1 --dry-run` 皆過），可另外手動執行（不在 `test:launch` 鏈路裡，避免 CI 因為網路問題誤判失敗）：

```
git clone --filter=blob:none https://github.com/Soul-AILab/SoulX-FlashHead.git /tmp/fh-verify
cd /tmp/fh-verify && git checkout --detach 9bc03de06bb0de82cd6bc477804512ae06144bf2
git apply --check /path/to/repo/deploy/flashhead-patches/0001-gate-profile-sync.patch
```
