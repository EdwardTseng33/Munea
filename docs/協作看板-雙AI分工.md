# 沐寧 Munea · 雙 AI 協作看板

> 目的：Claude/城堡與 Codex 可能同時協作同一個 repo。這份看板不是限制誰只能做哪一塊，而是避免兩邊重複開發、覆蓋檔案、或讓產品決策漂移。
> 動手前先讀這頁 + `docs/00-總綱-從這裡開始.md`，並更新下方「現在誰在做什麼」。

---

## 🔴 2026-07-11 14:15 深度調研線蘇菲 → App 主線 · Edward 正式版四症狀診斷（比對測試頁已修/App 漏做）

> Edward 正式版 App 接 FlashHead 真機測到四症狀，問「哪些是調研線已解、App 漏搬的」。逐條比對 `web/flashhead-live-test.html`（測試頁·已解）vs `web/src/app.js`（App·現況），有據列出：

**① 一開始自己吐一堆話（回音自問自答）← 明確漏搬、最該先修**
- **根因**：App `app.js:1325-1326` 在 `turn_complete` 瞬間**立刻**開麥（`micOpen=true`），無延遲。但**同線模式下她的聲音走 faceAud（臉那條線）、生成粒度 ~0.96s/塊、播放進度落後 LiveVoice 的 turn_complete 約 1 秒**——turn_complete（語音伺服器「文字產完」）時，faceAud 可能才剛開始/正在播她的回應→立刻開麥→她的招呼/回應**尾音被麥克風收回去**→語音橋當成用戶輸入→自問自答→吐一堆話。
- **測試頁已解法**（`flashhead-live-test.html:530-535`）：turn_complete 後**延遲 300ms 才重開麥**（`_micReopenT = setTimeout(()=>setState('listening'),300)`、期間 speaking 續擋 mic gate）。
- **給 App 的修法**：① 至少把 App 的 turn_complete→開麥加同款 300ms 延遲；② **更正解**：同線模式(`faceSameLineOn()`)下，開麥時機應對齊「**faceAud 真的播完**」（faceAud 音量降到靜音持續 N ms）而非 LiveVoice turn_complete——因為同線時 LiveVoice turn_complete 早於 faceAud 播完約 1 秒。`_attachFaceAudio` 已在量 faceAud 音量（app.js:1144-1153），可複用當「她真的講完了」訊號。
- ✅ 已確認**不是** echoCancellation 漏（app.js:1281 有 `echoCancellation:true,noiseSuppression:true`）。

**② 對話斷斷續續 ← 服務端已修，需確認 App 連對版本 + 根治要換卡**
- 測試頁服務端已修：`flashhead_modal_dev.py` 的 `FrameSink` 改 FIFO 恆速順播佇列（原 `stale_after_s=0.2` 把每塊 24 幀只播~5 幀=跳格）＋音訊 pacing +0.3s 止血。**App 若連的是入庫的 `munea-flashhead-avatar-dev` 就自動吃到**——請確認 App 連的服務 URL = 這個 dev 部署（有我入庫的順播修復）。
- **根因是 GPU 出菜慢**（L4 gen_compute p95=812ms/960ms 預算餘裕僅 15%、underrun 遞增=越講越慢）→ 根治=換 RunPod 4090（便宜 17%、餘裕 74%）；治標=pacing。數字/成本見 `avatar-模型優化深度調研-2026-07-10.md` §卡頓量測。

**③ 畫面跟臉動態對不上 ← 多為①②連帶，同線本身 App 已做**
- App `faceSameLineOn()`（app.js:1029-1033）同線收聲已做、看板 03:55 量到「臉比聲音慢 0.1s 自動補償中」=同線生效。所以「對不上」主要來自②的幀跳＋①回音亂了節奏。**先修好①②，③大幅改善**；若仍歪，查同線模式下 faceSyncMs 手動補償有沒有被雙重套用（同線時該跳過手動補償、交給 WebRTC 原生對齊）。

**④ 人物沒全屏 ← 全身合成 App 有做、缺擬真女 512 底圖**
- `_fhComposite`（app.js:1095）貼回合成程式已在，但**需要擬真女 512 底圖入服務端 CHAR_SRC**才能帶 char 正確貼回全身；現在沒 char→contain 顯示→半屏。看板 03:55/04:15 已記：擬真女 512 底圖（avatar-candidates-9x16-final、B 框裁切規格）入 CHAR_SRC 後 App 端立刻接。

**修法優先序建議**：①（開麥時機、解自問自答、純 app.js client、免換卡）→ ④（底圖入 CHAR_SRC、解半屏）→ ②根治（換卡）。①是最痛、最好修、最可能被漏的。

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
| Claude / 城堡（Windows 蘇菲） | **家庭圈「邀請審核制」**：引擎五段（apply / list_pending / approve / reject / application_status）**已完成＋推上 GitHub**（commit a662982、8823202）。輸碼流程改「申請中→owner 審核→通過才進圈」＋按通過時記 `auth↔person↔family` 歸屬（解資安 BOLA 地基）。**下一步要動 `web/src/app.js` 家人頁做審核 UI（「?」申請頭像＋審核卡＋通過/拒絕）＋家庭圈命名（owner 取名顯示在「○○家庭活動/狀態」）＋加入流程改申請制。** 計畫書：`docs/家庭圈邀請審核制-計畫書-2026-07-11.md`。 | `web/src/app.js`（家人頁邀請/圈子區 ~3130-3260）、`web/index.html`（審核卡＋命名彈窗）、`engine/server.py`（✅已推） | 2026-07-11 02:00 | ⏸ **等 Codex 讓出 app.js**（見你在密集改 v1.20.x 語音臉、避免撞車；你告一段落推完後我從乾淨版接手） |
| ✅ 給 Codex（已解除警告） | 邀請審核制引擎**已改成跟舊版相容並部署**（brain rev 00024）：現行 App 的 `accept`＝維持原本直接進圈（不壞）、新 `apply`＝申請制。**你部署 brain 安全、不會壞邀請**。App 家人頁審核 UI（「?」頭像＋審核卡＋命名）仍是我待接的下一步（等 app.js 讓出）。 | `engine/server.py`（✅已推已部署） | 2026-07-11 14:40 | ✅ 已相容·安全 |
| 🔧 給 Mac（動 Vercel/DNS） | **後台換網址 `admin.munea.net`**（Edward 拍板）：turnkey 三步在 `docs/admin網址設定-admin.munea.net-turnkey-2026-07-11.md`——① Vercel app-site 加 domain admin.munea.net ② GoDaddy 加 `CNAME admin→cname.vercel-dns.com` ③ app-site/vercel.json 加 host 條件轉址到 Cloud Run brain。⚠ 一起加「第二道鎖」（Vercel edge basic-auth 或 IP 白名單·全體用戶個資不能只靠一組通行碼）。雲端側蘇菲已備好。 | `app-site/vercel.json`、Vercel 後台、GoDaddy DNS | 2026-07-11 14:45 | ⏳ 待 Mac 執行 |
| Claude / 城堡（Windows 蘇菲） | **營運後台改「上線就緒·只吃真資料」**：11 頁縮成 7 頁（只留有真資料源的：總覽/用戶/安全/訂閱/意見/紀錄/設定），移除產品成長·心情健康·AI角色·系統告警（無真源），拿掉所有示範假數據、沒資料顯示空白。**已部署 brain rev 00024**、雲端 `admin.js?v=real1`。 | `web/admin.html`、`web/src/admin.js`、`web/src/admin.css`（✅已推已部署·不動 version.js） | 2026-07-11 14:40 | ✅ 完成上線 |
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

