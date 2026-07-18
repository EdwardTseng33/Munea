# Munea 營運後台資料品質契約

狀態：Current authority

Owner：Data / Operations / Backend

Schema：`munea.admin-data-meta.v1`

## 決策目的

營運後台必須區分「正式來源查得 0」、「正式來源不可用而改讀 fallback」與「來源可讀但新鮮度尚未證明」。任何一種狀態都不能只顯示成相同的 `0` 或「已更新」。

## 每個讀取端點的必要 metadata

每個受保護的 admin read response 必須附上 `meta`：

- `schema`：固定為 `munea.admin-data-meta.v1`。
- `metricVersion`：該指標或資料集的版本，定義變更時必須升版。
- `generatedAt`：本次 API 回應產生時間；不得當作資料更新時間。
- `dataAsOf`：本次結果中可證明的最新資料時間；沒有可信 timestamp 時為 `null`。
- `status`：`unverified`、`empty` 或 `degraded`。
- `degraded`／`degradationReasons`：是否使用 fallback／prototype，以及穩定、不洩密的原因代碼。
- `freshness`：沒有上游 watermark 或 ingestion SLA 證據時必須是 `unknown`。
- `sources[]`：每個實際讀取來源的 dataset、provider、authority、recordCount、dataAsOf 與降級狀態。

## 狀態語意

| 狀態 | 可下的結論 | 不可下的結論 |
|---|---|---|
| `unverified` | 已讀到聲明的來源與資料版本 | 資料一定新鮮 |
| `empty` | 這次讀取回傳 0 筆 | 業務真實值永久為 0 |
| `degraded` | 正在使用 fallback／prototype | 可拿來代表正式 Supabase 全量資料 |
| metadata missing | 舊後端或契約漂移；前端視為未驗證 | 顯示「正常」或「已更新」 |

## 指標選擇與 guardrail

- 主要營運 KPI 維持北極星、活躍人數、聊聊接通率與新訂閱；每個 KPI 必須帶 metric version 與來源 metadata。
- 診斷 driver 使用事件量、通話／Avatar 分鐘、家庭互動與提醒完成。
- guardrail：任何來源降級、metadata 缺失或 freshness unknown，都必須在 KPI 上方顯示可見警示。
- MRR、流失率等尚無完整來源的指標維持 `null`／待接，不可由新購事件推估成正式財務數字。

## 證據邊界

- 成功查詢 Supabase 只能證明 query 成功，不等於 ingestion pipeline 沒延遲。
- `dataAsOf` 是結果中最新 record timestamp，不是資料倉儲 watermark。
- `generatedAt` 只表示後台何時查詢，不能呈現為「資料更新於」。
- JSON fallback 與 instance-local prototype 必須標 `degraded=true`。
- metadata 不得包含例外原文、token、SQL、使用者逐字稿或其他秘密／敏感內容。

## Release Gate

1. `python engine/test_admin_data_quality.py`
2. `node scripts/test-admin-console.js`
3. `npm run smoke:no-api`
4. 部署後使用受保護的 admin smoke 確認所有 console endpoints 都回傳 schema。
5. 後台畫面必須顯示「查詢時間」與「可觀測紀錄最新時間」，並在缺失／降級／freshness unknown 時顯示警示。

來源 PR 合併不等於線上後台已更新；正式 Brain 部署與受保護 smoke 完成後才能記為 live evidence。
