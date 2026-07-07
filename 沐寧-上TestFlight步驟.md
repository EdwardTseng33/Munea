# 🍎 沐寧 Munea · 上 TestFlight 步驟單（白話版）

> 2026-06-28 蘇菲建立。展示版（點得動的 demo）包成 iPhone App、上 TestFlight。
> **我（蘇菲）已經把能用指令做的全做完了**；剩下的是「只有你能做」的步驟，照這份點。

---

## 現在的狀態（一眼看懂）

- ✅ **App 殼已經搭好**：`/Users/edward/Claude/Munea/ios/` 就是 iPhone App 專案
- ✅ App 名字 = **沐寧**、ID = `net.munea.app`（對齊你買的 munea.net 域名）
- ✅ 圖示 + 啟動畫面（含深色模式）都產好了
- ✅ 點得動的展示網頁已經包進去（打開 App 會直接進寧寧首頁）
- ⚠️ **這版是展示版**：寧寧還不會「真的」講話/AI（那是之後接引擎的事）；現在是給你跟家人裝在手機上、點著看樣子、確認流程跟長相

---

## 🔴 第 1 件（只有你能做）：裝 Xcode

做 iPhone App、上架，**一定要 Xcode**，這台 Mac 還沒裝。

1. 開 **App Store**（Mac 上的）→ 搜尋 **Xcode** → 按「取得 / 安裝」
2. 它很大（約 7–12GB），下載要一段時間，**現在就先按下去讓它跑**
3. 裝完第一次打開 Xcode：會跳「安裝額外元件」→ 按同意、輸入你的電腦密碼、等它跑完

> 💡 這是整件事**最久的一步**，先按下去，邊下載邊做下面第 2 件。

---

## 🔴 第 2 件（只有你能做）：確認 Apple 開發者帳號「已開通」

**沒開通就上不了 TestFlight**（誰都一樣）。你 6/26 付了錢、當時還在等審核。

1. 開瀏覽器到 **developer.apple.com** → 右上登入你的 Apple ID
2. 看 **Account** 頁：
   - 看得到「Membership / 會員資格」、狀態是 **Active** = ✅ 開通了
   - 還寫「處理中 / pending」= 還沒，要再等 Apple（通常 24–48 小時，偶爾更久）
3. 也可以開 **appstoreconnect.com** → 進得去、看得到「我的 App」= ✅ 沒問題

> 把結果告訴我（Active 還是還在等），我接著帶你走。

---

## 🟢 第 3 件（你跟我一起）：Xcode 裝好後，按這個流程上架

> 等上面兩件好了再做。指令的部分我幫你跑，Xcode 裡點的部分我帶你點。

### A. 把 Xcode 設成預設工具（一次性、要你的電腦密碼）
```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
```

### B. 打開專案（我會幫你跑這行）
```bash
cd /Users/edward/Claude/Munea
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm use --lts
npx cap open ios
```
→ Xcode 會打開 `沐寧` 專案。第一次它會自動抓 Swift 套件（等一下下）。

### C. 在 Xcode 裡設定簽章（防偽身分）
1. 左邊點最上面的 **App** 專案 → 中間選 **App** target → 上面分頁 **Signing & Capabilities**
2. 勾 **Automatically manage signing**（自動管理）
3. **Team** 下拉 → 選你的 Apple 開發者帳號（沒看到代表帳號還沒開通，回第 2 件）

### D. 出一個正式包（Archive）
1. Xcode 最上面，裝置選 **Any iOS Device (arm64)**（不要選模擬器）
2. 選單 **Product → Archive** → 等它跑完（幾分鐘）
3. 跑完跳出 **Organizer** 視窗

### E. 上傳到 TestFlight
1. Organizer 裡選剛那包 → **Distribute App**
2. 選 **App Store Connect** → **Upload** → 一路 Next（簽章選自動）→ **Upload**
3. 傳完等 Apple 處理（10–30 分鐘，會寄 email）

### F. 加測試人員（在 App Store Connect 網站）
1. **appstoreconnect.com** → 你的 App → **TestFlight** 分頁
2. 第一次它會問「出口合規 / 加密」→ 這版沒用特殊加密，選**否**即可（之後接語音再重答）
3. **內部測試（Internal Testing）**：把你自己 + 家人的 Apple ID email 加進去
4. 他們手機裝 **TestFlight** App（App Store 免費下載）→ 收到邀請 → 裝沐寧

✦ **成果**：你跟家人的 iPhone 上就有「沐寧」App，點得動、看得到長相跟流程。

---

## 常見會卡的地方（先講好）

| 狀況 | 怎麼辦 |
|---|---|
| Team 下拉沒有你的帳號 | 帳號還沒開通，或 Xcode 沒登入 → Xcode → Settings → Accounts 加 Apple ID |
| Archive 灰色點不了 | 裝置沒選「Any iOS Device」，選了模擬器就不能 Archive |
| 上傳被退「bundle id 沒註冊」 | 開自動簽章它會自己建；真不行我幫你在 App Store Connect 手動建 `net.munea.app` |
| 字型/頭像沒load出來 | demo 用線上字型 + 示意人像，手機要連網才完整（正式版會換掉） |

---

## 之後（不是現在）

這版是**展示殼**。真正會講話的寧寧（即時語音 + 會動的臉 + 記憶 + 守護）是 backlog 階段 1–2 的「真建造」，要你撥 codex 額度、約 2–3 週。**好消息：那些東西會塞進同一個殼**，這條上架路今天先驗通，之後換內容就好。

*配 STATUS.md + BACKLOG.md。*
