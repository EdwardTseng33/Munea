# Munea 上線健康度 69→90 Scorecard

評估日期：2026-07-16（Asia/Taipei）

Repo 基準：`origin/main@58c0870`

評估範圍：送審中的 iOS App、Brain／Voice／Gateway／Avatar、API、底層程式、Supabase migrations、Repo 資料結構、產品與版本文件、AI／服務狀態，以及 staging 營運後台。

## Executive Summary

- **目前整體健康度為 69/100，六個面向都尚未達 90。** 最新 main 已把 source、lockfile 與 iOS next binary 對齊到 `1.0.26 (Build 33)`，但「可運作」仍未全面升級成「可證明、可回滾、可持續營運」。
- **最大風險仍是跨時間線的產品真相漂移。** 使用者先前確認 `1.0.25 (Build 32)` 已進 App Store 審核；最新 repo 則明確記錄 `1.0.26 (Build 33)` 已完成 Archive／IPA 與手機開發版換裝、但尚未上傳。這兩件事可以同時成立，但 App Store readiness、Current Plan、Architecture、README 與 Backlog 尚未共享同一狀態模型。
- **送審包與 next binary 必須分開管理。** 本報告保留 `1.0.25 (Build 32)` 作為已送審稽核起點；目前 main 與下一包則是 `1.0.26 (Build 33)`。Brain／Voice 若推進，只能採向下相容、canary、探測通過後再切流量的方式，且必須持續驗證 Build 32 相容性。
- **營運後台已納入正式產品面。** staging 後台頁面可達，但 live `version.js` 顯示 `1.0.12`，`admin.html`／`admin.js` 也與 `origin/main` 不同；目前只能證明「舊後台殼可開」，不能證明「最新後台已部署且所有營運資料可信」。

## 評分方法與結論

六個面向等權，各佔六分之一；總分是六項算術平均後四捨五入。90 分的共同門檻是：關鍵能力有明確 owner、版本、SLO／驗收條件、機器化 gate、部署證據、回滾路徑，且沒有已知 P0 漂移。這是工程與營運 readiness score，不是 Apple 審核通過機率。

| 面向 | 目前分數 | 是否達 90 | 核心判斷 |
|---|---:|:---:|---|
| 1. 架構健康度 | 79 | 否 | 分層與容量地基存在，但跨服務營運證據、production 邊界與失效演練不足 |
| 2. API 健康度 | 80 | 否 | 權限與端點覆蓋不弱，但缺部署版本身分、統一契約與硬性 main gate |
| 3. App 與後端底層代碼健康度 | 75 | 否 | 測試量充足，但核心檔過大、CI push 可 soft-fail、版本狀態未制度化 |
| 4. Repo 資料結構健康度 | 63 | 否 | source／lockfile 已對齊，但 migration 重號、資產混放與歷史文件失控仍影響判讀 |
| 5. 產品資料／版本／功能／設計／AI／服務對焦 | 52 | 否 | STATUS 已區分 Build 32 與 33，但其他「權威文件」及 live 服務仍未同步 |
| 6. 營運後台健康度 | 67 | 否 | 後台與管理 API 已存在，但 live 資產落後、操作員身分與資料新鮮度證據不足 |
| **等權總分** | **69** | **否** | **距 90 還有 21 分；先修真相與 gate，再擴功能** |

## 本次採用的 release truth

| 對象 | 目前可信狀態 | 判讀 |
|---|---|---|
| App Store 審核二進位（稽核起點） | 使用者先前確認 `1.0.25 (Build 32)` 已進入 App Store 審核；repo readiness 仍保留 Build 32 上傳成功／處理中紀錄 | 視為不可變更的既有二進位；精確 Apple state 仍以 App Store Connect 為準 |
| `origin/main` Web／產品來源 | `package.json`、`package-lock.json` root／package entry 與 `web/src/version.js` 均為 `1.0.26` | source 與 lockfile 已恢復一致 |
| iOS next binary | Debug／Release 均為 `MARKETING_VERSION=1.0.26`、`CURRENT_PROJECT_VERSION=33`；STATUS 記錄 Archive／IPA 與手機開發版換裝完成，但尚未上傳 | 這是 Build 32 之後的 next binary，不得被誤寫成目前 App Store 審核包 |
| Brain／Voice Cloud Run | 2026-07-16 已執行 strict readiness；Brain／Voice Ready、必要 env、Secret Manager accessor 與 admin shell 檢查通過 | 證明基礎服務可用，不等於全部 API／真人 App E2E／SLO 已達標 |
| staging 營運後台 | 使用者提供 URL 回 HTTP 200；live `version.js=1.0.12`，live `admin.html`／`admin.js` 與 main 不同 | 部署漂移，未達可追溯營運版本門檻 |
| staging Brain／Voice API | Cloud Run revision 顯示 Ready；alias 與 canonical URL 的 `/healthz`、`/version` 實測皆回 HTTP 404 | 基礎設施存活不等於應用健康；線上缺少可追溯的 release／health contract |
| 本輪健康修復分支 | release gate、API metadata、migration governance、admin hardening 均在獨立未合併工作中 | **一律不計入 main 現況分數**；合併、測試、部署後才可加分 |

