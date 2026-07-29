# Munea Release State

本文件是 App、source、runtime、DB 與營運後台的 current release snapshot。品質分數看 [`PRODUCT-QUALITY-CONFIDENCE.md`](./PRODUCT-QUALITY-CONFIDENCE.md)；歷史活動看 `STATUS.md` 與協作看板。

Snapshot time: `2026-07-30 00:19 Asia/Taipei` (1.0.46 Build 2 packaged from latest main through PR #340 and installed; Apple upload not performed)

Source reconciliation baseline: `origin/main@61fc9870`; exact 1.0.46 package commit: `6d5eed83b76ae6c5ed5832447175b98bb10191c0`

Maintenance role: `Release / Platform` (`unassigned`)

## Status vocabulary

| Status | Meaning |
|---|---|
| `coded` | 只存在分支或 source |
| `tested` | 指定自動測試通過 |
| `merged` | 可由 `origin/main` 到達 |
| `packaged` | 已綁定精確 App Build／成品 |
| `deployed` | 已部署到具名環境與 revision |
| `verified` | 需求所需的 live／human gate 已通過 |
| `unknown` | 權威來源無法證明 |

狀態不得向上推論：`tested ≠ merged ≠ packaged ≠ deployed ≠ verified`。

## App lanes

| Lane | Version / Build | State | Evidence | Last verified |
|---|---|---|---|---|
| Latest source | `1.0.46 (Build 2)` | GitHub 精確 commit `6d5eed83b76ae6c5ed5832447175b98bb10191c0`，含 main through #340；本機測試 tree 與遠端 package tree 同為 `1911cecf`；完整 launch、Call Control、Voice／Avatar、i18n／UI、LocaleContext export 與 Archive／IPA 防漏 PASS。IPA 59,055,870 bytes，SHA-256 `c366017c14dee5c31d4e35d2cf3acdf9efe64436aa46460ab7885aafd645c316` | test logs; Xcode Archive／export; packaged build identity | 2026-07-30 00:19 |
| Latest uploaded App | `1.0.45 (Build 1)` | 2026-07-29 Apple upload 與 processing 完成並選入 1.0.45 版本頁。不得把該成品證據上推到 1.0.46 | App Store Connect live page; PR #288 | 2026-07-29 14:52 |
| App Store selected review lane | `1.0.45 (Build 1)` | 頁面標題與版本欄位均為 1.0.45，Build 1 已選入並儲存；仍為「準備提交」，未送審、未核准、未公開發佈 | App Store Connect live page | 2026-07-29 14:52 |
| Edward iPhone install lane | `1.0.46 (Build 2)` | Edward iPhone 15 Pro 已覆蓋安裝／啟動並由裝置資料庫回讀同版；Development signing＋production config，無 QA fixture。安裝成功不等於真人通話 Gate | `devicectl` install／launch／app inventory; build identity `6d5eed83` | 2026-07-30 00:19 |
| Pending Apple upload lane | `1.0.46 (Build 2)` | 精確 IPA 已準備完成（SHA-256 `c366017c14dee5c31d4e35d2cf3acdf9efe64436aa46460ab7885aafd645c316`）；尚未 upload／processing／選取。上傳會把此私有 binary 送往 Apple，需對此精確成品明確核准 | local verified IPA | 2026-07-30 00:19 |
| Draft call／purchase／QA fixes | #174 → #175 → #188，目標 `1.0.43 (Build 48)` | 三張 Draft 目前 merge state CLEAN 且 CI 綠；#175 stacked on #174、#188 stacked on #175。這仍只代表可整合，尚未 merged／packaged／iPhone verified | PR #174; PR #175; PR #188 | 2026-07-20 |

## Runtime services

| Environment | Service | Serving identity observed from public endpoint | Interpretation | Evidence time |
|---|---|---|---|---|
| production | Brain | `1.0.44@f6d9c7fa`, `munea-brain-00023-xoc` | `/version` 200；canary 0% PASS 後 exact-revision promotion 切 100% 流量（tag `prod-0727-003757-f6d9c7f`）。帶 #268 聊天品質三修（轉述紅線／內心戲清洗）；`MUNEA_REQUIRE_AUTH=1` 已查核；回滾至 `munea-brain-00021-kow` | 2026-07-27 00:44 |
| production | Voice | `1.0.44@f6d9c7fa`, `munea-voice-00013-joj` | `/version` 200；exact-revision promote（tag `prod-0727-003936-f6d9c7f`＝`00011-luw`）後疊試驗設定 `MUNEA_VOICE_LIVE_LOOKUP=1`／`MUNEA_VOICE_SILENCE_MS=1100`（tag `exp-0727-lookup`）切 100%；帶 #265 語音週包；回滾至 `munea-voice-00011-luw`（保留新版、去試驗設定）或 `munea-voice-00009-muh`（退 7/24 版） | 2026-07-27 00:52 |
| production | Call Control / Gateway | release identity `unknown` | 公開 `/health` 無憑證回 401，auth boundary 正常；authenticated lease／cleanup 與 source commit 未證明 | 2026-07-18 00:20 |
| staging | Brain | `1.0.44@dfea6aac`, `munea-brain-staging-00083-veh` | `/version` 200；安全兩閘（canary 0%→自動驗證→promote）PASS，語音 s2s 探針 5/5 PASS；`dfea6aac` 與正式線 `8ddab84c` 之間僅差文件、程式本體相同；不是 production | 2026-07-24 19:50 |
| staging | Voice | `1.0.44@dfea6aac`, `munea-voice-staging-00058-yer` | `/version` 200；同上安全兩閘 PASS；不是 production，真人通話仍需 App E2E | 2026-07-24 19:50 |

`/version` 是 runtime identity authority。上述 5 個公開 target 的 safe observation、target-config hash、capture time 與 capture source commit 保存在 [`RELEASE-EVIDENCE-LATEST.json`](./RELEASE-EVIDENCE-LATEST.json)，以 [`RELEASE-EVIDENCE-TARGETS.json`](./RELEASE-EVIDENCE-TARGETS.json) 及 `npm run release:evidence:check`（= `python scripts/release_evidence.py check --max-age-hours 24 --strict-version`）驗 freshness 與版號對齊；上線前跑這一條。CI 常駐的 `python scripts/release_evidence.py check`（無 `--strict-version`）只擋真漂移：sourceVersion 缺值、看不懂、或超前 package version。證據落後 package version 是版號跳了還沒重擷的正常開發狀態，只給 warning，重擷用 `npm run release:evidence:capture`。Cloud Run Ready、0% canary、source equivalence或 App 預設 URL 都不能替代 serving identity 與真實 client trace。

## Database and billing policy

| Item | Current state | Interpretation |
|---|---|---|
| Repo migration head | `019` | `019_pricing_plus100_pro200.sql` 存在；本輪補入 migration manifest。這只證明 source governance |
| Environment deployment ledger | `supabase/deployment-ledger.json` | 東京 27 支 migration 逐支對應 manifest checksum；17 筆 historical claim、4 筆 unknown（`020`／`021`／`022`／`026`）、3 筆 blocked（`017`／`018`／`019`）、3 筆 verified read-only-probe（`023`／`024`／`025`，2026-07-24）；`verifiedHead=null`（`001` 起未形成連續 verified chain） |
| Tokyo applied `017` | `blocked / HTTP 404` | 07:12 UTC GET-only probe 對正確東京 project 發出請求，`notification_settings` 不可到達；需核准套用後重驗 |
| Tokyo applied `018` | `blocked / partial photo-key=0` | destructive cleanup 仍需 approval、backup、完整 data-image pre-check／post-check；單一欄位零筆不能升格 |
| Tokyo applied `019` | `blocked / policy mismatch` | policy table 可查，但沒有符合 active v4 Plus 100／Pro 200 的資料；需核准套用後重驗 |
| Latest Tokyo probe attempt | `blocked after read-only requests` | target／observed project 都是東京 `fespbkdwafueyonppzwq`；使用 Cloud Run 現行 Secret reference，沒有顯示密鑰、個資或執行寫入 |
| App Store product prices / descriptions | `unknown` | STATUS 記錄為 Build 47 送審前置；App Store Connect 才是權威 |

任何 SQL 檔、manifest、CI PASS、historical claim 或文件聲明都不能標成 live applied。台帳由 [`supabase/deployment-ledger.json`](../supabase/deployment-ledger.json) 管理，更新規則見 [`docs/supabase/DEPLOYMENT-LEDGER.md`](./supabase/DEPLOYMENT-LEDGER.md)。

## Operations console

| Item | Current state | Interpretation |
|---|---|---|
| URL | staging `/admin.html` 回 200；body hash 與必要 asset tokens 已進 manifest | shell reachable；不代表 privileged data 正確 |
| Serving identity | 跟隨 staging Brain `1.0.40@fa14e4c` | admin shell 公開 hash／headers PASS；與 latest source `1.0.41` 不同版，privileged data 仍未證明 |
| Browser security | `nosniff`、`DENY`、`no-referrer` 已進 manifest；9 個 console read endpoints 無 token 均回 403 | delivery 與未授權拒絕 PASS；不代表具名 RBAC／MFA |
| Privileged APIs / data source / freshness | source contract `merged`；runtime `unknown` | #183 已加入 provenance／fallback／freshness unknown metadata，但 staging Brain 尚未部署；不能把空值當成零事件 |
| Operator security | per-operator identity／MFA／RBAC `unknown` | shared secret 或登入畫面本身不等於可稽核權限 |

## Critical feature rollout states

| Capability | Current state | Missing proof |
|---|---|---|
| Google login | fallback code 已進 Build 47；post-Build 47完整真人紀錄未找到 | 選帳 → callback → session → 登出／重登 → 真 token call |
| 0-credit call preflight | #174 `tested`, Draft，base 落後 main | rebase／merge → package next candidate → 0 點 iPhone 不得顯示「撥通中」 |
| Developer purchase / Apple account mismatch UX | #175 `tested`, Draft，stacked on #174 | 整合後包版；TEST 不觸發 Apple；真帳號 mismatch 不重複扣款 |
| Dedicated QA account | 正式 Supabase 登入狀態仍在 exact Build；2026-07-29 23:30 App 顯示餘額 `453`（原 505 測試額度已被過往測試扣用），本次 production call 已到「在線」並顯示 Avatar，隨後掛斷回到「未在線」 | iPhone Mirroring 明確禁止使用 iPhone 麥克風，因此未完成真上行／AI 可聽回覆；未獨立確認 Gateway lease／GPU 後端釋放，不能標 App E2E PASS |
| Subscription / points purchase | Build 47 使用者回報身份與購買後續無法完成 | Sandbox Apple ID、server verification、entitlement／wallet refresh E2E |
| Authenticated chat call | Exact Build `6d5eed83` 已在 Edward iPhone 安裝；自動化 Call Control 與 Voice／Avatar contract PASS | `App E2E pending`：Build 2 尚未直接在實體 iPhone 完成 0 點 lane 與 credited 真麥克風、可聽／可見 AI 回覆，並以後端證據確認 lease／GPU release |
| Pricing policy v4 | source／uploaded Build 47／production Brain 已對齊；Apple Product ID 維持原值，Brain 實際 grant mapping 為點數包 100／300／600／1000、Plus 100、Pro 200 | App Store price／description、Tokyo `019` 與登入後 Sandbox purchase／wallet refresh 真人驗收；DB policy mismatch 不參與目前 `/apple/transaction` 的 `verified.points` 入帳路徑，但仍需治理對焦 |
| Managed-cloud `/chat-test` | #182 已合併，source 預設 404 | Voice 尚未部署；production／staging live GET 仍須重新驗證 404 |

## Chat-call App E2E release gate

任何可能影響 App、Auth、bootstrap、點數、Gateway、Voice、Avatar／GPU、環境設定或部署的改動，最後必須由安裝版 iPhone App 通過：

`按通話 → 麥克風 → Auth/account/credits → Gateway lease → Voice＋Avatar ready → AI 開場 → 真實上行 → AI 聲音／畫面回來 → 掛斷 → lease/GPU release`

紀錄必須包含 App version/build、package profile、裝置、環境、Brain／Voice／Gateway／Avatar identity、驗證時間、結果與 diagnostic reference。developer-direct、瀏覽器、CI、health 或 synthetic probe 均不能把此 gate 標為 `verified`。

## Unknowns that block 90

- App Store Connect selected Build、商品價格／描述與 review state。
- Latest source／next candidate 四條關鍵旅程的 installed-iPhone acceptance。
- Production Gateway／Avatar release identity 與真實 client trace。
- Tokyo ledger 已存在且 live blocker 已具名；`017`／`018`／`019` 都是 blocked，verified head 仍為 null。
- Admin privileged source／freshness／RBAC evidence。
- 7 日以上登入、購買、call setup、通話中斷、扣點、API latency/error 與資料 freshness SLO。

## Update rules

1. Git 管 source；App Store Connect 管 selected Build／review／商品；Cloud Run 與 `/version` 管 runtime；approved ledger＋live probe 管 DB。
2. 易變事實超過 24 小時，發版前重新驗證。
3. FAIL 或 unknown 不得用舊文件、口頭推測或不同 Build 的成功覆蓋。
4. upload、deploy、traffic shift、migration、rollback 或真機 Gate 發生時，必須在同一交接更新本文件。
5. 不在此檔保存 token、secret、使用者資料或 privileged response payload。
