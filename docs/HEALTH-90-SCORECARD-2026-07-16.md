# Munea 上線健康度 77→90 Scorecard

評估日期：2026-07-16（Asia/Taipei）

Repo 基準：`origin/main@88ddc10`

評估範圍：送審中的 iOS App、Brain／Voice／Gateway／Avatar、API、底層程式、Supabase migrations、Repo 資料結構、產品與版本文件、AI／服務狀態，以及 staging 營運後台。

## Executive Summary

- **目前整體健康度為 77/100，六個面向都尚未達 90。** 最新 main 已對齊 `1.0.31 (Build 38)`，並合併 #139 Voice authenticated-chain probe 與 #140 Tokyo `017` live doctor gate；兩項都提升了阻擋能力，但尚未部署 Gateway、執行 live Voice wrapper 或套用 DB migration，因此不把 controls 當成 runtime ready。分數仍受 production release identity 缺失、Tokyo schema 漂移、Voice 真媒體鏈未驗證，以及後台指標完整性／新鮮度未證明所限制。
- **目前可驗證的 runtime 身分仍落後 main。** Brain `00058-jid` 0% canary 的 `/version` 為 `1.0.28@741fec7`；Brain staging 100% 與 production Brain／Voice 的 `/version` 都回 404。Voice staging 100% revision `00047-reb` 可回報 `1.0.28@1468f10`，但仍落後 `main@88ddc10`，且 #139 的真 Gateway lease／Call Token／Gemini media wrapper 尚未在線執行。
- **最大 P0 已從「未知」變成「已知漂移」。** Repo／local migration head 為 `018`，Tokyo observable head 為 `016`；`017` 尚未在 Tokyo 出現、`018` 尚未完成清理，且工作環境的 `engine/.env.local` 仍指 Sydney。任何依賴 017／018 的功能都不能標 DB ready。
- **營運後台的瀏覽器防護已在 `741fec7` exact-revision 0% canary 驗收，但尚未進 100% 流量。** CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy、九個無 token API 403 與 privileged reads 均通過；特權資料回傳 accounts=1、audit=2，其餘 events／privacy／feedback／safety 為 0。零值仍不能證明埋點完整，且 per-operator identity／MFA／RBAC 尚未完成。

## 評分方法與結論

六個面向等權，各佔六分之一；總分是六項算術平均後四捨五入。90 分的共同門檻是：關鍵能力有明確 owner、版本、SLO／驗收條件、機器化 gate、部署證據、回滾路徑，且沒有已知 P0 漂移。這是工程與營運 readiness score，不是 Apple 審核通過機率。

| 面向 | 目前分數 | 是否達 90 | 核心判斷 |
|---|---:|:---:|---|
| 1. 架構健康度 | 84 | 否 | production lane、八服務 watchdog 與 authenticated Voice probe 已建立，但 production identity 與 Voice／Gateway 真鏈路仍未在線驗證 |
| 2. API 健康度 | 87 | 否 | auth-boundary／cleanup probes、Brain canary 與 rate limit 已進 main；live Voice probe 未跑，production `/version` 仍為 404 |
| 3. App 與後端底層代碼健康度 | 84 | 否 | release consistency、hard CI、Voice security gates 與 admin header contract 已進 main；核心檔、coverage 與真人 Gate 仍不足 |
| 4. Repo 資料結構健康度 | 64 | 否 | migration manifest 與 #140 live doctor gate 已存在，但 Tokyo 只到 016、017／018 未完成，工作環境仍殘留 Sydney 指向 |
| 5. 產品資料／版本／功能／設計／AI／服務對焦 | 60 | 否 | main／Build 38 已對齊，但 Brain 741fec7、Voice 1468f10、production identity、review binary 與 DB head 尚未同版 |
| 6. 營運後台健康度 | 83 | 否 | `741fec7` 0% canary 的頁面、403、privileged reads 與四項安全 headers 通過；資料可信度及操作員身分仍不足 |
| **等權總分** | **77** | **否** | **距 90 還有 13 分；production、Voice、Tokyo DB、admin identity 與資料可信度仍是主要阻塞** |

### 本輪分數調整理由（相對前一版 75 分）

