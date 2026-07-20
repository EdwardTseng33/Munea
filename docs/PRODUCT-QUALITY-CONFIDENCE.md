# Munea 產品品質信心

更新：`2026-07-20 Asia/Taipei（runtime evidence refreshed；QA account ready；1 人＋AI 輕量治理）`

來源基準：`origin/main@00d3eb3`

本文件是目前「能不能放心把這一版交給使用者」的評分 SSOT。它不取代 [`RELEASE-STATE.md`](./RELEASE-STATE.md) 的版本／部署事實，也不把程式存在、測試通過、已合併、已部署或真機通過混成同一個「完成」。

## CTO 結論

**目前產品品質信心：69/100，未達 90。**

這不代表系統只有 69 分的工程能力；它代表目前缺少足以支持「上線可放心」的完整證據。#181–#199 已補 API inventory、managed-cloud `/chat-test` fail-closed、admin data provenance／freshness contract、DB deployment ledger、服務 watchdog、Cloud Monitoring 固定頻率控制面與輕量風險治理。2026-07-20 的公開 evidence 確認 production Voice 已由 `1.0.31` 前進到 `1.0.41@906732ab`，但部署身分不能替代安裝版 iPhone 通話。東京 live probe 仍證實 `017` 不可到達、`019` active v4 policy 不符合，`018` 缺核准備份與完整前後檢查。專用 QA 帳號已完成真密碼登入、account bootstrap 與 `505` 點讀回，讓一個 Build 的驗收可執行；Google／帳號、會員與點數購買、0 點通話預檢、真實聊聊撥通仍沒有同一個 Build 的完整 iPhone 驗收紀錄。latest source 是 `1.0.42 (Build 48)`，latest uploaded 仍是 `1.0.40 (Build 47)`，#174／#175 已於 2026-07-20 比對差異為空後關閉、內容收攏進 #188；#188 仍是 Draft PR。

在任何 P0 關鍵旅程失敗或缺少真機閉環時，整體分數最高只能是 69。自動測試全綠可以提高工程信心，不能解除這個上限。

## 1 人＋AI 的治理前提

Munea 的健康度是衡量「能否安全、快速、持續地把產品交給使用者」，不是衡量流程像不像大型企業。治理的價值來自降低事故、產品漂移與返工；文件數、會議數、Gate 數、人工核准數本身一律不加分。

- **一個事實一個 SSOT**：已有 authority 就更新原文件，不為同一事實再建報表；重複或互相矛盾的文件反而降低 Repo／產品對焦分數。
- **一次產證、多處引用**：CI、runtime manifest、監測與真機紀錄應自動產生或直接引用；不要求人工把同一結果重抄到多份文件。
- **風險決定 Gate，不是檔案數或企業慣例**：未觸及的 Gate 明確標示不適用即可，不得因未跑無關的全套流程扣分。
- **可逆變更優先自主推進**：AI 可在使用者授權範圍內完成分支、測試、PR、canary／唯讀驗證與回滾準備；只有不可逆、會花錢、會影響外部使用者／資料／商店審核／憑證的動作才需要額外人工確認。
- **Gate 要能刪除**：任何新增 Gate 必須寫出具名風險、觸發條件、最小證據與解除／自動化方式；無法說明降低哪個風險的流程視為治理債務。

### 最小風險分級

| 等級 | 典型範圍 | 最小驗收；不額外加碼 |
|---|---|---|
| L0 文件／註解／不改行為 | SSOT 更正、說明、連結 | scoped diff＋格式／連結檢查；不跑真機、不跑全套 release gate |
| L1 可逆程式變更、非 P0 | 內部重構、獨立 UI、工具 | 相關單元／契約測試＋CI；一個 branch／PR，不要求無關 E2E |
| L2 runtime／設定／資料相容性 | 可回滾部署、服務設定、schema 相容新增 | plan／preview 或 canary＋具名 smoke＋rollback；只驗受影響旅程 |
| L3 P0／不可逆／外部承諾 | 登入、購買、點數、聊聊、隱私資料、破壞性 migration、App Store | 完整受影響 E2E、前後檢查與人工確認；聊聊依永久 iPhone Gate |

