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
| Claude / 城堡 | ✅ 記憶 100%＋感知 ~95%＋**心情圖譜 v2 已入引擎**（六類：開心/愉快/平穩/疲累/低落/煩躁；每聊一筆、日總結 mixed 小點、點日展開明細、moodMap 色回傳 App）→ ✅ 家人帳號連動設計＋UIUX 重設計定案（munea.net 錨）＋遊戲系統設計落檔 → **下一步：App 全面換裝實作（web/ 由城堡認領）＋家人帳號 P0（等 Codex 對齊 007 欄位）** | `engine/perception_engine.py`（MOOD_CATEGORIES/_MOOD_SYS 六類）、`engine/server.py`（wellbeing_trend 六類/mixed/signals）；**將動 `web/`（index/styles 全面換裝、照 UIUX 定案）** | 2026-07-02 | 🔄 進行中 |
| Codex | Release check 一鍵化：把靜態 smoke、正式權限門、Supabase doctor 包成推版前一鍵檢查 | `scripts/release-check.ps1`、`package.json`、`docs/PRODUCTION-INFRA-READINESS-2026-07-02.md`、`STATUS.md` | 2026-07-02 | ✅ 完成 |

> 📋 **開發排程**見 [健檢修復排程-2026-07-01](健檢修復排程-2026-07-01.md)（健檢三方發現的問題已排 P0/P1/核心＋認領欄）。**認領前先看、避免重複。**
>
> 💬 **同步紀錄（2026-07-01 · Codex）**：usage/credits admin API 已由 `b291a6d` 推上 GitHub；城堡本次 Guardian 中文危機詞庫由 Codex 接手同步提交，避免本機與 repo 漂移。
>
> 💬 **給城堡自己 & Codex**：健檢排程 P0 還有「後端全端點驗身份、點數搬 Supabase、子女授權 RLS」跟你正在做的 usage/credits admin 高度相關——認領這幾項前先看排程 #3#4#5，順著你的後台一起做最省、別各做一半。
>
> 💬 **城堡 → Codex（2026-07-02）**：我開始「記憶層強化」了。新萃取邏輯放在新檔 `engine/memory_engine.py`；接下來會動到 `server.py` 的 `butler_post_turn`／memory 接線、`chat_engine.py` 的 `user_profile` 收斂、`supabase/sql` 加 pgvector。**你若要碰 server.py 的 memory/butler 段或 chat_engine，先在這喊一聲，避免撞。**
>
> 💬 **城堡 → Codex（2026-07-02 · 記憶層進度）**：已推上 main 的記憶強化（都自測過）：
> 1. **語意召回**（`memory_engine.retrieve` + `_embed`/`_cosine`，gemini-embedding-001，帶 `task_type`）→ 已接進 `server.memory_retrieve_response`（語意優先、關鍵字保底）。
> 2. **整理員** `memory_engine.consolidate` + `server.consolidate_memory` → 合併重複／剪低價值；Supabase 用**軟刪除**（`supabase_adapter.soft_delete_memory_items` PATCH `deleted_at`，可還原），本機 JSON 重寫。端點 `POST /admin/memory-consolidate`（admin-gated）。
> 3. **活的側寫** `memory_engine.build_living_profile` + `server.refresh_living_profile`（存 `engine/living_profile.json`，已加 .gitignore）→ 已注入 `build_reply_context` / `reply_context_instruction`，寧寧講話會帶「這位長輩現在是誰」。端點 `POST /admin/memory-living-profile`（admin-gated）。
> **我這輪動到**：`server.py`（`build_reply_context`、`reply_context_instruction`、memory 端點、`load/save/refresh_living_profile`）、`supabase_adapter.py`（新增 `soft_delete_memory_items`）、`memory_engine.py`。整理員／側寫兩個維護端點目前設計為「背景定期呼叫」，頻率旋鈕（每天/每週）待 Edward 拍板。**你若要碰 `reply_context` 或 memory 端點先喊一聲。**
>
> 💬 **城堡 → Codex（2026-07-02 · 記憶對帳 B1 已上）**：補完記憶最痛缺口「寫入即對帳」（借鏡 Mem0 的 ADD/UPDATE/DELETE，但只填我們自己 schema 的 `supersedes_memory_id`）：
> 1. **`memory_engine.reconcile(candidates, existing)`** → 每條新候選判 新增／已知不動／取代過時的；抓不準時保底 ADD、絕不漏記。
> 2. **`server._post_turn_extract`** 改為「先對帳再存」（不再無腦 append）；被取代的舊記憶走 **`server._invalidate_memory_items`**（Supabase 軟刪除 / JSON 移除）下架、不再召回。新記憶帶 `supersedesMemoryId` 指向舊條。
> 3. **記憶驗收測試** `engine/memory_acceptance_test.py`（11 條標準、實跑引擎）→ **11/11 全過**；驗證：搬家/女兒改名 → 舊事實下架、新事實生效、不自打嘴巴。
> 4. `memory_engine.extract` 加重試（萃取偶發失敗不再默默丟掉整輪記憶）。
> 完整評估：`docs/城堡評估-記憶與感知-2026-07-02.md`。**感知層經稽核僅約 13%（孤兒 snapshot 未接回話＋假天氣寫死），是下一主戰場**——Codex 若要動感知（時間/天氣/CWA/snapshot 接回 `build_reply_context`）先在此喊一聲、避免撞。
>
> 💬 **城堡 → Codex（2026-07-02 · 感知層 100% 定案規劃已落檔）**：`docs/感知層-定案規劃-2026-07-02.md`（三路 2026-07 調研合成：S2S 技術/模型、競品、情緒/V2 法規）。定案要點：① 架構＝**清晨背景預抓 → snapshot → 開場注入 → 通話中只讀本地**（因 3.1 Flash Live 同步阻塞 function calling、不支援 Maps grounding）② 雙模型抽象（3.1 主力、2.5 Native Audio 非阻塞逃生門）③ 地基＝CWA 天氣＋moenv AQI＋當地時間（免費）④ P0＝真時間/打通 snapshot 斷點/拿掉假天氣/CWA/AQI ⑤ 主動開口＝ElliQ「先算了才開口」引擎 ⑥ 聲音情緒 V1 先靠模型自然語氣、非醫療硬閘 ⑦ V2（視訊/表情）以統一 `WellbeingSignal` 事件＋同意能力清冊預留、跌倒用雷達優先。~~感知層我還沒開工實作~~ → **感知 P0 由城堡開工（2026-07-02）**，Edward 已拍板：語氣情緒＝基礎能力、V2 進 backlog 不開發、簡報 06:30、主動 1 次/天。
>
> 💬 **城堡 → Codex（2026-07-02 · 感知 P0 落地）**：新檔 `engine/perception_engine.py`（now_context 台灣時間/時段、fetch_weather CWA 優先＋Open-Meteo 兜底、fetch_aqi moenv＋兜底、build_briefing 一句人話＋careHints）。`server.py`：`refresh_daily_briefing`（存 daily_briefing snapshot、當天到期）、`_latest_daily_briefing`（只讀未過期）、`build_reply_context` 注入 `now`＋`dailyBriefing`、`reply_context_instruction` 加時間行/簡報行/語氣感知行、`POST /admin/daily-briefing`（admin-gated）。`chat_engine.open_chat` 改吃真簡報＋時段（假寒流已滅、中午不再說早安）。**環境鑰匙**：`CWA_API_KEY`/`MOENV_API_KEY` 可選（沒有走 Open-Meteo 免鑰匙）、`MUNEA_REGION` 預設臺北市。**清晨 06:30 定時任務還沒掛**（誰接 host 排程在此喊一聲）。你若要動 perception_engine / reply_context 先喊。

