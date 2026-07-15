# Munea App Store 上線狀態

更新：2026-07-16

> 本文件是 `1.0.24 (Build 29)` 上線狀態的唯一摘要。2026-07-16 已完成 iPhone-only 正式 Archive、IPA 防漏驗證與 App Store Connect 上傳；Apple 回執為 `Upload succeeded`／`package is processing`。這代表 Apple 已收件，不代表 TestFlight 已完成處理、已送審或已通過審核。舊成本、定價與原型文件只保留決策歷史，不可覆蓋目前 App、`web/src/version.js`、StoreKit 對應及 Edward 的最新定案。帳單細則以 `docs/BILLING-CREDITS-ENTITLEMENT-v1.md` 為準。

目前方案：Free / Plus / Pro。

## 目前版本

| 項目 | 現況 |
|---|---|
| App 版本 | `1.0.24` |
| Build | `29` |
| Bundle ID | `net.munea.app` |
| 支援裝置 | ✅ iPhone-only；Debug／Release `TARGETED_DEVICE_FAMILY=1`，IPA `UIDeviceFamily=[1]` |
| 候選 IPA | ✅ 已匯出；58,863,291 bytes，SHA-256 `773fa6a8ffb6b7062e2e0d9ecff056f3eb2ef09f20715d881bb96ff7bf8cb074` |
| 候選來源 | ✅ PR #93／`90d083a`；基於最新 `main@820b136` 並完整承接 PR #92 |
| App Store Connect | ✅ 2026-07-16 02:32（Asia/Taipei）上傳成功；Apple 處理中 |
| iOS 最低版本 | iOS 15 |
| 定位 | AI 身心健康陪伴與家庭照護，不提供診斷、治療或緊急服務 |

## 目前正式定價

此表已由 Edward 確認，舊文件中的 200／400 點或其他價格皆已失效。

| 方案 | 價格 | 每月贈點 |
|---|---:|---:|
| Free | NT$0 | 綁定帳號後一次性 5 點 |
| Plus 月繳 | NT$599 | 150 點 |
| Plus 年繳 | NT$5,750 | 每月 150 點 |
| Pro 月繳 | NT$1,199 | 300 點 |
| Pro 年繳 | NT$11,500 | 每月 300 點 |

| 加購 | 價格 | 既有 App Store Product ID |
|---:|---:|---|
| 150 點 | NT$500 | `net.munea.app.points.200` |
| 300 點 | NT$1,000 | `net.munea.app.points.500` |
| 600 點 | NT$2,000 | `net.munea.app.points.1000` |
| 1,000 點 | NT$3,000 | `net.munea.app.points.1800` |

Product ID 的數字是 Apple 後台既有識別碼，不代表現在實際發放點數，不能再依名稱自行推算。

## 自動驗證

