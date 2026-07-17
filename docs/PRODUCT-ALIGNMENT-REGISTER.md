# Munea Product Alignment Register

更新：`2026-07-18 02:10 Asia/Taipei`

來源基準：`origin/main@b94a631`

本表回答產品承諾、App、source、AI、服務、資料與真人驗收是否仍描述同一個產品。易變的版本／revision 以 [`RELEASE-STATE.md`](./RELEASE-STATE.md) 為準，品質分數以 [`PRODUCT-QUALITY-CONFIDENCE.md`](./PRODUCT-QUALITY-CONFIDENCE.md) 為準。

## Alignment vocabulary

| State | Meaning |
|---|---|
| `aligned-source` | 權威文件與 current source 一致；不代表已部署或真人通過 |
| `partial` | 部分層級一致，仍缺 package、runtime、data 或 human proof |
| `runtime-behind` | serving runtime 的可驗身分落後 current source |
| `blocked` | 已知依賴阻止產品旅程完成 |
| `unknown` | 權威來源無法證明 |

## Distribution and service alignment

| Surface | Source / product truth | Runtime / external truth | Alignment | Next gate |
|---|---|---|---|---|
| App source lane | `1.0.41 (Build 48)`；package、Web 與 iOS 已在 main 對齊 | 尚無 Archive／upload／iPhone 證據；latest uploaded 仍是 `1.0.40 (Build 47)` | `aligned-source` | 整合 intended fixes 後再跑 strict package／human Gate |
| App Store lane | latest uploaded `1.0.40 (Build 47)` | 已上傳、iPhone 已安裝；selected review Build／Apple state未確認 | `partial` | App Store Connect 截圖／狀態＋關鍵旅程真機 Gate |
| Draft call／purchase fixes | #174 0 點預檢；#175 TEST 購買與 Apple mismatch UX | base 落後 main；main 已獨立使用 `1.0.41 (48)`，未 rebase 前不能算進 Build 48 | `partial` | 依序 rebase／整合，再鎖定 next candidate |
| Production Brain | current source `1.0.41` | 02:10 manifest：`1.0.36@d6a72a1` | `runtime-behind` | 定價／購買 compatibility canary；不要為追版號盲目部署 |
| Production Voice | current source 含較新的 Voice／call contract | 02:10 manifest：`1.0.31@500c819` | `runtime-behind` | authenticated canary＋installed-iPhone Voice Gate |
| Production Gateway | App 正式路徑要求 Gateway | auth boundary 可觀察；release identity／真 client trace 未知 | `partial` | release identity＋lease／ready／cleanup trace |
| Staging Brain／Voice | current main `1.0.41` | 02:10 manifest：兩者皆 `1.0.34@136dc81`；Cloud Run metadata Ready | `runtime-behind` | 僅在有核准變更時 canary；驗證 exact commit |
| Avatar fleet | FlashHead／Call Control contract 存在 | serving worker identity、capacity freshness與真 App path 未列入 release snapshot | `unknown` | Gateway-to-worker identity＋長聊／故障 Gate |

## Product, AI, data, and operations alignment