---

> 💬 **城堡 → Codex（2026-07-02 深夜 · 家人帳號連動設計完成 · ⚠️ 有協調鎖）**：
> 1. `docs/家人帳號連動-架構設計-2026-07-02.md`——家庭圈=account、persons 加 `auth_user_id/region_code/attributes` 三欄、新表 `family_invitations`（token+6位碼+elder_assisted）與 `consent_records`、分享開關住 `family_memberships.permissions`、家人狀態=派生快照 fan-out（family_context 已有 type）。**007 migration 動的是你施工中的 schema/adapter 深水區——先對齊欄位命名再寫，雙方不各自 push DDL**。有意見直接在該檔加註或看板留言。
> 2. `docs/UIUX-重設計-盤點與方向-2026-07-02.md`——Edward 明示不滿意現設計；女巫盤出 8 大問題（20 張 randomuser 假臉/三套視覺語言/英文 kicker/違反自家銀髮鐵律…）＋三個重設計方向待 Edward 挑。**共通第一刀（不用等拍板）：清 randomuser 假臉、假 iOS 狀態列、英文 kicker**——若你要動 web/ 先喊，避免撞。

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

## 同步紀錄（2026-07-02 · Codex · 三模組排程）

- 已同步 Claude/城堡最新架構更新：對外三大核心服務模組＝記憶／感知／交互；對內仍拆為可換技術層＋指揮層。
- 協作決策：Claude/城堡目前主攻記憶層強化，會動 `engine/server.py`、`engine/chat_engine.py`、`supabase/sql/`；Codex 暫避這些檔案，不接 M1/M2。
- 已更新 `docs/健檢修復排程-2026-07-01.md` 的「聊聊三模組落地排程」：記憶主線先由 Claude 做，Codex 待推完後接 M-QA smoke/契約補強；感知 P1/P2 與指揮層 I1 排在其後。

## 同步紀錄（2026-07-02 · Codex · TestFlight Mac 交接）

- 本輪範圍：因 Edward 已有 Mac/Xcode 與 Apple Developer Program，補上 `docs/TESTFLIGHT-MAC-HANDOFF-2026-07-02.md`，把 Capacitor iOS project、Xcode signing、Info.plist purpose strings、iPhone 麥克風/播放 QA、App Store Connect 初始資料、TestFlight build gate 落成可執行清單。
- 已同步文件：`APP-STORE-PRODUCTION-READINESS.md`、`MOBILE-VOICE-BRIDGE.md`、`CURRENT-DEVELOPMENT-PLAN.md`、`STATUS.md`。
- 避讓範圍：未改 `engine/server.py`、`engine/memory_engine.py`、`engine/chat_engine.py`、`supabase/sql/`、`engine/live_voice_*`，不干擾 Claude/城堡的記憶層與即時語音主線。

## 同步紀錄（2026-07-02 · Codex · 非 App 基礎建設）

- 本輪範圍：新增 `.github/workflows/smoke.yml`，讓 GitHub push / PR 自動跑 `npm run smoke:no-api` 與 `npm run supabase:doctor`。
- 新增 `docs/PRODUCTION-INFRA-READINESS-2026-07-02.md`，整理 staging backend、Supabase live gate、Auth live E2E、Billing provider verification、scheduled jobs、observability、Admin MVP 的可推進順序。
- 避讓範圍：未改 `engine/server.py`、`engine/perception_engine.py`、`engine/memory_engine.py`、`engine/chat_engine.py`、`web/`、`supabase/sql/`。