- 架構 `83→84`：#130 將 watchdog 從六個目標擴為八個，GitHub Actions `workflow_dispatch` 在 main@741fec7 完整 PASS；cron 首次準點觸發與失敗路徑 Slack 投遞仍未演練，production 與 Voice 真鏈路亦未完成。
- API `84→87`：Brain root 與 invalid Apple JWS probe 通過，Brain／Voice runtime 分別可追到 `741fec7`／`1468f10`，#115 為 12 條 AI 燒錢入口加入 429 限流，#139 又將 Voice／Gateway security contracts 接入 hard gate；但真 Gateway lease／Call Token／Gemini media 仍未在線驗證。
- App／後端代碼 `83→84`：#133 增加 admin response header contract、live smoke hard gate並通過完整 `test:launch`；大型單檔、coverage 與真人 Voice Gate 未解。
- Repo `70→64`：本輪取得 live 證據後確認 Tokyo observable head 僅 `016`，repo/local 已到 `018`，且 Sydney 環境指向殘留；這是已確認的資料平面漂移，必須扣分。
- 產品對焦 `59→60`：main 與 next binary 已對齊為 `1.0.31 (Build 38)`；但 Brain canary `1.0.28@741fec7`、Voice staging `1.0.28@1468f10`、無 release metadata 的 production、App Store review binary 與 Tokyo `016` 仍是不同時間線。
- 營運後台 `75→83`：#133 已合併，`741fec7` exact-revision 0% canary 的四項 response security headers、dynamic console、九個 unauth 403 與 Secret Manager token privileged reads 均通過；尚未 promote，且 per-operator identity／MFA／RBAC、資料新鮮度與埋點完整度仍未證明。

## 本次採用的 release truth

| 對象 | 目前可信狀態 | 判讀 |
|---|---|---|
| App Store 審核二進位（稽核起點） | 使用者先前確認 `1.0.25 (Build 32)` 已進入 App Store 審核；repo readiness 仍保留 Build 32 上傳成功／處理中紀錄 | 視為不可變更的既有二進位；精確 Apple state 仍以 App Store Connect 為準 |
| `origin/main` Web／產品來源 | `package.json`、lockfile、`web/src/version.js` 與 iOS Debug／Release 均為 `1.0.31 (Build 38)` | source 與 next binary 已一致；Build 38 已包版／手機換裝，但 repo 證據明確標示未上傳、未取代既有審核包 |
| main CI／release gate | #120 release consistency、#123 deployment identity、#115 rate limit、#130 八服務 watchdog、#133 admin headers、#139 Voice probe 與 #140 migration doctor 均已合併；目前 main `88ddc10` | 已計入程式與發版治理分；#139／#140 尚未改變 runtime、流量或 DB |
| staging Brain 0% canary | revision `00058-jid`；`/version` 回 `1.0.28`、commit `741fec79c67a...`、env `staging`；root、invalid Apple JWS、admin headers 與 privileged smoke PASS | exact revision 身分與後台 Phase A 有 live 證據；目前已落後 main，且仍未承接使用者流量 |
| staging Voice 100% | revision `00047-reb`；`/version` 回 `1.0.28`／`1468f109dee9...`／staging | 可追溯但落後 main；#135 與 #139 的 merged code 尚未由此身分證明已部署，真 Gateway／Call Token／Gemini media wrapper 未跑 |
| production Brain／Voice | 兩個正式 `/version` 目前均回 404；Cloud Run latest-ready 為 Brain `00001-jtk`、Voice `00001-zmw` | 無法由公開 runtime metadata 證明版本／commit；不得再把舊部署紀錄 `1.0.26` 寫成當前 `/version` 事實 |
| staging 營運後台 | `741fec7` exact-revision 0% canary 的 shell、dynamic console、九個 unauth 403 與 privileged reads PASS；accounts=1、audit=2，其餘觀察值為 0 | 證明權限門與讀取路徑可用；零值不證明事件／privacy／feedback／safety 埋點完整 |
| admin HTTP headers | 0% canary 上 CSP、X-Frame-Options=DENY、X-Content-Type-Options=nosniff、Referrer-Policy=no-referrer 全 PASS | Phase A 已完成；100% traffic 尚未包含此 revision，Phase B identity／MFA／RBAC 未完成 |
| Supabase schema | repo／local head=`018`；Tokyo observable head=`016`；`017` 不存在、`018` 尚未清理；工作環境 `engine/.env.local` 仍指 Sydney | manifest 不能替代 live applied state；Tokyo migration 與環境清理為 P0 |
| #139／#140 | #139 的 account cleanup binding、user health redaction、lease／queue cleanup 與兩支 security tests 已由 `smoke:no-api`／release check／GitHub CI 驗證；#140 只在 doctor 中辨識 Tokyo 缺 `017` | 兩者均已 merged、未部署／未跑 live wrapper／未套 SQL；控制面進步不等於資料面或 Voice runtime 已完成 |
| #115／#130／#133 | AI rate limit、八服務 watchdog 與 admin headers 已合併至 main；Brain 0% canary 已包含 exact main；watchdog workflow_dispatch run 29505204065 PASS | 已計入程式與治理分；尚未 promotion，cron 準點觸發與失敗路徑 Slack 投遞仍待演練 |

## 1. 架構健康度 — 84/100

**判斷：架構不是從零開始，真正缺的是 production 化的證明鏈。**

### 現有證據