## 1. 架構健康度 — 79/100

**判斷：架構不是從零開始，真正缺的是 production 化的證明鏈。**

### 現有證據

- `engine/server.py`、`engine/live_voice_server.py` 已分出 Brain 與 realtime Voice；Cloud Run strict readiness 於本日確認兩服務 Ready，且必要環境變數／secret accessor 通過。
- `deploy/gateway/gateway_core.py` 已有 worker capacity、voice capacity、排隊、heartbeat、release 與 queue advancement；`deploy/runpod-avatar/flashhead_server.py` 已有多 slot、admission lock、call token 與 unhealthy slot 回收。
- `engine/supabase_adapter.py` 與 `supabase/sql/001...018` 已建立帳號、家庭、AI memory、billing、notification、audit 等正式資料邊界；prototype JSON fallback 讓本機仍可跑。
- `scripts/cloud-run-status.ps1` 已能檢查服務 Ready、必要 env、Secret Manager 權限與 `/admin.html` shell。

### 主要問題

- production／staging／canary／App Store review binary 的拓撲沒有一份機器可讀的 release manifest；目前要跨 `STATUS.md`、App Store readiness、Cloud Run 與程式預設值人工拼圖。
- Brain 主程式與 App 主程式仍是大型單體；服務分層存在，但模組邊界與責任邊界尚未反映到程式尺寸與獨立發布能力。
- JSON fallback 對開發有價值，但尚缺 production 模式「不得悄悄落回本機資料」的全面 gate 與告警證據。
- Gateway／Voice／Avatar 的容量控制已有演算法，仍缺跨 replica／程序重啟／部分網路分割下的原子性、復原與重複指派演練紀錄。
- live App／後台仍直接指向 staging 服務語境；production domain、資料區域、流量政策與 rollback owner 尚未成為同一個可稽核契約。

### 優化方向

**P0**

1. 建立單一 release manifest：列 App review build、main source、Brain／Voice revision、DB migration head、admin asset hash、環境角色與 rollback revision。
2. 所有送審期間的 backend 變更採 backward-compatible canary；contract probe、真實 Voice probe、admin smoke 與回滾演練通過前不切 100% 流量。
3. production 模式把 JSON fallback 轉為明確故障／告警，禁止使用者資料或 entitlement 在 Supabase 失敗時靜默落本機。
4. 對 Gateway／Voice／Avatar 做重啟、重複 ready、slot 遺失、DB 暫時中斷與 queue 恢復測試，證明不會超賣容量或把同一通話指派兩次。

**P1**

1. 依 auth／family、billing、AI memory、notifications、admin 拆出明確 application service；先縮短依賴方向，不急著為拆而拆成微服務。
2. 建立架構 owner／SLO／runbook 矩陣，並將 dashboard、告警、on-call 與 rollback 連回每個服務。

### 90 分驗收條件

- release manifest 能唯一回答 App、API、DB、admin 現在各跑哪一版，CI 能驗證部署 revision 與 source commit。
- Brain／Voice／Gateway／Avatar 的 p95、錯誤率、容量、fallback 與成本均有 7 天以上可信 dashboard 與告警門檻。
- production 故障演練證明：單服務 rollback、worker 掉線、DB 暫斷、重複請求都不造成越權、重複扣點、重複指派或資料遺失。
- production 不存在無告警的 JSON fallback；所有關鍵資料路徑都有明確 authoritative store。

## 2. API 健康度 — 80/100