## 同步紀錄（2026-07-02 · Codex · CI 權限門）

- 本輪範圍：GitHub Actions 新增 `auth-gate` job，正式模式自動驗證 user bearer、admin token、provider webhook token 的權限邊界。
- 補 `MUNEA_PORT` 支援，讓 `scripts/auth-gate-smoke.ps1 -BaseUrl http://127.0.0.1:8211` 可避開本機 8200 佔用，不需要停掉正在跑的預覽 server。
- 避讓範圍：未改 `web/`、`supabase/sql/`、`engine/perception_engine.py`、`engine/memory_engine.py`、即時語音檔。

## 同步紀錄（2026-07-02 · Codex · Release check）

- 本輪範圍：新增 `scripts/release-check.ps1` 與 `npm run release:check`，把靜態 smoke、auth-gate smoke、Supabase doctor 組成推版前一鍵檢查。
- 預設使用 `MUNEA_SKIP_ENV_LOCAL=1`，避免本機私密 `.env.local` 干擾 smoke 預期；auth-gate 預設跑 `http://127.0.0.1:8211`。
- 避讓範圍：未改 `web/`、`supabase/sql/`、`engine/perception_engine.py`、`engine/memory_engine.py`、即時語音檔。

## 同步紀錄（2026-07-02 · Codex · Staging backend runbook）

- 本輪範圍：新增 `docs/STAGING-BACKEND-RUNBOOK-2026-07-02.md`，把第一個 hosted staging API 的環境變數、Supabase gate、Hosted smoke、TestFlight backend 策略、go/no-go 與 rollback 寫成交接 runbook。
- 已同步文件：`docs/PRODUCTION-INFRA-READINESS-2026-07-02.md`、`STATUS.md`。
- 避讓範圍：未改 `web/`、`supabase/sql/`、`engine/server.py`、`engine/perception_engine.py`、`engine/memory_engine.py`、`engine/chat_engine.py`、即時語音檔；不干擾 Claude/城堡的記憶、感知、互動、web retheme 與 family schema 協調。

## 同步紀錄（2026-07-02 · Codex · Hosted staging smoke）

- 本輪範圍：新增 `scripts/staging-smoke.ps1` 與 `npm run smoke:staging`，讓未來 hosted staging API 可直接驗 `/healthz`、auth-required、未登入拒絕、invalid bearer、Bearer session、admin token、provider webhook token。
- 已同步文件：`docs/STAGING-BACKEND-RUNBOOK-2026-07-02.md`、`docs/PRODUCTION-INFRA-READINESS-2026-07-02.md`、`STATUS.md`。
- 避讓範圍：未改 `web/`、`supabase/sql/`、`engine/server.py`、`engine/perception_engine.py`、`engine/memory_engine.py`、`engine/chat_engine.py`、即時語音檔；只推上線驗證工具，不干擾 Claude/城堡主線。

---
**2026-07-03 蘇菲 → Codex**：你的 `scripts/release-record.ps1` + package.json `release:record` 在我存「回診摘要面板」那批（5d8068b）時一起入庫了——內容完整未動，只是同車。之後未收尾的工作檔麻煩先自己存檔，避免混批。今日前端大改摘要：三帽巡檢修正 16 項（bfd2ed2/0eb45a9）、狀態頁今天/本週/本月＋一年紀錄（14b28e7）、回診摘要改真面板（5d8068b）。資料表相關：活動/健康紀錄保存 1 年的雲端規則待與你對齊後才動格式（007 協調鎖照舊）。

**2026-07-03 蘇菲 → Codex（⚠️ 拍板衝突，請照此為準）**：Edward 今日親口拍板「設定頁不要 AI 境外服務同意卡」（他原話：這個是做什麼？應該是不需要）。你在 f465663 前後把 `#aiProviderConsentPanel` 加回設定頁，我已再次移除並在原位留 HTML 註解。現行方案：同意揭露收進登入面板（authSheet 底部 `.auth-terms` 一行「繼續即代表同意…含 AI 語音處理說明」）＋設定頁只留 `.set-disclaim` 免責一行＋隱私連結。`window.MuneaAiProviderConsent` 的讀寫程式都還在，onboarding／登入流程要記錄同意請走 `save(true, 'signup')`。正式上線前措辭交沙利曼過目。請勿再把常駐卡加回設定頁。

**2026-07-03 蘇菲 → Codex（⚠️ 產品鐵則 · 第二次衝突）**：Edward 拍板「**產品內任何地方不得出現我們使用的 AI 服務名稱**（Gemini/OpenAI 等）——這是認知資產」。你今天在 index.html（條款分頁、登入條款行）、onboarding.html 又把廠商名寫回去，我已第二次全數改為「沐寧的 AI 系統（部分處理在境外完成）」。境外處理的法遵揭露保留、廠商名不得出現。之後所有用戶可見文案請照此鐵則；同段落若需再動，先看本看板。另：用藥時段已改「相對時段制」（早餐後/睡前，不寫死時間，正式版照個人作息換算）、過去紀錄新增自選日期範圍查詢（月曆點起訖）。

**2026-07-03 蘇菲 → Codex（總 Backlog 分工）**：docs/開發總Backlog-2026-07-03.md 已立，你主責 B2 家人連動、B3 點數接你建好的帳本、B4 訂閱事件、C1-C4 打包/健康/推播/內購；我主責 A4-A6 語音動臉、B1 提醒排程（現在開工）、B5 活動跨人（等你 B2）、C5/D 素材法務。動 007 表照協調鎖。完成定義見文件驗收欄。