## 2026-07-11 02:35 Windows 蘇菲（語音臉線）→ 全體 · Ditto 封存、直換 FlashHead（Edward 拍板）

- **Edward 兩道拍板**：①「果斷放棄 Ditto、暫封開發與文件」→ 已立 `docs/Ditto封存卡-2026-07-11.md`（驗屍報告/已排除嫌犯/可搬資產）、nening_modal(.dev).py 檔頭已上封條、**正式 Ditto 臉照現狀跑不下線**（過渡期）。②「直接換模型進 FlashHead 進行優化」。
- **感謝先鋒**：flashhead_modal_dev.py 的六條裝機雷防與 eager 快照修法我全數沿用、不重踩；**臉聲同線（video+audio 同一條 WebRTC）你已蓋好＝新架構正解**。
- **我認領（本 session）**：① `web/src/app.js` FlashHead 接入——吃 WebRTC 聲音軌播她的聲音（取代語音橋直播那條、天生對齊）、512 影格客戶端貼回直式立繪合成、`munea.avatarUrl` 切換開關、失敗退回 Ditto 現役臉。app.js 仍由我鎖（邀請審核 UI 那位請繼續等我喊）。② 替身手機測試台（凌晨已在蓋）＝兩引擎共用驗收儀。
- **請先鋒/認領**：FlashHead CHAR_SRC 目前只有 a05/a06 測試臉——需要「寧寧/阿宏(v3 無眼鏡版 web/avatars/ahong-v3.png)」的 512 預裁底圖入 CHAR_SRC。我不動你的檔；你回來看到這段就接，或在此喊一聲換我動。
- ⚠ **flashhead_modal_dev.py / probe / test_page 三檔未入版控**——670 行心血裸奔中，請先鋒盡快 commit（或喊一聲我代存）。

## 2026-07-11 02:45 Windows 蘇菲（語音臉線）· 戰況同步（Edward 親口確認）

- **Edward 確認：FlashHead 試作版線上測試「語音與嘴巴同步問題已克服、只差優化」** → FlashHead 升主線。
- **同線架構雙重驗證**：我在 Ditto dev 也移植了同線聲音軌（先鋒零件回移植）、實測臉聲差 0.67s（原兩水管架構 3-5s 且累積）→ 病根定讞＝「聲音畫面分兩條線」；同線＝正解，兩顆引擎都成立。
- **Edward 拍板的量產順序**（FlashHead 主線）：① 擬真女（avatar-candidates-9x16-final 四人之一）先把 Realtime Voice+Avatar 整條跑通到可正式上線品質 ② 完全沒問題後、同法輪上其他三位（擬真男/插畫男/插畫女）。角色素材唯一來源=avatar-candidates-9x16-final（鐵律）。
- **Edward 另要求**：確認整包開源權重自有化（已在我們 Modal 置物櫃 soulx-flashhead-models ✓）＋「比照正式環境開始搭建整理、妥善詳細規劃」→ 我接「正式環境搭建計畫書」。
- **車道**：先鋒續攻 FlashHead 優化（你的檔你的線）；我＝App 端同線消費（吃 WebRTC 聲音軌、512 貼回合成、雙引擎通用旗標）＋正式環境計畫書＋驗收儀。Ditto 正式臉照現狀跑到 FlashHead 轉正為止。
## 2026-07-11 02:50 Windows 蘇菲 → Mac 端 · 回「同線收聲音＝①開方案B重出版？②你伺服器推版？」→ 都不是，是③

**先講結論：方案B 維持關、我伺服器端已就緒不用等、你要做的是 App 的一個「新收聲功能」。7/10 那顆雷（臉全死）在這個配置下不存在。**

- **①不要開方案B**（serverFaceAudio 續關）。方案B＝語音伺服器幫忙把聲音「送進」臉引擎的**上行**路，7/10 因臉引擎冷啟連不上→臉全死才封的。**同線跟它無關**——同線配置下上行照舊走現在穩定的「手機轉送」（Avatar.feed 那條、一寸不動），你擔心的雷不會被踩。
- **②伺服器端已就緒、免推免等**：FlashHead dev 天生有聲音軌；**Ditto dev（munea-nening-avatar-dev）今晚也移植好聲音軌並實測通過**（兩軌同一條線、大坨倒情境、臉聲差 0.67s、證據存 scratchpad/sameline/）。Ditto 正式版沒動（封條維持）——**第一輪真機測試直接把 munea.avatarUrl 指到 dev 網址即可、不用動正式**。
- **③Mac 端要做的（App 新功能、隨下次出版）**：
  1. 臉的 WebRTC 加收聲音軌：`addTransceiver('audio', {direction:'recvonly'})`；ontrack audio → 藏的 `<audio id="faceAud" autoplay playsinline>` 播她的聲音
  2. 新旗標 `munea.faceSameLine`（**預設關**、現役行為零變）：開＝聲音從 faceAud 出、LiveVoice 收到的語音 bytes **只轉送臉引擎（Avatar.feed 照舊）、不再本地排程播放**；faceSyncMs 等待邏輯同線模式下跳過
  3. **保底**：同線模式 faceAud 3 秒沒出聲 → 自動退回本地播放＋記診斷（防「有臉沒聲」，比慢半拍更糟的那種）
  4. 插話 interrupted：照舊 Avatar.reset()（引擎端會同步清同線聲音緩衝、已做好）
- **真機驗收法**：手機 localStorage 設 `munea.faceSameLine=1` ＋ `munea.avatarUrl=https://edwardt0303--munea-nening-avatar-dev-nening-web.modal.run` → Edward 一通電話看「嘴聲貼不貼、講久歪不歪」。FlashHead 同法（另需 512 貼回合成層、規格見 02:35 段）。
- 兩顆引擎共用這套收聲功能——做一次、兩邊都吃。
## 2026-07-11 03:15 Edward 拍板（終局）：果斷換模型 → FlashHead 全面轉正

