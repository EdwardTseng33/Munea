# 沐寧 Munea · STATUS（接力檔）

## 2026-07-01 Update - Dual-AI collaboration board aligned

**Status:** completed and ready for GitHub sync.

- Reviewed Claude/城堡 local repo organization update and found the new collaboration board at `docs/協作看板-雙AI分工.md`.
- Reframed the board from fixed ownership lanes into an SSOT-first collaboration protocol: task registration, file avoidance, small commits, no force push, and required documentation backfill.
- Updated `docs/00-總綱-從這裡開始.md` so Codex is not constrained to Avatar-only work; Codex can continue as CTO/technical architect/full-stack development agent while still respecting coordination rules.

## 2026-07-01 Update - Billing tier naming

**Status:** product naming decision locked.

- AI model target updated: Butler Brain and Guardian Brain now default to `Claude Sonnet 5` / `claude-sonnet-5`.
- Subscription ladder: `Free / Plus / Premium / Concierge`.
- Added `docs/BILLING-CREDITS-ENTITLEMENT-v1.md` as the billing, credits, and entitlement source of truth, including prior-plan review and the current service architecture.
- Added `supabase/sql/006_billing_credits_foundation.sql` for entitlement policy versions, credit wallets, credit transactions, and credit ledger.
- Added local runtime credits contracts: `/credits/balance`, `/credits/grant`, and `/credits/consume`, backed by `engine/credits_store.json`.
- Connected premium Avatar overage to credits in `/avatar-session`; when credits are insufficient, the session falls back to `2d-viseme` instead of breaking.
- Added Supabase adapter support for runtime credits tables: `credit_wallets`, `credit_transactions`, and `credit_ledger`.
- Credits remain reserved for expensive/bursty add-ons such as premium Avatar/GPU minutes; basic companionship should not feel metered.
- Current implementation still uses backend entitlements + usage ledger; full credits wallet remains future work.

## 2026-06-30 Update - Relationship state readback

**Status:** completed for local/backend contract.

- `/butler/post-turn` can save structured memory and companion relationship state after a turn.
- `/persona/context` now reads the latest matching relationship state and returns it with the persona pack.
- `/chat`, `/voice-note`, and `/voice-session` use the same persona context path, so rapport, preferred address, tone overrides, and relationship memory can affect the next response.
- `aiContext` now includes a relationship summary for developer diagnostics.
- Smoke tests now verify the write/read loop: post-turn writes `companion_relationship_states`, then the next persona/build context reads it back.

**Next:** Gemini Live realtime adapter and Supabase/RLS validation against the real project.

## 2026-06-30 Update - AI diagnostics panel

**Status:** completed for frontend developer visibility.

- Settings now includes a developer-only `AI context diagnostics` panel.
- Normal user mode keeps the panel hidden; `?debug=ai` or local developer mode can show it.
- The panel displays persona template, rapport level, Guardian risk, memory count, perception domains, tone overrides, and compact raw context JSON.
- Chat, voice-note, voice-session, and Butler post-turn responses now feed their latest `aiContext` into the panel.
- A manual refresh calls `/persona/context` so developers can inspect the current persona + relationship state without storing raw transcript text.

**Next:** Gemini Live realtime adapter and live Supabase project validation.

> 沐寧 Munea · 智慧健康陪伴 App · **新 session cold-start：先讀 `docs/00-總綱-從這裡開始.md`（唯一真相入口）+ `docs/SPEC-沐寧-v1-2026-06-28.md`（權威規格）+ `docs/BILLING-CREDITS-ENTITLEMENT-v1.md`（帳單/訂閱權威），再看本檔現況**
> 最後更新 **2026-07-01（帳單/訂閱制命名鎖定：Free/Plus/Premium/Concierge + 點數只用於加值；Butler/Guardian 腦改用 Claude Sonnet 5）**——見本檔最上方 2026-07-01 段。6/30 段（AI 服務架構補 Companion Persona Layer）為前一版最新，保留於下方。

> **2026-06-28 晚間校正：產品不是老人 App。核心是 AI 健康照護 + 家人互動 + `聊聊`。語音語言策略為中文（台灣）優先、英文第二；台語只保留研究觀察，不列入 v1/v2 承諾，也不自研語言模型。語音腦接點以 SPEC 的 Gemini 3.1 Flash Live 方向為準。下方 6/27 歷史段落若仍出現 gpt-realtime、台語護城河或純長輩定位，一律視為歷史紀錄，不作為施工依據。**

---

