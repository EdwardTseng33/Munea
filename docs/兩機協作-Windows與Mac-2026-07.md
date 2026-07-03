# 兩機協作制度 · Windows（現役）× Mac（打包期加入）
2026-07-03 立 · Apple 開發者已過（Team ID V77L5245MR · 效期 2027/7/4）

## 單一事實來源
- **程式碼**：GitHub `EdwardTseng33/Munea`（main）。鐵律：**開工先拉、收工必推**；每台機器每輪工作＝拉 → 做 → 驗 → 存 → 推。
- **協調**：`docs/協作看板-雙AI分工.md`（誰在做什麼、拍板、交接），跨機跨 AI 都寫這裡。
- **狀態**：`STATUS.md` 每次收工更新（本機做到哪、下一步）。
- **家庭資料**：一律走雲端（家庭存放區 → 之後 Supabase），不存在任何一台電腦上。

## 分工
| 機器 | AI | 職責 |
|---|---|---|
| Windows（此機） | 蘇菲＋Codex | 引擎（AI 腦/感知/記憶）、網頁層、家庭同步、設計規範、文件 |
| Mac（新加入） | Claude（蘇菲同人格，讀同一套憲章/看板/Backlog 開工） | Xcode 打包、真機測試、推播憑證、內購設定、TestFlight 出包、Apple Health 串接 |

## Mac 開工第一天清單
1. 裝 git / Claude Code / Xcode；`git clone https://github.com/EdwardTseng33/Munea.git`
2. 讀順序：docs/產品設計期待-對齊憲章 → 開發總Backlog → 協作看板 → STATUS.md
3. 進 App Store Connect 用 Team V77L5245MR 建 App 條目 + TestFlight
4. Capacitor 打包（`npm run cap:doctor` 起手）→ 真機跑通聊聊
5. 推播憑證 + 內購四檔草稿（價格等 Edward 最後按確認）

## 出包鐵門（不變）
聊聊成熟度計分卡 ≥9/10 綠才進 TestFlight；出包前 Windows 端先鎖版（tag），Mac 只包不改功能。

## 衝突預防
- 同檔避讓：看板先認領；Codex 昨日起的「同車/回改」事件已有前例，**動別人認領的檔前先看看板**。
- 引擎鑰匙等機密：不進程式庫，各機環境變數自管；看板只記「已設定」。