- `engine/server.py`、`engine/live_voice_server.py` 已分出 Brain 與 realtime Voice；Cloud Run strict readiness 於本日確認兩服務 Ready，且必要環境變數／secret accessor 通過。
- `deploy/gateway/gateway_core.py` 已有 worker capacity、voice capacity、排隊、heartbeat、release 與 queue advancement；`deploy/runpod-avatar/flashhead_server.py` 已有多 slot、admission lock、call token 與 unhealthy slot 回收。
- `engine/supabase_adapter.py` 與 `supabase/sql/001...018` 已建立帳號、家庭、AI memory、billing、notification、audit 等正式資料邊界；prototype JSON fallback 讓本機仍可跑。
- `scripts/cloud-run-status.ps1` 已能檢查服務 Ready、必要 env、Secret Manager 權限與 `/admin.html` shell。
- #112 已將 Brain／Voice release metadata、`/healthz`／`/version` 與部署版號／commit stamping 合併進 main，讓下一個 canary revision 具備可追溯的服務身分。
- #118 建立獨立 production Brain／Voice lane與 App 正式預設；#123 讓 production revision identity 成為 release gate。Brain 0% canary 與 Voice staging 100% 已能分別回報 `1.0.28@741fec7`、`1.0.28@1468f10`。
- #130 watchdog 已擴為巡檢八個現役服務，手動 workflow run 已 PASS；cron 準點觸發與真實故障告警仍需 production evidence。

### 主要問題

- production／staging／canary／App Store review binary 的拓撲仍沒有一份跨 App、API、DB、admin 的機器可讀 release manifest；#112 只補齊服務 metadata，整體仍要跨 `STATUS.md`、App Store readiness、Cloud Run 與程式預設值人工拼圖。
- Brain 主程式與 App 主程式仍是大型單體；服務分層存在，但模組邊界與責任邊界尚未反映到程式尺寸與獨立發布能力。
- JSON fallback 對開發有價值，但尚缺 production 模式「不得悄悄落回本機資料」的全面 gate 與告警證據。
- Gateway／Voice／Avatar 的容量控制已有演算法，仍缺跨 replica／程序重啟／部分網路分割下的原子性、復原與重複指派演練紀錄。
- App 正式預設已改指 production，但 production Brain／Voice `/version` 仍為 404，無法證明其 release identity；「程式指向正式」與「正式已更新」仍是兩件事。
- #139 已在 repo 建立 authenticated Voice wrapper、失敗清理與安全邊界 gate，但尚未部署 Gateway 或執行 live wrapper；架構圖中的完整通話鏈仍無本輪 runtime 證據。
- Tokyo DB observable head 僅 `016`，而 repo／local 到 `018`；工作環境仍殘留 Sydney 指向，production 資料邊界尚未真正封口。

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
- production Brain／Voice revision 必須回報與 release manifest 相同 commit，並完成含 Gateway lease、Call Token、Gemini media 的真 Voice Gate。

## 2. API 健康度 — 87/100

**判斷：API 功能、權限與 release metadata 已在 main 形成良好地基，但尚未部署成可在線比較的契約身分。**

### 現有證據

- `engine/server.py` 的 `/healthz` 列出 auth、profile、family、billing、voice、memory、guardian、notifications、admin、privacy 等 40+ contract。
- `require_verified_auth`、request-scoped identity、family invite 強制身份、admin／provider token 分流、HMAC constant-time compare、JSON body size limit 與 Apple JWS webhook 例外路徑均已存在。
- Admin endpoints 未帶 admin token 會拒絕；`scripts/admin-smoke.ps1` 會檢查 shell、無 token 403，以及有 token時的 accounts／north-star／usage／credits／privacy／safety／audit 讀取。
- Repo 有 23 支 `engine/test_*.py` 與 15 支 `scripts/test-*`，`test:launch` 已涵蓋 auth、account scope、privacy、Store、family、notification、voice 等重要路徑。
- #112 已在 main 為 Brain／Voice 加入安全的 release metadata，以及 HTTP `/healthz`／`/version`；部署腳本也會注入 source version 與 commit，且有 metadata／部署設定契約測試。
- Brain 0% canary `00058-jid` 可精確對到 `1.0.28@741fec7`，root、invalid Apple JWS 與 admin smoke PASS；目前已落後 main。Voice staging 100% `00047-reb` 可回報 `1.0.28@1468f10`，仍落後 main。
- #120 已將 release consistency 與 main smoke 轉成 hard gate，且本輪 main CI success；先前「push 可 soft-fail」缺口已在 main 修正。
- #115 已為 12 條 AI 成本入口加入每分鐘限流與 429 契約，並把對應測試納入 launch chain。
- #139 已將 Voice probe cleanup／credential boundary 與 Gateway HTTP auth surface 兩支安全契約接入 `smoke:no-api`；本機完整 `release:check` 與 GitHub Windows smoke／auth gate 均 PASS。