## 🆕 2026-06-30 最新（AI 服務架構 + 角色人格層）

**策略校正：** 三顆腦仍是責任分層，但六角色不能只是 UI 皮膚。正式架構新增 **Companion Persona Layer / 角色人格層**，負責角色人格、語氣、關係感、聲音演出與 avatar 表達；Guardian 仍保有安全最高優先權。

**核心公式已寫入北極星：**

```text
回應 = 角色人格 + 使用者記憶 + 即時感知 + 當下對話 + 安全規則 + 語音表達限制
```

**做完：**
- ✅ `docs/產品遠景-核心目標.md` 補上真實回話公式與六角色人格要求。
- ✅ 新增 `docs/COMPANION-PERSONA-LAYER-v1.md`：定義六角色模板、使用者命名、persona / memory / perception / relationship state 分離。
- ✅ `docs/AI-SERVICE-DESIGN-v1.md` 補上 Persona Layer 在 Reflex / Butler / Guardian 之間的組裝鏈。
- ✅ `engine/model_router.py` 新增六角色 persona template 與 `persona_context_response()`。
- ✅ `engine/server.py` 新增 `POST /persona/context`，`/healthz` 加入 `persona-context` 合約。
- ✅ `/chat` fallback 已接入 persona + memory retrieval + perception plan + Guardian policy 組裝鏈，回傳輕量 `aiContext` 供驗證。
- ✅ `/voice-session` 已回傳 persona-aware `aiContext` 與 speech-first session context，供未來 Gemini Live S2S 熱路徑沿用。
- ✅ 新增 `/butler/post-turn`：背景做 memory extraction 與 `companion_relationship_states` 更新，不預設保存 raw transcript。
- ✅ 新增 `engine/companion_relationship_states.json` 作為 Supabase 前的本機 relationship state fallback。
- ✅ Supabase adapter 補上 `companion_relationship_states` load/save mapping。
- ✅ 中文感知關鍵詞補齊：書籍、旅遊、出去玩、運動、財經、影視/韓劇/日劇/台劇/Netflix、音樂、美食、新聞、信仰反思。
- ✅ 新增 `supabase/sql/005_companion_persona_layer.sql`：`companion_persona_templates` + `companion_relationship_states`。
- ✅ README、總綱、Backend Architecture、Supabase Setup 均已補上 persona layer 與 005 schema。
- ✅ `scripts/smoke.ps1 -SkipApi` 通過，涵蓋 persona layer、文件契約、前端語法與現有後端合約。

**下一步：**
1. 接 Gemini Live ephemeral session / realtime adapter，讓 `MuneaVoiceProvider` 從 `stt-chat-tts` 升級為真正 S2S。
2. 把 `/butler/post-turn` 的 relationship state 納入下一輪 `/persona/context` 檢索，形成「關係狀態會影響下次說話」。
3. 讓 `/chat` / voice loop 的 `aiContext` 進入 dev diagnostics，不進正式使用者主畫面，維持 S2S 非逐字稿體驗。

---

## 🆕 2026-06-29 最新（產品架構 + Avatar 開發提前）

**策略校正：** Avatar 不再等 Gemini Live 完全穩定後才開始；改成先建立 **Avatar Runtime 合約**，讓 `聊聊` 的待命／聆聽／思考／說話、角色切換、音訊結束都先走同一層。這代表 Avatar 開發已往前搬，但不是現在就押注 LiveAvatar GPU，而是先把產品體驗與工程接點立起來。

