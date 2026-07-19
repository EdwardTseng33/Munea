# Munea 輕量多 Agent 協作方式

## 目的

讓 Claude、Codex、Mac、Windows 與不同 session 可以平行工作，但不要同時修改同一份檔案，也不要到合併時才發現彼此覆蓋。

不使用 JSON 鎖、租期、lock-only PR 或路徑鎖 CI。協作資訊放在兩個大家都看得到的地方：

1. `docs/協作看板-雙AI分工.md`：較長或跨模組任務的分工與產品脈絡。
2. GitHub 開啟中的 PR：目前實際分支、變更檔案、進度與跨電腦交接。

## 1 人＋AI 的預設治理

這是小型產品團隊的安全協作方式，不是大型企業審批流程。預設讓 AI 在已授權範圍內持續推進，只有具名風險需要對應 Gate：

- L0 文件／不改行為：scoped diff 與必要格式檢查即可。
- L1 可逆、非 P0 程式變更：跑相關測試與 CI；不要求無關的完整 release／真機流程。
- L2 runtime／設定／相容性資料變更：plan、preview 或 canary，搭配受影響 smoke 與 rollback。
- L3 登入、購買、點數、聊聊、隱私資料、破壞性 migration、App Store 等 P0／不可逆動作：才使用完整受影響 E2E 與人工確認。

一個任務原則上只有一個 branch、一個 PR、一組可重用證據。已有 SSOT 就更新原處；不為同一結果建立第二份人工報表。新增 Gate 前必須回答「降低哪個具名風險、何時觸發、最小證據是什麼、何時可自動化或移除」。答不出來就不新增。

## 開始工作

1. `git fetch origin`，先看協作看板和開啟中的 PR。
2. 每個 session 使用自己唯一的 branch。同一台電腦已有 dirty checkout 或其他 session 時，另外建立 worktree。
3. 在任務說明或 Draft PR 列出預計修改的檔案；長時間或跨模組任務再補一筆看板紀錄。
4. 若已有 session 修改同一檔案，採先後交接：第一位完成並合併，第二位同步最新 `origin/main` 後再接。不要開兩份互相競爭的同檔版本。
5. 不同檔案可以直接平行，不需要等待或取得鎖。

## 工作中與合併

- 一個實作任務只需要一個 PR；不另外開鎖定 PR。
- 小步 commit，只提交自己的範圍，不混入另一個 worktree 或 dirty main 的內容。
- 不 force push `main`、不 reset 或刪除別人的未完成內容。
- 合併前同步最新 `origin/main` 並跑**該風險等級的相關測試**；只有 release candidate 或 L2／L3 受影響範圍才需要較完整 Gate。
- 發生衝突時，比對兩邊目的後整合；看不懂對方意圖就通知對方，不直接選 ours/theirs。
- PR 合併後，長期任務在看板標記完成，下一個需要同檔案的 session 再接手。

## 聊聊撥通 App 端到端硬 Gate

凡是可能影響聊聊通話鏈的變更，都要在任務／PR 標記「call-path risk」。範圍包含 App／WebView、iOS 包版、登入、onboarding／account bootstrap、方案／點數、Gateway／Call Control、Voice、Avatar／GPU、服務 URL／環境變數、權限、CORS、部署與 fallback；不能因為只改後端、文件宣稱「不影響 App」，就省略最終 App 驗收。

單元測試、瀏覽器測試頁、服務 `/health`、WebSocket／API 探針都只是前置檢查，不能代替下列真機 Gate：

1. 使用本次實際要驗的版本、Build、profile 與環境，完成 `cap sync`、安裝並啟動 iPhone App。
2. 在 App 內進入聊聊並按下通話，確認麥克風權限、登入／帳戶初始化／點數與 Gateway 領席（或明確記錄的 developer-direct 路徑）通過。
3. 確認 Voice 與 Avatar 都 ready、聽得到開場；使用 iPhone 麥克風說一句話，伺服器收到上行，App 聽得到 AI 回話且看得到預期畫面／字幕。
4. 主動掛斷，確認通話、麥克風、WebSocket 與 Gateway lease／GPU 席位正確釋放。
5. 在 PR 與 `STATUS.md` 或 `docs/RELEASE-STATE.md` 記錄：版本／Build、profile、環境與服務 revision、裝置、時間、結果及日誌／診斷證據。

developer-direct 包只能驗直連測試路，不能替代真登入＋Gateway／Release 路徑。若當下沒有實體 App 可測，狀態只能寫 `App E2E pending`；可以保留 staged／merged 事實，但不得宣稱 verified、可上線、可送審或任務完成。

## 跨電腦交接範例

- Windows 正在改 `web/src/app.js`：在 Draft PR 或看板標明。Mac 可以同時處理 `ios/`，但暫不另改 `web/src/app.js`。
- Windows 的 PR 合併後，Mac 執行 `git fetch origin` 並把自己的 branch 更新到最新 `origin/main`，再開始 App 同檔修改。
- 如果兩項工作只碰不同檔案，兩邊照常平行並各自開 PR。

## GitHub main 保護

`main` 保留最小保護：透過 PR 合併、禁止 force push 與刪除。沒有強制鎖定檢查，也不要求另一位真人核准；目的是避免覆蓋，不是增加流程。