**判斷：API 功能與權限地基已相當完整，但缺少可部署、可比較的契約身分。**

### 現有證據

- `engine/server.py` 的 `/healthz` 列出 auth、profile、family、billing、voice、memory、guardian、notifications、admin、privacy 等 40+ contract。
- `require_verified_auth`、request-scoped identity、family invite 強制身份、admin／provider token 分流、HMAC constant-time compare、JSON body size limit 與 Apple JWS webhook 例外路徑均已存在。
- Admin endpoints 未帶 admin token 會拒絕；`scripts/admin-smoke.ps1` 會檢查 shell、無 token 403，以及有 token時的 accounts／north-star／usage／credits／privacy／safety／audit 讀取。
- Repo 有 23 支 `engine/test_*.py` 與 15 支 `scripts/test-*`，`test:launch` 已涵蓋 auth、account scope、privacy、Store、family、notification、voice 等重要路徑。

### 主要問題

- main 的 `/healthz` 只回 `service: munea-local-engine`、時間、runtime 與 contract 清單，沒有 git SHA、release version、revision、environment role 或 API contract version；無法把異常精準對到部署。
- 線上 staging 更明確暴露可觀測性落差：Brain／Voice 的 alias 與 canonical URL 對 `/healthz`、`/version` 都回 HTTP 404。Cloud Run Ready 目前只能證明容器 revision 可服務，不能證明應用 contract、模型依賴或 release identity 健康。
- 成功回應仍有多種 shape，與架構文件宣稱的統一 `{ok,data}` envelope 不完全一致；錯誤契約相對一致，成功契約尚未鎖定。
- API 沒有一份由程式生成或 CI 驗證的 OpenAPI／contract inventory；文件與 handler 容易各自演進。
- `.github/workflows/smoke.yml` 在 `push` 對 static smoke、Supabase doctor、auth gate 使用 soft-fail；main 可在關鍵檢查失敗時維持綠色表象。
- strict Cloud Run readiness 證明服務與設定存在，尚未證明每個 privileged API、真 Supabase schema、真人 App token、延遲與錯誤率達標。

### 優化方向

**P0**

1. Brain／Voice health metadata 回傳 service、source version、git SHA、revision、environment、contract version；不得包含 secret。
2. 將 release consistency、auth gate、static smoke 與 migration manifest 變成 main／PR 的硬 gate；失敗必須阻擋合併或部署。
3. 建立 critical endpoint matrix：每支 endpoint 的 auth、scope、idempotency、rate limit、PII、source of truth、error envelope 與測試 case。
4. 以凍結 `1.0.25 (32)` App 做向下相容 contract probe，確保 backend 變更不要求新 client 欄位。

**P1**

1. 由 route registry 生成 OpenAPI／contract 文件與 smoke cases，逐步收斂成功 envelope。
2. 加入 SLO 測量、request ID、結構化 log、trace correlation 與 endpoint-level error budget。

### 90 分驗收條件

- 所有 production-critical endpoints 均有 auth／scope 正反向測試，且 PR/main gate 不可 soft-fail。
- health／version metadata 能由部署 revision 追到 commit、API contract 與 App 相容範圍。
- API contract inventory 與實際 routes 在 CI 零漂移；成功／錯誤 envelope 有版本策略。
- 連續 7 天量測符合已核定 SLO，並完成至少一次 timeout、provider failure、DB failure 與 rollback 演練。

## 3. App 與後端底層代碼健康度 — 75/100

**判斷：有大量針對真問題的測試，但可維護性與 release gate 還沒有跟上功能成長速度。**

### 現有證據

- `test:launch` 已串起 Python 與 Node 驗收，涵蓋用藥照片隱私、family relays、voice memory／diagnostics、APNs、薄門、CORS、account scope、Store、privacy export、localization 與 UI contracts。
- iOS 已有 Archive、防漏、Capacitor parts check 等打包 gate；Build 31 缺原生零件的事故已轉成自動阻擋。
- 目前核心檔規模：`web/src/app.js` 約 7,263 行、`engine/server.py` 約 6,334 行、`engine/live_voice_server.py` 約 1,553 行。
- main 目前 `package.json=1.0.26`、`package-lock.json=1.0.26`、`web/src/version.js=1.0.26`、iOS Debug／Release=`1.0.26 (33)`；STATUS 也明確記錄 Build 33 尚未上傳。