**做完：**
- ✅ `docs/ARCHITECTURE.md` 重寫為當前產品／服務架構：Munea = AI 健康照護 + 家人互動 + `聊聊`，不是老人限定 App。
- ✅ 新增 `docs/PRODUCT-ARCHITECTURE-AVATAR-FIRST-PLAN.md`：Avatar-first 但不 GPU-first；先做 runtime、2D viseme 保底，再接 Ditto / LiveAvatar PoC。
- ✅ 前端新增 `window.MuneaAvatarRuntime`：`setState`、`setCharacter`、`speak`、`onAudioEnd`。
- ✅ Avatar engine mode 往前推：`static-css`、`2d-viseme`、`ditto`、`liveavatar`；2D 角色已可跑 mock mouth-state。
- ✅ RunPod Avatar PoC 路線補齊：Ditto 先復測 online fps；LiveAvatar 尚未排，先走 H100/H200 單卡 FP8 首測，不直接燒 5×H800。
- ✅ 技術棧審查完成：保留 Capacitor + Web Core；語音改為 Voice Provider Adapter；資料層建議 Postgres + RLS；Avatar 保持 Runtime/2D 保底，Ditto/LiveAvatar 只在 RunPod gate 通過後接。
- ✅ Voice Provider Adapter baseline 已落地：前端新增 `window.MuneaVoiceProvider`，後端新增 `/voice-session` 能力回傳，先走 `stt-chat-tts` fallback，保留 Gemini Live / Interactions 接入點。
- ✅ Companion Identity Model 校正：陪伴角色拆成「使用者命名」與「角色模板」，設定頁改為帳號與家庭／AI 陪伴角色／健康資料與安全／App 體驗，不再重複「選一位管家」。
- ✅ 首頁與聊聊 UIUX 優化：首頁頂部降噪、聊聊入口改為左右分層模組、聊天頁改用手機直式滿版人物圖，避免標籤與人物/CTA 重疊。
- ✅ S2S 產品框架校正：聊聊頁改為「像視訊聊天」的狀態提示，不再把使用者/AI 逐字稿作為主要畫面；字幕僅保留為未來輔助功能方向。
- ✅ Companion Profile 串接：登入/裝機流程選角色與命名會寫入同一份 profile；首頁、聊聊、設定頁同步讀取；設定更改角色或命名會同步回寫。
- ✅ Companion Profile 後端橋接：新增 `engine/companion_profile.json` 與 `/companion-profile` 讀寫 route，前端靜態預覽用 localStorage、完整 App 模式可同步本機後端。
- ✅ App Profile Store 底座：新增 `engine/app_profile_store.json` 與 `/app-profile`，先把帳號、家庭圈、主要使用者、陪伴角色 profiles 收進同一個本地結構，方便後續移往正式資料庫。
- ✅ App Store / 訂閱服務底座：新增 `engine/billing_store.json`、`/entitlements`、`/subscription-event`、`/healthz`，並補 `docs/APP-STORE-PRODUCTION-READINESS.md`。
- ✅ API 安全 baseline：限制 JSON/audio payload、限制錄音 MIME、標準化錯誤回應並避免預設外洩 exception detail。
- ✅ 資料權利底座：新增 `engine/privacy_requests.json`、`/privacy-export`、`/account-deletion`，補上 App Store 帳號刪除與資料匯出合約。
- ✅ Supabase DB bootstrap：新增 `supabase/sql/001_initial_munea_schema.sql`、`docs/supabase/SETUP.md`、`docs/supabase/munea-env.example.txt`，先完成正式 DB schema / RLS / grants 草案。
- ✅ Backend Architecture v1：新增 `docs/BACKEND-ARCHITECTURE-v1.md`，定義 API surface、Supabase/RLS、訂閱權益、資料權利、管理後台 MVP 與北極星數據板。
- ✅ Supabase Adapter v1：新增 `engine/supabase_adapter.py`，`/companion-profile` 與 `/app-profile` 回傳 backend 狀態；Supabase env 完整時可啟用，否則安全回 JSON fallback。
- ✅ Supabase App Profile Aggregate：`/app-profile` 已可在 Supabase env 完整時聚合 `accounts`、`persons`、`family_groups`、`family_memberships`、`companion_profiles`。
- ✅ `scripts/smoke.ps1` 新增 `node --check web/src/app.js`，避免前端 runtime 改動沒被驗收。
- ✅ `npm run smoke` 全綠：`/open`、`/chat`、`/voice-note`、語音 payload、JS syntax 都通過。

**新優先序：** 產品架構 + Avatar Runtime → 2D viseme fallback → iOS 麥克風真機 → Gemini Live voice loop → Ditto / LiveAvatar PoC 接入。
**核心原則：** Avatar 是早期產品層，不是早期 GPU 依賴；對話不能因為臉還沒即時而中斷。

---

## 🆕 2026-06-28 最新（規劃底重建 + 核心畫面修正）
> 觸發：6/28 主對話蘇菲沒先讀北極星／設計簡報就動手、把對話畫面做歪（小圓頭像 ≠ 簡報明寫的「全屏管家臉」）。Edward 點出根因＝**沒有「唯一真相＋動手前先讀」的路由**，要求重建「規劃的底」、不要「講一個修一個」。

