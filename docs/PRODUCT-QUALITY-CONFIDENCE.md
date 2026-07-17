# Munea 產品品質信心

更新：`2026-07-18 00:25 Asia/Taipei`

來源基準：`origin/main@a53655c`

本文件是目前「能不能放心把這一版交給使用者」的評分 SSOT。它不取代 [`RELEASE-STATE.md`](./RELEASE-STATE.md) 的版本／部署事實，也不把程式存在、測試通過、已合併、已部署或真機通過混成同一個「完成」。

## CTO 結論

**目前產品品質信心：69/100，未達 90。**

這不代表系統只有 69 分的工程能力；它代表目前缺少足以支持「上線可放心」的完整證據。主因是 Google／帳號、會員與點數購買、0 點通話預檢、真實聊聊撥通仍沒有同一個 Build 的完整 iPhone 驗收紀錄；Build 48 修正仍在 Draft PR；App `1.0.40`、production Brain `1.0.36`、production Voice `1.0.31`、staging `1.0.34` 與 DB migration 狀態也不是同一條 release timeline。

在任何 P0 關鍵旅程失敗或缺少真機閉環時，整體分數最高只能是 69。自動測試全綠可以提高工程信心，不能解除這個上限。

## 評分模型

| 面向 | 權重 | 目前分數 | 加權貢獻 | 判斷 |
|---|---:|---:|---:|---|
| 1. 架構與復原能力 | 15% | 78 | 11.7 | 服務分層、canary 與 rollback 基礎存在；缺 7 日 SLO、完整故障演練及 App 真鏈路證據 |
| 2. API／服務可靠性與安全 | 15% | 80 | 12.0 | release identity、權限與契約測試良好；Gateway identity、authenticated call trace 與一致監控端點仍不足 |
| 3. App 與後端程式品質 | 20% | 64 | 12.8 | release gate 強，但 #174／#175 尚未合併、包版與真機驗收，關鍵旅程不得標 verified |
| 4. Repo／資料／migration 治理 | 15% | 62 | 9.3 | migration manifest 可阻擋漂移，但 main 的 `019` 原先未登記；live `017`／`018`／`019` 沒有新 ledger 證據 |
| 5. 產品／版本／AI／服務對焦 | 20% | 58 | 11.6 | Build 47、runtime、Draft Build 48、DB 與多份 current 文件不同步，是目前最低分項 |
| 6. 營運後台與可觀測性 | 15% | 74 | 11.1 | staging 後台 shell 與安全 headers 可用；特權資料來源、新鮮度、RBAC／MFA 與 7 日營運指標未證明 |
| **加權結果** | **100%** |  | **68.5 → 69** | **P0 真機關鍵旅程上限同為 69** |

### 每個面向如何得分

每個面向都依相同證據梯度計分：

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

| 證據 | 2026-07-18 判讀 |
|---|---|
| Source／App | `origin/main@a53655c`；source、Web、package 與 iOS 為 `1.0.40 (Build 47)`；STATUS 記錄 20:44 上傳成功與 Edward iPhone 換裝成功 |
| App Store | Build 47 已上傳；精確 selected Build 與 Apple review state 未由本輪 App Store Connect 證據確認，因此保持 `unknown` |
| 待驗修正 | Draft #174：0 點不進入「撥通中」；Draft #175：TEST 本機購買模擬與 Apple account-token mismatch 說明。兩者均未計為 merged／packaged／human verified |
| Production Brain | 公開 `/version` 回 `1.0.36@d6a72a1`，revision `munea-brain-00004-leb` |
| Production Voice | 公開 `/version` 回 `1.0.31@500c819`，revision `munea-voice-00002-sub` |
| Staging Brain／Voice | 服務端點分別回 `1.0.34@136dc81`，revisions `00061-dow`／`00051-qom` |
| Gateway | 公開 `/health` 無憑證回 401，證明 auth boundary；release identity 與真實 App lease／cleanup trace仍未知 |
| 營運後台 | staging `/admin.html` 回 200，CSP 與 `X-Frame-Options: DENY` 存在；privileged metrics、Tokyo source 與 freshness 未驗 |
| Repo migration | source 已有 `019_pricing_plus100_pro200.sql`；本輪修正其原先未列入 manifest 的治理缺口。這不代表 Tokyo 已套用 |
| Live DB | `017`／`018`／`019` 本輪沒有新的 approved ledger 與 live read-only proof，全部不得標 ready |