若低風險任務的流程時間長於實作本身，且不能指出被降低的具名風險，先簡化流程而不是再補一層規定。健康度 90 分也必須同時代表產品能穩定前進，而不是只有證據齊全但交付停滯。

## 評分模型

| 面向 | 權重 | 目前分數 | 加權貢獻 | 判斷 |
|---|---:|---:|---:|---|
| 1. 架構與復原能力 | 15% | 78 | 11.7 | 服務分層、canary、rollback 與 5 分鐘 watchdog 存在；7 日保守可用率開始收集，仍缺完整週期、故障演練及 App 真鏈路證據 |
| 2. API／服務可靠性與安全 | 15% | **80→84** | 12.6 | 94-route inventory、critical test target、managed-cloud `/chat-test` fail-closed 與 synthetic SLO 分母已建立；production Voice 已對齊 source，但仍缺完整 7 日、Gateway identity 與 authenticated App call trace |
| 3. App 與後端程式品質 | 20% | 64 | 12.8 | release gate 強，#188（已收攏 #174／#175）CI 綠且可整合，但尚未合併、包版與真機驗收，關鍵旅程不得標 verified |
| 4. Repo／資料／migration 治理 | 15% | **62→69（raw 74）** | 10.35 | manifest、逐環境 ledger、16 項 authority、current-plan 負向 CI 與東京 secret-safe live probe 已齊；治理採一事實一 SSOT、風險分級與自動證據，不以文件／Gate 數量加分；17 筆 historical claims、`017`／`018`／`019` 全為 blocked，`verifiedHead=null`，因此仍受 69 分上限限制 |
| 5. 產品／版本／AI／服務對焦 | 20% | **58→66→69** | 13.8 | source／uploaded／runtime 分 lane；production Brain 已對齊 Build 47 pricing mapping、production Voice 已對齊 current Voice source；App Store、Gateway／Avatar、DB 與真機仍未形成單一候選版本，受 69 分上限限制 |
| 6. 營運後台與可觀測性 | 15% | 74 | 11.1 | data provenance／fallback／freshness unknown contract 已合併但尚未部署；特權資料來源、RBAC／MFA 與 7 日營運指標未證明 |
| **加權結果** | **100%** |  | **72.35，硬上限後 69** | **工程／治理 raw 信心持續上升；整體仍被 P0 真機與 live DB 證據限制** |

本輪只計入可重現證據：16 個 current authorities、94-route inventory、API／deployment-ledger／current-plan 負向測試、admin data contract、GitHub workflow、service SLO schema／分母負向測試、2026-07-20 00:21 的公開 runtime capture、production Brain exact-revision rollout smoke、專用 QA 帳號的真登入／bootstrap／餘額讀回，以及東京 DB GET-only probe。production Voice 已對齊 source，QA 驗收前置也已完成；但尚未累積 7 日，P0 iPhone 與 live DB Gate 沒有新增通過項，因此總分與各 hard-capped 分數不調高。

產品對焦 `69` 是有效期分數：release decision 時若 `npm run release:evidence:check` 因超過 24 小時失敗，且未重新 capture，該面向回退到 `66`，不得沿用本次 runtime 證據。

### 每個面向如何得分

每個面向都依相同證據梯度計分：

這是證據成熟度，不是每個任務都必須依序手動跑完五層。只評估該面向目前已具備的真實證據；低風險變更不需要為了「湊層級」製造無關 artifact 或真人驗收。

| 證據層 | 配分 | 必要證據 |
|---|---:|---|
| Source／contract | 20 | 權威規格、owner、明確邊界與可追溯 source |
| Automated verification | 20 | 正反案例、自動 gate、CI 可重現 |
| Merged／packaged | 15 | 已進 main；App 能綁定精確 Build／IPA |
| Runtime／data alignment | 20 | exact revision、DB ledger、設定與 source 對得上 |
| Human E2E／operations | 25 | 安裝版真機關鍵旅程，或連續 7–30 日 SLO／告警／復原證據 |

### 硬性上限

- 任一登入、付款、點數、通話或資料安全 P0 為 FAIL／未驗：整體最高 `69`。
- App Store 選用 Build、服務 revision 或 DB head 無法唯一回答：產品對焦最高 `69`。
- migration 存在但未列 manifest、無 ledger 或未驗 live：Repo／資料最高 `69`。
- 沒有 7 日以上 latency、error rate、availability、freshness 與 incident 證據：架構、API、營運後台單項最高 `84`。
- Draft PR、0% canary、synthetic probe 或 developer-direct 包不能取得 `human verified` 分數。