**做完（依 Edward 親定規劃五步）：**
- ✅ **Edward 親定「規劃五步」工作流** `docs/產品規劃工作流-Edward定義-2026-06-28.md`（① 記得根 ② 看外面 ③ 長規格 ④ Codex 交叉審 ⑤ 整理路由）。**鐵律：任何 agent 動手前先讀根。**
- ✅ **SSOT 唯一真相入口** `docs/00-總綱-從這裡開始.md`（路由＋40 份文件地圖＋待對齊清單）。
- ✅ **對齊盤點**（霍爾）`docs/對齊盤點報告-2026-06-28.md`：揪 11 項漂移／重複版本；最致命＝語音換 Gemini 但訂價還建在舊貴成本（gpt-realtime）上。
- ✅ **SPEC v1 權威規格**（霍爾·12 章）`docs/SPEC-沐寧-v1-2026-06-28.md` ＝ **新唯一規格**（舊「規格書-完整」降備查）。**§6 補「對話畫面＝單一全屏臉」缺口（做歪根因）**。
- ✅ **官方一句話定位鎖定**：「**會記得你，也在乎你在乎的人。**」靈魂＝懂得何時講何時靜、讓人驚豔的感知互動（立為設計鐵則）。
- ✅ **訂價重算（Gemini 成本）** `docs/訂價重算-Gemini成本-2026-06-28.md`：499 中度從倒虧 −318 翻正 +314（74% 毛利）；全包成本 1.15→0.55/分（省 52%）；**四檔維持**。Edward 拍板：**商業機制先做、精確點數等開發完用真成本再定**。
- ✅ **對話畫面重做＝單一全屏管家臉**（卡西法·照 §6）：臉鋪滿全屏＋呼吸眨眼＋S2S 狀態提示＋底部超大結束鈕＋四狀態（待命／聆聽／思考／說話）；接上會記憶的腦＋Leda 真聲音＋主動開口＋6 角色切換。**蘇菲親核（結構＋活語音）✅**。**砍掉舊小圓臉聊聊頁＋多餘視訊頁**。
- ✅ **6 角色頭像統一插畫風**（用 `avatar-candidates` 那套一致風格）。

**怎麼跑／測（取代下方舊的 8126 靜態法）：**
```
雙擊 run-munea-app.bat            # 鑰匙在 gitignore 的 engine/.env.local
# 或：GEMINI_API_KEY=... py engine/server.py
# → 瀏覽器 http://localhost:8200 → 點「聊聊」＝全屏臉會講話
```

**現在到哪（整體 ~60% 到「avatar＋voice 完整體驗」）：**
- 🟢 規劃底／寧寧的腦（語音＋記憶）／6 頭像／**全屏臉對話畫面** ＝ 好了、可測。
- 🔴 **最後一哩＝臉真的對嘴動（avatar）**：卡 RunPod 顯卡 online fps 重測（暫停·新機器要重裝）。過了才能接會動的臉。
- ⏸️ 上 TestFlight：開發者帳號審核中。
- 🟡 Codex 交叉審 SPEC（第④步）待排；7 份過時文件待歸檔 `docs/archive/`。

**待 Edward：** ① 再開 RunPod 跑 avatar fps 重測（解鎖會動的臉）② Codex 交叉審要不要我安排 ③ 小拍板（記憶 4 轉鈕／尊榮 1999 額度／擴大客群後市場 TAM 重算）。

---
*以下為 6/27 及更早歷史紀錄，結論一律以上方 2026-06-28 段 ＋ SPEC v1 為準。*

---