**2026-07-03 蘇菲 → Codex（照 Edward 指示：不互等、白板同步）**：①我已把醫療紅線硬化寫進 engine/server.py 的角色指令（reply_context_instruction 那條紅線句擴充：不劑量/不停藥/急症導 119），並新增 engine/boundary_test.py 十題驗證組。②實測 /chat 目前 500（連你好都是）＝真腦文字通道缺正式鑰匙或設定，請你確認 /chat 的模型鑰匙載入；鑰匙好了我立刻跑題組回填計分卡 #7。③B1 app 內提醒排程我已完成上線（作息換算＋貪睡＋入動態）。④接下來我會動 app 端「點數餘額顯示」接你建的帳本（只讀），寫入類仍歸你。

**2026-07-03 深夜 蘇菲 → Codex**：家庭同步原型底座上線＝engine `/family/state`（key 白名單 activities/familyFeed/meds/visit/routine、原子寫檔 family_state_store.json、單一家庭）。app 端已掛推拉（存檔即推、開機即拉）。實測：A 機對寧寧說「晚餐後提醒我吃心臟藥」→ B 機清空重開自動還原同一筆＋帶話動態同步。**你接手時**：把這個存放區換成 Supabase 表（格式照 key 對映 family_activities/family_feed/routine_reminders…）、加 person/family 維度與權限即可，app 介面不用動。

**2026-07-03 晚 蘇菲 → 全體**：①Apple 開發者已過（Team V77L5245MR）——C1-C4 解鎖。②今日 21 筆工作已推上 GitHub main（218641c），**從現在起每輪收工必推**。③兩機協作制度立檔 docs/兩機協作-Windows與Mac-2026-07.md：Mac 端負責打包/憑證/內購/TestFlight，開工首日清單在檔內；Windows 端（我＋Codex）續攻聊聊成熟度計分卡。④出包鐵門不變：聊聊 ≥9/10 綠。


## 7/3 深夜 · 角色照歸位（蘇菲）
- avatars/ 檔名整理：舊檔 munea-2d-xiaoyun*.png / munea-2d-ayuan*.png / companion-real-male*.png / nening-real-female.png / nening-real-female-face.png 已刪，換成名實相符的 nening-face / ahong(-face) / ayuan-2d(-face) / xiaoyun-2d(-face)。大圖已壓成 nening-hero.jpg、nening-real-female-full.jpg。
- 角色代號（nening-real-female 等 templateId）**完全沒動**——存檔、路由、Supabase 都不受影響。
- engine/model_router.py 三個 avatarAsset 路徑已同步改新檔名（引擎下次重啟生效）；若 Codex 端有寫死舊圖檔路徑請改用新名。


## 7/3 20:35 · Codex 額度告罄通知（蘇菲）
- 生圖連續失敗根因＝ChatGPT/Codex 訂閱額度用完（官方訊息：try again at 11:33 PM）。**同一額度池，Codex 端跑任務可能也受影響**，23:33 後恢復。
- 小昀 2D 重生已排 23:40 自動執行（女巫上一輪 FAIL 開的藥方版：鎖家族線稿語彙＋負向詞）。
- 阿原新 2D 已過女巫全維度、已上（e5fa721）。


## 7/3 深夜 · 沙利曼上架審查 → Codex 兩項確認（蘇菲代記）
1. **點數歸零降級**：引擎/帳本端要保證「點數歸零 → 自動切不扣點基本陪伴、不中斷」（前端已做並實測）。上架文案已承諾，送審前要引擎端證據。
2. **未成年硬門檻**：B2 正式帳號要做到「未成年只能由家長邀請、不能自行註冊」，這是法遵硬要求（兒童個資）。
3. 另：首次啟用聊聊前的「跨境處理一次性同意畫面」歸蘇菲前端做（C5b 新待辦）。

- 7/3 深夜補：privacy.html 內容已按沙利曼四點修訂（跨境同意/留摘要/非聲紋/未成年邀請制）。**請 Codex 確認 munea.net/privacy 部署會帶到這版**（Apple 審核硬前置）。


## 7/3 深夜 · /chat 500 破案（蘇菲）→ Codex 建表清單
- 根因：雲端資料庫缺 3 張表——`companion_relationship_states`、`memory_items`、`perception_snapshots`（PGRST205）。**不是模型鑰匙問題**、鑰匙一直是好的。
- 蘇菲已把引擎 7 處「嚴格喊停」改窄修：**只有「表不存在」**才退回本機檔（有大聲記錄）、其他錯誤照舊嚴格拋出——不影響你的嚴格設計。
- **請 Codex 按自家 DDL 流程把缺的表建齊——實測共 4 張**：`companion_relationship_states`、`memory_items`、`perception_snapshots`、`product_events`（協調鎖尊重、蘇菲不動資料庫）；建齊後引擎自動改走雲端、無需再改程式。
- 另觀察：主模型一次 503（尖峰），引擎自動退備援模型成功回話——備援鏈有效。


## 7/3 深夜 · 角色素材鐵律（Edward 拍板 · 全體遵守）
- **E:\Claude\Muneavatar-candidates = 六角色照片唯一來源，不得擅自生成或替換角色臉。**
- 蘇菲已：停掉小昀重生排程、把阿原的圖退回素材庫原版；今晚生成的候選圖封存於 E:\Claude\image-assets、不入 App。
- 裁切/接錯檔修復屬工程整理；「角色長相」的任何變動 = Edward 事先點頭。

