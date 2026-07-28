# Supabase 環境部署台帳規則

Current machine-readable authority：[`supabase/deployment-ledger.json`](../../supabase/deployment-ledger.json)

這份台帳回答「某支 repo migration 在哪個 Supabase 環境有什麼證據」。它不執行 SQL，也不能把 SQL 檔存在、manifest PASS、歷史文件或 table 可讀，自動升格成已完成 migration。

## 狀態

| 狀態 | 可以下的結論 | 不可以下的結論 |
|---|---|---|
| `unknown` | 尚無足夠證據 | migration 未套用或已套用 |
| `historical-claim` | 過去文件曾聲明此狀態 | 目前仍有效、可作 release gate |
| `verified` | 具名環境、checksum、時間、source commit 與證據已通過審查 | 其他環境也相同 |
| `blocked` | 已知缺少核准、備份、migration 或驗收條件 | 可直接執行 |

`verifiedHead` 只可由 ledger 從第一支 migration 起連續具有完整 verified evidence 的 chain 推導；中間出現 historical／unknown／blocked 就不能跳過。沒有連續 verified chain 時必須為 `null`。

## 更新流程

1. 先確認目標 project ref、region、目前備份與 rollback target；不得靠 URL 名稱猜環境。
2. 將 migration checksum 與 `supabase/migration-manifest.json` 對齊。
3. Schema／seed migration 必須保存核准的執行紀錄與 read-only post-check；證據要綁定 migration、source commit、環境與時間。
4. `data-cleanup` 必須另外保存 approval、backup、pre-check 與 post-check。沒有四項證據不得標 `verified`。
5. 證據不得包含 service-role key、JWT、SQL Editor session、使用者資料或逐筆敏感 payload。
6. 更新 ledger 後執行：
   - `npm run test:supabase-governance`
   - `npm run test:product-alignment`
   - `npm run release:check`

Secret-safe 的東京唯讀觀測命令是 `npm run supabase:deployment:probe`。它只送 GET，拒絕 project ref 不符，輸出不含 key 或逐筆資料；`017` 檢查 table reachability、`019` 檢查 active policy v4 的 100／200 點，`018` 只回 photo key 筆數且永遠標示 partial，不能取代核准、備份與完整前後驗收。

## 東京目前邊界

- `001`–`016` 只有歷史聲明，尚未轉成 current verified ledger。
- 2026-07-18 07:12 UTC 透過 Cloud Run 現行東京 Secret reference 執行 GET-only probe：目標與觀測 project ref 都是 `fespbkdwafueyonppzwq`，且沒有寫入。
- `017` 的 `notification_settings` 在東京回 `HTTP 404`，因此由 unknown 改為 `blocked`；這是 live 不可用證據，不是 migration 執行授權。
- `019` 可到達 policy table，但找不到 active v4 Plus 100／Pro 200 policy，因此由 unknown 改為 `blocked`。
- `018` 的 photo-key 計數為 0，但探針沒有掃描完整 `data:` payload，也沒有核准、備份與完整前後筆數，仍保持 `blocked`。
- 更早的本機 probe 曾因共享 backend env 指向 Sydney 而在 HTTP 前 fail closed；新證據已改由 Cloud Run 的東京 secret reference 取得，不代表本機 `.env.local` 已被修改。
- Sydney rollback project 只有歷史保留聲明；正式切回前仍需重新確認可用性與 secrets／Gateway revision／重新登入步驟。
- 2026-07-24 對 `023_test_account_flag.sql`／`024_inactive_free_account_retention.sql`／`025_person_profile_fields.sql` 執行唯讀觀測，三支欄位／函式已存在於東京，狀態由 `unknown` 改為 `verified`（`captureMethod=read-only-probe`、`sourceCommit=8ddab84c`）；證據見 `STATUS.md`（129 號）。`020`／`021`／`022`／`026` 仍未套用，維持 `unknown`，等 Edward 手動貼 SQL。

修改本文件或 JSON 不等於部署，也不授權 migration、資料清理、traffic shift 或刪除任一 Supabase project。
