# Munea Release State

本文件是 App、source、runtime、DB 與營運後台的 current release snapshot。品質分數看 [`PRODUCT-QUALITY-CONFIDENCE.md`](./PRODUCT-QUALITY-CONFIDENCE.md)；歷史活動看 `STATUS.md` 與協作看板。

Snapshot time: `2026-07-18 01:38 Asia/Taipei`

Source baseline: `origin/main@9f43287`

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
| Latest source | `1.0.41 (Build 48)` | `origin/main` 的 package、lockfile、Web changelog 與 iOS Debug／Release 一致；本輪沒有 Archive、upload 或 iPhone 安裝證據 | `package.json`; `web/src/version.js`; Xcode project; PR #177/#178 | 2026-07-18 01:38 |
| Latest uploaded App | `1.0.40 (Build 47)` | STATUS 記錄 IPA 五道防漏、20:44 上傳成功與 Edward iPhone 安裝／啟動成功；不以 later source 覆寫此成品事實 | `STATUS.md`; PR #172/#173 | 2026-07-17 20:44 |
| App Store selected review lane | Exact Build／Apple state `unknown` | Build 47 已上傳不等於已選用、已送審、審核中或核准；只能由 App Store Connect 或使用者明確證據更新 | App Store Connect required | 2026-07-18 |
| Draft call／purchase fixes | #174／#175 originally intended `1.0.41 (Build 48)` | main 已獨立前進到同版號／Build；兩個 Draft 的 base 落後，必須先 rebase，才能決定是否併入尚未出貨的 Build 48。#175 目前 stacked on #174 | PR #174; PR #175 | 2026-07-18 01:38 |

## Runtime services

| Environment | Service | Serving identity observed from public endpoint | Interpretation | Evidence time |
|---|---|---|---|---|
| production | Brain | `1.0.36@d6a72a16`, `munea-brain-00004-leb` | `/version` 200；落後 latest source `1.0.41`，不能假設含最新定價或 Draft 修正 | 2026-07-18 00:20 |
| production | Voice | `1.0.31@500c819f`, `munea-voice-00002-sub` | `/version` 200；明顯落後 source，真人通話仍需 App E2E | 2026-07-18 00:20 |
| production | Call Control / Gateway | release identity `unknown` | 公開 `/health` 無憑證回 401，auth boundary 正常；authenticated lease／cleanup 與 source commit 未證明 | 2026-07-18 00:20 |
| staging | Brain | `1.0.34@136dc81b`, `munea-brain-staging-00061-dow` | service URL `/version` 200；不是 production，也落後 main | 2026-07-18 00:18 |
| staging | Voice | `1.0.34@136dc81b`, `munea-voice-staging-00051-qom` | service URL `/version` 200；不是 production，也落後 main | 2026-07-18 00:18 |

`/version` 是 runtime identity authority。Cloud Run Ready、0% canary、source equivalence 或 App 預設 URL 都不能替代 serving identity 與真實 client trace。

## Database and billing policy

| Item | Current state | Interpretation |
|---|---|---|
| Repo migration head | `019` | `019_pricing_plus100_pro200.sql` 存在；本輪補入 migration manifest。這只證明 source governance |
| Tokyo applied `017` | `unknown / previously missing` | 本輪沒有新的 approved migration ledger 或 live read-only proof |
| Tokyo applied `018` | `unknown` | destructive cleanup 必須先有 backup／ledger／核准，再執行與驗證 |
| Tokyo applied `019` | `unknown` | App source／Build 47 顯示新方案不代表 DB policy v4 已套用 |
| App Store product prices / descriptions | `unknown` | STATUS 記錄為 Build 47 送審前置；App Store Connect 才是權威 |

任何 SQL 檔、manifest、CI PASS 或文件聲明都不能標成 live applied。

## Operations console

| Item | Current state | Interpretation |
|---|---|---|
| URL | staging `/admin.html` 回 200 | shell reachable |
| Serving identity | 跟隨 staging Brain `1.0.34@136dc81b` | 與 latest source `1.0.41` 不同版 |
| Browser security | CSP 與 `X-Frame-Options: DENY` 已觀察 | 只證明 delivery headers |
| Privileged APIs / data source / freshness | `unknown` | 未以具名 operator 做 read-only smoke；不能把空值當成零事件 |
| Operator security | per-operator identity／MFA／RBAC `unknown` | shared secret 或登入畫面本身不等於可稽核權限 |

## Critical feature rollout states

| Capability | Current state | Missing proof |
|---|---|---|
| Google login | fallback code 已進 Build 47；post-Build 47完整真人紀錄未找到 | 選帳 → callback → session → 登出／重登 → 真 token call |
| 0-credit call preflight | #174 `tested`, Draft，base 落後 main | rebase／merge → package next candidate → 0 點 iPhone 不得顯示「撥通中」 |
| Developer purchase / Apple account mismatch UX | #175 `tested`, Draft，stacked on #174 | 整合後包版；TEST 不觸發 Apple；真帳號 mismatch 不重複扣款 |
| Subscription / points purchase | Build 47 使用者回報身份與購買後續無法完成 | Sandbox Apple ID、server verification、entitlement／wallet refresh E2E |
| Authenticated chat call | synthetic／contract evidence 存在 | exact Build＋production Gateway／Voice／Avatar 的安裝版 iPhone 完整路徑 |
| Pricing policy v4 | source／App 已對齊 100／200 與新點數包 | App Store price／description、Tokyo `019`、Brain serving code與 Sandbox purchase |

## Chat-call App E2E release gate

任何可能影響 App、Auth、bootstrap、點數、Gateway、Voice、Avatar／GPU、環境設定或部署的改動，最後必須由安裝版 iPhone App 通過：

`按通話 → 麥克風 → Auth/account/credits → Gateway lease → Voice＋Avatar ready → AI 開場 → 真實上行 → AI 聲音／畫面回來 → 掛斷 → lease/GPU release`

紀錄必須包含 App version/build、package profile、裝置、環境、Brain／Voice／Gateway／Avatar identity、驗證時間、結果與 diagnostic reference。developer-direct、瀏覽器、CI、health 或 synthetic probe 均不能把此 gate 標為 `verified`。

## Unknowns that block 90

- App Store Connect selected Build、商品價格／描述與 review state。
- Latest source／next candidate 四條關鍵旅程的 installed-iPhone acceptance。
- Production Gateway／Avatar release identity 與真實 client trace。
- Tokyo `017`／`018`／`019` applied ledger 與 post-check。
- Admin privileged source／freshness／RBAC evidence。
- 7 日以上登入、購買、call setup、通話中斷、扣點、API latency/error 與資料 freshness SLO。

## Update rules

1. Git 管 source；App Store Connect 管 selected Build／review／商品；Cloud Run 與 `/version` 管 runtime；approved ledger＋live probe 管 DB。
2. 易變事實超過 24 小時，發版前重新驗證。
3. FAIL 或 unknown 不得用舊文件、口頭推測或不同 Build 的成功覆蓋。
4. upload、deploy、traffic shift、migration、rollback 或真機 Gate 發生時，必須在同一交接更新本文件。
5. 不在此檔保存 token、secret、使用者資料或 privileged response payload。