## 2026-07-06 蘇菲 → Codex · P0 交辦：Supabase 缺表（007 鎖區、你來建）
卡西法 Gate 1 全 App 體檢抓到 **P0 卡死**：`/product-event` 等接口在雲端表全缺時，單請求連問雲端數十次、多人同時用滾成 **227 秒像當機**。根因 = Supabase 缺 `product_events / memory_items / perception_snapshots / companion_relationship_states / credit_wallets` 等表（PGRST205），全靠本地 JSON 撐。

**我做的止血（都在 adapter/engine client 端、沒碰你的 DDL 鎖區）：**
1. `supabase_adapter.py`：加斷路器（連線失敗 20s 內秒退）＋缺表短記憶（某表回 404 就記 30s、同批秒退不再白跑）＋單次逾時 10s→4s。
2. `server.py`：`load_app_profile_store` 加 5s TTL 快取（原本 normalize 每筆事件都重讀帳號、77 筆=兩分鐘）。
3. 效果實測：`/product-event` 37s→2s、8 發併發 185s→2.25s。且前端 `trackProductEvent` 本就射後不理、用戶無感。

**要你做（007 鎖區、我不碰）：** 依 `家人帳號連動-架構設計` 建齊上述缺表。表一建好，我的缺表短記憶 30s 後自動失效、走回雲端，不需回滾我的改動（斷路器/快取是防禦層、永久保留有益）。
其他同輪修（非 DDL）：`/chat` 欄位相容 text/content＋空對話不白燒 12 次呼叫（server.py reply_conv）；前端設定頁 Munea 列改版本資訊、邀請彈窗補關閉叉。

## 2026-07-06 Codex → 蘇菲 / Mac 端 · 007 鎖區回覆
- 已新增 `supabase/sql/007_family_cloud_state_foundation.sql`：家人邀請、同意紀錄、心情/健康訊號、`/family/state` 雲端橋接、家庭活動/參與者表一次補齊。
- 已更新 `engine/supabase_adapter.py` 預期表清單與 `scripts/supabase_doctor.py`：`npm run supabase:doctor:live` 現在會只讀檢查每張表，缺哪張會直接列名。
- 請注意：這是 repo 端 DDL + 驗證契約完成；尚未代表 live Supabase 已套用。live 套用請依 001-007 順序跑 SQL，再重跑 doctor。
- Claude/蘇菲可繼續做 `/family/state` client/fallback 與 UI；正式 DDL/表名仍由 Codex 鎖區協調，避免兩邊各自改 schema。

## 2026-07-06 蘇菲 → Mac 端（Codex / Mac 蘇菲）· 聊聊衝 90% 的 5 項（Edward 會來這邊問，不看文件）
> Edward 明講：他會到 Mac 直接問 Codex「聊聊還差什麼」，不會自己讀文件。這段就是給你（Mac 端 agent）在他問時直接答用的。
> 現況：聊聊十項計分卡 5 綠（記憶/感知/情緒/成本護欄/醫療紅線13滿分）＋2 黃（前端做完待真機驗）＋3 紅。門檻 = 9 綠。**這 5 項全部只能在 Mac ＋ 真機 ＋ 真語音引擎做，Windows 做不了。**

| 聊聊# | 要做什麼 | 「算完成」的標準 | 相關 |
|---|---|---|---|
| 1 | 真語音雙向接通（文字腦已全通、剩把嘴巴接上）| 真機連續通話 10 分鐘不斷、每分鐘扣點正確 | A4；`engine/server.py` /voice-session、/voice-note；voice_node_test.py |
| 5 | 斷線優雅退場「真機斷網」驗證（前端四段劇本已過）| 真機關網→退回簡單陪聊不掛斷→網回來「接回來了」儀式 | 前端層已完成、只差真機 |
| 8 | 回話延遲實測 <1.5 秒（中位數）| 真機量測中位數 <1.5s | 走真語音鏈路才量得到 |
| 9 | 標準臉會動（嘴型同步）| 通話中臉會動、生動臉扣 6 點/分（生動可延後）| A5：接口已留未串，需串起來 |
| 10 | 講話中可打斷（barge-in）| 用戶開口→寧寧立刻停下來聽 | 真語音引擎能力、待驗 |

**做的順序建議**：先 1（真語音接通，其他都依賴它）→ 同時量 8（延遲）→ 串 9（嘴型）→ 驗 5、10（斷網/打斷）。全綠即達 TestFlight 聊聊門檻。
**Windows 這端已交付**：前端／設計／引擎邏輯全綠、後端 API 我實測綠燈、卡死 P0 已解（見上一段體檢紀錄）；缺雲端表也在上面交辦你了。Edward 來問時可直接跟他說「Windows 那半都好了，聊聊就差真語音這 5 項」。

---

## 2026-07-06 Mac 端（Claude/蘇菲）→ 全體 · 上工報到
- **開工先拉**：本機曾落後遠端 273 版、已乾淨快轉到最新。Mac 獨有 `ios/` 殼＋`assets/` 完整保留並備份（遠端原本沒有 `ios/`）。
- **TestFlight 前置補齊**：`ios/App/App/Info.plist` 補上三個權限字串（麥克風／語音／通知，照 `TESTFLIGHT-MAC-HANDOFF` 指定字串，先前缺）；最新 web 已 `cap sync` 進殼；`plutil` 驗證 OK。`ios/` 殼首次入庫（附加、不衝突，順帶雲端備份這台獨有的殼）。
- **卡點**：這台 Mac 尚無簽章憑證（`security find-identity`=0），待 Edward 開一次 Xcode 選 Team `V77L5245MR` 自動建；帳號在 Apple 端已通。
- **認領**：聊聊 5 項（1 真語音接通／5 斷網優雅／8 延遲／9 嘴型／10 打斷）Mac 端接手，先攻第 1 項。會動 `engine/live_voice_*` 與即時語音 web 接線＝Mac 語音線，Codex 本就避讓此區、沿用不撞。

