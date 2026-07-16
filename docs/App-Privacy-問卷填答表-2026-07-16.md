# App Store Connect · App Privacy 問卷填答表

- 產生日期：2026-07-16
- 對象：https://appstoreconnect.apple.com/apps/6788658125/distribution/privacy
- 版本基準：`package.json` 1.0.23 · Build 27 候選
- 方法：**逐項對照實際程式碼**產生，不採信文件與註解（本次查核發現註解與事實不符共 2 處，見附錄 A）
- 前身：`docs/上架素材與審核包-C5-2026-07-03.md` 第三節（該版有 3 處與現況不符，本表取代之）

> Apple 對「收集（Collect）」的定義 = **資料離開裝置**，傳到你或第三方的伺服器。
> 只存在裝置本機（localStorage / UserDefaults）**不算收集**。本表全部依此判定。

---

## 填寫狀態（2026-07-16 03:xx 更新）

**15 項子問題已於 App Store Connect 全部填妥、已存檔**，「發佈」鍵已由灰轉藍（Apple 判定表格完整）。
**「發佈」未按**——該按由 Edward 本人執行（對 Apple 的法律聲明）。

Apple 產品頁面預覽已驗證呈現為：
- 與你身分連結的資料：使用者內容、識別碼、健康與健身、使用狀況資料、診斷、聯絡資訊、購買項目
- 未與你身分連結的資料：位置

---

## 〇、送審前必須先處理（阻擋項）

| # | 問題 | 嚴重度 | 為什麼擋 |
|---|---|---|---|
| **A-0** | **App Store Connect 的「隱私權政策 URL」目前填的是 `https://claude.ai/code/artifact/db866b16-f152-4f3a-9460-ff56dcab1eae`** —— 一個 Claude 產生的暫存頁，非正式隱私政策 | 🔴 **最高** | Claude artifact 預設私人，審核員極可能打不開 → 必退。正確值應為 `https://app.munea.net/privacy`（2026-07-14 已驗證可公開存取，見上架素材包） |
| A-1 | 公開隱私政策寫「用藥照片只儲存在裝置本機，不會上傳雲端」，但程式碼會上傳到 `/routine-reminders` → Supabase | 🔴 高 | 對外法律文件與事實不符。**Edward 2026-07-16 拍板：補修程式，讓照片真的只留本機**（選項 A） |
| A-2 | 打包用的 `PrivacyInfo.xcprivacy` 仍宣告「精確位置」，但 7/9 已移除 GPS、Info.plist 根本沒有定位權限說明 | 🟡 中 | 多報。Xcode Privacy Report 會與問卷打架（問卷已填「不收集精確位置」） |
| A-3 | `NSPrivacyAccessedAPITypes` 是空陣列，但自寫的 `NotifyPlugin.swift` 有用 UserDefaults（Required Reason API） | 🟡 中 | App Store Connect 常見自動退件原因 |
| A-4 | `PrivacyInfo.xcprivacy` 的 `Name` 宣告了 ProductPersonalization，但問卷填「僅 App 功能」 | 🟢 低 | 兩邊不一致，建議擇一對齊（實際行為偏 App 功能） |

> ⚠ A-1 的修補必須進到**實際送審的那個 Build**。Build 27 若仍含舊程式，上架的 App 行為仍與隱私政策不符。

---

## 〇之二、本表的自我更正（2026-07-16）

本表初版列 12 項，經與 App Store Connect 既有勾選（15 項）逐項對帳後，**確認 15 項才正確**，初版漏列三項：

| 漏列項 | 為什麼該列 | 證據 |
|---|---|---|
| **電子郵件或訊息** | 家人傳話表有 sender／recipient／content 三欄，完全符合 Apple 對本格的定義（初版誤歸入「其他使用者內容」） | `supabase/sql/015_family_relay_messages.sql:9-13` |
| **裝置識別碼** | 推播通知會把裝置代碼存到伺服器 | `web/src/notify.js:435`、`/push/devices`、`supabase/sql/016_notification_platform.sql` |
| **粗略位置** | 城市字串會送到第三方天氣服務（open-meteo） | `web/src/app.js:3014` |

---

## 一、要勾「Yes, we collect」的項目