| Capability | Current authority | Evidence gap / conflict | Alignment | Next gate |
|---|---|---|---|---|
| Pricing / entitlement | [`BILLING-CREDITS-ENTITLEMENT-v1.md`](./BILLING-CREDITS-ENTITLEMENT-v1.md)：Plus 100、Pro 200、packs 100／300／600／1000；policy v4 | App Store 商品與 Tokyo `019` 未證明；production Brain 落後 App source | `blocked` | ASC 商品＋DB ledger／post-check＋Sandbox purchase |
| Google login | 原生優先＋PKCE fallback 已進 Build 47 | 缺 Build 47 選帳／callback／session／登出重登完整紀錄 | `partial` | exact-build iPhone acceptance |
| Purchase / membership | StoreKit 與 server verification contract 存在 | 使用者回報身份不變、後續不可見；#175 尚 Draft；Apple account-token mismatch 需帳號處理 | `blocked` | TEST local simulation＋新 Sandbox Apple ID 真交易 |
| 0-credit call UX | 應先查點數，0 點顯示原因，不進「撥通中」 | latest uploaded Build 47 未含 #174；Draft 尚未 rebase | `blocked` | next candidate 0 點真人 Gate |
| Authenticated Voice＋Avatar | 永久 App E2E Gate 已寫入 Release State／協作看板 | 沒有 exact Build＋production identities 的完整成功紀錄 | `blocked` | 有點數真帳號完整 call＋cleanup |
| Reflex / realtime voice | Gemini Live path、turn policy與 Guardian gate 存在 | production Voice 落後、model/config與真人體感未綁 release evidence | `partial` | safe model metadata＋真人長聊 |
| Butler | 產品文件曾宣告 Claude Sonnet；可執行路徑仍混合 deterministic／Google GenAI | provider authority、成本、安全與 deployed trace 不一致 | `blocked` | 拍板 provider SSOT，對齊 adapter／測試／telemetry／文件 |
| Guardian | deterministic rules＋semantic review source 存在 | 多 provider safety claim、red-team與 production audit evidence 不完整 | `partial` | provider authority＋red-team＋audit freshness |
| Migration / data | source head `019`，manifest 本輪補登 | live `017`／`018`／`019` 無新 ledger；不能由 source 推論 live | `blocked` | backup／approval／apply／read-only post-check |
| Operations console | staging shell／asset hash／security headers 已進 manifest；9 個 read endpoints 無 token 全回 403 | privileged source、data freshness、RBAC／MFA、empty-state truth 未驗 | `partial` | 具名 operator read-only smoke＋freshness SLA |

## Confirmed drift to remove

| Drift | Current action |
|---|---|
| 2026-07-16 Health scorecard 仍顯示 77、Build 38 與舊 runtime | 已標 historical；current score 改由 `PRODUCT-QUALITY-CONFIDENCE.md` 管理 |
| source 版號前進時 current 文件立刻過期 | 本輪新增 `CURRENT-AUTHORITIES.json`、alignment validator、負向測試、CI 與 release gate；latest source `1.0.41 (48)`、latest uploaded `1.0.40 (47)` 分 lane |
| `019` SQL 存在但 migration manifest 未列 | 本輪補入 checksum 與 order 20；需 CI／review 通過後才算 merged governance |
| Billing SSOT 方案已改，但 data model 段落仍稱 policy v3 | 本輪改為 policy v4／migration `019`，保留 v3 為歷史 migration |
| App source `1.0.41` 與 production Brain `1.0.36`／Voice `1.0.31` | 不以盲目部署消除版號差；以 compatibility canary＋App E2E 決定 rollout |
| runtime identity 靠人工抄寫，無 freshness／target config 綁定 | 新增 `RELEASE-EVIDENCE-TARGETS.json`、secret-free capture、latest manifest、24 小時 strict check 與 CI 負向測試 |

## 90-point alignment gates

1. App Store selected Build、source commit、packaged targets、商品價格／描述與 Apple state 都有權威證據。
2. Production Brain／Voice／Gateway／Avatar 可回報 exact release identity，並與 approved manifest 一致。
3. Tokyo DB 有不可變 migration ledger，`017`／`018`／`019` 的 backup、apply 與 post-check 完整。
4. Google 登入、會員／點數、0 點提示、有點數聊聊四條旅程在同一候選 Build 通過。
5. AI provider 宣告、實際 adapter、deployed model、成本與 safety telemetry 一致。
6. 營運後台能顯示服務／DB／指標版本、資料來源與 freshness，並有具名 RBAC／MFA 稽核。
7. current SSOT 零個已知版本、價格、點數、功能、AI 或服務狀態矛盾。

## Update protocol

1. 先更新對應 authority，再更新本 register；不要把 register 當成原始證據。
2. `merged`、`packaged`、`deployed`、`human-verified` 分欄保存，不使用單一「完成」。
3. App Store、runtime 與 DB 易變事實超過 24 小時，任何發版決策前重查。
4. 新 FAIL 立即降級；修正 PR 在新 Build／deployment 與 required Gate 通過前不得升級。