## 現在到哪（2026-06-27 大躍進日 · 規劃＋地基基本完成、進入「真的蓋」）
今天一天做完：
- ✅ **改名 Munea 沐寧**（域名 munea.net 已購、名字鎖定）。
- ✅ **商業模式全定案**：四檔點數制（免費 5 分試用／基礎 499／高級 999／尊榮 1999）、1 點=NT$2、標準臉 1 點/分・生動臉 6 點/分、兩油箱（月送當月歸零＋購買永久）、子女管錢長輩端永不見計量。詳 `docs/定案-商業模式與開發路線圖` + `商業模式-v3`。
- ✅ **雙引擎 avatar 技術藍圖**（標準=Ditto／生動=LiveAvatar、AvatarEngine 介面、idle-loop、多租戶分艙）`docs/avatar-雙引擎技術藍圖`。
- ✅ **avatar 親跑實測（Edward 親跑、蘇菲全程導 ~1hr）**：Ditto TRT 在 1×RTX4090 跑通 = **便宜消費卡自架可行已證**。16fps（上次 PyTorch 12、TRT +30%），未達 25 即時門檻；卡西法分析「降解析度+減步數幾乎零成本可推 25-30」、keystone(a)=🟡 有條件 GO 偏樂觀。重測指南 `docs/Ditto-優化重測指南`（下次 RunPod 跑 online 量真 go/no-go）。
- ✅ **6 角色臉定案**：2 擬真（real-female/male-homey、已接進首頁/聊天/視訊/裝機選角/設定換臉）+ 4 韓系插畫（muning-*、Edward 自製、陸續接）。
- ✅ **原型推進**：家人端「訂閱與點數」管理畫面 + 設定頁「換寧寧的樣子」（會真的換臉）。
- ✅ **Sprint-1 施工表** `docs/開發-Sprint1-施工表`（外殼+標準臉+語音接點+iPhone 殼、待 Edward 點頭開蓋）。
- ✅ **擴大客群定位**（霍爾）：定位傘「沐寧＝會記得你、在乎你、你也在乎的人」、三客群（孤獨長輩/慢性病日常者/需慰藉者）不貼身份標籤、雙入口（幫家人裝/自己用）、tagline「有人在乎就會心安」、醫療紅線禁用詞表（待沙利曼 Gate 5）。`docs/品牌定位-擴大客群-Howl`。
- ✅ **對外漏斗全打通**：著陸頁 `landing.html`（暖色襯線門面）→ 裝機雙入口（`onboarding.html?mode=family/self`、選了帶進流程）→ 長輩端 App＋子女端。子女端加「生動切換」demo（標準啟用／生動上鎖尊榮·6 倍燒點·升級話術）。整條走得通、原型完整可對外展示。
- ✅ **語音線整條收尾（深夜大成果）**：① 語音大腦定案 **Gemini 3.1 Flash Live**（Edward 親耳秤 30/30/30/10、比 GPT 便宜 ~3 倍、台灣中文更自然；推翻舊成本表 GPT-realtime 假設、語音成本下修）② **6 角色語音卡司**親耳定案（寧寧=Leda／2D女=Callirrhoe／大哥=Charon／2D男=Algenib／貓=Aoede 卡通貓演技／狗=Charon 低沉大狗演技；**動物=人聲+演技指令、已實測可行**）③ **6 角色人格聖經**（霍爾）：寧寧/小昀/阿宏/阿原/咪咪/旺財，性格+講話方式+範例台詞+醫療紅線「軟性帶開」當人設 ④ **記憶+守護架構**說明給 Edward（會話腦 Gemini+記憶層[整理員/記憶庫/搜尋員]、議題規範軟引導、情緒感知三來源[語氣/用詞/長期趨勢]+危機轉介 1925）。詳 `docs/語音卡司表-6角色`、`docs/角色人格聖經-6角色`、樣本 `voice-samples/`。用 Edward 充值的 Google key（限速 3/分免費→已充值）。

**下一步**：① **Edward 點頭「蓋」→ Sprint-1 交 codex 開蓋**（真引擎、唯一把漂亮 demo 變成可上架產品的一步）② Edward 下次 RunPod 跑 avatar online 重測（推 🟡→🟢、真 go/no-go）③ Edward 拍板鎖定位傘那句 ④ 補 2D 韓系圖 + 商標查（Munea／沐寧／巴西 Munai）⑤ 醫療紅線禁用詞交沙利曼 Gate 5 ⑥ 「對話與守護建置藍圖」（記憶/議題規範/情緒感知/危機網整成 build spec、卡西法＋沙利曼）⑦ 把 6 角色卡司＋名字＋人格接進原型換臉頁。
⑧ **資料與隱私安全藍圖已落檔**（沙利曼 6/27 · `docs/建置藍圖-資料與隱私安全-2026-06-27.md`）：四抽屜資料設計（檔案/時序/向量/對話＋對應 DB）＋加密分層＋子女看長輩的同意機制（長輩授權、三層可見度）＋台灣個資/醫療合規＋危機告警資料流。🟢 **核心利多：守住醫療紅線→健康數字不算特種個資**（霍爾禁用詞表＝法律護城河）。**🔴 待 Edward 拍板 5 件**（子女可見度預設偏向／對話保留天數／退訂硬刪期／接受 V1 雲端語音三道防線／危機自傷通知界線）｜**🔴 待外部律師 4 件**（點數是否屬禮券需信託履約⭐最優先／特種個資判定確認／高齡電子同意要件／自傷違意願通知界線）。
- **✅ Edward 6/27 深夜拍板 2 件**（沙利曼那兩項撤）：① **點數＝遊戲鑽石／服務預付模式、V1 不做信託履約**（單一用途點數只能花在沐寧服務、非「能當現金的商品禮券」，業界普遍免信託；有規模再請律師確認一次、不擋 V1）② **隱私＝加密存好＋隱私條款揭露即接受 V1 baseline**；唯一硬性補：條款須誠實揭露「聊天語音經 OpenAI／Google 第三方伺服器處理」以確保知情同意。
- **✅ Edward 6/27 拍板 · 產品定性鎖定**：沐寧 ＝ **智慧健康／智慧照護（陪伴），非醫療軟體**。法律意義：不走醫療器材／醫療軟體重監管（免衛福部醫材查登）、健康數字非特種個資——**前提＝守住「非醫療」**。守門靠霍爾禁用詞紅線（陪伴／生活提醒 ✅；監測／診斷／治療／管理病情 ❌）。文案／功能／App Store 分類／對外講法一律照「智慧照護陪伴」定性走。
- **✅ 底層建置藍圖齊了（6/27 深夜）**：①`建置藍圖-資料與隱私安全`（沙利曼·35KB）②`建置藍圖-系統架構與API`（蘇菲收尾·卡西法兩次連線斷·後審）——含三顆腦對應真零件、**背景管家腦選型建議（排程代碼＋規則＋Gemini Flash-lite 級判讀）**、聯網/離線/延遲(<1.5s)/更新頻率、端到端服務流、生臉串接 idle-loop、**動土前必驗（Capacitor 麥克風 go/no-go＋avatar fps 重測）**、Sprint 順序（0驗命脈→1最薄一條→2長肉→3上架）。**地基打完、可動工**；真 codex 建造＝下一階段（要 Edward 撥額度＋先驗命脈）。
⚠️ **已知坑**：中文專案路徑 NFC/NFD 分裂（bash/python 有時抓不到檔；Read/Write/Edit/git 穩）→ 終究建議改 ASCII 資料夾名。