### 主要問題

- `app.js` 與 `server.py` 同時承載多個 bounded context，改一個家庭、語音或營運需求容易觸發大範圍回歸與多人衝突。
- 現有測試多為契約／回歸 script；缺少可追蹤的 statement／branch coverage、flaky test 指標、耗時分層與最小 critical suite。
- push gate 可 soft-fail，代表測試存在但不能保證 main 永遠滿足它。
- source／lockfile／next iOS binary 的直接版號不一致已修正；但 repo 仍缺工具把「Build 32 審核中」與「Build 33 尚未上傳」建模成兩條合法 release lane，後續文件仍可能互相覆蓋。
- 開發 fallback、staging URL 與正式行為仍在同一批程式中，容易出現「測試可跑，但出貨指向錯環境」。

### 優化方向

**P0**

1. 合併並啟用 release consistency gate：source／lock／Web 必須一致；iOS 可因 review freeze 落後，但需由 manifest 明示，下次包版使用 strict-iOS 阻擋。
2. 把 main push 的 static／auth／Supabase gate 改為硬失敗；通知降噪不能以放過紅燈實現。
3. 固定一套 10–15 分鐘 critical CI：登入、family scope、subscription、privacy、Voice contract、migration、admin gate；較慢真人／live probe 放 deployment gate。
4. 不得把 next binary 的狀態覆寫到既有審核包；任何 backend 合併都需跑 `1.0.25 (32)` compatibility fixture，Build 33 上傳前另跑 strict release gate。

**P1**

1. 先從衝突最多的 `app.js` 與 `server.py` 抽出 auth／family／billing／notifications／admin 模組，設 import boundary 與 owner。
2. 建立 coverage baseline、complexity threshold、flaky quarantine 規則與依賴更新節奏。

### 90 分驗收條件

- main 任一 critical gate 失敗即紅；最近 30 天無因 soft-fail 漏進 main 的回歸。
- source、lock、Web、iOS review state 可被同一工具正確解釋；下次 Archive 無法在版號或原生零件不一致時產出。
- 核心 bounded contexts 有獨立模組與 owner，重大功能不再集中修改 6k–7k 行單檔。
- critical code 有可見 coverage／flaky／duration 趨勢，真人／live E2E 有固定 deployment gate。

## 4. Repo 資料結構健康度 — 63/100

**判斷：資料很多，但 authority、runtime 與歷史資產沒有被清楚分層，已增加發版判讀成本。**

### 現有證據

- Repo 共 852 個 tracked files；其中 `docs/` 168 個、`design-import/` 145 個、`ds-bundle/` 80 個。
- `package.json`、`package-lock.json` root／package entry、`web/src/version.js` 與 iOS next binary 已對齊 `1.0.26`，修掉一項可由 repo 直接判讀的版本 metadata 漂移。
- 頂層同時存在 runtime (`engine/`, `web/`, `ios/`, `deploy/`, `supabase/`)、設計匯入、原型、App Store 圖、SalesKit、voice samples 與多套文件。
- Supabase migrations 從 `001` 到 `018`，但存在兩個 `011`：`011_family_invitation_integrity.sql` 與 `011_free_signup_trial_policy.sql`。
- Repo 已有協作看板、上架狀態、架構與主題規格；問題不是沒有文件，而是沒有可靠的 authority index、有效期與機器檢查。

### 主要問題

- migration 重號讓「已套用到哪一版」無法只靠序號回答；沒有 canonical manifest／checksum／legacy exception。
- `docs/` 數量大，歷史決策與 current truth 混在同一閱讀路徑；「保留歷史」常靠段落警告，無自動失效機制。
- 設計匯入與 bundle 共 225 個 tracked files，約佔全 repo 26%；加上 prototype、SalesKit、App Store 素材，使 runtime checkout、CODEOWNERS 與搜尋結果噪音偏高。
- 頂層資料夾缺少一致的 owner、生命週期（runtime／source asset／generated／archive）與發版影響標記。
- migration governance 修復仍在獨立分支，尚未合併，不能視為 main 已解。

### 優化方向

**P0**

