# Munea Release State

本文件是 App、source、runtime、DB 與營運後台的 current release snapshot。品質分數看 [`PRODUCT-QUALITY-CONFIDENCE.md`](./PRODUCT-QUALITY-CONFIDENCE.md)；歷史活動看 `STATUS.md` 與協作看板。

Snapshot time: `2026-07-31 23:2X Asia/Taipei` (source 升版為 1.0.51 Build 520；uploaded／review／iPhone 三條 lane 仍是 Build 492 的凍結成品，runtime 兩台已上 1.0.51 對應 commit，DB lane 未變)

Source reconciliation baseline: `origin/main@6786c1ba`; frozen uploaded App source: `72a0bd46` (parent `5d2008c`)

> ⚠️ **版號回填缺口（2026-07-31 Edward 點出）**：Edward 說 App 端「已經要準備上 1.0.51」，但 repo 的 source 從 07-30 起一直停在 1.0.45——中間 1.0.46～1.0.50 這幾個號**只存在於 Edward 那端的打包，從未回寫 repo**。後果是每個 session 讀 repo 都只查得到 1.0.45（session 沒有錯，是唯一權威來源本身落後），而使用者在設定頁看到的「更新內容」也停在 07-30。本次把 source 直接推到 **1.0.51** 並補齊該段更新紀錄（1.0.45 之後 main 上共 174 個 commit、其中 83 個使用者可見）。Build number 從 500 跳到 **520 是留空間的估計值**，實際可用號以 App Store Connect 為準——Edward 打包前請對一次。

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
| Latest source | `1.0.53 (Build 523)` | 純 source 升版。版號直接從 1.0.45 推到 **1.0.51** 以對齊 Edward App 端實際要出的號（1.0.46～1.0.50 從未回寫 repo，見上方缺口說明）；更新紀錄補齊 1.0.45 之後 main 的 174 個 commit（83 個使用者可見）：家人帶話上首頁、傳話送出前複誦確認、免費版 1 位家人、四語系與四國衛教庫、主動關心、急難號碼照所在地、蘋果健康重裝自動接回、訂閱與點數顯示修復、內購重送修復、視覺與版面一批。Build 520 是留空間的估計值，**實際可用號以 App Store Connect 為準**。尚未 Archive、未打包、未上傳；沒有任何適用此版的 IPA／iPhone 證據，不得把下列 Build 492 證據上推到 current source | `package.json`; `package-lock.json`; `web/src/version.js`; Xcode project; Git history | 2026-07-31 23:2X |
| Latest uploaded App | `unknown`（本表最後有憑證的是 `1.0.44 (Build 492)`） | **這一列已知過期。** Edward 2026-07-30 表示 492 之後又包過幾版，但那些 Archive／上傳沒有回填本表，所以最大 Build number 目前無法從 repo 證明。下面 492 的憑證只證明它上傳過，不證明它是最新：Apple 於 07-28 17:22:57 回傳 `Upload succeeded`，IPA 58,865,329 bytes，SHA-256 `287b264172f9316a827911c314e61c50f4720c8c93cb9a651c4bd2824fc107f1`。要恢復這一列，得由 Edward 從 App Store Connect 回填實際上傳過的版本與 Build | Xcode upload receipt（僅限 492）; App Store Connect（權威，尚未回讀） | 2026-07-28 17:31（已過期） |
| App Store selected review lane | `1.0.44 (Build 492)` | 17:31 已選入 1.0.44 版本頁並儲存；頁面狀態仍為「準備提交」。未點「新增以供審查」、未送審、未核准、未公開發佈 | App Store Connect live page | 2026-07-28 17:31 |
| Edward iPhone install lane | `1.0.44 (Build 492)` | iPhone 15 Pro 安裝與啟動成功，`devicectl` 從手機回讀版本；使用 Development signing＋production config，未注入 direct／gateway QA fixture。安裝成功不等於正式 App Store binary 或真人通話 Gate | `devicectl` install／launch／app inventory | 2026-07-28 17:25 |
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
| Dedicated QA account | 正式 Supabase password sign-in、account bootstrap 與 Brain balance readback 已驗證；purchased balance `505`（免費 5＋授權測試 500），帳密只存 Secret Manager，事件排除營運分析 | #188 合併後由 Mac 安全載入 Secret，包一個開發版完成 iPhone 登入與 credited chat-call；後端帳號存在不等於 App Gate 通過 |
| Subscription / points purchase | Build 47 使用者回報身份與購買後續無法完成 | Sandbox Apple ID、server verification、entitlement／wallet refresh E2E |
| Authenticated chat call | 凍結 commit `72a0bd46` 的 Build 492 已通過 App Call Control 15/15 與 Avatar render contract，手機已安裝／啟動 | `App E2E pending`：仍需針對該 exact Build＋production Gateway／Voice／Avatar 完成真麥克風、AI 聲畫回應與掛斷釋位；post-package source 不承接結果 |
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