## 關鍵旅程信心

| 關鍵旅程 | Source／測試 | Build 47 真機 | 判定 |
|---|---|---|---|
| Google 登入 → session → 登出重登 | fallback 修正已進 source／Build | 缺同一份完整驗收紀錄 | `partial` |
| 會員購買 → entitlement 改變 → 點數入口 | 自動契約存在；#175 補錯誤與 TEST 行為 | 使用者回報無法改變身分／看不到後續；新版未驗 | `fail / draft fix` |
| 0 點按通話 → 立即說明、不顯示撥通中 | #174 自動測試通過 | Build 47 尚未包含 #174 | `fail / draft fix` |
| 有點數真帳號 → Gateway → Voice＋Avatar → 掛斷釋放 | synthetic／服務契約存在 | 缺精確 Build＋revision 的完整 iPhone 證據 | `unknown` |

目前「完整通過且有可追溯證據」為 `0/4`。這是證據缺口統計，不等於四條路徑都必然壞掉；任何一條只有口頭成功、沒有 Build／環境／revision／時間記錄，仍不算通過。

## 從 69 推到 90 的順序

### P0：先解除上線硬上限

1. 依序完成 #174、#175 的審查與整合，從最新 main 產出同一個 Build 48；不要把 stacked Draft 直接當成可包版主線。
2. iPhone 分別驗：Google 真帳號、TEST 身分、0 點真帳號、有點數真帳號、Sandbox Apple ID。記錄 Build、profile、Brain／Voice／Gateway／Avatar revision、時間與結果。
3. Apple account-token mismatch 必須以換／重置 Sandbox 帳號解決；不得放寬伺服器綁定，也不得重複扣款測試。
4. App Store Connect 的商品售價／描述與 Build 47 畫面一致後，才能決定送審 Build；selected Build 與 review state 回寫 `RELEASE-STATE.md`。
5. 以核准的 backup／ledger 流程處理 Tokyo `017`／`018`／`019`，逐支做 read-only post-check；本文件更新不能代替執行證據。

### P1：把單次驗收變成可持續信心

1. 為 production Brain／Voice／Gateway／Avatar 建立單一 release manifest 與 signed App E2E attestation。
2. 後台顯示 source project、service revision、DB head、資料最後事件時間、fallback 狀態與指標定義版本。
3. 建立 7 日 dashboard：登入成功率、購買驗證成功率、call setup success、p95 接通時間、通話中斷率、點數扣除／退款異常、admin data freshness。
4. 在 CI 增加 current-doc freshness／版本漂移 gate，並維持 migration file 與 manifest 的零漂移。

## 90 分的最低條件

- 四條關鍵旅程在同一候選 Build 全部通過，聊聊 Gate 必須是安裝版 iPhone App 的正式 Gateway 路徑。
- App Store selected Build、main commit、production Brain／Voice／Gateway／Avatar identity、Tokyo DB head與 admin asset 能由一份 manifest 唯一回答。
- 沒有已知 P0；所有 P1 都有 owner、到期日、monitor 或 rollback。
- 至少 7 日 SLO／告警／freshness 資料可信，並完成一次不造成錯扣點、重複 lease 或資料遺失的故障／回滾演練。
- current SSOT 零個已知版本、價格、點數、AI provider、功能狀態或服務部署矛盾。

## 更新規則

1. 只有新的可追溯證據才能加分；文件改字本身不加「runtime／human」分。
2. volatile runtime 證據超過 24 小時，發版決策前必須重查。
3. 任一真人回報 FAIL，立即降回 FAIL；修正 PR 在重新包版與真機通過前不得恢復分數。
4. 每次改分數都要列出原分數、新分數、證據、仍缺證據與是否觸發硬上限。