1. 建立 canonical migration manifest：排序、檔名、checksum、依賴、legacy duplicate `011` 的明確處理與 live applied state；CI 每次必驗。
2. 建立 `docs` authority index：每個主題只能有一份 current SSOT，其餘標 `historical`、`supersededBy`、最後驗證日與 owner。
3. 在 repo map 標示每個頂層資料夾是否進包、是否部署、是否生成、是否可封存，避免設計／銷售資產被誤認 runtime 依賴。

**P1**

1. 將大型原始設計匯入、已封存 prototype、SalesKit 與 App Store 成品移至 artifact storage 或獨立 archive repo；主 repo 只保留必要 source 與索引。
2. 補 CODEOWNERS、dependency boundaries、generated-file policy 與 docs freshness gate。

### 90 分驗收條件

- migration ID／checksum／live applied state 可一鍵對帳，無未註冊重號或人工猜順序。
- 所有主題只有一份 current SSOT；歷史文件不會被預設搜尋／入口當成現況。
- 每個頂層目錄都有 owner、生命週期與 release impact；generated／archive 資產不污染 runtime gate。
- 新 session 能在 10 分鐘內從 repo map 找到目前版本、服務、schema、設計與營運權威來源。

## 5. 產品資料／版本／功能／設計／AI／服務對焦 — 52/100

**判斷：這是目前離 90 最遠、也最容易造成錯誤決策的面向。**

### 現有證據

- `STATUS.md` 現在清楚區分兩條時間線：Build 32 已上傳、Build 33 已完成 Archive／IPA 與手機開發版換裝但未上傳；source、lockfile 與 iOS next binary 也已對齊 `1.0.26 (33)`。
- `docs/APP-STORE-PRODUCTION-READINESS.md` 開頭仍只記錄 `1.0.25 (Build 32)` 已上傳，內文多次寫 Build 30，並在「上傳決策」寫「已上傳、不可送審」；同時沒有反映使用者先前確認 Build 32 已進審核，以及 Build 33 已成為 next binary 的最新 repo 事實。
- `docs/CURRENT-DEVELOPMENT-PLAN.md` 首行仍是 Updated 2026-06-30；7/14 override 寫 App `1.0.3 (6)`，進度表仍寫 first TestFlight path 30–35%、not ready。
- `docs/BACKEND-ARCHITECTURE-v1.md` Updated 2026-06-29，前段仍寫「Admin and analytics are not built yet」，但同文件後段與程式已列出完整 Admin endpoints，staging 後台也已可達。
- `BACKLOG.md` 標記日期 2026-06-28，仍把 realtime voice、moving face、iPhone package、Health、reminders、credits、family linkage 等大量已施工項目列為未做。
- `docs/00-總綱-從這裡開始.md` 仍寫 App `1.0.2 (5)`，README 寫 iOS `1.0.3 (6)`；`docs/BILLING-CREDITS-ENTITLEMENT-v1.md` 也以 `1.0.2` 作更新基準。
- `docs/AI-SERVICE-DESIGN-v1.md` Updated 2026-07-01；其設計方向仍有價值，但未與本日 Brain／Voice revision、實際 model、persona contract、fallback 與部署狀態形成同一份 service catalog。
- staging admin live `version.js=1.0.12`，而 main 是 `1.0.26`；實際營運介面沒有顯示其 source commit／deployment revision。

### 主要問題

- STATUS 已開始正確分出「review binary」與「next binary」，但「現在版本」「Apple 狀態」「功能是否上線」「服務是否部署」仍沒有跨文件共享狀態機；uploaded、processing、TestFlight、submitted for review、approved、released 仍可能被其他 current 文件混用。
- 產品功能常以「程式存在」「PR 合併」「staging deployed」「App binary 內含」「真人驗收通過」任一狀態代表完成，造成文件彼此看似都對、合在一起卻衝突。
- 設計、AI persona、TTS、realtime voice、backend service 與 App package 沒有同一個 compatibility matrix；新規則寫進 main 不代表送審包或 live service 已吃到。
- 舊版本資訊散落在 current 文件頂部，會直接誤導接手 session、營運與發版決策。

### 優化方向

**P0**

1. 建立唯一 `release-state` SSOT，至少分開：source version、review binary、App Store state、Brain revision、Voice revision、admin revision、DB migration head、最後真人 gate 與 owner。
2. 立即對齊 App Store readiness、STATUS、Current Plan、Backend Architecture、總綱、README、Backlog；歷史內容移到明確 history 區，不再讓舊狀態出現在 current summary。
3. 建立 feature status vocabulary：`planned / coded / merged / staged / deployed / in-review-binary / production / verified`，所有功能、AI、設計與服務只能選明確狀態並附 evidence。
4. App Store 狀態由使用者／App Store Connect 回報更新；文件不可用舊 Build 的「不可送審」覆蓋已發生的送審事實。

