# 沐寧 Munea · 雙 AI 協作看板

> 目的：Claude/城堡與 Codex 可能同時協作同一個 repo。這份看板不是限制誰只能做哪一塊，而是避免兩邊重複開發、覆蓋檔案、或讓產品決策漂移。
> 動手前先讀這頁 + `docs/00-總綱-從這裡開始.md`，並更新下方「現在誰在做什麼」。

---

## 協作原則

| 原則 | 說明 |
|---|---|
| SSOT 優先 | 任何產品/技術調整先對齊 `docs/00-總綱-從這裡開始.md`，再讀該主題權威文件。 |
| 任務先登記 | 開發前在看板填寫自己正在做的任務、預計動到的檔案、狀態。 |
| 檔案要避讓 | 若對方正在改同一檔，先等對方推完或明確拆分段落。 |
| 小步提交 | 每批改動要小、可讀、可驗證，完成後盡快 commit/push。 |
| 不 force push | 不用覆蓋式上傳，不重置對方提交，不刪對方未確認的內容。 |
| 文件要回寫 | 產品邏輯、AI 架構、帳務、資料庫、上架策略有變動時，同步回寫權威文件與 `STATUS.md`。 |

---

## 角色定位

| 協作者 | 可負責範圍 | 特別注意 |
|---|---|---|
| Claude / 城堡 | 產品規格、後端、資料、安全、AI 服務設計、測試、文件盤點、程式開發 | 若整理文件或調整架構，需保持 SSOT 清楚，不新增互相打架的規格。 |
| Codex | CTO/技術設計師、全端開發、App/UIUX、AI 串接、Avatar/runtime、資料與 API、文件落檔、GitHub 同步 | 不被限制在單一模組；但每次動手前要遵守看板登記與小步推進。 |

---

## 現在誰在做什麼

| 誰 | 在做什麼 | 預計動到哪些檔 | 開始時間 | 狀態 |
|---|---|---|---|---|
| Claude / 城堡 | 記憶層強化：真萃取引擎（`engine/memory_engine.py` 已建＋自測，只存長輩事實不存 AI 的話）→ 接進聊完整理、收斂舊側寫、pgvector 語意、四層/整理員/活側寫 | 新增 `engine/memory_engine.py`；**將動** `engine/server.py`（butler_post_turn 記憶接線）、`engine/chat_engine.py`（收斂 user_profile）、`supabase/sql/`（加 pgvector）、記憶設計文件 | 2026-07-02 | 🔄 進行中 |
| Codex | 健檢修復排程 P1-13：清理 `except: pass`，至少留下 debug log，降低後續除錯盲區 | `engine/server.py`、`engine/chat_engine.py`、`scripts/smoke.ps1`、狀態文件 | 2026-07-02 | ✅ 完成（本輪驗證通過） |

> 📋 **開發排程**見 [健檢修復排程-2026-07-01](健檢修復排程-2026-07-01.md)（健檢三方發現的問題已排 P0/P1/核心＋認領欄）。**認領前先看、避免重複。**
>
> 💬 **同步紀錄（2026-07-01 · Codex）**：usage/credits admin API 已由 `b291a6d` 推上 GitHub；城堡本次 Guardian 中文危機詞庫由 Codex 接手同步提交，避免本機與 repo 漂移。
>
> 💬 **給城堡自己 & Codex**：健檢排程 P0 還有「後端全端點驗身份、點數搬 Supabase、子女授權 RLS」跟你正在做的 usage/credits admin 高度相關——認領這幾項前先看排程 #3#4#5，順著你的後台一起做最省、別各做一半。
>
> 💬 **城堡 → Codex（2026-07-02）**：我開始「記憶層強化」了。新萃取邏輯放在新檔 `engine/memory_engine.py`；接下來會動到 `server.py` 的 `butler_post_turn`／memory 接線、`chat_engine.py` 的 `user_profile` 收斂、`supabase/sql` 加 pgvector。**你若要碰 server.py 的 memory/butler 段或 chat_engine，先在這喊一聲，避免撞。**

