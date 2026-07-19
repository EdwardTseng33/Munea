# 服務 SLO 證據契約

更新：2026-07-19
適用：`.github/workflows/service-watchdog.yml`、`.github/workflows/service-slo-report.yml`

## 目的與邊界

這組證據回答「公開服務門面是否持續可達、排程是否真的有跑」，用來補足架構、API 與營運可觀測性的 7 日證據。它是 **synthetic control-plane** 監控，不是 App 真實用戶旅程；因此不能單獨證明登入、購買、點數、聊聊接通或通話品質正常，也不會取代 iPhone 安裝版驗收。

監控只送匿名 GET 到既有公開端點，不寫入正式資料、不建立通話、不扣點、不改流量。JSON artifact 不含 token、webhook、回應本文、用戶資料或 workflow run 明細。

## 證據來源

1. `Service watchdog`：設定為每 5 分鐘巡一次 8 個既有端點；單次失敗 10 秒後重試，仍失敗才讓 workflow 紅燈並走既有 Slack 告警。實際排程可能漏跑，完整性以報表的 coverage 為準，不以 cron 設定推定。
2. `Service SLO evidence`：每日台北時間 00:17 產生：
   - `current-snapshot.json`：當下每個端點的 HTTP 狀態、延遲、嘗試次數與是否重試恢復。
   - `rolling-7d.json`：由 GitHub Actions 歷史計算最近 7 日排程覆蓋與保守可用率。
3. artifact 保留 14 日；每日一份，不在每個 5 分鐘 run 上傳 artifact，避免一週產生 2,016 份小檔。

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
- 優先後續：先觀察合併後的 daily artifact；若 coverage 持續不足，將固定頻率監控移至 Cloud Monitoring uptime check／Cloud Scheduler 等有執行保證與告警的正式控制面。這會涉及雲端設定，另案審核後再部署。

## 延遲的正確說法

每日快照可用來建立 synthetic latency 趨勢，但每日一個樣本不能宣稱為正式流量 p95。正式 p95 接通時間仍需 App／Gateway／Voice 的同一個匿名 trace 串接，且要有明確的「開始通話」分母與「可聽見第一句」成功事件。

## 啟用與驗收

```powershell
node scripts/test-service-watchdog.js
node scripts/service-watchdog.mjs --dry-run
```

合併主線後可手動觸發一次 `Service SLO evidence` 驗證權限、API 分頁與 artifact；7 日證據時鐘從 workflow 進入預設分支後才開始。未滿 7 日以前，健康度分數保持原值，只能標記「收集中」。

## 不影響線上服務的護欄

- 僅 `GET` 公開健康門面；不呼叫登入、購買、扣點、通話 offer 或管理後台寫入。
- workflow 權限只有 `actions: read`、`contents: read`。
- 當下探測失敗仍先上傳已有證據，最後保留紅燈，不把事故吃掉。
- 所有計算有契約測試鎖定：2,016 分母、手動 run 排除、漏跑降低保守可用率、快照不含密鑰／回應本文。