### 主要問題

- staging canary 已證明 metadata 可部署，但 production Brain／Voice `/version` 仍為 404，尚未證明 production revision 與 main／Build 38 同版。
- authenticated Voice wrapper 已合併但沒有在線執行；目前仍不能用 repo gate 或容器可啟動替代真 Gateway lease、Call Token 與 Gemini media 證據。
- 成功回應仍有多種 shape，與架構文件宣稱的統一 `{ok,data}` envelope 不完全一致；錯誤契約相對一致，成功契約尚未鎖定。
- API 沒有一份由程式生成或 CI 驗證的 OpenAPI／contract inventory；文件與 handler 容易各自演進。
- strict Cloud Run readiness 證明服務與設定存在，尚未證明每個 privileged API、真 Supabase schema、真人 App token、延遲與錯誤率達標。
- rate limit 與 watchdog 已進 main；watchdog 手動 workflow run 已 PASS，但 Brain／Voice runtime 身分仍落後 main，尚未證明 rate limit 已在服務端生效，cron 準點觸發與故障通知也未演練。

### 優化方向

**P0**

1. staging 0% canary identity 已通過；下一步補齊 Voice access token 與真 Gateway／Call Token／Gemini media probe，再將同一 exact commit 部署 production 並驗證 `/healthz`／`/version`。
2. 保持 release consistency、auth、static smoke 與 migration governance 為 required hard gate；將 live deployment probes 納入 promotion gate。
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

## 3. App 與後端底層代碼健康度 — 84/100

**判斷：有大量針對真問題的測試，但可維護性與 release gate 還沒有跟上功能成長速度。**

### 現有證據

- `test:launch` 已串起 Python 與 Node 驗收，涵蓋用藥照片隱私、family relays、voice memory／diagnostics、APNs、薄門、CORS、account scope、Store、privacy export、localization 與 UI contracts。
- iOS 已有 Archive、防漏、Capacitor parts check 等打包 gate；Build 31 缺原生零件的事故已轉成自動阻擋。
- 目前核心檔規模：`web/src/app.js` 約 7,263 行、`engine/server.py` 約 6,334 行、`engine/live_voice_server.py` 約 1,553 行。
- main 的 `package.json`、lockfile、`web/src/version.js`、iOS Debug／Release 均為 `1.0.31 (38)`；Build 38 已完成正式 Archive 與手機換裝，repo 明確記錄未上傳、未取代既有審核包。
- #112／#113／#114 已把 service metadata、migration integrity 與 admin console 的正負向契約測試帶進 main，增加 release／schema／營運介面的回歸保護。
- #120 的 release consistency、static smoke、Supabase doctor 與 auth gate 已成為 main 硬性檢查；本輪 main CI success。
- #115／#119 已在 rebase 後保留 release consistency、rate-limit、watchdog 三組測試意圖並合併。

### 主要問題

- `app.js` 與 `server.py` 同時承載多個 bounded context，改一個家庭、語音或營運需求容易觸發大範圍回歸與多人衝突。
- 現有測試多為契約／回歸 script；缺少可追蹤的 statement／branch coverage、flaky test 指標、耗時分層與最小 critical suite。
- hard gate 已進 main，但尚無 30 天穩定度、flaky／coverage／duration 趨勢，不能只用單次 main CI success 推定長期健康。
- release consistency 已能阻擋直接版號漂移；但 review binary 與 Build 38 next binary 仍需 release-state 明確建模，避免文件互相覆蓋。
- 開發 fallback、staging URL 與正式行為仍在同一批程式中，容易出現「測試可跑，但出貨指向錯環境」。
- Voice deployment probe 未覆蓋真媒體鏈；Tokyo schema 落後與 Sydney env 殘留也代表程式 gate 尚未完整約束 runtime 資料環境。

### 優化方向

**P0**

1. release consistency 與 hard CI 已合併；下一步把 review binary、next binary、production revision、Tokyo migration head 納入同一 release-state gate。
2. 將 production deployment identity、Voice 真媒體鏈與 Tokyo live schema probe 加入 promotion gate，避免「main 綠、runtime 漂移」。
3. 固定一套 10–15 分鐘 critical CI：登入、family scope、subscription、privacy、Voice contract、migration、admin gate；較慢真人／live probe 放 deployment gate。
4. 不得把 next binary 的狀態覆寫到既有審核包；任何 backend 合併都需跑 `1.0.25 (32)` compatibility fixture，Build 38 若未來要上傳須另跑 strict release gate。

**P1**

1. 先從衝突最多的 `app.js` 與 `server.py` 抽出 auth／family／billing／notifications／admin 模組，設 import boundary 與 owner。
2. 建立 coverage baseline、complexity threshold、flaky quarantine 規則與依賴更新節奏。

### 90 分驗收條件

