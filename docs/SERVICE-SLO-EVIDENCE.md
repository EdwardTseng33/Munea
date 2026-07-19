# 服務 SLO 證據契約

更新：2026-07-19
適用：`.github/workflows/service-watchdog.yml`、`.github/workflows/service-slo-report.yml`、`deploy/monitoring/uptime-checks.json`

## 目的與邊界

這組證據回答「公開服務門面是否持續可達、排程是否真的有跑」，用來補足架構、API 與營運可觀測性的 7 日證據。它是 **synthetic control-plane** 監控，不是 App 真實用戶旅程；因此不能單獨證明登入、購買、點數、聊聊接通或通話品質正常，也不會取代 iPhone 安裝版驗收。

監控只送匿名 GET 到既有公開端點，不寫入正式資料、不建立通話、不扣點、不改流量。JSON artifact 不含 token、webhook、回應本文、用戶資料或 workflow run 明細。

## 證據來源

1. `Service watchdog`：設定為每 5 分鐘巡一次 8 個既有端點；單次失敗 10 秒後重試，仍失敗才讓 workflow 紅燈並走既有 Slack 告警。實際排程可能漏跑，完整性以報表的 coverage 為準，不以 cron 設定推定。
2. `Service SLO evidence`：每日台北時間 00:17 產生：
   - `current-snapshot.json`：當下每個端點的 HTTP 狀態、延遲、嘗試次數與是否重試恢復。
   - `rolling-7d.json`：由 GitHub Actions 歷史計算最近 7 日排程覆蓋與保守可用率。
3. artifact 保留 14 日；每日一份，不在每個 5 分鐘 run 上傳 artifact，避免一週產生 2,016 份小檔。

## 正式固定頻率控制面

GitHub Actions cron 不保證準時或每次執行，因此它保留作為 repo 外部 watchdog／Slack 備援，不再被當成 5 分鐘 SLO 的唯一分母。正式固定頻率來源定義在 `deploy/monitoring/uptime-checks.json`：

