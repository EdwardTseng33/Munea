# Munea Release State

本文件是 App、source、runtime、DB 與營運後台的 current release snapshot。品質分數看 [`PRODUCT-QUALITY-CONFIDENCE.md`](./PRODUCT-QUALITY-CONFIDENCE.md)；歷史活動看 `STATUS.md` 與協作看板。

Snapshot time: `2026-07-20 00:21 Asia/Taipei` (public runtime refresh and QA account readiness)

Source baseline: `origin/main@00d3eb3`

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
| Latest source | `1.0.43 (Build 48)` | `origin/main` 的 package、lockfile、Web changelog、iOS Debug／Release與品質治理一致；#181–#199 已完成 API、release evidence、SLO 與輕量治理主線，本輪沒有 Build 48 Archive、upload 或 iPhone 安裝證據 | `package.json`; `web/src/version.js`; Xcode project; PR #176–#199 | 2026-07-20 |
| Latest uploaded App | `1.0.40 (Build 47)` | STATUS 記錄 IPA 五道防漏、20:44 上傳成功與 Edward iPhone 安裝／啟動成功；不以 later source 覆寫此成品事實 | `STATUS.md`; PR #172/#173 | 2026-07-17 20:44 |
| App Store selected review lane | Exact Build／Apple state `unknown` | Build 47 已上傳不等於已選用、已送審、審核中或核准；只能由 App Store Connect 或使用者明確證據更新 | App Store Connect required | 2026-07-18 |
| Draft call／purchase／QA fixes | #174 → #175 → #188，目標 `1.0.43 (Build 48)` | 三張 Draft 目前 merge state CLEAN 且 CI 綠；#175 stacked on #174、#188 stacked on #175。這仍只代表可整合，尚未 merged／packaged／iPhone verified | PR #174; PR #175; PR #188 | 2026-07-20 |

## Runtime services

| Environment | Service | Serving identity observed from public endpoint | Interpretation | Evidence time |
|---|---|---|---|---|
| production | Brain | `1.0.40@fa14e4c`, `munea-brain-00006-faw` | `/version` 200；100% traffic 已由 exact-revision promotion 切換。此 revision 與 uploaded Build 47 同 commit，含 Apple Product ID 不變的 100／300／600／1000 點數包與 Plus 100／Pro 200 入帳 mapping；不含 Draft #174／#175。安全 smoke 與新 revision ERROR log 檢查 PASS，真人 Sandbox purchase 仍 pending | 2026-07-18 17:23 |
| production | Voice | `1.0.41@906732ab`, `munea-voice-00007-xab` | `/version` 200；已與 current source Voice commit 對齊。這只證明部署身分，真人通話仍需安裝版 App E2E | 2026-07-20 00:21 |
| production | Call Control / Gateway | release identity `unknown` | 公開 `/health` 無憑證回 401，auth boundary 正常；authenticated lease／cleanup 與 source commit 未證明 | 2026-07-18 00:20 |
| staging | Brain | `1.0.40@fa14e4c`, `munea-brain-staging-00063-tod` | `/version` 200；pricing exact revision 100% serving，安全 smoke PASS；不是 production，且不代表真人購買驗收 | 2026-07-20 00:21 |
| staging | Voice | `1.0.41@906732ab`, `munea-voice-staging-00053-xow` | `/version` 200；公開 identity 已刷新；不是 production，真人通話仍需 App E2E | 2026-07-20 00:21 |

`/version` 是 runtime identity authority。上述 5 個公開 target 的 safe observation、target-config hash、capture time 與 capture source commit 保存在 [`RELEASE-EVIDENCE-LATEST.json`](./RELEASE-EVIDENCE-LATEST.json)，以 [`RELEASE-EVIDENCE-TARGETS.json`](./RELEASE-EVIDENCE-TARGETS.json) 及 `npm run release:evidence:check`（= `python scripts/release_evidence.py check --max-age-hours 24 --strict-version`）驗 freshness 與版號對齊；上線前跑這一條。CI 常駐的 `python scripts/release_evidence.py check`（無 `--strict-version`）只擋真漂移：sourceVersion 缺值、看不懂、或超前 package version。證據落後 package version 是版號跳了還沒重擷的正常開發狀態，只給 warning，重擷用 `npm run release:evidence:capture`。Cloud Run Ready、0% canary、source equivalence或 App 預設 URL 都不能替代 serving identity 與真實 client trace。

## Database and billing policy

| Item | Current state | Interpretation |
|---|---|---|
| Repo migration head | `019` | `019_pricing_plus100_pro200.sql` 存在；本輪補入 migration manifest。這只證明 source governance |
| Environment deployment ledger | `supabase/deployment-ledger.json` | 東京 20 支 migration 逐支對應 manifest checksum；17 筆 historical claim、0 筆 unknown、3 筆 blocked；`verifiedHead=null` |
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
| Authenticated chat call | synthetic／contract evidence 存在 | exact Build＋production Gateway／Voice／Avatar 的安裝版 iPhone 完整路徑 |
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