- main 任一 critical gate 失敗即紅；最近 30 天無因 soft-fail 漏進 main 的回歸。
- source、lock、Web、iOS review state 可被同一工具正確解釋；下次 Archive 無法在版號或原生零件不一致時產出。
- 核心 bounded contexts 有獨立模組與 owner，重大功能不再集中修改 6k–7k 行單檔。
- critical code 有可見 coverage／flaky／duration 趨勢，真人／live E2E 有固定 deployment gate。

## 4. Repo 資料結構健康度 — 64/100

**判斷：資料很多，但 authority、runtime 與歷史資產沒有被清楚分層，已增加發版判讀成本。**

### 現有證據

- Repo 共 852 個 tracked files；其中 `docs/` 168 個、`design-import/` 145 個、`ds-bundle/` 80 個。
- `package.json`、lockfile、`web/src/version.js` 與 iOS next binary 已對齊 `1.0.31 (38)`，release consistency gate 可阻擋直接 metadata 漂移。
- 頂層同時存在 runtime (`engine/`, `web/`, `ios/`, `deploy/`, `supabase/`)、設計匯入、原型、App Store 圖、SalesKit、voice samples 與多套文件。
- Supabase migrations 從 `001` 到 `018`，但存在兩個 `011`：`011_family_invitation_integrity.sql` 與 `011_free_signup_trial_policy.sql`。
- #113 已在 main 建立 `supabase/migration-manifest.json`，涵蓋 19 個 SQL 的 LF-normalized SHA256、migration 類型與兩個歷史 `011` 的有序 allowlist；checker、7 個治理測試與 path-filtered CI 會阻擋未登記漂移。
- #140 已把 `notification_settings` 的 live table probe 接入 doctor 與 `smoke:no-api`，且嚴格區分 401／403 與 `404 + PGRST205`；它能阻擋誤判與提供安全建議，但沒有套用任何 SQL。
- 本輪完成 live applied-state 觀察：repo／local head 為 `018`，Tokyo observable head 僅 `016`；`017_notification_settings.sql` 在 Tokyo 不存在，`018_strip_medication_photos.sql` 尚未完成清理。
- Repo 已有協作看板、上架狀態、架構與主題規格；問題不是沒有文件，而是沒有可靠的 authority index、有效期與機器檢查。

### 主要問題

- migration 重號已由 canonical manifest／checksum／legacy allowlist 治理，但 live Tokyo 明確落後兩步；這不再是「尚未查明」，而是已確認的 schema drift。
- `engine/.env.local` 仍指 Sydney，顯示工作環境與 Tokyo production target 尚未完成清理；錯誤環境變數可能讓驗證對到錯的資料平面。
- `docs/` 數量大，歷史決策與 current truth 混在同一閱讀路徑；「保留歷史」常靠段落警告，無自動失效機制。
- 設計匯入與 bundle 共 225 個 tracked files，約佔全 repo 26%；加上 prototype、SalesKit、App Store 素材，使 runtime checkout、CODEOWNERS 與搜尋結果噪音偏高。
- 頂層資料夾缺少一致的 owner、生命週期（runtime／source asset／generated／archive）與發版影響標記。

### 優化方向

**P0**

1. 依 issue #126 先在 Tokyo 安全套用／驗證 017，再完成 018 清理與資料保留檢查；不得跳號或只改 observable head。
2. 將 live applied-state 對帳加入 deployment gate：精確比對 Tokyo migration head、檔名與 checksum，任何缺漏即阻擋 promotion。
3. 清除 Sydney `engine/.env.local` 指向，建立環境 allowlist／doctor，確保測試、部署與營運後台均連到明示 project。
4. 建立 `docs` authority index：每個主題只能有一份 current SSOT，其餘標 `historical`、`supersededBy`、最後驗證日與 owner。
5. 在 repo map 標示每個頂層資料夾是否進包、是否部署、是否生成、是否可封存，避免設計／銷售資產被誤認 runtime 依賴。

**P1**

1. 將大型原始設計匯入、已封存 prototype、SalesKit 與 App Store 成品移至 artifact storage 或獨立 archive repo；主 repo 只保留必要 source 與索引。
2. 補 CODEOWNERS、dependency boundaries、generated-file policy 與 docs freshness gate。

### 90 分驗收條件

- Tokyo 必須完成 017／018，migration ID／checksum／live applied state 可一鍵對帳，且 CI／deployment gate 能阻擋任何回退或漏套。
- repo、CI、Cloud Run 與 admin 所有 Supabase project ref 均可由 allowlist 解釋；不得殘留無 owner 的 Sydney 指向。
- 所有主題只有一份 current SSOT；歷史文件不會被預設搜尋／入口當成現況。
- 每個頂層目錄都有 owner、生命週期與 release impact；generated／archive 資產不污染 runtime gate。
- 新 session 能在 10 分鐘內從 repo map 找到目前版本、服務、schema、設計與營運權威來源。