- 8 個 target 與 `scripts/service-watchdog.mjs` 完全一致，契約測試會阻擋 URL／status／JSON `ok=true` 漂移。
- 每 5 分鐘由 `asia-pacific`、`europe`、`usa-oregon` 三區執行，timeout 15 秒、HTTPS 憑證必須有效。
- Gateway 匿名 401 與 monitor 403 是預期的「服務活著且鎖著」，不可改成只接受 2xx。
- 每月預估 `8 × 3 × 12 × 24 × 30 = 207,360` executions，低於 [Google Cloud Monitoring pricing](https://cloud.google.com/stackdriver/pricing) 所列每專案每月 100 萬 uptime-check executions 免費額度。若 target、區域或頻率改變，必須重算。
- Cloud Monitoring 的 metrics 用於正式 coverage／latency 趨勢；現有 Gateway monitor 每 60 秒檢查容量並走 Slack，GitHub watchdog 繼續作為跨控制面的備援。尚未建立 Cloud Monitoring alert policy，不得宣稱八個 uptime checks 已有即時通知閉環。

### 2026-07-19 live 啟用證據

- PR #194 建立 repo-managed manifest／plan/apply 控制面；PR #195、#196、#197 補齊 Windows gcloud 成功 stderr、create/update 狀態碼旗標與 update 保留建立期 identity labels 的回歸保護。
- `gen-lang-client-0229303523` 已啟用 **8 個 checks**，全部為 5 分鐘、15 秒 timeout、`ASIA_PACIFIC`／`EUROPE`／`USA_OREGON` 三區；再次 plan 為 **8 update、0 create、0 delete**。
- Monitoring `check_passed` 最近 30 分鐘已出現 **24 條時序（8 checks × 3 checker locations）**，新加坡、比利時、奧勒岡的最新樣本全為 `true`。這證明固定頻率控制面已運作，但資料尚未滿 7 日，所以健康度仍不加分。
- 套用只改 Cloud Monitoring 控制面；沒有 App 重包、Cloud Run revision／流量切換、DB migration、購買／點數或聊聊通話路徑變更。

部署腳本預設只有 plan，不會修改雲端：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/cloud-monitoring-uptime.ps1
```

PR 合併、plan review 通過後，才可明確加入 `-Apply`。腳本只 create／update 帶 `managed_by=munea_repo`、`component=service_slo`、`target_id` 的資源，不會自動 delete；host 改變時會硬擋，必須另做具名 migration，以免重建 check ID 讓歷史斷線。

## 7 日分母與公式

時間窗採半開區間 `[from, to)`；5 分鐘一次、完整 7 日的預期格數固定為：

`7 × 24 × 60 ÷ 5 = 2,016 slots`

只接受 `event=schedule` 且 `status=completed` 的 `Service watchdog` run；手動觸發、進行中 run 不得灌入完成分母。

| 指標 | 公式 | 解讀 |
|---|---|---|
| 排程覆蓋率 | completed scheduled slots ÷ 2,016 | 監控證據是否完整 |
| 已觀測成功率 | successful slots ÷ completed scheduled slots | 只看實際完成的巡邏 |
| 保守可用率 | successful slots ÷ 2,016 | 漏跑排程也視為不可證明，避免美化 |
| 保守不可用率 | (2,016 − successful slots) ÷ 2,016 | 包含失敗、取消與漏跑 |

`evidenceReady=true` 只表示完整 168 小時且排程覆蓋率至少 95%，**不表示產品達 90 分，也不表示服務達成任何尚未核定的商業 SLO**。

## 2026-07-19 首次唯讀驗證

- GitHub Actions 真實 history API 相容性通過；2026-07-18 00:00Z 至 2026-07-19 00:00Z 共完成 `18/288` 個 scheduled slots。
- 已完成的 18 次皆成功，所以「已觀測成功率」為 `100%`；但排程覆蓋率與保守可用率都只有 `6.25%`。這證明只報成功率會誤導，也代表目前 GitHub 排程不能作為 5 分鐘 SLO 的充分證據。
- 2026-07-19 04:16Z 單輪 8 個端點全數通過；單次 synthetic latency 中正式 Voice 約 `8,709 ms`、staging Voice 約 `3,568 ms`，其餘約 `54–262 ms`。這可能包含冷啟動，只有一個樣本，不是 p95，也不是通話接通時間。
- 優先後續：讓已啟用的 repo-managed Cloud Monitoring uptime checks 累積完整 7 日，再以 Cloud Monitoring 時序取代 GitHub schedule 作為正式 7 日分母。告警通知仍需另外完成與既有 Slack 相容的 relay／channel，不能把 Slack incoming webhook 直接當作 Cloud Monitoring incident webhook。

## 延遲的正確說法

每日快照可用來建立 synthetic latency 趨勢，但每日一個樣本不能宣稱為正式流量 p95。正式 p95 接通時間仍需 App／Gateway／Voice 的同一個匿名 trace 串接，且要有明確的「開始通話」分母與「可聽見第一句」成功事件。

## 啟用與驗收

```powershell
node scripts/test-service-watchdog.js
node scripts/service-watchdog.mjs --dry-run
```

合併主線後可手動觸發一次 `Service SLO evidence` 驗證權限、API 分頁與 artifact；7 日證據時鐘從 workflow 進入預設分支後才開始。未滿 7 日以前，健康度分數保持原值，只能標記「收集中」。

Cloud Monitoring 啟用後驗收：

```powershell
gcloud monitoring uptime list-configs --project=gen-lang-client-0229303523
```

必須看到 8 個帶 repo-managed labels 的 checks，且實際 metric 已從三區出現。需要回滾時逐筆 `gcloud monitoring uptime delete CHECK_ID`；刪除會中斷 check ID 的歷史，所以必須先匯出設定／證據並經人工核准，部署腳本刻意不提供自動刪除。

## 不影響線上服務的護欄

- 僅 `GET` 公開健康門面；不呼叫登入、購買、扣點、通話 offer 或管理後台寫入。
- workflow 權限只有 `actions: read`、`contents: read`。
- 當下探測失敗仍先上傳已有證據，最後保留紅燈，不把事故吃掉。
- 所有計算有契約測試鎖定：2,016 分母、手動 run 排除、漏跑降低保守可用率、快照不含密鑰／回應本文。