## 本次採用的現況證據

| 證據 | 2026-07-20 判讀 |
|---|---|
| Latest source | `1.0.42 (Build 48)`；source、Web、package、iOS 與品質治理已在 `origin/main@00d3eb3` 對齊，包含 #181–#199 的 release／SLO／治理工作；本輪沒有 Build 48 Archive／upload／iPhone 證據 |
| Latest uploaded App | `1.0.40 (Build 47)`；STATUS 記錄 20:44 上傳成功與 Edward iPhone 換裝成功 |
| App Store | Build 47 已上傳；精確 selected Build 與 Apple review state 未由本輪 App Store Connect 證據確認，因此保持 `unknown` |
| 待驗修正 | Draft #174：0 點不進入「撥通中」；#175：TEST 購買模擬與 Apple account-token mismatch；#188：gateway profile 真 QA 帳號。三張目前 CLEAN、CI 綠，但未計為 merged／packaged／human verified |
| Production Brain | 17:23 secret-free manifest：公開 `/version` 回 `1.0.40@fa14e4c`，revision `munea-brain-00006-faw`，100% traffic；點數包 100／300／600／1,000 與 Plus 100／Pro 200 mapping 已部署，安全 smoke 與新 revision ERROR log 檢查 PASS，真人 Sandbox purchase 仍 pending |
| Production Voice | 00:21 secret-free manifest：公開 `/version` 回 `1.0.41@906732ab`，revision `munea-voice-00007-xab`；已與 current Voice source 對齊，真人通話仍需 App E2E |
| Staging Brain／Voice | 00:21 secret-free manifest：Brain `1.0.40@fa14e4c`／`00063-tod`，Voice `1.0.41@906732ab`／`00053-xow`；這是 runtime identity，不代表真人購買或通話驗收 |
| Dedicated QA account | 正式 Supabase password sign-in、account bootstrap 與 Brain balance readback 已通過；purchased `505`（免費 5＋授權測試 500），帳密只存 Secret Manager，QA 事件排除營運分析；仍未在 #188 對應 iPhone Build 完成登入與撥通 |
| Gateway | 公開 `/health` 無憑證回 401，證明 auth boundary；release identity 與真實 App lease／cleanup trace仍未知 |
| 服務 SLO | 5 分鐘 GitHub watchdog／每日 artifact 已進 main；首次完整 7 日報表只有 `43/2,016` 格、coverage 2.133%。Cloud Monitoring 三區 5 分鐘 **8 checks 已 live**，最近 30 分鐘已有 24 條 `check_passed` 時序且最新樣本全過；仍須累積完整 7 日，現在不能加分 |
| 營運後台 | staging `/admin.html` 回 200；#183 的 provenance／fallback／freshness unknown contract 已進 main，但 staging Brain 尚未部署該 source；privileged metrics、Tokyo source 與 operator RBAC 未驗 |
| Repo migration | manifest 有 20 支 migration；`supabase/deployment-ledger.json` 已逐支對應東京 project ref、checksum、狀態與 rollback claim。這是 source governance，不代表 Tokyo 已套用 |
| Live DB | ledger 明示 `historical-claim=17`、`unknown=0`、`blocked=3`；`verifiedHead=null`。07:12 UTC 東京 GET-only probe 證實 `017` 回 404、`019` 無符合的 active v4 100／200 policy；`018` photo-key=0 仍只是 partial |

## 關鍵旅程信心

| 關鍵旅程 | Source／測試 | 目前成品／真機證據 | 判定 |
|---|---|---|---|
| Google 登入 → session → 登出重登 | fallback 修正已進 source／Build | 缺同一份完整驗收紀錄 | `partial` |
| 會員購買 → entitlement 改變 → 點數入口 | 自動契約存在；#175 補錯誤與 TEST 行為 | 使用者回報無法改變身分／看不到後續；新版未驗 | `fail / draft fix` |
| 0 點按通話 → 立即說明、不顯示撥通中 | #174 自動測試通過 | Build 47 尚未包含 #174 | `fail / draft fix` |
| 有點數真帳號 → Gateway → Voice＋Avatar → 掛斷釋放 | synthetic／服務契約與 505 點 QA 帳號存在 | 缺 #188 對應精確 Build＋revision 的完整 iPhone 證據 | `ready to test / not verified` |