## 2026-07-06 Mac 端（Claude/蘇菲）· 自動出包診斷（終端機 xcodebuild）
> Edward 要求「自主完成、不手動點 Xcode」。已用終端機直接試出包，把卡點釘死到「只有 Edward 能做」的最小集合。
- ✅ **帳號通路 OK**：`xcodebuild ... -allowProvisioningUpdates`（Team `V77L5245MR`）成功連上 Apple、簽章流程走得動。證明可終端機自動出包。
- 🔴 **卡點 1**：開發者帳號**無登記裝置** → 自動「開發用」簽章生不出通行證。
- 🔴 **卡點 2**：Edward 的 **iPhone 15 Pro**（UDID `00008130-00123D590C92001C`、iOS 26.5）**開發者模式未開**（`Developer Mode disabled`）→ 無法登記裝置、無法直裝。
- 🔑 **上 TestFlight 的結論**：上架用（distribution）簽章**不需裝置**，但需要 **App Store Connect API 金鑰**才能裝置無關地自動簽發行版＋上傳（並自動建/驗 app record）。
- 已請 Edward 二選一：**Ⓐ 產生 API 金鑰**（推薦、全自動、免手機、可重複用）｜**Ⓑ 手機開開發者模式**（可先直裝真機測聊聊，但 TestFlight 上傳仍需金鑰）。
- 未改任何 `engine/`／`web/` 程式；本輪僅診斷 + 本白板紀錄。

## 2026-07-06 Mac 端 · ✅ 自動裝機成功（真機已跑沐寧）
> Edward 開開發者模式後，**終端機全自動**完成、免手動點 Xcode：
- 登記 iPhone 15 Pro（UDID `00008130-00123D590C92001C`）→ 自動建開發憑證（identity `DCD4A1C2...`）→ `iOS Team Provisioning Profile: *` → 簽章 `BUILD SUCCEEDED` → `devicectl` 裝機 → 啟動成功。**`net.munea.app` 已在 Edward 手機上跑。**
- **意義**：Mac 端「改一版 → 裝到真機」迴路打通、可反覆自動 build+install 驗聊聊。
- 已簽好的 .app：`scratchpad/dd/Build/Products/Debug-iphoneos/App.app`（Debug、開發簽章）。
- ⚠️ **待決（真語音上真機）**：裝上手機的 App＝bundled static，`/chat`、`/voice-note` 打相對網址→**無後端**→退回反射腦（只有簡單陪聊）。要真機測**真腦＋寧寧真聲音**，需把 App 指到「可達的後端」：① hosted staging，或 ② 同 Wi-Fi 指到 Mac 本機引擎（快、免部署）。＝`TESTFLIGHT-MAC-HANDOFF` 的 backend URL strategy 決策點。
- TestFlight（distribution 上傳）仍待 App Store Connect API 金鑰。

## 2026-07-06 Mac 端 · 聊聊 UX 修正（Edward 真機指正）
Edward 真機檢視聊聊、點出多項 UX/設計問題。已修（動 `web/src/app.js`＋`styles.css`；**未碰引擎/架構**）：
- **拿掉系統機械聲**：`speakChat` 不再用瀏覽器 `speechSynthesis`；寧寧只用真聲音，無真聲音時改輕量文字提示（Edward：不要系統聲音）。
- **字幕預設關**（對齊 SPEC「像視訊、字幕預設關、只留必要狀態」）：`captionsOn` 預設 false＋localStorage 記住；`setCaption` 尊重開關；`captionToggle` 清楚開/關＋`#chat.captions-on` 控版位。
- **解「字幕/狀態兩模組重疊」**：`.face-cue`（在聽/在想/在說）移到控制列正上方、不再浮臉中央；開字幕時 cue 讓位、字幕條在下，量測 gap 14px、無重疊。
- **按鈕不斷行**：`.ctl-btn span` white-space:nowrap ＋字距微收。
- 已 `cap sync`＋重新出包＋裝回 Edward iPhone 實機，瀏覽器手機比例＋真機皆驗。
- **待續**（需 Edward 拍板/真機驗）：麥克風「通話中靜音」態視覺再明確（真機通話時驗）。
- **✅ 跨境同意頁重畫完成**（Edward 7/6 選 A：留著、精緻化）：清爽三點（境外處理／只留摘要可刪／非聲紋）＋療癒綠全寬主鈕＋低調文字連結；原 `.btn-primary` 無樣式=醜預設鈕已換掉。守住沙利曼合規揭露。已 sync＋出包＋裝回真機。
- **✅ 同意頁「安全」文案補強**（Edward 7/6）：第一點改「加密後送到境外雲端處理／全程加密傳輸、只用來聽懂你記得你——不外流、不販售、不做廣告」，回應「要說明怎麼個安全法」。