## 5. 產品資料／版本／功能／設計／AI／服務對焦 — 60/100

**判斷：這是目前離 90 最遠、也最容易造成錯誤決策的面向。**

### 現有證據

- `STATUS.md` 現在清楚區分兩條時間線：Build 32 有上傳／處理紀錄，使用者另確認已有一版送審；Build 38 已完成 Archive 與手機換裝但明確未上傳。source、lockfile、Web 與 iOS next binary 對齊 `1.0.31 (38)`。
- `docs/APP-STORE-PRODUCTION-READINESS.md` 仍以先前不上傳決策為主，STATUS 已前進到 Build 38；App Store Connect 的精確 review state 與實際選用 Build 仍須以外部事實確認，不能用 repo 的 next binary 狀態覆寫 Apple 上既有審核包。
- `docs/CURRENT-DEVELOPMENT-PLAN.md` 首行仍是 Updated 2026-06-30；7/14 override 寫 App `1.0.3 (6)`，進度表仍寫 first TestFlight path 30–35%、not ready。
- `docs/BACKEND-ARCHITECTURE-v1.md` Updated 2026-06-29，前段仍寫「Admin and analytics are not built yet」，但同文件後段與程式已列出完整 Admin endpoints，staging 後台也已可達。
- `BACKLOG.md` 標記日期 2026-06-28，仍把 realtime voice、moving face、iPhone package、Health、reminders、credits、family linkage 等大量已施工項目列為未做。
- `docs/00-總綱-從這裡開始.md` 仍寫 App `1.0.2 (5)`，README 寫 iOS `1.0.3 (6)`；`docs/BILLING-CREDITS-ENTITLEMENT-v1.md` 也以 `1.0.2` 作更新基準。
- `docs/AI-SERVICE-DESIGN-v1.md` Updated 2026-07-01；其設計方向仍有價值，但未與本日 Brain／Voice revision、實際 model、persona contract、fallback 與部署狀態形成同一份 service catalog。
- main／next binary 已是 `1.0.31@88ddc10`／Build 38，Brain 0% canary 是 `1.0.28@741fec7`，Voice staging 100% 是 `1.0.28@1468f10`，production `/version` 無 release metadata；Tokyo schema又停在 `016`。App、main、Brain、Voice、production、DB 六個 release component 尚未同版。

### 主要問題

- STATUS 已開始正確分出「review binary」與「next binary」，但「現在版本」「Apple 狀態」「功能是否上線」「服務是否部署」仍沒有跨文件共享狀態機；uploaded、processing、TestFlight、submitted for review、approved、released 仍可能被其他 current 文件混用。
- 產品功能常以「程式存在」「PR 合併」「staging deployed」「App binary 內含」「真人驗收通過」任一狀態代表完成，造成文件彼此看似都對、合在一起卻衝突。
- 設計、AI persona、TTS、realtime voice、backend service 與 App package 沒有同一個 compatibility matrix；新規則寫進 main 不代表送審包或 live service 已吃到。
- 舊版本資訊散落在 current 文件頂部，會直接誤導接手 session、營運與發版決策。
- #115 rate limit 與 #119 watchdog 已由 `coded` 進到 `merged`，但尚未 `staged/deployed/verified`；文件若只寫「完成」仍會混淆狀態。

### 優化方向

**P0**

1. 建立唯一 `release-state` SSOT，至少分開：source version、review binary、App Store state、Brain revision、Voice revision、admin revision、DB migration head、最後真人 gate 與 owner。
2. 立即對齊 App Store readiness、STATUS、Current Plan、Backend Architecture、總綱、README、Backlog；歷史內容移到明確 history 區，不再讓舊狀態出現在 current summary。
3. 建立 feature status vocabulary：`planned / coded / merged / staged / deployed / in-review-binary / production / verified`，所有功能、AI、設計與服務只能選明確狀態並附 evidence。
4. App Store 狀態由使用者／App Store Connect 回報更新；文件不可用舊 Build 的「不可送審」覆蓋已發生的送審事實。
5. release-state 明列 `main=1.0.31@88ddc10`、`next binary=Build 38`、`production API identity=unknown (/version 404)`、`Brain canary=1.0.28@741fec7`、`Voice staging=1.0.28@1468f10`、`Tokyo DB=016`，直到各 gate 完成才逐項升級狀態。

**P1**

1. 建立 product catalog：每個功能對應 UX spec、design source、frontend flag、API、schema、AI model／persona、服務 revision、測試與 rollout state。
2. AI／Voice 建立 compatibility contract：characters JSON、Brain prompt、TTS style、realtime voice、locale、model 與 deployment revision 必須能一一對帳。
3. docs freshness CI：current SSOT 超過期限、版號落後或互相矛盾時阻擋 release，不阻擋純研究／history 文件。