- ✅ PASS：`smoke:no-api`、`test:launch`、完整 `release:check`；Mac 專案工具 PowerShell 7.6.3 可用。
- ✅ PASS：Google PKCE 系統瀏覽器跳轉／回跳契約；Apple 原生 AuthenticationServices＋ID token／nonce 交換契約。
- ✅ PASS：消費者登入只保留 Google／Apple；Email OTP／個人 Email 註冊入口已移除，登入視窗不含輸入框且不自動叫出鍵盤。
- ✅ PASS：StoreKit 購買驗證、防重複入帳、恢復購買與 Apple 訂閱管理契約。
- ✅ PASS：現行訂閱與點數包在 App、管理後台、StoreKit、後端測試中的對應一致。
- ✅ PASS：候選來源基於最新 `main@a9f23ea`，包含通知中心、權限同步、家庭狀態、角色呼吸與個人行程資料接線。
- ✅ PASS：固定 PCM 全語音探測通過台灣繁中 ASR（園藝／回診、吃藥／爸爸／血壓、阿宏／懷舊老歌／看診）、S2S 回覆、插話 7/7、30 秒低噪音不誤接話及句尾靜音保護；探測不依賴文字輸入。
- ✅ PASS：`1.0.24 (Build 29)` 開發版已覆蓋安裝到 Edward iPhone 15 Pro；手機回讀版本與啟動通過，開發 profile 設定為 TEST、Pro、1,000 點與家人假資料。
- ✅ PASS：正式 App 強制走 Call Control；只有腳本產生的 Edward 開發包可直連，Call Control 10 項契約與 Release 防漏均通過。
- ✅ PASS：Build 29 Release Archive 與 App Store IPA 已在 Mac 重建；正式 IPA 沒有測試帳號、假資料、自動登入或開發直連，並驗證 production APNs、`get-task-allow=false`、簽章、版本／Build、Bundle ID、`UIDeviceFamily=[1]`、相機／照片用途說明、HealthKit、Apple 登入 entitlement、Privacy Manifest、東京設定與最新 Web 資源。
- ✅ PASS：Build 29 已由 Xcode 正式上傳 App Store Connect；Apple 回執為 `Upload succeeded`，目前等待後台處理完成。
- ✅ PASS：App 端已加入說話後 1.8 秒收音守門與開場前兩輪 300ms 持續人聲門檻；契約測試含真人預捲與插話保護。
- ✅ PASS：Xcode 原生檢查、Release contract 與 IPA export 都會阻擋 iPad 支援意外回歸。
- ✅ PASS：正式 npm 依賴已知漏洞為 0。
- ✅ PASS：App Store Server Notifications V2 已實作外層／交易／續訂 JWS 驗證，並處理續訂、關閉續訂、寬限、到期、退款、撤銷與退款撤回；事件以 notification UUID／transaction ID 冪等處理。
- ✅ PASS：個資匯出已改為 request-scoped Supabase 資料包，只含登入者本人、其家庭圈身分與所屬帳務資料；App 可直接透過 iOS 分享表或 JSON 下載交付。
- ✅ PASS：iOS target 已加入 `PrivacyInfo.xcprivacy`，宣告不追蹤及目前實際蒐集類型；IPA export gate 會拒絕缺少 manifest 的正式包。
- ✅ PASS：正式 IPA 匯出腳本已修正 Privacy Manifest 陣列計數誤判，並新增回歸契約；仍需在送審前用 Xcode Privacy Report 複核第三方 SDK manifest。

## 真機驗收環境

- ✅ PASS：Mac「iPhone 鏡像輸出」已完成設定，可啟動並辨識 Edward 的配對 iPhone。
- ✅ PASS：已建立即時鏡像工作階段，Mac 可取得 iPhone 主畫面與 App 切換器控制。
- ⚠️ 官方限制：Apple 說明 iPhone 鏡像不可使用 iPhone 相機、麥克風、Face ID 或通話；拍照、語音通話與需要 Face ID 的流程仍須直接操作手機。來源：https://support.apple.com/en-us/120421
- 範圍說明：此項只代表一般畫面操作工具已備妥。Apple／Google 登入、實際拍照、HealthKit、通知、StoreKit 與音訊仍須逐項操作通過，不能由鏡像環境 PASS 代替。

## 尚未通過