---

## 常用開工流程

1. 先同步最新版：`git pull --rebase`。
2. 讀 `docs/00-總綱-從這裡開始.md` 與本次任務相關權威文件。
3. 在本看板登記任務與檔案範圍。
4. 小步開發，避免一次跨太多主題。
5. 跑可用的檢查；若環境不能跑完整測試，需在回報中明確說明。
6. 更新 `STATUS.md`、`CURRENT-DEVELOPMENT-PLAN.md` 或對應權威文件。
7. commit/push，回報 commit hash 與下一步。

---

## 衝突處理

- 若 Git 顯示同一檔衝突，不直接覆蓋，先保留雙方意圖再合併。
- 若產品方向衝突，以 Edward 最新明確決策為最高優先，再回寫 SSOT。
- 若文件與程式衝突，以目前已實作且已推上 main 的程式行為為事實基準，再補文件。
- 若涉及帳務、醫療安全、個資、App Store 上架風險，先收斂架構與風險，再進功能開發。

---

## 同步紀錄（2026-07-02 · Codex）

- 本輪範圍：本機 smoke / Supabase doctor 穩定化、`MUNEA_REQUIRE_AUTH=1` 權限契約測試補強、完整 API smoke 驗證。
- 避讓範圍：未改 `engine/live_voice_*`、`engine/voice_playback_probe.py`、即時語音 web 接線；不影響 Claude/城堡的 Gemini Live / 播放診斷主線。
- 驗證：`npm run smoke:no-api`、`npm run supabase:doctor`、本地 engine `127.0.0.1:8200` 完整 `scripts/smoke.ps1` 皆通過。

## 同步紀錄（2026-07-02 · Codex · P0-3 收尾）

- 本輪範圍：新增 `npm run smoke:auth`，用臨時 JSON store 啟動 `MUNEA_REQUIRE_AUTH=1` engine，驗證正式模式 HTTP auth gate。
- 已驗證：user-scoped endpoint 要 Bearer、admin endpoint 要 admin token、credit grant/entitlement mutation 不接受一般 Bearer、subscription event 接受 provider token。
- 避讓範圍：仍未改 `engine/live_voice_*`、`engine/voice_playback_probe.py`、即時語音 web 接線。

## 同步紀錄（2026-07-02 · Codex · P1-12）

- 本輪範圍：補 `memory_extract` deterministic 中文保底詞庫，讓偏好/家人/作息/情緒/健康脈絡的中文句子可產生結構化記憶候選。
- 已驗證：中文樣本「喜歡韓劇、女兒、每天散步、膝蓋痛、睡不著、孤單」會抓到 preference / relationship / routine / emotion / health_context。
- 避讓範圍：未改 `engine/live_voice_*`、`engine/voice_playback_probe.py`、即時語音 web 接線。

## 同步紀錄（2026-07-02 · Codex · P0-6）

- 本輪範圍：補 onboarding 境外 AI／語音服務知情同意、設定頁同意狀態、App 內隱私權政策頁與 smoke 契約。
- 已驗證：`npm run smoke:no-api` 通過；同意 UI、onboarding gate、隱私連結、前端 secret boundary 均納入檢查。
- 避讓範圍：未改 `engine/live_voice_*`、`engine/voice_playback_probe.py`、即時語音 web 接線。

## 同步紀錄（2026-07-02 · Codex · P1-13）

- 本輪範圍：補 backend / legacy chat engine fallback logging，避免 Supabase fallback、模型回覆、TTS、記憶萃取失敗時靜默。
- 已驗證：`npm run smoke:no-api` 通過；smoke 會用 AST 檢查 `engine/server.py` 與 `engine/chat_engine.py` 不再出現 silent `except ...: pass` handler。
- 避讓範圍：未改 `engine/live_voice_*`、`engine/voice_playback_probe.py`、即時語音 web 接線。
