# Munea 輕量多 Agent 協作方式

## 目的

讓 Claude、Codex、Mac、Windows 與不同 session 可以平行工作，但不要同時修改同一份檔案，也不要到合併時才發現彼此覆蓋。

不使用 JSON 鎖、租期、lock-only PR 或路徑鎖 CI。協作資訊放在兩個大家都看得到的地方：

1. `docs/協作看板-雙AI分工.md`：較長或跨模組任務的分工與產品脈絡。
2. GitHub 開啟中的 PR：目前實際分支、變更檔案、進度與跨電腦交接。

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
- 合併前同步最新 `origin/main` 並跑相關測試。
- 發生衝突時，比對兩邊目的後整合；看不懂對方意圖就通知對方，不直接選 ours/theirs。
- PR 合併後，長期任務在看板標記完成，下一個需要同檔案的 session 再接手。

## 跨電腦交接範例

- Windows 正在改 `web/src/app.js`：在 Draft PR 或看板標明。Mac 可以同時處理 `ios/`，但暫不另改 `web/src/app.js`。
- Windows 的 PR 合併後，Mac 執行 `git fetch origin` 並把自己的 branch 更新到最新 `origin/main`，再開始 App 同檔修改。
- 如果兩項工作只碰不同檔案，兩邊照常平行並各自開 PR。

## GitHub main 保護

`main` 保留最小保護：透過 PR 合併、禁止 force push 與刪除。沒有強制鎖定檢查，也不要求另一位真人核准；目的是避免覆蓋，不是增加流程。