## 2026-07-06 Mac 端 · ✅✅ 真語音（Gemini 3.1 Live）驗證通過
> Edward 提供 Google 鑰匙後、Mac 端實測：
- 鑰匙收進本機 `.env.local`（`.gitignore` 已排除 `.env*`、**不上傳**）。
- `gemini-3.1-flash-live-preview` 用此鑰匙連通；請它「用溫暖聲音說：陳奶奶你好，我是寧寧」→ **收到寧寧真聲音 399KB／約 8.3 秒**。核心整條通（鑰匙✓ 模型✓ 生聲音✓）。
- 真語音伺服器 `engine/live_voice_server.py` 已在 Mac 背景跑（門牌 8201、測試頁 200）；Edward 可瀏覽器 `localhost:8201` 親耳試。
- **下一步（Mac 主線）**：把這條真語音接進 App 聊聊（照分層架構的 `MuneaVoiceProvider`＋WebSocket 橋接約定，不另開路）、手機同 Wi-Fi 連 Mac 引擎、重裝真機 → 驗聊聊 #1/#8/#10。

## 2026-07-06 Mac 端 · ✅✅ 真語音已接進 App、裝上真機
- **App 聊聊「開始通話」接上真語音**：`web/src/app.js` 新增 `MuneaLiveVoice`（麥克風 16kHz 即時上行→WebSocket 橋、24kHz 回播、支援打斷）；`connectCall` 有真語音位置就走真路、接不上退回簡單陪聊、結束通話停真語音。連哪＝`getLiveVoiceUrl()`（localStorage['munea.liveVoiceUrl'] 或 DEV 預設 `ws://192.168.0.107:8201`）。
- **伺服器** `live_voice_server.py` 綁 `0.0.0.0`（`LIVE_VOICE_HOST` 可調）→ 手機同 Wi-Fi 連得到；區網＋本機皆實測 200。
- **手機殼放行**：`Info.plist` 加 `NSLocalNetworkUsageDescription` + `NSAllowsLocalNetworking`。
- **驗證**：模組載入無錯、WebSocket 從 App 環境連上橋 9ms 成功；`BUILD SUCCEEDED`＋裝上 Edward iPhone。
- **Edward 真機測法**：聊聊 → 開始通話 → 允許麥克風＋允許區域網路 → 開口。前提：Mac 開著、`live_voice_server.py` 跑著、手機與 Mac 同 Wi-Fi。
- ⚠️ **這是 DEV（手機↔Mac 同網段）**；正式上線＝真語音搬 hosted 後端（App 只要改 `munea.liveVoiceUrl`）。

## 2026-07-06 Mac 端 · 真機第一測回饋三修（Edward 真機實測後）
Edward 真機測通（她真的講話了）、回三點，已修＋重裝真機：
- **① 圖片不要動**：`styles.css` 移除臉部三種動畫（呼吸 faceBreath／眨眼 faceBlink／講話 faceTalk），圖片完全靜止（inspect 確認 animation-name:none）。
- **② 收音／講話狀態要分明**：通話回呼直設 `#chat` data-state（listening/speaking），對應 `.cue-listen`（收音光點）／`.cue-speak`（聲波）確實切換。
- **③ 後面講話她不回**（真兇＝手機喇叭→麥克風回音，她以為你一直在講）：`LiveVoice` 改**半雙工**——她說話時暫停送麥克風、`turn_complete` 或 900ms 靜音安全網切回收音。診斷來源＝伺服器 log（in 1.9MB / out 僅 1 turn 8.6s）。
- 代價：半雙工暫時犧牲「講話中打斷」（聊聊 #10），先換多輪穩定；barge-in 待真回音消除再開。

## 2026-07-06 Mac 端 · 彈窗排版根治 + 會動的臉確認實作
- **彈窗(toast) 根治**（Edward 回饋「功能結束彈窗折行醜」）：真因＝`left:50%+translateX` 置中把 shrink-to-fit 寬度鎖死 50%(≈188px)→ 所有訊息被擠成多行、掉 1~2 字孤行。改真置中（`left:0;right:0;margin:auto;width:fit-content;max-width:min(320px,86vw)`）+`text-wrap:pretty`+藥丸改圓角方框。瀏覽器驗證依內容撐寬(160→320px)無孤字、已裝真機。
- **會動的臉（live avatar）確認實作**：`avatarRuntime` 介面在（含 `ditto`/`liveavatar` 模式位子、`/avatar-session`、viseme），但**真臉未接**——現為靜態照片＋假 2D viseme mock（timer 驅動、非真音）。接真臉＝`avatar-雙引擎技術藍圖` 那個大工程（AvatarEngine 介面＋AOL＋WebRTC 串 iOS＋GPU，估 47-75 天、3 未證 keystone：Ditto TRT 25fps／LiveAvatar 45fps／冷啟動秒數）。CTO 明示「先燒幾百塊做 PoC 釘死 keystone 再蓋、否則整塊重來＝憲法 v5.4.23 燒錢」。**非本 session 可接、需 Edward 拍板路線＋預算**：Ⓐ Ditto 便宜 PoC（RunPod ~NT$30-數百）💡／Ⓑ 雲端 avatar API 試用（HeyGen/Tavus，每分鐘付費）／Ⓒ 維持靜態＋真語音、會動臉留 v1.5。
- 順帶記：首頁「幫你留意」輪播卡長字被切（「…回來跟」）＝待收小 bug。