原型設計：沐寧配色（療癒綠+珊瑚橘+奶油底）+ 線條圖示 + 融入 Elfie 行為科學。

## 品名 / 角色（本 session 更新）
- 品名：**Munea**（英）/ **沐寧**（中）。〔英文定 Munea：Edward 6/27 拍板、PAINING 棄用——英文負面義「使人痛苦」+ 與已查證域名/商標不符〕
- 管家：**寧寧**（女）；範例長輩：陳奶奶；子女：美華（女兒）/ 志明（兒子）；孫子：小寶

## App 架構（底部 5 分頁 + 延伸流程）
- **寧寧**（首頁）/ **狀態** / **聊聊**（中央語音鈕）/ **家人** / **設定**
- 延伸流程：首頁 → 視訊通話 → 用藥服務窗
- 「聊聊」中央凸起 = 命脈動作「主動開口」

## 已做的功能（原型）
| 分頁 | 內容 |
|---|---|
| 寧寧 | 管家英雄卡 + 視訊入口 + 「今天一起完成」可勾任務 + 安心存摺條 + 家人留言 |
| 狀態 | 身體數據（血壓/睡眠/用藥/活動）+ 安心存摺卡 + 寧寧觀察 + 回診摘要 + Apple Watch 數據來源標記 |
| 聊聊 | **S2S 日常語音陪聊**：全屏真人感 avatar + 麥克風語音對話 + 聆聽／思考／說話狀態提示，預設不顯示逐字稿 |
| 家人 | **全家健康圈**：成員切換看每人健康（身體/活動/睡眠/用藥）+ 週月趨勢；多元家庭挑戰 + 發起挑戰（自由邀請·不強制·依人數+能力動態難度）+ 家庭記錄簿 + 成就徽章牆 + 互動回應 |
| 設定 | 連接的裝置（Apple Watch / Apple 健康 / 跌倒求救）+ 一般設定 |
| 視訊通話 | 已併入「聊聊」單一全屏 S2S 對話畫面 |
| 用藥服務窗 | 藥卡 + 連續服藥 + 我吃過了/再提醒 |

## 設計
- **沐寧 配色**：療癒綠 `#3AA8A0` + 珊瑚橘 + 奶油底（讀自 careon-site 實際數值）
- 線條圖示（非表情符號）+ Poppins / Noto Sans TC
- 規範：`docs/design-system.md`（哪個位置用哪個圖示都有定）
- App 圖示：`web/icon.svg`
- 人物素材：randomuser（**西方臉示意，正式版換亞洲真人**）