**P1**

1. 建立 product catalog：每個功能對應 UX spec、design source、frontend flag、API、schema、AI model／persona、服務 revision、測試與 rollout state。
2. AI／Voice 建立 compatibility contract：characters JSON、Brain prompt、TTS style、realtime voice、locale、model 與 deployment revision 必須能一一對帳。
3. docs freshness CI：current SSOT 超過期限、版號落後或互相矛盾時阻擋 release，不阻擋純研究／history 文件。

### 90 分驗收條件

- 由 release state 一次回答「使用者現在拿到什麼、Apple 正在審什麼、main 下一版是什麼、後端與後台跑什麼」。
- current SSOT 零個已知版號／Build／方案／功能／服務狀態矛盾，CI 可抓到主要漂移。
- 每個 P0 功能都有 `in binary`、`backend deployed`、`DB ready`、`human verified` 的分離證據，不再用單一「完成」代替。
- AI persona、TTS、realtime voice、locale 與服務 revision 有自動 contract test 及一次真實端到端驗收。

## 6. 營運後台健康度 — 67/100

**判斷：後台已經是可見產品，不再是「未建」；但目前 live 版本、操作員身分與資料可信度不足以支撐 90 分營運。**

### 現有證據

- staging `/admin.html#overview` 回 HTTP 200；`web/admin.html` 與 `web/src/admin.js` 實作總覽、用戶、訂閱、feedback、安全、privacy、conversation summaries、audit 等營運視圖。
- `engine/server.py` 已有 `/admin/login`、accounts、north-star、usage、credits、subscription metrics、privacy、safety、audit、voice diagnostics 等管理 endpoints。
- 管理讀取以 `X-Munea-Admin-Token` 與 constant-time compare 保護；login 密碼由環境／Secret Manager 提供，且有來源失敗次數限制。
- `scripts/admin-smoke.ps1` 可檢查後台 shell、無 token 403 與 privileged reads；Cloud Run strict readiness 已確認 admin shell 與必要 admin env 存在。
- 後台 live `version.js=1.0.12`，而 main 是 `1.0.26`；live `admin.html`／`admin.js` 也與 main 不同。

### 主要問題

- HTTP 200 與 shell token 只能證明頁面可載入；目前沒有本次檢查中的 live privileged read、資料新鮮度、空資料／fallback 來源與 endpoint latency 證據。
- live 後台缺 git SHA、Cloud Run revision、部署時間、schema head 與 data freshness；營運者無法知道畫面是不是最新或資料是否落後。
- `/admin/login` 是共享 email／password 後回傳共用 admin API token，前端存於 sessionStorage；缺 per-operator identity、MFA／SSO、RBAC 與可歸責的操作員 audit identity。
- 目前是 staging Cloud Run 直達網址；看板所列 `admin.munea.net` 與第二道 access control 尚未形成已驗證 production ingress。
- 管理介面與 API 的 source drift 已發生；admin hardening 修復仍在未合併分支，不能算成 main 或 live 已解。
- 後台可同時讀 Supabase 與 JSON fallback；若沒有醒目標出來源，營運者可能把 prototype／fallback 資料誤認為正式數據。

### 優化方向

**P0**

1. 後台頁首顯示 environment、source version、git SHA、Cloud Run revision、部署時間、migration head、資料最新時間與 backend source。
2. 以 exact asset hash 部署 main 對應後台；deployment gate 驗證 `admin.html`、`admin.js`、`version.js` 與 API metadata 同一 release manifest。
3. 增加第二道存取控制（Cloud Run IAM／IAP 或公司 SSO），再用 per-operator session、MFA、RBAC 與 audit actor 取代共享長效 token 的人員登入模式。
4. 排程執行完整 admin smoke：未授權拒絕、privileged reads、資料來源、資料新鮮度、敏感欄位遮罩與 endpoint latency；結果進營運 dashboard。
5. 所有卡片明示 `Supabase / fallback / unavailable`，production 發現 JSON fallback 直接紅燈，不顯示成正常數字。