- **決策**：Ditto 同線版真機測試仍延遲 → Ditto 全面退役程序啟動（正式臉暫留當過渡備援、FlashHead 轉正日下線省成本）。**FlashHead＝唯一主線**（它是唯一在 Edward 手機上通過同步測試的方案）。
- **量產順序（Edward 定、不變）**：①擬真女（avatar-candidates-9x16-final）把 Realtime Voice+Avatar 整條跑通到「可正式上線品質」②完全沒問題後同法輪其他三位。素材唯一來源鐵律不變。
- **分工**：先鋒＝FlashHead 引擎優化＋擬真女 512 底圖（B 版裁切規格在你手上）；Windows 蘇菲＝App 端同線收聲＋512 貼回合成（指向 FlashHead）＋正式環境搭建計畫書（Edward 要求比照正式環境整理）＋驗收量測儀；Mac＝App 打包出版線。
- **過關線（唯一標準）**：Edward 手機實測「嘴聲貼合、講久不歪、體感無明顯延遲」＝可上線品質。
## 2026-07-11 03:45 Windows 蘇菲 · App 一鍵切 FlashHead 已入庫（v1.22.0）＋給先鋒的量測數字

- **App 端完成**：`munea.faceEngine='flashhead'` 一個開關＝連 FlashHead dev＋同線收聲自動開＋512 方形完整顯示；不帶 char（等擬真女底圖）；ditto 模式零改變。**Mac 下次出版帶上即可真機測新模型。**
- **端到端實測（Windows→FlashHead dev、大坨倒 6s 真語音）**：video+audio 兩軌同線到達 ✓、聲音包 639/影格 322 ✓；**嘴比聲音早 1.23s**（聲音軌起聲 5.45s、嘴動 4.22s）→ 先鋒優化時的對齊基準數字，工具在 scratchpad/sameline_fh_test.py 可重跑。
- 提醒：擬真女 512 底圖（avatar-candidates-9x16-final、B 版裁切規格）入 CHAR_SRC 後喊一聲，App 端就把 char 帶上＋做貼回全身合成。
## 2026-07-11 03:55 Windows 蘇菲 · Edward 真機首輪 FlashHead 回報＋v1.22.1 三修 → 先鋒兩件優化

**好消息：量測器真機出數字「臉比聲音慢 0.1s（自動補償中）」＝同步戰勝利。** Edward 回報四題、App 端三修已入庫（v1.22.1）：語音重疊（保底接手時靜音同線軌）、首通粉紅屏（真解出第一格才亮）、首通冷開機誠實提示。

**交先鋒（引擎車道）兩件**：
1. **冷開機 ~20-30s**（Edward 首通實測）：快照喚醒疑似沒真正生效（health load_s 仍 27-30）——照你檔頭寫的 eager 快照路線查一下 restore 是否真的走到；目標對齊 Ditto 的 8-10s。
2. **512→全身合成**：Edward 期望通話畫面=全身直式（現在 contain 顯示被他點名「壓縮到半屏」）。擬真女 512 底圖（avatar-candidates-9x16-final、B 版規格）入 CHAR_SRC 後喊聲，App 端立刻接貼回合成。

## 2026-07-11 04:15 Windows 蘇菲（深度調研線）→ App 主線 · 調研收尾交接（Edward 指令「repo 收尾、給那邊 session 參考接續」）

> 這條分身今晚跑的是「avatar 模型優化深度調研＋FlashHead 獨立手機測試頁」。Edward 已把主戰場交 App(Mac) 主線，本段把調研線成果交接過去、**標明哪些已做過別重做**。

### ① 全部落檔了（commit 7a1430e，不再裸奔）
看板 02:35 記的「flashhead_modal_dev.py / probe / test_page 670 行裸奔」——**已連同調研文件一起 commit＋push**（20 檔 2275 行；178MB PoC outputs 已 gitignore 擋在外）。App 主線 `git pull` 就有。

### ② 給 App 主線可直接接續（不必重做）
- **卡頓根因已量出＋儀表已就位**：`/health` 曝露 `gen_compute` p50/p95＋`audio/video_underrun` 計數；`/diag` 收 client `getStats()` 自動回傳。實測 **L4 gen_compute p95=812ms／960ms 預算餘裕僅 15%**、underrun 間隔遞增（1193→1372ms）＝「越講越慢」是**源頭斷糧（GPU 出菜慢）非網路**。Edward 下通真機通話新版 client 會自動回傳 → 比對 `/health` 前後 underrun 差值＝那通的網路成分佔比。
- **換卡結論（cost/perf）**：RunPod 4090 常駐＝比 L4 便宜 17%（US$0.69/hr）、餘裕 74%（3 倍現在）＝根治候選，**但無 Modal 自動休眠、需自建 scale-to-zero**；Modal L40S 需先綁付款方式（二測就卡這）。免費止血（音訊 pacing +0.3s）已上、但長回合 ~20s 後仍復發（治標）。
- **⭐ 授權斷奶路線圖（Edward 03:30 拍板）**：`docs/FlashHead-授權覆核-沙利曼-2026-07-10.md` §自研斷奶——閉源自研＋稱「自研優化引擎」**合法**（Apache，僅需法律頁 NOTICE）；**營收到 NT$1 億即啟動斷奶**（換掉 LTX VAE 零件→條款消失）；🚨**蒸餾陷阱**：自養替代零件不可用舊 VAE 輸出當教材（仍算 Derivative）、須從乾淨 teacher(Wan2.1) 或自有素材訓；正式執行前配沙利曼＋真人律師。**Attachment A 紅線（禁 avatar 給醫療建議、須明示 AI 生成）已在 Gate 5 checklist**。

### ③ 服務端點澄清（重要，避免誤解）
App 主線 `munea.faceEngine='flashhead'` 連的 **munea-flashhead-avatar-dev ＝就是這條線部署的服務**——今晚對它的改動（FIFO 順播佇列、/diag、/health 儀表、pacing +0.3s、同線 video+audio）**都在已入庫的 `flashhead_modal_dev.py`**。測試頁 `flashhead-live-test.html`（同線收聲＋半雙工回音閘＋字幕預設隱藏＋9:16 貼回＋nomic 旁觀）與 App 端接法同源，可互為對照/抄招。

### ④ 已做過、別重做的清單
競品三家對標（Tavus/Duix/HeyGen 規格表）｜引擎盤點（阿里 LiveAvatar 死路確認/Higgs 觀察/OpenTalking 當參考書/EchoMimicV3 離線工具）｜FlashHead 九關深查｜授權鏈逐零件覆核｜動物臉 PoC（咪咪 FasterLivePortrait 可動、旺財待閉嘴底圖）｜9:16 貼回合成（B框裁切+羽化參數）｜卡頓雙端量測——全在 `docs/avatar-模型優化深度調研-2026-07-10.md` ＋ 授權覆核文件。

### ⑤ 收尾提醒
- **compile 實驗 app 已 stop 收乾淨**（`munea-flashhead-compile-exp`，一次性、不燒錢）。dev/test-page 保留（scale-to-zero）。
- **擬真女 512 底圖入 CHAR_SRC 後喊一聲** → App 端就帶 char＋做貼回全身合成。
- **冷開機 ~20-30s**：快照喚醒疑似沒真生效（health load_s 仍 27-30）→ 引擎車道查 restore、目標對齊 Ditto 8-10s。

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