三個子問題一律是：**Purposes（用途）／ Linked to the user（連結身分）／ Used for tracking（用於追蹤）**。
本 App **全部不追蹤**（無 IDFA、無 ATT、無廣告 SDK、`NSPrivacyTracking = false`）→ 追蹤欄位一律 **No**。

✅ = 已於 App Store Connect 實際填入並存檔（2026-07-16）

| # | Apple 分類 | 子項 | 對應我們的什麼 | 用途（已填） | 連結身分 | 追蹤 | 證據 |
|---|---|---|---|---|---|---|---|
| 1 ✅ | 聯絡資訊 | **姓名** | 姓名／暱稱、家人照護圈成員稱呼 | App 功能 | 是 | 否 | `family_state_entries` 帶 name／nick |
| 2 ✅ | 聯絡資訊 | **電子郵件地址** | 帳號 email（Apple／Google／Email 註冊） | App 功能 | 是 | 否 | `web/src/auth.js` |
| 3 ✅ | 健康與健身 | **健康** | 心率、血壓（收縮／舒張）、血氧、睡眠＋用藥提醒、回診 | App 功能＋產品個人化 | 是 | 否 | `HealthPlugin.swift:25-36` → `app.js:3411` → `POST /family/state` → `family_state_entries` |
| 4 ✅ | 健康與健身 | **健身** | 步數 | App 功能＋產品個人化 | 是 | 否 | 同上 |
| 5 ✅ | 位置 | **粗略位置** | 使用者自填的縣市（查天氣用） | App 功能 | **否** | 否 | `app.js:3014` → open-meteo；不存我方伺服器、不帶識別碼 |
| 6 ✅ | 使用者內容 | **電子郵件或訊息** | 家人傳話（寄件者／收件者／內容） | App 功能 | 是 | 否 | `supabase/sql/015_family_relay_messages.sql:9-13` |
| 7 ✅ | 使用者內容 | **照片或影片** | 用藥照片＋意見回饋附圖（頭像**不算**，只在本機） | App 功能 | 是 | 否 | `app.js:568` → `POST /routine-reminders`；`app.js:6547` → `POST /feedback`。**⚠ 見 A-1；修完後仍需申報，因回饋附圖照舊上傳** |
| 8 ✅ | 使用者內容 | **音訊資料** | 通話語音（送 Gemini 理解內容） | App 功能＋產品個人化 | 是 | 否 | 隱私政策已揭露；原始錄音不作主要保留紀錄 |
| 9 ✅ | 使用者內容 | **客戶支援** | 意見回饋文字內容 | App 功能 | 是 | 否 | `server.py:4352` → `feedback_store.json` |
| 10 ✅ | 使用者內容 | **其他使用者內容** | 聊天文字、AI 對話摘要（長期保留）、家人留言／塗鴉、心情紀錄 | App 功能＋產品個人化 | 是 | 否 | Supabase |
| 11 ✅ | 識別碼 | **使用者識別碼** | 帳號 ID（`account_id` / `personId`） | 分析＋App 功能 | 是 | 否 | `supabase_adapter.py:2602-2613` |
| 12 ✅ | 識別碼 | **裝置識別碼** | 推播通知的裝置代碼 | App 功能 | 是 | 否 | `notify.js:435`、`/push/devices` |
| 13 ✅ | 購買項目 | **購買記錄** | 訂閱方案狀態、點數餘額 | App 功能 | 是 | 否 | StoreKit → 引擎 |
| 14 ✅ | 使用狀況資料 | **產品互動** | 產品事件（onboarding 完成、通話開始…40+ 個埋點） | App 功能＋分析 | 是 | 否 | `app.js:1043` → `POST /product-event`；身分由後端補上 `server.py:3558-3578` |
| 15 ✅ | 診斷 | **效能資料** | 通話診斷（各階段耗時、失敗碼） | 分析＋App 功能 | 是 | 否 | `voice-call-diagnostics.js` → 同一條 `/product-event` 管線 |

**「連結身分」為什麼全是 Yes**：即使前端送出的事件不含身分，後端會依 Authorization token 補上 `account_id` 再落庫（`server.py:382-401`）。Apple 看的是最終結果，所以是 Linked。

---

## 二、要勾「No」／不勾的項目（附理由，備審核詢問）

