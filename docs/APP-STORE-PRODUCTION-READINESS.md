# Munea App Store 上線狀態

更新：2026-07-16

> 本文件是 `1.0.26 (Build 33)` 發版準備的唯一摘要。Build 33 已完成 iPhone-only Release Archive、IPA 防漏驗證與 Edward iPhone 開發包安裝；2026-07-16 18:05 Edward 決定先留在手機驗證，**不上傳 App Store Connect、不送審**。Apple 目前收到的最新可用候選仍是 `1.0.25 (Build 32)`，但真人 Voice、真登入、拍照、StoreKit、APNs 與審核資料尚未完成，因此也不可送審。Build 30（缺隱私修補）與 Build 31（缺原生零件）已作廢。舊成本、定價與原型文件只保留決策歷史，不可覆蓋目前 App、`web/src/version.js`、StoreKit 對應及 Edward 的最新定案。帳單細則以 `docs/BILLING-CREDITS-ENTITLEMENT-v1.md` 為準。

目前方案：Free / Plus / Pro。

## 目前版本

| 項目 | 現況 |
|---|---|
| App 版本 | `1.0.26` |
| Build | `33` |
| Bundle ID | `net.munea.app` |
| 支援裝置 | ✅ iPhone-only；Debug／Release `TARGETED_DEVICE_FAMILY=1`，IPA `UIDeviceFamily=[1]` |
| Build 33 IPA | ✅ 已匯出；58,866,082 bytes，SHA-256 `f364880e2ff3711f167884fc2271126ee6cb357660d63733e4489c7d363d7d0a` |
| Build 33 來源 | ✅ PR #109 已合併；含 PR #101 隱私修補、PR #108 開場收音預捲與首通黑閃修正；原生零件與 iPhone-only 已驗證 |
| iPhone | ✅ Edward iPhone 已安裝並成功啟動；裝置回讀 `1.0.26 (33)` |
| App Store Connect | ⏸️ Build 33 依 Edward 決策不上傳；Apple 現有候選仍是 2026-07-16 12:40 上傳的 Build 32 |
| Cloud Run canary | ✅ Brain `00055-vuc`、Voice `00039-zaq` 均 Ready 且 0% 流量；尚未 promote |
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
- ✅ PASS：Build 33 來源為 PR #109／`1.0.26`，包含通知中心、權限同步、家庭狀態、個人行程、App 收音守門、PR #94 撥號前三線暖機與 PR #108 開場預捲／首通黑閃修正。
- ✅ PASS：固定 PCM 全語音探測通過台灣繁中 ASR（園藝／回診、吃藥／爸爸／血壓、阿宏／懷舊老歌／看診）、S2S 回覆、插話 7/7、30 秒低噪音不誤接話及句尾靜音保護；探測不依賴文字輸入。
- ✅ PASS：`1.0.26 (Build 33)` 開發版已覆蓋安裝到 Edward iPhone 15 Pro；手機回讀版本與啟動通過，開發 profile 設定為 TEST、Pro、1,000 點與家人假資料。
- ✅ PASS：正式 App 強制走 Call Control；只有腳本產生的 Edward 開發包可直連，Call Control 10 項契約與 Release 防漏均通過。
- ✅ PASS：Build 33 Release Archive 與 App Store IPA 已在 Mac 重建；正式 IPA 沒有測試帳號、假資料、自動登入或開發直連，並驗證 production APNs、`get-task-allow=false`、簽章、版本／Build、Bundle ID、`UIDeviceFamily=[1]`、相機／照片用途說明、HealthKit、Apple 登入 entitlement、Privacy Manifest、東京設定與最新 Web 資源。
- ⏸️ HOLD：Build 33 IPA 已可上傳，但依 Edward 18:05 決策保留本機，不上傳 App Store Connect。
- ✅ PASS：App 端已加入說話後 1.8 秒收音守門與開場前兩輪 300ms 持續人聲門檻；契約測試含真人預捲與插話保護。
- ✅ PASS：App 開啟 2.5 秒後及回前景時，對 Avatar／Voice／Call Control 做一次性暖機；60 秒防抖、不輪詢、不預佔席位。
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