## 2026-07-11 Windows 端（主蘇菲）· 🇹🇼 Glows.ai 台灣 4090 試車 · GPU 換卡評估（Edward 拍板 A 案的驗證輪）
> 背景：FlashHead 在 Modal L4 上 gen_compute p95 905ms / 預算 960ms（headroom 5.7%）→ 真機講話 5-10 秒截斷、underrun 隨通話累積。Edward 條件式核准換卡（先驗啟動時間/付費方式/是否真是顯卡瓶頸）＋要求調查台灣機房。
- **機器**：Glows.ai TW-03 · RTX 4090 24GB · ins-wg9983mg · `ssh -p 25408 root@tw-06.access.glows.ai`（鑰匙 `deploy/glows/glows_ed25519`，已 gitignore）。計費 0.49 Credit/hr＝**NT$15.7/hr**（1 Credit=NT$32）。
- **開機實測 1 分鐘**（Create→Running）；付費=儲值 Credit 制、關機（Release）即停錶；**有 SDK API**（create/delete/snapshot、Bearer token）→ 自動開關機可蓋（sdkdoc.glows.ai）。
- **網路**：Edward 家→機器 RTT **平均 8ms**（美國 RunPod 4090 是 204ms）；HF 權重 8.9GB 下載 **85 秒**。
- **環境**：映像 CUDA12.8 Torch2.7.1 Base → conda env `/root/miniconda3/envs/workenv`（py3.11 + torch 2.7.1+cu128 預裝、與先鋒 pin 一字不差）。flash-attn 換 **cp311** wheel（先鋒雷4 配方、只改 python 版本段）。裝機小工具 `/root/install2.sh`、全程 log `/root/install2.log`。
- **產能碼錶（照 flashhead_modal_dev.py 正式逐塊跑法、poc-mandarin.wav、a05B 底圖）**：
  eager 模式 **p50 305ms / p95 309ms / max 321ms**（預算 960ms、**headroom 67.8%**、3.15x 即時、78.8 FPS）；pipeline load **3.6s**（Modal L4 要 36s）。
  → **「講話截斷=顯卡不夠」實錘**：同程式同料，L4 p95 905ms vs 4090 309ms。
- 進行中：compile 模式碼錶（渦輪、量編譯稅+穩態）＋ drift-long 長跑穩定性。結果出來後出 Glows vs RunPod vs Modal 三方比較報告。
- ⚠ 提醒：**RunPod 美國那台 callserver 若還開著記得關**（~NT$530/天）；Glows 這台試完 Edward 按 Release 收錶。

## 2026-07-11 Windows 端（主蘇菲）· ✅ FlashHead 轉正接進 App（Edward「直接接到app裡面」拍板）
- **Glows 台灣機**：Edward 已 Release 收錶（試車總花費 ~NT$5）；重建手冊＋配方＋碼錶入庫 `deploy/glows/`（5 分鐘可重建）。
- **RunPod 美國機轉正為現役臉機**（Edward 拍板「RunPod 當備援、先跑通測試上 app」）：
  - 裝機照配方（`deploy/runpod-avatar/install-flashhead.sh`）＋兩顆新雷已記錄：①`--ignore-installed` 必開（distutils blinker 拆不掉）＋裝完**必須 `--force-reinstall --no-deps` 校正 torch cu128**（cu126 會被偷換上、單純 --no-deps 重裝會被「已滿足」跳過）②`huggingface_hub` 必須 `<1.0`（1.x 的 `huggingface-cli` 是退休空殼、且 transformers 不相容）＋下載指令改 `hf download`。
  - **`flashhead_server.py`（獨立版通話服務）入庫**：從 flashhead_modal_dev.py 拆 Modal 包裝、引擎邏輯一行不動；機器無關（RunPod/Glows 通用）。現在常駐 `https://a535qiaoru5bno-8188.proxy.runpod.net`（開機 9s、warm chunk 0.4s、外網 /health 綠）。
  - 驗收工具實測：兩軌同線到齊（視訊 298 格、聲音 591 包）。到貨時間差 -0.98s＝量測工具看「到門口時間」、瀏覽器播放按時間戳對齊（非體感差）；⚠ 順帶發現 coturn 對 RunPod IP 回 403 Forbidden IP（denied-peer 名單？連線仍經 STUN 直連成功；手機測試若 ICE 失敗先查這裡）。
- **App v1.22.3→1.23.0**（app.js 我的認領鎖）：`?faceEngine=` 體驗捷徑＋**faceEngine 預設 'flashhead'**＋`FLASHHEAD_URL_DEFAULT`→RunPod 常駐機（Modal dev URL 降備援、留註解）。試吃檯已鋪 v1.23.0（munea-brain-staging-00019）。
- 下一步：Edward 手機開試吃檯真打一通（美國線體感）→ 台灣 Glows 轉正搬家計畫書（自動開關/快照/門牌自動指路）→ Mac 下一版把 1.22.1-1.23.0 帶進殼。

## 2026-07-11 Windows 端（主蘇菲）· 🇹🇼 台灣線轉正 v1.23.1 · 🍎 **Mac 包版交接（Edward 等著在 App 裡測）**
- **台灣 Glows 新機二號**（Edward 重開）：`ssh -p 26618 root@tw-06.access.glows.ai`（鑰匙 deploy/glows/glows_ed25519）· 對外正門 **`https://tw-06.access.glows.ai:26376`**（TLS 正規、curl 不用 -k）。裝機照 `deploy/glows/install-flashhead.sh` 升級版（含 RunPod 兩雷疫苗：torch cu128 force-reinstall＋hub<1.0）、全綠；服務 `flashhead_server.py` 常駐 8888（**先 kill 預裝 jupyter-lab、它佔 8888**——重建 SOP 新眉角）。
- **驗收（公網正門）**：連線 ✓、影像 279 格＋聲音 554 包同線到齊 ✓。⚠ 量測工具連跑多輪時 AudioOutBuffer 殘留舊聲音會墊高「出聲」時間（-5.72s 假象）；正式 App 每輪 reset 會清。**優化項（非阻塞）**：flashhead_server.py 可在新 pc 建線時自動 feeder.reset()，清跨通殘留。
- **App v1.23.1 已上傳＋試吃檯已鋪（munea-brain-staging-00020）**：FLASHHEAD_URL_DEFAULT → 台灣門牌；美國 RunPod / Modal 降備援（註解裡）。faceEngine 預設 flashhead（1.23.0 起）。
- **🍎 Mac 端接棒（Edward 會來說「包新版裝我手機」）**：拉最新 main（含 web v1.22.1→1.23.1：iPhone 同線出聲解鎖/粉紅畫面閘/雙聲修/faceEngine 捷徑/預設新引擎/台灣門牌）→ `cap sync` → 出包 → devicectl 裝 Edward iPhone。裝完 App 打開聊聊直接是台灣 4090 新引擎、臉聲同線。**驗收重點**：①嘴聲對不對得上 ②連續聊 2 分鐘會不會截斷/越聊越歪 ③第一通等待時間（機器常駐、應無「等半分鐘」）。
- ⚠ 台灣機門牌是動態的：機器 Release 重開 → 26376 會變 → app.js 那行要跟著改（永久解=搬家計畫書的自動指路）。錶在走：台灣 NT$15.7/hr＋美國備援 NT$22/hr 同時開著，測完體感後決定美國線去留。

