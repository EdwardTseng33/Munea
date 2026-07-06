# STATUS · 2026-07-06（Mac 機 · Claude/蘇菲）

## Mac 端上工 · 環境對齊 + TestFlight 前置補齊
- ✅ **開工先拉**：本機曾落後遠端 **273 版**，已乾淨快轉到最新（真腦上線／記憶閉環／北歐改版／上架文件包全到）；本機獨有 `ios/` 殼與 `assets/` 完整保留並備份。
- ✅ **Apple 開發者帳號確認已開通**（Team `V77L5245MR`、效期 2027/7/4）——TestFlight 不再卡帳號。
- ✅ **補齊 iOS 權限字串**（麥克風／語音／通知）進 `ios/App/App/Info.plist`（真機測聊聊硬前置、先前缺）；`plutil` 驗證 OK；最新網頁已 `cap sync` 進殼。
- ✅ **Mac 環境體檢**（`npm run mac:doctor`）：git/node v24/npm/npx/Xcode 26.6 全通；缺 PowerShell（跑 smoke/release-check 才需：`brew install --cask powershell`）。
- 🔴 **這台 Mac 尚無簽章憑證**（`security find-identity` = 0）——需 Edward 開一次 Xcode 選 Team `V77L5245MR` 讓它自動建憑證，才能 Archive→上傳。帳號在 Apple 端已通，只差這台電腦生憑證。
- 🎯 **聊聊衝 9/10 綠的 5 項**（真語音接通／斷網優雅退場／回話延遲<1.5s／嘴型同步／講話中可打斷）＝**Mac＋真機＋真語音**、Windows 做不了、是 Mac 主戰場。第 1 項（真語音接通）為關鍵、其他都依賴它。現況計分卡 5 綠 2 黃 3 紅。

**下一步**：① Edward 開 Xcode 建憑證（一次性）＋插 iPhone ② Mac 端把聊聊「嘴巴接上」（web 聊聊接 `/voice-session`、`/voice-note` 真語音鏈、`engine/live_voice_*`）③ 真機跑 10 分鐘通話驗第 1／8 項。

---

# STATUS · 2026-07-04 凌晨（Windows 機 · 蘇菲）
- 深夜大戰果：真腦上線（文字通道、App 內 18.8s 實證）＋記憶迴圈閉環＋紅線 13/13 滿分＋上架文件包過沙利曼＋北歐改造兩波（女巫五輪把關到 PASS）＋CI 郵件轟炸止血（119/1925 回 App）。
- 聊聊計分卡 65%；上架準備 65%；北歐質感收官（留：卡片錯位進場已上、B9b 殘項小）。
- 雲端 4 表仍等 Codex（相關功能本機檔頂著）；Mac 階段清單見 docs/兩機協作。