- ❌ FAIL：Build 33 的語音契約與固定探測通過，但 Edward 尚未完成真人 10 分鐘長聊，不能宣稱斷字已解決。
- ❌ FAIL：Build 33 的低噪音／插話契約通過，但 Edward 尚未完成真人五組靜音與五次插話；不能以自動結果取代真機 PASS。
- ⚠️ CANARY：PR #92／#95 的 Voice 伺服器人格、上一通記憶防編造、行程工具、稱呼頻率與純語音現實邊界已進 Voice `00039-zaq` 0% canary；尚未用正式 Call Token／iPhone 真人 Gate，也未 promote，因此正式使用者仍使用舊 revision。
- ❌ FAIL：開場輪替、禁台語與「興趣／濃醇」穩定替代表達已寫入系統規則，但尚未由 Edward 實聽五輪確認。
- ⚠️ CANARY：Brain `00055-vuc` 與 Voice `00039-zaq` 已部署 0% canary；部署層 Ready、根頁 200，Brain 無效 Apple JWS 正確回 400。Voice 的正式 Call Token、Gemini 音訊、ASR、插話、靜音與真人體感仍未通過，不得升正式流量。
- ❌ FAIL：Google Cloud OAuth 已是 external／production 且名稱已儲存為「Munea App」，但品牌仍未驗證，Logo、首頁、隱私權與條款網址尚未補齊。
- ❌ FAIL：Apple 公開網頁 OAuth 仍回 `Invalid client id or web redirect url`；Build 33 使用原生 Apple 登入，但尚未以真帳號完成 ID token 端到端驗收。
- ❌ FAIL：Repo 的 Apple 點數發放新對應尚未部署到唯一 Cloud Run，也尚未用真交易驗證。
- ❌ FAIL：尚未在 iPhone 用真實 Apple／Google 帳號完成登入、登出與重登全流程。
- ❌ FAIL：正式 Call Control 已拒絕無 token 請求，但尚未以真實登入 token 完成 Voice＋Avatar Gateway 端到端通話。
- ❌ FAIL：Build 33 尚未由 Edward 實際點「拍照」確認相機畫面可開啟；自動檢查與權限字串已通過，但不能代替實體相機操作。
- ❌ FAIL：尚未完成 StoreKit Sandbox 購買、取消、續訂與恢復購買。
- ❌ DEPLOY：資料匯出程式與 App 檔案交付已完成，仍需合併、部署唯一 Brain Cloud Run，並以正式登入帳號驗證匯出內容只屬於本人。
- ❌ CONFIG：App Store Server Notifications V2 接收器已進 Brain 0% canary，無效 JWS 會安全拒絕為 400；但 App Store Connect 的實際執行 URL 仍指向已退役、回 404 的 `https://munea-brain-491603544409.asia-east1.run.app/apple/notifications`。精確替換值為 `https://munea-brain-staging-491603544409.asia-east1.run.app/apple/notifications`（2026-07-16 複測無效 JWS 回 400），再送 TEST 與 Sandbox 續訂／到期／退款事件；完成前通知閉環維持紅燈。
- ❌ FAIL：雲端帳號永久刪除已有實作，但 Mac 缺正式後台憑證，尚未用測試帳號做端到端驗收。
- ❌ FAIL：HealthKit 同意／拒絕、通知、麥克風、藍牙音訊、長通話及重裝後資料恢復尚未逐項人工驗收。
- ❌ WAIT：Build 32 已上傳，但尚未在本輪確認 TestFlight／版本頁可選用；Build 33 依決策尚未上傳，也尚未產生 Xcode Privacy Report。
- ⚠️ ACTION：App Store Connect 的 App Privacy 15 項已填完並已保存，「發佈」按鈕待 Edward 本人確認；發布前仍須再對照 Build 33 Privacy Manifest。
- ❌ WAIT：需在 App Store Connect 選取 iPhone-only Build，確認 13 吋 iPad 截圖要求已消失；舊 Build 的裝置支援不會被修改。

## 上傳決策

目前 **Build 33 已備妥但依決策不上傳、不可送審**。Build 32 雖已由 Apple 收件，也仍不可送審。Voice／Brain 新版只有 0% canary，真人語音、真實登入／Gateway 通話、APNs、拍照、Sandbox 金流、App Privacy 發佈、資料權利與審核元資料仍有未通過項目。

## 下一步

1. 把 App Store Connect 實際執行通知 URL 改為 `https://munea-brain-staging-491603544409.asia-east1.run.app/apple/notifications`，完成 TEST notification、Sandbox 生命週期與本人資料匯出 E2E。
2. Edward 直接操作 iPhone，完成五輪開場／禁台語／發音、10 分鐘長聊、五次插話與五組 30 秒靜音。
3. 補齊 Google OAuth Logo／首頁／隱私權／條款並送品牌驗證；以真實 Google／Apple 帳號完成登入、登出與重登。
4. 完成實際拍照、真 token Gateway 通話、StoreKit Sandbox、資料匯出與帳號刪除正式帳號端到端測試。
5. 真人 Voice Gate 通過後才 promote Brain／Voice；未通過就維持 0%，正式流量不動。
6. 等 Edward 解除 Build 33 凍結後才上傳；在版本頁確認 iPhone-only、生成 Xcode Privacy Report 並複核第三方 SDK manifest。
7. 補完訂閱商品元資料、掛入 IAP／訂閱、App Privacy 發佈、年齡分級與審核備註；所有 Gate 通過後才送審。