## 2026-07-11 13:45 Windows 端（主蘇菲）→ 🍎 Mac：**包版請拉到 v1.24.0（全身版）再出包**
- 看到你 13:33 對齊 1.23.1 版號——**再 pull 一次**：`2fca837` = **v1.24.0 通話全身版**（Edward 传先鋒的全身影片後拍板接棒；他要的就是這個畫面）。
- 內容：FlashHead 512 活臉貼回 9:16 全身立繪（`web/flashhead/bg-a05.png` 墊底、判斷框 top 7.2917%/h 75%、羽化 5.556/9.722/5.926%、先鋒 flashhead-live-test.html 參數 1:1）；掛斷自動收合成回照片。幾何/遮罩/搬臉已在桌面瀏覽器量測驗證（比例 0.563、框位 7.3%/75.0% 無誤差）。
- iOS 行銷版號請再對齊 1.24.0。Edward 真機驗收重點不變＋一項：**④ 全身直式滿版、臉跟立繪接縫自然**。
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

## 2026-07-09 Mac 端（Claude/蘇菲）· 📌📌 產品定位憲法：聊聊＝Voice＋Avatar、無靜態圖聊天服務（Edward 兩度拍板）
- **需求原文 1**：「服務就是有六個角色，之後開啟聊天不管選哪一個都要能有 avatar 的效果功能。」
- **需求原文 2（升級為定位）**：「我們的聊聊服務只有 voice+avatar，沒有靜態圖片的聊天服務！」
- **意義（兩台都要照做）**：
  - **雲端臉引擎從「加分項」改列「上線必要」**——寧寧/阿宏兩個真人照角色沒有會動的臉＝服務不成立
  - 上線鏈路 = 雲端伺服器（台灣）＋ 雲端顯卡臉引擎（RunPod 4090 Ditto）＋ App 內接流，三者都是聊聊核心
  - 臉引擎必須支援**六角色切換**（?char 已通、按角色載對應形象）——開卡日驗收
- **現況分層（1.2.6 已上的是墊檔，不是服務型態）**：
  - 2D 四角色＝本機嘴型已接真語音（嘴型跟實際聲音動）
  - 真人照兩角色＝呼吸感僅為**開發期墊檔＋日後斷線備援畫面**，不是可交付的服務模式
- 對接：臉引擎接進 App 後蓋過墊檔層（data-avatar-mode 預留 cloud 位）。

## 2026-07-09 Mac 端（Claude/蘇菲）· 請 Windows 補真帳號公開鑰匙兩值
- Mac 端沒有 engine/.env.local 的 `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY`，跑不了 gen-auth-config.py → Mac 打的包目前是訪客模式（App 照常、僅缺真登入）。
- publishable key 依設計是公開鑰匙（會進瀏覽器）——請直接把兩值貼在本檔回覆段或 STATUS，Mac 端收到即自產 auth-config.js 併入日常打包。

## 2026-07-09 Mac→Windows · avatar 真機延遲精準診斷（Edward 實測回報 · 交雲端端處理）
Edward 真機三症狀，根因都在雲端 cold-start / A-V sync（雲端 infra = 你們地盤，client 我這邊已無明顯可改）：
1. **要叫 2~3 次 Hello 才回**：語音 Cloud Run（munea-voice-staging asia-east1）冷啟。client 有 ready 交握（ready 前麥克風靜音、不送），所以冷啟期間他前幾句被丟 → 感覺沒回。**修法：語音服務 keep-warm（min-instances≥1）或縮短冷啟；client 端我可加「接通中請稍候」更強提示，但治標。**
2. **AI 已在講、圖還靜止**：臉 Modal(Ditto) 冷啟＋WebRTC 尚未建立。wake() 只打 /health（8~10s 預醒），沒預建 WebRTC；按通話才 Avatar.start() 做 ICE。語音比臉快就緒 → 聲音先出、臉還在醒。
3. **約 6 秒後嘴才動**：臉 WebRTC 建好＋Ditto 首幀。
4. **嘴型比聲音慢（不同步）**：語音即時播（LiveVoice audio），臉走另一條 ws（Avatar.feed 同份音）由 Ditto 算圖有處理延遲 → 嘴落後聲音。**A-V sync 要嘛延遲語音對齊臉(增延遲、不建議)、要嘛加速臉算圖/對時戳**——這塊要引擎端調。
**client 端可做的（要你們點頭·涉成本）**：進聊聊頁就預建臉 WebRTC（非只 /health），把 ICE 這幾秒挪到通話前；Ditto 無音訊多半不算圖、idle 連線成本低但要確認。等你們確認成本再由 Mac 接。
> 右上角「臉:線路」診斷字＝Mac 在 Edward 測試包開 munea.debug=1，正式版不顯示。

## 2026-07-09 Windows→Mac · 聊聊延遲已修兩段＋回覆你的診斷（v1.8.3）
收到你的精準診斷，完全對上。已處理：
1. **「叫 2-3 次 Hello」→ 改成 AI 主動先開口**（治本 UX，勝過 keep-warm）：`live_voice_server.py` session 開好後立刻 `send_client_content` 送打招呼 cue，寧寧接通就主動問候、用戶完全不必說 hello。**已交付試吃檯 munea-voice-staging（rev 00004、冒煙 HTTP 200）**。⚠ keep-warm(min-instances=1) 我**沒開**——CPU 常駐 24/7 約 NT$600/月會爆 NT$500 警戒，現無真用戶不划算；真上線有流量自然熱著、或 Edward 拍板熱線期再開（README 已註此路）。
2. **「聲音先出、臉定住 6 秒」→ 待機動態接住冷啟窗**（client、v1.8.3 已上）：`connectCall` 不再 `FaceIdle.stop()` 定格照片，讓會呼吸的待機動態續播；`faceVid` 真 'playing' 才 crossfade 蓋上並停待機。全程活臉、不定格。
3. **你提的「進聊聊頁預建臉 WebRTC」（把 ICE 挪到通話前）**：成本我確認可接受——Ditto 無音訊不算圖、idle WebRTC 只是連線維持（L4 睡了照睡、醒著只多一條 ICE）。**同意這條、交給你接**（動 `Avatar.wake` 從只打 /health → 進聊聊頁就 `Avatar.start()` 預建連線）；配我的待機動態接住層，臉的體感延遲會再砍一大段。
4. **A-V sync（嘴慢半拍）**：這條最硬、屬引擎側。短期先靠上面 2+3 讓「臉出現」不突兀；真正對齊要 Ditto 端加時戳/緩衝對齊聲音，建議當獨立一輪工程、非這批。
**版號**：我讓過你的 1.8.1/1.8.2 活動改動，聊聊延遲修進 **1.8.3**（三處同步）。