### 90 分驗收條件

- 由 release state 一次回答「使用者現在拿到什麼、Apple 正在審什麼、main 下一版是什麼、後端與後台跑什麼」。
- current SSOT 零個已知版號／Build／方案／功能／服務狀態矛盾，CI 可抓到主要漂移。
- 每個 P0 功能都有 `in binary`、`backend deployed`、`DB ready`、`human verified` 的分離證據，不再用單一「完成」代替。
- AI persona、TTS、realtime voice、locale 與服務 revision 有自動 contract test 及一次真實端到端驗收。

## 6. 營運後台健康度 — 83/100

**判斷：後台已經是可見產品，不再是「未建」；但目前 live 版本、操作員身分與資料可信度不足以支撐 90 分營運。**

### 現有證據

- staging `/admin.html#overview` 回 HTTP 200；`web/admin.html` 與 `web/src/admin.js` 實作總覽、用戶、訂閱、feedback、安全、privacy、conversation summaries、audit 等營運視圖。
- `engine/server.py` 已有 `/admin/login`、accounts、north-star、usage、credits、subscription metrics、privacy、safety、audit、voice diagnostics 等管理 endpoints。
- 管理讀取以 `X-Munea-Admin-Token` 與 constant-time compare 保護；login 密碼由環境／Secret Manager 提供，且有來源失敗次數限制。
- `scripts/admin-smoke.ps1` 可檢查後台 shell、無 token 403 與 privileged reads；Cloud Run strict readiness 已確認 admin shell 與必要 admin env 存在。
- #114 已在 main 修正 refresh 後 token 遺失，加入同源／localhost／明示 HTTPS host guard、timeout、retry、partial failure、logout、可及性與 9 endpoint smoke 契約；這些是已合併程式能力，尚不是 live 驗證結果。
- 本輪以 Secret Manager token（未落檔／未輸出）對 Brain canary 跑完整 `scripts/admin-smoke.ps1`：shell、dynamic console、九個無 token API 403 與 privileged reads 全部 PASS。
- privileged reads 回傳 accounts=1、events=0、privacy=0、feedback=0、safety=0、audit=2；證明查詢路徑可用，但零值不等於對應產品事件已完整埋點。

### 主要問題

- Phase A 安全標頭已在 0% canary 通過，但 100% traffic revision 尚未包含；仍需在不影響正式流量的前提下完成 promotion 決策與回歸。
- live 後台缺 git SHA、Cloud Run revision、部署時間、schema head 與 data freshness；營運者無法知道畫面是不是最新或資料是否落後。
- `/admin/login` 是共享 email／password 後回傳共用 admin API token，前端存於 sessionStorage；缺 per-operator identity、MFA／SSO、RBAC 與可歸責的操作員 audit identity。
- 目前是 staging Cloud Run 直達網址；看板所列 `admin.munea.net` 與第二道 access control 尚未形成已驗證 production ingress。
- privileged reads 雖 PASS，但零值項目尚無 ingestion freshness／expected volume／last event timestamp，不能判定是「真的沒有事件」或「埋點未接」。
- 後台可同時讀 Supabase 與 JSON fallback；若沒有醒目標出來源，營運者可能把 prototype／fallback 資料誤認為正式數據。

### 優化方向

**P0**

1. ✅ issue #127 Phase A：CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy、自動 header contract 與 0% canary deployment smoke 已完成；保持 issue 開啟追蹤 Phase B。
2. 後台頁首顯示 environment、source version、git SHA、Cloud Run revision、部署時間、migration head、資料最新時間與 backend source。
3. 以 exact asset hash 部署 main 對應後台；deployment gate 驗證 `admin.html`、`admin.js`、`version.js` 與 API metadata 同一 release manifest。
4. 依 issue #127 增加第二道存取控制（Cloud Run IAM／IAP 或公司 SSO），再用 per-operator session、MFA、RBAC 與 audit actor 取代共享長效 token 的人員登入模式。
5. 排程執行完整 admin smoke：未授權拒絕、privileged reads、資料來源、資料新鮮度、敏感欄位遮罩與 endpoint latency；結果進營運 dashboard。
6. 所有卡片明示 `Supabase / fallback / unavailable`，production 發現 JSON fallback 直接紅燈，不顯示成正常數字。

**P1**

1. 建立 safety、privacy、subscription、voice incident 的處理 SLA、owner、acknowledgement 與 closed-loop audit。
2. 增加 cohort／conversion 定義版本、內部帳號排除、成本對帳與指標 freshness monitoring。

### 90 分驗收條件