## 重要文件
- 📕 **`docs/規格書-完整-2026-06-27.md`** — **完整專案規格書（一本串全部、先看這本）**
- ⭐ **`docs/產品遠景-核心目標.md`** — **北極星**（Edward 6/27 親訂：avatar 兩軌標竿、聽講像真人、感知、記憶、視訊取捨）。任何設計/實作對齊這份。
- `docs/解決方案與系統骨架-管家版-2026-06-26.md` — 系統架構（三顆腦 + 一張臉，實現上面的遠景）
- `docs/自架成本與PoC計畫-2026-06-26.md` · `docs/擬真avatar授權合規查核-2026-06-26.md` — 自架成本 / 擬真授權（Ditto）
- `docs/design-brief-peining.md` — 產品設計需求
- `docs/design-system.md` — 設計原則規範（顏色/字體/圖示/元件）
- `docs/architecture-elfie-fusion.md` — Elfie 融入 + 家人傳話架構 + Apple 健康 + 家庭遊戲（§一~九）

## 怎麼跑原型
```
python3 -m http.server 8126 --directory web
# 瀏覽器開 localhost:8126，或 open http://localhost:8126/index.html
```

## 技術路線（最新施工依據）
Capacitor 把網頁包成 iPhone App；語音互動以中文（台灣）優先、英文第二，接成熟即時語音模型/供應商能力，不自研語言模型。三顆腦 + 一張臉仍是主架構；iOS 先、Android 後。台語暫列研究觀察，不擋 v1/v2。

## 夜間自治進度（蘇菲 · 6/27 凌晨、Edward 睡後）
- ✅ **擬真 Ditto PoC 成功**（Edward 在 RunPod RTX 4090 親跑通、生出 talking-head 影片、24GB 夠、~12fps 半即時、TRT 預期到即時）→ 一鍵重跑指南 `docs/Ditto-PoC結果與重跑指南-2026-06-27.md`。便宜消費卡自架擬真「跑得動」實證。
- ✅ **子女端 `family.html` 補「寧寧的提醒」**（收通知：回診 7/2／膝蓋痛關懷／天氣轉涼主動關照；沿用設計系統、eval + 截圖驗證）。
- ✅ **底色改單一米黃**（Edward 6/27 回饋：`.app-shell` 拿掉薄荷綠+橘暈光漸層→單一 `--cream`；聊聊頁 `.chat-screen`→單一薄荷綠當區隔底；薄荷綠其餘只當點綴。驗證+雙截圖過）。
- ✅ **串引擎計畫 v2 落實**（讀完 `castle-voice-engine` 程式庫 STATUS/PASSPORT/路由）：① 引擎=Edward 個人語音蘇菲(BeyondVoice、單人)、**沐寧商業多人要自己一套部署** ② **管家腦感知+記憶 API 大半已做好**（`/brain/morning_brief`、`/perception`、`/memory/shared`、`/brain/start_interview`）= 大省 ③ 臉走 **Ditto**(可商用)、**不照抄**引擎 SoulX/Duix/MuseTalk(Track-A/死路) ④ 台語 Breeze PoC 有起點 ⑤ ⚠️ **發現即時語音用 gpt-realtime-2=OpenAI 用量計費**、跟「全自架不付每分鐘費」初衷有一張要算清的帳。詳 `docs/串引擎計畫-castle-voice-engine.md`。