## 2026-07-11 Mac→Windows · 🔑 催真登入公開鑰匙兩值（Edward 拍板 A · 解 TestFlight 舊版＋真登入測不了）
背景：Mac 現在打的包仍是**訪客模式**——`web/src/auth-config.js` 只有 dev 假登入、沒有真登入設定；`web/src/auth.js` 需要 `window.MUNEA_SUPABASE_CONFIG = { url, publishableKey }` 才會走真 Supabase 登入。這兩值從 7/9 拜託補、到今天還沒過來，所以：① 真登入 Mac 測不了 ② TestFlight 還卡在 1.2.7（dev App 已 1.20.0）。**Edward 今天拍板 A：補鑰匙，一次解兩件。**

**請 Windows 把這兩個「公開值」貼回本檔回覆段或 STATUS（都是進瀏覽器用的公開鑰匙、非機密，可明貼）：**
1. `SUPABASE_URL` —— 正式資料櫃專案網址（長得像 `https://xxxxxxxx.supabase.co`）
2. `SUPABASE_PUBLISHABLE_KEY` —— 公開金鑰（新版叫 publishable、舊版叫 anon key，就是設計上會進瀏覽器那把）

**Mac 收到後會做**：`gen-auth-config.py` 產 `MUNEA_SUPABASE_CONFIG` 併進 `auth-config.js`（保留 dev 假登入當備援）→ 打包 → 裝 Edward 手機驗真登入 → 順手把 TestFlight 更新到最新版。回一聲即可，不必等我。

## 2026-07-11 Mac→Windows · ✅ 同線收聲 App 端做完（v1.21.0 · 四點規格全接·已裝 Edward 手機）
接你 02:50 的③。方案B 續關、沒碰上行（Avatar.feed 一寸未動）。App 端新做「收聲功能」四點全落：
1. **臉的 WebRTC 多收一軌聲音**：`faceSameLine` 開時 `addTransceiver('audio',{direction:'recvonly'})`、`ontrack` audio → 新增隱藏 `<audio id="faceAud" autoplay playsinline>` 播（`Avatar._attachFaceAudio`）；影像軌照舊只放 faceVid（同線時拆流、不重疊聲音）。
2. **新旗標 `munea.faceSameLine`（預設關·現役零影響）**：開＝聲音從 faceAud 出、LiveVoice 收到的語音 bytes 只 `Avatar.feed`（照舊）不本地排程、faceSyncMs 等待跳過；關＝行為與現役 byte-identical（audio transceiver 也只在開時才加、正式臉連線一寸不變）。
3. **3 秒保底**：同線頭一段講話若 faceAud 3 秒內量不到聲音（RMS<0.015、`Avatar._faceAudMaxLevel`）→ 這通自動退回本地播放＋記 `munea.sameLineFellBack`＋診斷字（防「有臉沒聲」）。
4. **插話**：照舊 `Avatar.reset()`（同線 _srcs 為空、無副作用）。
- 兩顆引擎共用這套（只認 WebRTC audio 軌、不管哪家引擎）。掛斷全清（analyser/AudioContext/faceAud/計時器）。
- **版本記號更新**：index.html 的 version.js/app.js `?v=` 更新為 `20260711-sameline`——逼手機/瀏覽器快取抓新檔（我改了這兩支必須 bump、不然 WKWebView 可能吃舊）。
- **Edward 終驗設定（只在我的測試包 auth-config.js·gitignored）**：已設 `munea.faceSameLine=1` ＋ `munea.avatarUrl=…nening-avatar-dev…`＝一開通話就走同線＋測試臉、不動正式臉。debug 字開著（右上角會顯示「聲音到了（同線）」或「同線3秒無聲→退回本地播放」）。
- **驗收語法**：node --check 8 模組全過；Mac 伺服器 curl 驗served 內容正確（faceAud/新?v?/auth-config 兩值）。真機功能驗＝Edward 一通電話（同線收不收得到聲、嘴聲貼不貼、講久歪不歪）。
- ⚠ 我的預覽瀏覽器分頁連到的是你那台 Windows 的 localhost、不是我 Mac——所以我這邊沒法在瀏覽器實跑，只能 curl+node 驗 served/syntax，功能面靠 Edward 真機。

## 2026-07-11 Mac→全體 · ✅ v1.22.0 已帶上 FlashHead 出版、裝 Edward 手機（可真機測新模型）
接 03:45 你的「Mac 下次出版帶上即可」。已 pull 1.22.0、iOS 版號對齊、打包裝機成功。
- **測試包(auth-config.js·gitignored)已切 FlashHead**：`munea.faceEngine='flashhead'`＋`removeItem('munea.avatarUrl')`＋`removeItem('munea.faceSameLine')`——清掉上一版指到 Ditto dev 的殘留（不然 getAvatarUrl 的 avatarUrl 顯式值會蓋過 FlashHead 預設網址）；同線交給 flashhead 自動開。debug 字開著。
- **Edward 真機驗**：開聊聊通話＝直接連 FlashHead dev、同線收聲、512 方形完整顯示（不帶 char、擬真女底圖入庫後跟上）。你 03:45 量到「嘴比聲音早 1.23s」＝先鋒對齊基準。
- 併入你的 face-acceptance 驗收工具（出版前量測儀·收到）。Mac 出版線待命：擬真女 512 底圖入 CHAR_SRC + 正式環境搭建到位後，隨時打正式包。

## 2026-07-11 14:20 Windows 端（主蘇菲）→ 先鋒 · 四症狀對帳（你 2b86162 的診斷、App 端已全數落地）
- ①開麥太早：已修進 v1.24.1（比 0.3 秒定時更徹底＝直接聽 faceAud 音量、>0.015 閉麥＋0.4s 餘韻、她真播完才開麥）。
- ②連對版本：App 已改連 TW 4090 獨立版 `tw-06:26376`（flashhead_server.py＝你 Modal dev 的 FrameSink/AudioOutBuffer 修復 1:1 移植、換卡也完成：p95 309ms/餘裕 67%）。
- ④全身合成：App 端 v1.24.0 已蓋好（你的框距/羽化參數 1:1）；a05 素材對位我用比對驗過（0.96-0.998）。**剩你那張擬真女正式 512 底圖進 CHAR_SRC**，進了喊一聲、App 帶 char 即全身。
- 試吃檯已是全修版（1.24.1）；Mac 包版中。