| 分類 | 判定 | 理由 |
|---|---|---|
| **Precise Location** | 不收集 | 7/9 已移除 GPS 備援；`Info.plist` **沒有**任何定位權限說明字串 → App 技術上無法取得。（`PrivacyInfo.xcprivacy` 需同步移除，見 A-2） |
| **Coarse Location** | 不收集（判斷題，見第三節 D-1） | 城市為使用者在「個人資料」自行輸入的偏好字串，存 localStorage、不進我們的伺服器 |
| **Contacts** | 不收集 | 不讀通訊錄。家人照護圈為手動輸入 |
| **Crash Data** | 不收集 | 無 Crashlytics／Sentry；無 `window.onerror`、無 `NSSetUncaughtExceptionHandler` |
| **Device ID** | 不收集 | 無 IDFA／`identifierForVendor`。`muneaDeviceId()` 是自生的 localStorage 字串，且不在任何事件 payload 內 |
| **Payment / Credit / Other Financial Info** | 不收集 | 付款全由 Apple 處理，我方不取得卡號 |
| **Browsing History / Search History** | 不收集 | 無此功能 |
| **Advertising Data** | 不收集 | 無廣告 |
| **Sensitive Info** | 不收集 | Apple 此格指種族／性向／宗教／政治／工會／基因／生物特徵。語音**不用於聲紋辨識或身份識別**（已於隱私政策定性）→ 不構成生物特徵 |
| **Gameplay Content** | 不收集 | 無此功能 |

---

## 三、需要 Edward 拍板的判斷題

### D-1 · 城市欄位算不算 Coarse Location？
- 事實：使用者自己打「台北市中山區」→ 存 localStorage → 送 open-meteo 天氣 API 當搜尋字串 → **不存我方伺服器**
- 選項 A（建議）：**不勾**。理由：Apple 的 Location 指從裝置取得的位置資料；這是使用者主動輸入的偏好設定，我方不留存
- 選項 B：保守勾 Coarse Location／App Functionality／Linked=No／追蹤=No
- 風險差：A 若被審核質疑，用上面理由回覆即可，屬可辯護；B 則是自願多報，無罰則但與隱私政策「不收集位置」的敘述不一致

### D-2 · 用藥照片怎麼辦（＝ A-1）
- 選項 A（建議）：**補修程式**，讓 `/routine-reminders` 比照 `/family/state` 剝掉照片欄位 → 用藥照片真的只留本機 → 隱私政策不用改。回饋附圖仍需申報 Photos
- 選項 B：**改隱私政策**，誠實寫明用藥照片會上傳雲端 → 問卷照勾 Photos
- 差別：A 守住原本對用戶的承諾、動程式；B 不動程式、動對外文件

---

## 附錄 A · 本次查核發現的「註解與事實不符」

| 位置 | 註解寫的 | 事實 |
|---|---|---|
| `web/src/app.js:3725` | 「用藥照片只留本機、不上雲（隱私修正 7/9）」 | 只補了 `/family/state` 這條，漏了 `/routine-reminders`，照片仍會離開裝置 |
| `ios/App/App/HealthPlugin.swift:11` | 「資料留在裝置端，交給網頁決定怎麼呈現」 | 7/9「數據真同步」後已不成立，健康資料會上雲給家人看 |

兩處都建議一併修正註解——審核員若閱讀原始碼，會認為程式與宣告打架。

## 附錄 B · 順帶發現（與問卷無關，但上架前該確認）

- **正式 App 打的是 staging 後端**：`web/src/app.js:439` 的 `BRAIN_URL_DEFAULT` 指向 `munea-brain-staging-...run.app`，且 `isPackagedApp()` 為真時無條件使用（`app.js:453`）。請確認是否刻意。
- **Google Fonts CDN**：`ios/App/App/public/index.html:9-11` 直連 `fonts.googleapis.com`，真機開 App 會向 Google 發請求（Google 因此取得 IP）。不影響問卷，但「零第三方連線」的說法不成立。
- **第三方 SDK 全清單**（`Package.resolved`）：GoogleSignIn-iOS 9.1.0（僅帳號登入資料）＋其傳遞依賴（AppAuth／GTMAppAuth／gtm-session-fetcher／GoogleUtilities／app-check／interop／promises）＋ Capacitor 8.4.1。**無 Firebase Analytics、無廣告 SDK、無歸因 SDK。**