## 6/27 上午（Edward 起床後）
- 🎯 **語言決策拍板**：v1 **只做台灣中文（華語）、先克服華語**；英語+台語往後期（台語＝v2 護城河加深）。→ v1 語音腦 = gpt-realtime-2 單腦、台語「兩顆腦」架構延後。詳規格書 §6 + 串引擎 §6。
- ✅ **深度盤點即時語音模型**（霍爾）：gpt-realtime-2 仍是 2026 即時對話天花板、不換；台語**全市場無即時對話模型**（只有 TTS 朗讀層 Qwen3-TTS/Breeze Taigi）→ 印證台語得自拼 pipeline、延後合理。
- ✅ **子女裝機流程 `onboarding.html` 做出來**（5 步：歡迎→給誰用→挑樣子〔擬真 4 選／2D 4 選 兩軌〕→邀家人→交給媽媽）。補上 MVP 缺的關鍵流程；**avatar 兩軌首次進畫面**；3 張截圖驗證。出口接 `index.html`（長輩端）+ `family.html`（子女端）。
- ✅ **台語 copy 對齊**（app.js [ENGINE] 註解 + family.html 傳話 placeholder：台語→台灣中文/中性，配合 v1 決策）。
- ✅ **城堡四方體檢**（卡西法 CTO／霍爾 CPO／蘇菲 sub CFO／沙利曼 Trust）→ `docs\體檢報告-城堡四方-2026-06-27.md`。核心：殼 8 分能跑 0 分；**v1 主線=接引擎＋多租戶分艙＋3 個 P0 回路（危機/付費/推播）**、擬真 avatar 延後 v1.5（v1 用 2D 保底）；引擎是單租戶要 fork 改造；Apple IAP 抽成下 NT$299 毛利隱憂、申請小型開發者方案降 15%。**待 Edward 拍板 3 件**（NT$299 救毛利 Ⓑ用量上限／v1 臉 2D 保底／申請 SBP）。**codex 工項清單**已列（多租戶/危機/付費/推播）。
- ✅ **城堡四方體檢 第 2 輪**（女巫視覺／蕪菁頭 UX／卡西法 代碼+Capacitor上架／沙利曼 Apple審核）→ `docs\體檢報告-城堡四方-第2輪-2026-06-27.md`。核心：視覺**舒適 85/驚艷 55**、體驗**子女 8/長輩 5/付費 0**、代碼 **B+ 無重寫但距上架 0%（缺 Capacitor 殼）**、Apple **三重高敏裸送必退、8 hard blocker 有解無死路**。🎯 **四方共同第一優先＝給寧寧一張原創 2D 臉**（換掉西方 stock 照、記憶點、拆深偽雷）。長輩端三大病：太重/字太小/邊緣時刻沒設計。最硬上架閘門：隱私清單(2024強制)+醫療宣稱掃描+語音境外同意。go/no-go：Capacitor 麥克風橋接先 PoC。**新增拍板：寧寧臉方向（Ⓐ親和擬人/Ⓑ吉祥物/Ⓒ光球）**。
- ✅ **商業模式 v2 深算**（蘇菲sub成本/霍爾競品/沙利曼IAP）→ `docs\商業模式-點數制-v2-2026-06-27.md`。Edward 拍板方向：Freemium(送5分鐘)+月訂閱+點數。**CFO 諫言修正待點頭：訂閱=聊到飽、點數只扣擬真+加值**（不扣基本聊天——殺信任+語音其實便宜、真燒錢是擬真GPU）。訂價：台 349/599/999、英 US$24.99、點數包 199/499/899 不設到期。生死兩平~2600戶、Year1燒~450萬。
- 🎯 **Edward 6/27 拍板**：v1 **6 avatar 鎖定**（擬真1男1女30-35＋2D卡通1男1女＋貓＋狗）｜**Apple 健康統一一個入口**（不單獨串手錶）｜設定頁加個人資料（頭像/名稱/暱稱/年齡/所在地/週活動）｜申請 Apple 小型方案。
- **待 Edward 拍板**：點數扣法 Ⓐ逐分鐘/Ⓑ只扣擬真+加值(💡建議)｜訂價數字｜寧寧臉方向。**待建**：onboarding 改 6 avatar、設定頁個人資料、連接畫面併 Apple 健康一格、女巫 P0 視覺（寧寧的臉/會呼吸/字放大/空狀態）。

## 下一步（接手做這些）
1. ~~子女端畫面~~ ✅ **已做**（`family.html` 儀表板 + `onboarding.html` 子女裝機 5 步流程）；可再串雲端傳話 + 通知推播
2. **亞洲臉真人素材**換上（現為西方臉/示意 avatar）
3. **串真實引擎**（v1 以 **Gemini 3.1 Flash Live 方向 + 中文（台灣）優先、英文第二** 為準；台語暫不承諾；擬真 avatar 依 PoC 結果）
4. **Apple 健康/Watch 真串接** + 跌倒求救
5. **Capacitor 包 iOS**（✅ Apple 開發者帳號已辦 · 個人 Individual · 2026-06-26 付費完成、等 Apple 審開通）

## 立項決策（保留）
- 第一切入仍可由家人/照護場景帶動，但產品不是老人 App；核心是 AI 健康照護 + 家人互動 + `聊聊`。語言策略以中文（台灣）優先、英文第二；台語保留研究觀察。全自架不串第三方付費主要指 avatar 與可控後端，v1 語音腦務實使用成熟雲端模型並做好隱私揭露。
- 法規紅線：用藥＝鬧鐘不給建議、陪伴不稱諮商/治療、危機＝轉介（1925/119/家人）
- Elfie 借「行為科學的骨」丟「遊戲外觀的皮」；家庭連結是沐寧 vs Elfie 最大差異化

---
*STATUS v2 · 2026-06-26 · 取代舊構想階段版。原型 + 設計 + 架構文件齊備，交棒下一個 session。*