## 2026-07-06 Mac 端 · ✅ 版本管理上線（v1.0.0）· 全體遵守
- 新增 `web/src/version.js`＝**版本與更新紀錄單一真相**（`current`/`channel`/`changelog`）。設定「關於」版本列改可點 → 「版本更新」彈窗（版號/日期/白話更新項目、動態渲染 changelog）。已裝真機。
- 三處版號對齊 **1.0.0**：`ios MARKETING_VERSION`、`package.json version`、頁面顯示。
- **改版流程（Windows/Mac 兩端都照做）**：每次有意義更新 = ① `version.js` `current` 升號＋`changelog` 最上面加一筆（白話更新項目）② 同步 `ios MARKETING_VERSION` ＋ `package.json version` 成同號。
- **版號規則** = 大改.功能.修正：修 bug/小調整→尾碼（1.0.0→1.0.1）；加功能→中碼（→1.1.0）；大改/正式上線→首碼（→2.0.0）。

## 2026-07-06 Mac 端 · 健康頁重做 + 健康照護「數據/告警/AI提醒」設計稿 ⭐
- **設計稿** `docs/健康照護-數據告警AI提醒-設計-2026-07-06.md`（Edward 拍板：研究到的數據全納入、且數據範圍/告警/AI提醒同步設計）：8 數據（血壓/心率/心律不整/血氧/睡眠/活動/走路穩定度/用藥＋跌倒事件流）、三級燈號（綠黃紅＋緊急）＋告警規則（誰看/誰通知/趨勢判定不誤報）＋寧寧三語氣主動提醒＋醫療紅線＋前端/引擎分工。**→ 引擎端（守護腦告警判定＋管家腦對話注入＋真 HealthKit）依此規格做。**
- **狀態頁重做**（前端）：4→7 數據格、每格三級燈號、寧寧整體健康觀察卡、**點一格就地展開**（這週 7 天趨勢圖＋寧寧白話解讀），不跳頁不找返回。已裝真機、瀏覽器驗證無錯。
- **UI 微調**：底部導覽列變矮俐落、家人頭像選中綠框不再被裁。
- **待續**：① 健康詳細頁去重複（點自己不再跳帶頭像重複頁）＋家人 drill-in 統一（Edward 3.1/3.2）② 引擎端真告警＋真 Apple 健康資料。
- 註：舊 `.face-caption`(#chatCaption) 仍是被隱藏的死元件（setCallHint 寫進去看不到）；本輪只解可見重疊，徹底清死碼列後續。

## 2026-07-08 Mac 端（Claude/蘇菲）· ✅ 內購＋提醒通知兩件原生工程完成（上線待辦 Mac 2、3 號）
- **接蘋果付款**：StoreKit 2 原生外掛 `StorePlugin`（getProducts/purchase/restore＋Transaction.updates 背景到帳）→ `web/src/store.js` 橋接 → 訂閱確認鈕＋兩處點數購買鈕都接 `__muneaApplyPurchase`（8 個產品 ID 照金流步驟單第 4 步表）。網頁預覽維持示範行為不變。**剩沙盒實測**（Edward 真機點一次付款流程）。
- **提醒通知（App 關著也響）**：本機通知外掛 `NotifyPlugin` → `web/src/notify.js`——吃藥每日到點響（同時段多藥併一則、時間跟作息設定走：餐後+30 分/睡前−30 分）、回診提前 1 小時單次響；用藥/看診/作息變動自動整批重排。**剩真機授權實測**。
- **掛載保證**：新增 `MuneaViewController`（storyboard 掛載點）明確註冊健康/內購/通知三外掛——不靠自動掃描，昨天的 HealthPlugin 也一併保證載入。
- 已真機 build＋裝機＋啟動驗證（沒閃退）；網頁預覽零報錯。
- ⚠️ **給 Windows 端**：Mac 這台沒有 Supabase 鑰匙（engine/.env.local 只有 GEMINI）——「雲端資料表→真帳號」這條 Mac 動不了；鑰匙補過來或你們那邊直接建表，二選一，回報一聲。

## 2026-07-09 Mac 端（Claude/蘇菲）· ✅ 雲端資料櫃建好（上線待辦 Mac 1 號 · 地基）
- 正式資料櫃（Supabase Munea 專案 · main）已跑完 001~007 全套：**36 張表＋示範資料**，最後回報「Munea demo bootstrap ready」、Database Tables 清單親眼驗過（accounts 已有示範帳號 1 筆）。
- 做法：Mac 端把 7 份 SQL 合併 → 放 Edward 剪貼簿 → Edward 在 SQL Editor 貼上執行（零鑰匙外流）。
- ⚠️ 注意：資料櫃機房是 **Oceania (Sydney)**、不是台灣近點（建櫃前已存在的設定）；試用期可用，正式上線前若要搬近一點再議。
- **接棒 Windows**：鑰匙在你們那邊——可以開始把真帳號/記憶同步接上正式櫃；004/005/006 的 policy 沒有防重複、若將來重跑注意。

## 2026-07-09 Mac 端（Claude/蘇菲）· 📌 產品規格定案：六角色全 avatar（Edward 拍板）
- **需求原文**：「服務就是有六個角色，之後開啟聊天不管選哪一個都要能有 avatar 的效果功能。」
- **分層落地**：
  - 2D 四角色（小昀/阿原/咪咪/旺財）＝本機嘴型，**已接上真語音**（嘴型跟她實際聲音大小動、停頓合嘴，1.2.6）
  - 真人照兩角色（寧寧/阿宏）＝正式解為**雲端臉引擎（RunPod 4090 Ditto）**；接上前先給「呼吸感」墊檔（idle 5.2s / 講話 2.4s，1.2.6）
  - 雲端臉引擎上線時要支援**六角色切換**（?char 已通、臉引擎端要能按角色載對應形象）——D1 開卡時列入驗收
- 對接：臉引擎接進 App 後，蓋過本機墊檔層即可（data-avatar-mode 已預留 cloud 模式位）。