- `admin.munea.net` 或正式 ingress 有第二道 identity control；每個操作員具唯一身分、MFA、最小 RBAC 與可追溯 audit。
- CSP、X-Frame-Options（或 CSP frame-ancestors）、X-Content-Type-Options 與 Referrer-Policy 均由自動 smoke 驗證，不得缺失。
- 後台 asset、API、DB schema 與 release manifest 完全一致；頁面可直接辨識版本與資料新鮮度。
- privileged admin smoke、敏感欄位遮罩、權限負向測試與資料來源檢查連續 7 天通過。
- Safety／privacy／billing／voice 事件具有 SLA、owner、處理狀態與閉環證據，且營運數字排除 internal／QA／demo 流量。

## 從 77 推到 90 的執行順序

### P0-A：先建立真相與阻擋線，不動送審包

1. 登記使用者確認的 App review lane（repo 可證 Build 32 曾上傳／處理；精確送審 Build 待 App Store Connect 確認）與 next binary `1.0.31 (38)` 為兩條獨立 lane；禁止互相覆寫狀態。
2. hard CI 已進 main；下一步將 production revision、Voice 真鏈路與 Tokyo migration head 納入 promotion gate。
3. Brain 0% canary identity 已通過；#139 authenticated Voice wrapper 已合併，下一步需以受控 staging 身分在線執行，通過真媒體鏈後才可部署同 commit production。
4. #140 doctor gate 已合併但未套 SQL；依 issue #126 完成 Tokyo 017／018、備份／ledger 與 Sydney env 清理，差異未清零前不宣稱 DB ready。
5. 更新所有 current SSOT，讓 App Store、功能、設計、AI、服務與 admin 使用同一狀態詞彙。

### P0-B：canary 驗證 live，不直接切正式

1. Brain／Voice 0% canary 已建立；下一步跑真 Voice media、auth、family、billing、privacy 與 production-identity smoke。
2. 後台以 exact commit 部署並顯示版本／revision／資料來源；live asset hash 必須與 manifest 相同。
3. 對 Gateway／Voice／Avatar／Supabase 做故障與 rollback 演練，保存證據。
4. 所有結果通過後才逐步切流量；任一 compatibility 或資料來源紅燈立即 rollback。

### P1：降低下一次回歸的結構性成本

1. 拆解 `app.js`／`server.py` 高衝突 bounded contexts，建立 owner 與 module boundary。
2. 清理 repo authority 與 archive，移出不需常駐 runtime repo 的大型設計／銷售／原型資產。
3. 建立 SLO、coverage、flaky、成本、資料新鮮度與營運事件閉環 dashboard。

## 本輪分工與計分邊界

- `codex/health90-control-20260716`：release consistency、CI hard gate、送審凍結版與 next source 的版本判讀。
- #112（原 `codex/health90-api-observability-20260716`）已合併：Brain／Voice service metadata 與 health contract；尚未部署。
- #113（原 `codex/health90-schema-governance-20260716`）已合併：migration manifest、checksum 與 duplicate `011` governance；尚未與 live DB head 對帳。
- #114 已合併：營運後台權限、失敗狀態、accessibility 與 smoke 強化；後續 #133 headers 只在 `741fec7` 0% canary 驗收，未進 100% traffic。
- #139 已合併：authenticated Voice chain probe、account cleanup binding、user health redaction、lease／queue cleanup 與 CI hard gate；尚未部署或跑 live wrapper。
- #140 已合併：Tokyo `017` live doctor gate與權限／缺表分類；未讀取秘密、未套 SQL、未改 DB。
- 本文件已刷新至 `origin/main@88ddc10`，並重新查核 Brain／Voice staging 與 production `/version`。已合併與 canary 驗收均計入程式／治理分，但 **0% canary 不等於 production traffic，merged probe 不等於 live probe，manifest／doctor 不等於 live schema 已套用**；目前總分為 77。

## 仍需外部確認的問題

1. App Store Connect 的精確狀態是 `Waiting for Review`、`In Review` 或其他狀態，以及已送審項目實際選用的 Build 是否確為 32；Build 38 依最新 repo 證據未上傳。
2. staging 後台目前 privileged reads 是否全部來自正確 Supabase project，而非 JSON fallback；各指標最後資料時間為何。
3. 送審包實際使用的 Brain／Voice／Gateway URL 與 revision；`main` 的後端變更是否對該包完全向下相容。
4. production ingress、資料區域、on-call owner、SLO 與 rollback 權限由誰最終負責。

## 限制與假設

- 本報告將使用者提供的「已送 App Store 審核」視為最新外部事實；repo 文件仍落後，因此精確 Apple state 列為待確認，而不是自行推定。
- Cloud Run strict readiness 與 staging admin HTTP 200 是本日點檢結果；它們證明可達與設定存在，不替代長期 SLO、真人 App E2E、完整 privileged admin smoke 或 Apple 審核結果。
- 分數採 readiness rubric，不是從 production telemetry 計算；當 7–30 天 SLO、error budget、資料新鮮度與 incident data 建立後，應改用量化證據重評。