- ❌ FAIL：Build 29 的語音契約與固定探測通過，但 Edward 尚未完成真人 10 分鐘長聊，不能宣稱斷字已解決。
- ❌ FAIL：Build 29 的低噪音／插話契約通過，但 Edward 尚未完成真人五組靜音與五次插話；不能以自動結果取代真機 PASS。
- ❌ DEPLOY：PR #92 的 Voice 伺服器人格、上一通記憶防編造與行程工具尚未部署；本次 App 包版不會讓伺服器改動自動生效。
- ❌ FAIL：開場輪替、禁台語與「興趣／濃醇」穩定替代表達已寫入系統規則，但尚未由 Edward 實聽五輪確認。
- ❌ DEPLOY：本輪 Voice S2S／ASR／VAD／插話修正尚未部署 Cloud Run canary，手機目前仍可能連到舊服務；部署及真人驗收前不得升正式流量。
- ❌ FAIL：Google Cloud OAuth 已是 external／production 且名稱已儲存為「Munea App」，但品牌仍未驗證，Logo、首頁、隱私權與條款網址尚未補齊。
- ❌ FAIL：Apple 公開網頁 OAuth 仍回 `Invalid client id or web redirect url`；Build 29 使用原生 Apple 登入，但尚未以真帳號完成 ID token 端到端驗收。
- ❌ FAIL：Repo 的 Apple 點數發放新對應尚未部署到唯一 Cloud Run，也尚未用真交易驗證。
- ❌ FAIL：尚未在 iPhone 用真實 Apple／Google 帳號完成登入、登出與重登全流程。
- ❌ FAIL：正式 Call Control 已拒絕無 token 請求，但尚未以真實登入 token 完成 Voice＋Avatar Gateway 端到端通話。
- ❌ FAIL：Build 29 尚未由 Edward 實際點「拍照」確認相機畫面可開啟；自動檢查與權限字串已通過，但不能代替實體相機操作。
- ❌ FAIL：尚未完成 StoreKit Sandbox 購買、取消、續訂與恢復購買。
- ❌ DEPLOY：資料匯出程式與 App 檔案交付已完成，仍需合併、部署唯一 Brain Cloud Run，並以正式登入帳號驗證匯出內容只屬於本人。
- ❌ DEPLOY：App Store Server Notifications V2 程式已完成，仍需部署 Brain、在 App Store Connect 填入正式／Sandbox webhook URL `https://<brain-domain>/apple/notifications`，再送 TEST 與 Sandbox 續訂／到期／退款事件。
- ❌ FAIL：雲端帳號永久刪除已有實作，但 Mac 缺正式後台憑證，尚未用測試帳號做端到端驗收。
- ❌ FAIL：HealthKit 同意／拒絕、通知、麥克風、藍牙音訊、長通話及重裝後資料恢復尚未逐項人工驗收。
- ❌ WAIT：Build 29 已上傳 App Store Connect，但尚未確認 Apple 處理完成、TestFlight 可選用，也尚未產生 Xcode Privacy Report。
- ❌ FAIL：App Store Connect 的 App Privacy 尚未填完；Munea 涉及帳號、健康、音訊與使用資料，不能選「不收集資料」。
- ❌ WAIT：必須在 Apple 處理完成後選取 Build 29，才能確認 13 吋 iPad 截圖要求已消失；舊 Build 的裝置支援不會被修改。

## 上傳決策

目前 **已上傳、不可送審**。Build 29 的工程驗證、正式簽章、iPhone-only IPA 防漏與 App Store Connect 收件均通過；但 Apple 尚在處理，而且 Voice 伺服器新版、真人語音、真實登入／Gateway 通話、APNs、拍照、Sandbox 金流、App Privacy、資料權利與審核元資料仍有未通過項目。

## 下一步

1. 部署 Voice 與 Brain canary，設定 App Store Notifications V2 URL，完成固定探測、TEST notification、Sandbox 生命週期與本人資料匯出 E2E；通過再升正式流量。
2. Edward 直接操作 iPhone，完成五輪開場／禁台語／發音、10 分鐘長聊、五次插話與五組 30 秒靜音。
3. 補齊 Google OAuth Logo／首頁／隱私權／條款並送品牌驗證；以真實 Google／Apple 帳號完成登入、登出與重登。
4. 完成實際拍照、真 token Gateway 通話、StoreKit Sandbox、資料匯出與帳號刪除正式帳號端到端測試。
5. 等待 Apple 完成 Build 29 處理，在版本頁選取新 Build，確認 iPad 截圖要求消失與 TestFlight 可選用；生成 Xcode Privacy Report 並複核第三方 SDK manifest。
6. 補完訂閱商品元資料、掛入 IAP／訂閱、App Privacy、年齡分級與審核備註；所有真人 Gate 通過後才送審。