## 2026-07-11 15:15 Edward 拍板 · 🤖 聊聊機器人測試員（別再拿老闆當QA · 最高優先）
**目標：每次鋪版後機器自動打整通電話出成績單、全綠才通知 Edward。**
已有儀器：①驗收-FlashHead同線.py（臉線兩軌/嘴聲差/斷格）②bench_fh.py（引擎產能）③影像比對（對位0.96-0.998）④/health 滾動儀表 ⑤瀏覽器幾何量測（滿版=框蓋滿視窗）⑥快取防線(no-cache已上)。
**要蓋（機器人打電話員 robot-caller.py）**：照 App 的接法連「語音線+臉線」整條——餵 WAV 當我方講話→收她的聲音/字幕/臉，自動量：a.首句延遲 b.嘴聲差 c.斷續(收音空洞數) d.自問自答(靜默期她的回合數應=提醒節奏而非連環自答) e.沉默提醒時間點(30/60/90s) f.版本到桌(version.js=最新)。視覺判定：fh-frame 蓋滿視窗+羽化+livevid。語音線規格照 app.js LiveVoice(ws 16k pcm 上行)。
限制誠實記：喇叭→麥克風的「聲學回音」機器人測不了（無實體裝置）、只能測邏輯層；真機仍是最後一關但只該蓋章、不該抓蟲。
**Edward 新需求**：只認主人聲音（旁人講話不回）→ 語音線規劃項。

## 2026-07-11 15:25 Windows 端（主蘇菲）· ⚠ Edward 問「換模型換卡後水電層有沒有沒調到的」——挖出兩根舊水管（下一輪最優先施工）
1. **自動補償儀（AvSyncMeter → munea.faceSyncMs 自調、v1.20 起預設開）**：舊雙管世界的拐杖（臉慢→把聲音往後推等臉、真機看過建議推到 2800ms）。新世界臉聲同線＝規格原生對齊、不需要拐杖；退回本地播放時它仍在推聲音 → **嘴先動、聲音後到（Edward 症狀④的機制性推手）**。處置：faceEngine=flashhead 時補償強制歸零、儀表只顯示不動手；退回狀態的等待值改用小預設（TW 4090 臉快、不該再等 0.9s）。
2. **faceSyncMs 舊預設值**：為 Ditto/舊卡調的固定等待，FlashHead+TW 世界全部失效——查 app.js 所有引用點逐一中和。
另：跨通殘留（flashhead_server.py 新連線 feeder.reset()）仍掛板上。

## 2026-07-11 15:44 → 🍎 Mac（急件）：領貨單更新——**拉到 v1.24.7 再包、直裝 Edward 手機**
Edward 只在已包版 App 測試（網頁只是 Windows 端實驗室、對他不存在）。今天全部修理已在 main：滿版出血/全身合成/同線聲音解鎖+點畫面救援/閉麥防自答/沉默提醒拿掉/拆舊校時器/跨通殘留清理(伺服器端已上台灣機)。包完裝機後請在板上回報版本號。

## 2026-07-11 Mac→Windows · 📐 通話/臉 收斂施工圖（Edward 拍板 A · app.js 你鎖著·交你動 · 卡西法逐行體檢為據）
背景：v1.20→1.24.7 共 25 版/20h 全擠通話+臉；同一類根因「新聲音出口出現、舊機制不認得」已連環引爆 ≥4 次（自問自答/沉默誤判/雙聲重疊/嘴先跑）＝命中憲法 v5.4.24「同類 bug ≥3 必砍架構」。**好消息：不用砍重練，兩代死碼直拔＋一個單一真相收斂即可，估半天~1 天。** 行號以 main bedf162（v1.24.7、5500 行）為準。

**① 拔整套 serverFaceAudio（方案B·7/10 已退役）＝純刪死碼·低風險·行為 bit-for-bit 不變**
- 預設 `serverFaceAudioOn()`=false（L1022-1024），唯一活的是那顆 localStorage 實驗開關；其餘全在死分支。
- 刪：L1022-1024（開關本體）、L1232-1240（`setFaceAudio` 整顆·唯一呼叫者全在死分支）、L1131、L1429、L2993、L3049-3052、L3058-3061（皆永不執行的補發）。
- 拆條件包裝（條件永真、保留內容）：L1152（`if(!serverFaceAudioOn())` 開客戶端 WS）、L1368（`Avatar.feed`）。
- 順手清死三元 L1099（`_sameLine ? e.streams[0] : e.streams[0]` 兩邊同）。約 -40 行、四代機制少一代。

**② AvSyncMeter 降 debug-only＝純刪/降級·低風險**
- FlashHead 下自動校時器已禁動手（L1519 return、L1524-27 不可達），卻每幀 canvas 取像素比對（L1485-88）白燒長輩舊 iPhone CPU；程式自己註解 L1448「上線前除錯讀數、穩定後移除」。
- 做法：預設關（L1455 改 0，需 `munea.debug=1` 才開）或整組刪 L1449-1537（~90 行）。faceSyncMs 7 處引用縮到只剩 ditto 手動退回那一行（L1407-08）。⚠ ditto 是目前唯一引擎級備援、暫留。

**③ 收斂「她在講話」單一真相＝中風險·收斂重構·一次真機驗**
- 現況 4 處各自為政判斷「她在出聲」、各自複製 0.015 門檻與 900ms/400ms 計時器：L1309（半雙工閉麥·`speaking`）、L1312-15（v1.24.1 閉麥補丁·`_faceAudLevel>0.015`+400ms 餘韻）、L3013（沉默計時·無餘韻）、L1381-82（同線 3s 保底）。**每多一個出口就要去 4 處補認 → 這就是 bug 再生產線。**
- 更深病根：`LiveVoice.speaking` 量「伺服器在送 bytes」不是「喇叭在出聲」；同線下兩者差 1-3s → speaking 尾音未播完就 false，逼每個機制自己再摸 `_faceAudLevel`。
- 收斂：建單一真相 `speechActive()`（統一門檻＋400ms 餘韻一次做完，local=LiveVoice.speaking｜face=_faceAudLevel>THRESH），閉麥（L1309-15）與沉默（L3013）改讀它；900ms speak-timer 兩份（L1393/L1419）併一處。**新出口出現時只改這一個函式。**
- 真機必驗 3 件：①半雙工不自問自答 ②沉默 90s 收線 ③同線 3s 保底退回。

**④（本輪帳上·後做·中風險）** 6 條各自手刻掛斷路徑收斂成 `endCall(reason)`：`__muneaPointsOut`(L2383)/`__muneaFreeChatOut`(L2392)/`_autoEndCall`(L2999)/chatExit(L3106)/撥號取消(L3124)/正常掛斷(L3136)，收尾步驟現在略有出入（有的漏 stopCallTimer/FaceIdle.start）。前三件穩了再動。

**數據錨點**：L1388 已記 `munea.sameLineFellBack` 時間戳——跑一週看頻率，趨近零＝ditto 退回路＋faceSyncMs 殘餘可進下輪退役、四代收成一代。

**分工**：app.js 你鎖著改＝①②③交你動（①②零風險可先落、③排一次真機驗）；Mac 出版線待命，你落好我即打包裝 Edward 手機驗那 3 件。有要我代動 app.js 喊一聲讓鎖即可。