目前「完整通過且有可追溯證據」為 `0/4`。這是證據缺口統計，不等於四條路徑都必然壞掉；任何一條只有口頭成功、沒有 Build／環境／revision／時間記錄，仍不算通過。

## 從 69 推到 90 的順序

### P0：先解除上線硬上限

1. 依序 review／合併 #174 → #175 → #188，再決定是否仍使用尚未出貨的 Build 48；三張目前 CLEAN、CI 綠，但 stacked Draft 不能直接當成已包版主線。
2. iPhone 分別驗：Google 真帳號、TEST 身分、0 點真帳號、有點數真帳號、Sandbox Apple ID。記錄 Build、profile、Brain／Voice／Gateway／Avatar revision、時間與結果。
3. Apple account-token mismatch 必須以換／重置 Sandbox 帳號解決；不得放寬伺服器綁定，也不得重複扣款測試。
4. App Store Connect 的商品售價／描述與 latest uploaded Build 47 畫面一致後，才能決定 selected Build；若改送後續 Build，必須重新核對商品、成品與 review state。
5. 依核准流程補套 Tokyo `017` 與 `019`，完成後重跑 read-only post-check；`018` 必須先取得 backup／approval／完整 pre-check，不能因 photo-key=0 跳過。文件更新不能代替執行證據。

### P1：把單次驗收變成可持續信心

1. ✅ 已為 production／staging Brain、Voice 與 staging admin shell 建立 secret-free release evidence manifest；下一步納入 Gateway／Avatar identity、App Store、verified DB head 與 signed App E2E attestation。
2. ✅ 後台 source 已能顯示資料來源、紀錄時間、fallback 與 metric version；仍需部署 Brain、具名 operator smoke，以及接入 verified DB head／service revision。
3. 🟡 GitHub schedule 分母已證實 coverage 不足；8 targets × 3 regions × 5 分鐘的 Cloud Monitoring checks 已啟用並確認 metrics 產生。累積完整 7 日後才可取代 GitHub schedule 作正式 control-plane 分母；仍需補登入、購買、call setup、p95 接通、通話中斷、點數／退款與 admin freshness。synthetic latency 不得冒充正式流量 p95。
4. ✅ 已把 current authority、版本／Build、定價、AI provider reality、historical marker、migration manifest、deployment ledger 與 runtime evidence contract 加入 CI／release gate；DB verified evidence 與人工作業仍需具名／簽章 attestation。

## 90 分的最低條件

- 四條關鍵旅程在同一候選 Build 全部通過，聊聊 Gate 必須是安裝版 iPhone App 的正式 Gateway 路徑。
- App Store selected Build、main commit、production Brain／Voice／Gateway／Avatar identity、Tokyo DB head與 admin asset 能由一份 manifest 唯一回答。
- 沒有已知 P0；所有 P1 都有 owner、到期日、monitor 或 rollback。
- 至少 7 日 SLO／告警／freshness 資料可信，並完成一次不造成錯扣點、重複 lease 或資料遺失的故障／回滾演練。
- current SSOT 零個已知版本、價格、點數、AI provider、功能狀態或服務部署矛盾。
- L0／L1 變更不被無關的 release／真機 Gate 阻塞；同一證據不需人工重複維護，關鍵 Gate 已自動化或只在風險觸發時執行。

## 更新規則

1. 只有新的可追溯證據才能加分；文件改字本身不加「runtime／human」分。
2. volatile runtime 證據超過 24 小時，發版決策前必須重查。
3. 任一真人回報 FAIL，立即降回 FAIL；修正 PR 在重新包版與真機通過前不得恢復分數。
4. 每次改分數都要列出原分數、新分數、證據、仍缺證據與是否觸發硬上限。
5. 新增文件、表格、審批或 Gate 本身不加分；若造成重複 SSOT、無關阻塞或長期人工同步，應列為治理債務並優先刪減／自動化。
