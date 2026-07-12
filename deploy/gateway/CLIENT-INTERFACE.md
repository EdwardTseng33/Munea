# 聊聊分流閘道 · Client 對接規格（給 Codex 接 app.js 用）

> 2026-07-12 卡西法出。對應設計文件 `docs/多人併發容量架構-2026-07-12.md` §5.2 + §5.4。
> 卡西法這輪只做後端＋資料流＋介面——**app.js 怎麼接、排隊畫面長什麼樣，是 Codex 的地盤**。
> 這份文件只定「打哪支 API、傳什麼、收什麼」。

## 現況 vs 未來（重要，先讀）

閘道服務（`deploy/gateway/gateway_server.py`）**這輪還沒真的部署到任何地方**——沒開真卡、
沒接真的 worker。app.js 目前仍然是直連單一 avatar URL（`getAvatarUrl()`），這份規格是給
「閘道正式上線那天」用的對接契約，讓 Codex 現在就能照著寫、等閘道部署好直接接線，不用等。

在閘道正式接上之前，**不要動 `web/src/app.js:3216-3222`（滿載退純語音那段）**——按照
架構文件 §5.1，那段要整段拔掉換成排隊流程，但拔掉前必須先有閘道真的在跑，否則滿載時
使用者會什麼反應都沒有（比現在的退化語音還糟）。這步驟順序很重要：**先部署閘道 + 接好
下面這幾支 API，測試過排隊流程真的會觸發，才能拔掉舊的退化邏輯。**

## Base URL

閘道跟 avatar 引擎是兩個獨立服務（CPU-only vs GPU），會有自己的網址，先假設
`GATEWAY_URL`（環境變數/設定檔決定，跟現有 `munea.avatarUrl` 平行放）。

## 認證

所有端點都吃 `?key=<通行碼>` query 參數（跟現有 `MUNEA_APP_KEY` 同一套模式，沿用
`encodeURIComponent(MUNEA_APP_KEY)` 那條既有邏輯即可，不需要新鑰匙）。

## 三支 client 端點

### 1. 按下撥通 → 請求配對

```
POST {GATEWAY_URL}/v1/call/request?client_id=<裝置或使用者唯一 ID>&key=<通行碼>
```

回應三種形狀之一：

**有空位，直接配到 worker：**
```json
{"status": "connect", "worker": {"worker_id": "glows-tw-03", "url": "https://tw-06.access.glows.ai:25220"}}
```
→ client 拿到 `worker.url` 後，**直接照現有邏輯打那台 worker 的 `/offer`**（沿用
`web/src/app.js` 現有的 WebRTC 交握流程，只是 URL 從 `getAvatarUrl()` 固定值換成
這裡動態拿到的 `worker.url`）——media 面完全不繞閘道，這是設計文件 §2.1 的核心。

**沒空位，進佇列：**
```json
{"status": "queued", "queue": {"position": 3, "eta_s": 360.0, "depth": 5}}
```
→ 顯示「排第 `position` 位，預估等待約 `eta_s` 秒」（UX 怎麼呈現是 Codex/女巫的活），
畫面維持待機動畫、**不接通、不計費、不消耗點數**。接著開始輪詢（見第 2 支端點）。

**佇列已滿，真拒絕：**
```json
{"status": "reject", "reason": "queue_full"}
```
→ 這是唯一保留的「真拒絕」出口（§5.2 第4點）。告知使用者「現在真的很忙」，
不要靜默失敗、不要偷偷退化成純語音。

### 2. 排隊中心跳／輪詢（同時當「我還在線上」的訊號）

```
GET {GATEWAY_URL}/v1/call/poll?client_id=<同上>&key=<通行碼>
```

建議輪詢頻率：3-5 秒一次（心跳太密集浪費、太疏會讓「離線判定」不準）。回應形狀跟
`/call/request` 完全一樣（`connect` / `queued` / `unknown`）：

- 收到 `queued` → 更新畫面上的排隊位置/預估時間，繼續輪詢
- 收到 `connect` → 排到了！照第 1 支端點「connect」分支的方式接上 `worker.url`
- 收到 `{"status": "unknown"}` → 閘道不認得這個 client_id 了（可能閘道重啟過或
  這個 client 從沒排過隊），回到「按下撥通」重新走一次第 1 支端點

**App 被切到背景太久**：輪到時用 push notification 叫回來（§5.2 第3點最後一句），
push 邏輯不在閘道這裡，是既有的推播機制去打。

### 3. 使用者主動取消排隊

```
POST {GATEWAY_URL}/v1/call/cancel?client_id=<同上>&key=<通行碼>
```
回應：`{"cancelled_queue": true/false, "cancelled_assignment": true/false}`——
使用者離開排隊畫面、或主動按「取消排隊」時打這支，不留殘留佔位（§5.2 第5點）。

## worker 端 webhook（不是 client 打的，是 avatar 引擎通話結束時打的）

```
POST {GATEWAY_URL}/v1/call/release?key=<通行碼>
Body: {"worker_id": "glows-tw-03", "duration_s": 187.4}
```

`flashhead_server.py`（或包在它外面的一層小腳本）在通話真正掛斷時打這支，讓閘道：
1. 把該 worker 的占用槽位 -1
2. 把這次通話時長記進滾動平均（下次排隊 ETA 估算會更準）
3. 自動嘗試把佇列最前面還在線的人接上（這步是閘道自己做的，client 只要繼續輪詢
   `/call/poll` 就會自然收到 `connect`）

**這輪還沒接**：`flashhead_server.py` 目前沒有呼叫這支 webhook 的程式碼（本輪任務
邊界內只做了 N 槽改造，閘道整合是下一步）。等閘道正式部署、worker 也登記進閘道後，
要在 `flashhead_server.py` 的 `_release_session()` 或 pc 斷線回調裡補上這通 HTTP 呼叫。

## 決策流程圖（跟架構文件 §5.4 一致）

```
按下撥通
 │
 ├─ 顯卡+語音都有空位 → POST /call/request 回 connect → 直連 worker.url 打 /offer
 │
 ├─ 沒空位、佇列 < 上限 → POST /call/request 回 queued → 顯示位置+預估等待、開始輪詢
 │      └─ GET /call/poll 收到 connect → 自動接通
 │      └─ 使用者離線/取消 → POST /call/cancel
 │
 └─ 佇列已滿 → POST /call/request 回 reject → 明確告知「現在真的很忙」
```

## 現在可以先做的事（不等閘道部署）

Codex 若想先把排隊 UI 元件、輪詢邏輯的殼寫好（元件化、之後直接接真 API），可以先對著
這份規格的 JSON 形狀寫 mock（固定回傳 `queued`/`connect`/`reject` 幾種假資料），排隊
畫面、動畫、文案都可以先做，只是先不要拔掉 `app.js:3216-3222` 那段舊的退化邏輯，等
真的接上閘道、測過排隊流程真的會觸發，才能拔。