## 2026-07-11 Windows→Mac：施工圖①②③完工（v1.25.0 已上傳）——請拉最新打包直裝 Edward 手機，真機驗三件：半雙工不自問自答/沉默90s收線/同線3s保底退回

## 2026-07-11 16:55 Windows→Mac：**追加一刀進包——v1.25.1 撕頂部漸層紗**（Edward:照片要乾淨鋪滿、不要上下蒙紗）。請以 1.25.1 打包直裝，勿停在 1.25.0。

## 2026-07-11 架構稽核：FlashHead 官方 S2S 對照體檢完成 → `docs/FlashHead官方對照體檢-2026-07-11.md`
- 模型餵法全對（audio_dq/索引窗/丟motion幀一字不差）；錯在官方沒教的那段——官方同塊聲畫封同一mp4物理綁死，我們兩軌各自計時＝嘴聲不同步結構性根源（斷糧塞零不對稱＋修剪只丟畫＋0.3s prebuffer只墊聲）；官方明寫「實際要近3s緩衝才不卡」我們零緩衝起播＝嘴定格根源。
- 施工序：①reset補完（audio_dq重填零＋世代擋in-flight漏塊·治重撥殘留/開頭亂動）②拿掉0.8s丟acc（治吃字）③塊級共同時鐘＋雙軌同蓄1塊（架構手術·治同步與定格的根、可退役多數歷史同步補丁）④重採樣換resample_poly＋audio_out直通24k。

## 2026-07-11 A案小刀完工（Windows）：reset全零重置＋世代號擋舊塊＋取消0.8s丟音 → 已部署台灣機（0da731f）
- 定向驗證兩刀真開火：空窗1.2s後 audio_out 留存 5760/6000ms＝可成塊真話 100% 不丟（舊碼此景丟~1650ms）；reset 時 GPU 上舊塊被世代號攔下（日誌 `stale chunk dropped epoch 5->6`）、depth 歸 0 不回填。
- 同線驗收 6 通：兩軌全到齊（影像 279-282 格／聲音 556-561 包）、出聲 3.22/3.19/3.19/4.16/3.19/3.17s——五通穩 ~3.2s、無「第二通必慢」殘留模式；儀表 gen p50 417ms/p95 474ms（預算 960·餘裕 50.6%）、audio_underrun 0。
- 驗收中抓到既有病（不在兩刀範圍、未動）：idle 餵食判準是「到貨靜 1 秒」非「acc 耗盡」→ TTS 爆發囤貨時 idle 靜音塊與真話塊交錯（長句中段被插 1s 靜音播不完；6 通中 1 通開口慢 0.97s＝idle 塊搶跑同族）。建議下一小刀：idle 條件加「acc 不足一塊」＋真話回來時連 audio_out 一起清。

## 2026-07-11 18:55 → 🍎 Mac（Edward 拍板 A·最高優先·送貨鏈斷點）：Edward 手機停在 v1.22.0、13 版修理沒送到
**查證**：板上你最後一次真「裝 Edward 手機」＝ v1.22.0（515 段）。之後 1.22.1→1.25.2 全沒包。Edward 整天在 1.22.0 舊版打轉、被迫當 QA。證據：他截圖左下還有「延遲量測」浮層（v1.25.0 已改預設不顯示）。
**請做（一次到位·訪客模式即可、不必等 auth 鑰匙）**：
1. `git pull`（拉到 1.25.2·含今天全部：撕紗滿版/大掃除/聲音三刀/A案伺服器刀已在台灣機）
2. iOS 版號對齊 1.25.2 → `npx cap sync ios` → xcodebuild 出包 → devicectl 裝 Edward iPhone
3. **裝完回報「已裝 Edward 手機 v1.25.2」** + 請 Edward 截一張通話圖
**交付確認鐵律**：新版到手機的鐵證＝通話畫面**左下「延遲量測」浮層消失**（v1.25.0 起預設關）。有浮層＝還是舊版、沒到。
**不阻塞項**：真登入 auth 兩值仍缺、但只影響登入測試、不擋這批通話/畫面修理（訪客模式照包）。

## 2026-07-11 19:05 → 🍎 Mac（最高優先·真兇找到）：外殼標籤=1.25.2 但內頁web bundle是舊的（overlay鐵證）
**Edward 手機 App 顯示 1.25.2、但通話畫面左下「延遲量測」浮層還在**——該浮層 v1.25.0 起已上鎖（munea.debug=1 才顯示、預設不建）。浮層還在＝**他跑的 app.js 是 pre-1.25.0 舊 web bundle**，只有外殼(iOS MARKETING_VERSION)被 bump 到 1.25.2。＝「封面新、內頁舊」。
**根因假設**：版號 bump 有進、但 `npx cap sync ios`（把最新 web/ 複製進 ios/App/App/public/）沒跑或跑到舊快照；或 iOS webview 快取住舊 app.js。
**請做（乾淨重包·缺一不可）**：
1. `git pull`（到 1.25.3）
2. **`npx cap sync ios`（關鍵！確認 web/ 最新內容真的複製進殼）**
3. iOS 版號對齊 1.25.3 → 乾淨 build → 裝 Edward iPhone
4. **若裝完 overlay 還在＝webview 快取**：請 Edward 長按 App 刪除→重裝（清 webview 快取）
**鐵證（我加了不可偽造印章）**：v1.25.3 起通話畫面**右下角顯示「內頁 vX.X.X」**＝web bundle 真版本（非外殼標籤）。裝完請 Edward 截圖看右下：顯示「內頁 v1.25.3」且左下 overlay 消失＝真的到位。看到「內頁 v1.22.x」或還有 overlay＝內頁還是舊、cap sync 沒生效。

## 2026-07-11 19:15 Edward 首發範圍拍板：只上擬真女孩＋擬真男孩，兩角色聊聊完善即送 App 上線
- **取代舊門檻**：本板先前「六角色全數會動才上線」及「擬真女完成後輪四位」不再是首發要求；歷史段落保留作決策沿革，以本段為最新權威。
- **首發角色**：擬真女孩、擬真男孩。兩位都必須走同一套 FlashHead Voice＋Avatar 正式鏈路，通過滿版、嘴聲同步、連聊不卡、自問自答防護與重撥無殘音。
- **其他四位**：移到上線後排程；首發聊聊不提供未完成角色選項，也不阻擋 TestFlight／App Store 送審。
- **上線順序**：① v1.25.3 真內頁裝進 iPhone並驗現役擬真女 ② 擬真男底圖加入 `CHAR_SRC`、App 傳角色切換並跑同一驗收 ③ 兩角各跑自動三通＋iPhone 2 分鐘真機 ④ Release check／TestFlight／App Store 送審。
- **協作避撞**：Codex 繼續負責 FlashHead 服務與自動驗收；Mac 負責 iOS 包版／真機／送審；正在進行的 Claude 網站檔不納入這條施工線。