**P1**

1. 建立 safety、privacy、subscription、voice incident 的處理 SLA、owner、acknowledgement 與 closed-loop audit。
2. 增加 cohort／conversion 定義版本、內部帳號排除、成本對帳與指標 freshness monitoring。

### 90 分驗收條件

- `admin.munea.net` 或正式 ingress 有第二道 identity control；每個操作員具唯一身分、MFA、最小 RBAC 與可追溯 audit。
- 後台 asset、API、DB schema 與 release manifest 完全一致；頁面可直接辨識版本與資料新鮮度。
- privileged admin smoke、敏感欄位遮罩、權限負向測試與資料來源檢查連續 7 天通過。
- Safety／privacy／billing／voice 事件具有 SLA、owner、處理狀態與閉環證據，且營運數字排除 internal／QA／demo 流量。

## 從 69 推到 90 的執行順序

### P0-A：先建立真相與阻擋線，不動送審包

1. 登記 App review binary `1.0.25 (32)` 與 next binary `1.0.26 (33)` 為兩條獨立 lane；禁止互相覆寫狀態。
2. 合併 release consistency／hard CI gate；目前 source／lock／iOS next binary 已對齊，後續由 strict gate 防止再次漂移。
3. 合併 API health metadata 與 backward-compatibility probes。
4. 合併 migration manifest／checksum gate，並對帳 live schema head。
5. 更新所有 current SSOT，讓 App Store、功能、設計、AI、服務與 admin 使用同一狀態詞彙。

### P0-B：canary 驗證 live，不直接切正式

1. Brain／Voice 先建 canary revision；跑 contract、真人 Voice、auth、family、billing、privacy、admin smoke。
2. 後台以 exact commit 部署並顯示版本／revision／資料來源；live asset hash 必須與 manifest 相同。
3. 對 Gateway／Voice／Avatar／Supabase 做故障與 rollback 演練，保存證據。
4. 所有結果通過後才逐步切流量；任一 compatibility 或資料來源紅燈立即 rollback。

### P1：降低下一次回歸的結構性成本

1. 拆解 `app.js`／`server.py` 高衝突 bounded contexts，建立 owner 與 module boundary。
2. 清理 repo authority 與 archive，移出不需常駐 runtime repo 的大型設計／銷售／原型資產。
3. 建立 SLO、coverage、flaky、成本、資料新鮮度與營運事件閉環 dashboard。

## 本輪分工與計分邊界

- `codex/health90-control-20260716`：release consistency、CI hard gate、送審凍結版與 next source 的版本判讀。
- `codex/health90-api-observability-20260716`：Brain／Voice service metadata 與 health contract。
- `codex/health90-schema-governance-20260716`：migration manifest、checksum 與 duplicate `011` governance。
- 獨立 admin hardening 工作：營運後台的部署版本、權限與 smoke 強化。
- 本文件只記錄 `origin/main@58c0870` 與本日 live 驗證。main 的 Build 33／lockfile 改善已計入，但上述獨立健康修復工作在 **merge + CI + canary／live 驗證** 前不能預支成 90；目前總分為 69。

## 仍需外部確認的問題

1. App Store Connect 的精確狀態是 `Waiting for Review`、`In Review` 或其他狀態，以及先前已送審項目實際選用的 Build 是否確為 32；Build 33 依最新 repo 證據尚未上傳。
2. staging 後台目前 privileged reads 是否全部來自正確 Supabase project，而非 JSON fallback；各指標最後資料時間為何。
3. 送審包實際使用的 Brain／Voice／Gateway URL 與 revision；`main` 的後端變更是否對該包完全向下相容。
4. production ingress、資料區域、on-call owner、SLO 與 rollback 權限由誰最終負責。

## 限制與假設

- 本報告將使用者提供的「已送 App Store 審核」視為最新外部事實；repo 文件仍落後，因此精確 Apple state 列為待確認，而不是自行推定。
- Cloud Run strict readiness 與 staging admin HTTP 200 是本日點檢結果；它們證明可達與設定存在，不替代長期 SLO、真人 App E2E、完整 privileged admin smoke 或 Apple 審核結果。
- 分數採 readiness rubric，不是從 production telemetry 計算；當 7–30 天 SLO、error budget、資料新鮮度與 incident data 建立後，應改用量化證據重評。
