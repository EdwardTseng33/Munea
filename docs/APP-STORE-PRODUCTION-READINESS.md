# Munea App Store 上線狀態

更新：2026-07-14

> 本文件是 `1.0.5` 上線狀態的唯一摘要。舊成本、定價與原型文件只保留決策歷史，不可覆蓋目前 App、`web/src/version.js`、StoreKit 對應及 Edward 的最新定案。帳單細則以 `docs/BILLING-CREDITS-ENTITLEMENT-v1.md` 為準。

目前方案：Free / Plus / Pro。

## 目前版本

| 項目 | 現況 |
|---|---|
| App 版本 | `1.0.5` |
| Build | `10`（最新真機開發驗收包與 App Store 候選 IPA） |
| Bundle ID | `net.munea.app` |
| 候選 IPA | 54,781,117 bytes；SHA-256 `47c324464d483b8d01753f5840210029050a5d5e1a65aac8a81d6072679a8848` |
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
- ✅ PASS：以 `main@fac3a49` 為功能來源，PR #29 點數週期、PR #23 語音開場緩衝／台語安全閘、PR #30 訂閱頁水彩新設計與 PR #31 Gateway 長駐監控已和既有帳號、Call Control、登入及拍照修正同步；Web 與 iOS 內嵌資源一致。
- ✅ PASS：`1.0.5 (Build 10)` 測試版已覆蓋安裝到 Edward iPhone 15 Pro；裝置版本查詢、安裝與啟動通過，開發 profile 設定為 TEST、Pro、1,000 點與三位家人假資料。
- ✅ PASS：正式 App 強制走 Call Control；只有腳本產生的 Edward 開發包可直連，Call Control 10 項契約與 Release 防漏均通過。
- ✅ PASS：Build 10 Release Archive 與 App Store IPA 已依 `main@fac3a49` 重建；正式 IPA 沒有測試帳號、假資料、自動登入或開發直連，並驗證簽章、版本／Build、Bundle ID、相機／照片用途說明、HealthKit、Apple 登入 entitlement、訂閱頁 HTML／樣式／插圖與最新設計資源。
- ✅ PASS：正式 npm 依賴已知漏洞為 0。

## 真機驗收環境

- ✅ PASS：Mac「iPhone 鏡像輸出」已完成設定，可啟動並辨識 Edward 的配對 iPhone。
- ✅ PASS：已建立即時鏡像工作階段，Mac 可取得 iPhone 主畫面與 App 切換器控制。
- ⚠️ 官方限制：Apple 說明 iPhone 鏡像不可使用 iPhone 相機、麥克風、Face ID 或通話；拍照、語音通話與需要 Face ID 的流程仍須直接操作手機。來源：https://support.apple.com/en-us/120421
- 範圍說明：此項只代表一般畫面操作工具已備妥。Apple／Google 登入、實際拍照、HealthKit、通知、StoreKit 與音訊仍須逐項操作通過，不能由鏡像環境 PASS 代替。

## 尚未通過

- ❌ FAIL：Build 9 真機連聊約 10 分鐘曾出現句尾約 4～5 次短暫斷續；Build 10 已納入 PR #23 的開場緩衝，但尚未通過 10 分鐘長聊零斷裂驗收，也尚未補齊長聊期間的持續 RTP／播放品質降級處理。
- ❌ FAIL：Build 9 偶爾在使用者完全沒說話時自行認定有發言並接話；Build 10 尚未通過 30 秒靜音五組驗收，本機仍未加入足以取代雲端 Automatic VAD 的靜音防誤觸門檻。
- ❌ FAIL：Google Cloud OAuth 品牌欄位已填成「Munea App」，但尚未按儲存；Google 頁面也要求完成品牌驗證後才會對使用者顯示。
- ❌ FAIL：Apple 公開網頁 OAuth 仍回 `Invalid client id or web redirect url`；Build 10 使用原生 Apple 登入，但尚未以真帳號完成 ID token 端到端驗收。
- ❌ FAIL：Repo 的 Apple 點數發放新對應尚未部署到唯一 Cloud Run，也尚未用真交易驗證。
- ❌ FAIL：尚未在 iPhone 用真實 Apple／Google 帳號完成登入、登出與重登全流程。
- ❌ FAIL：正式 Call Control 已拒絕無 token 請求，但尚未以真實登入 token 完成 Voice＋Avatar Gateway 端到端通話。
- ❌ FAIL：Build 10 尚未由 Edward 實際點「拍照」確認相機畫面可開啟；自動檢查與安裝已通過，但不能代替實體相機操作。
- ❌ FAIL：尚未完成 StoreKit Sandbox 購買、取消、續訂與恢復購買。
- ❌ FAIL：資料匯出目前只建立申請，尚未完成實際檔案產出與交付工作。
- ❌ FAIL：雲端帳號永久刪除已有實作，但 Mac 缺正式後台憑證，尚未用測試帳號做端到端驗收。
- ❌ FAIL：HealthKit 同意／拒絕、通知、麥克風、藍牙音訊、長通話及重裝後資料恢復尚未逐項人工驗收。
- ❌ FAIL：尚未確認 App Store Connect 是否接受 Build 10，候選 IPA 尚未上傳。

## 上傳決策

目前 **不可送審**。簽章與 IPA 已通過，但公開登入設定、真實登入／Gateway 通話、Cloud Run 點數對應、Sandbox 金流及資料權利仍有未通過項目。

## 下一步

1. 直接用 Build 10 完成 10 分鐘長聊及 30 秒靜音五組真機驗收；若仍失敗，再補長聊持續品質監測、Avatar 背壓隔離與本機靜音防誤觸。
2. Edward 確認後儲存 Google OAuth 品牌名稱，再完成 Google 品牌驗證；以 Build 10 真實 Google／Apple 帳號完成登入、登出與重登。
3. 以 canary 部署 Cloud Run 點數對應，驗證後再升 100% 流量。
4. 使用 Mac iPhone 鏡像完成一般畫面流程；拍照、麥克風、Face ID、通話與需要實體確認的金流則直接在 Edward iPhone 完成。
5. 完成資料匯出交付流程與帳號刪除端到端測試。
6. 真登入通過後查 App Store Connect Build 10 可用性，再上傳已驗證的候選 IPA。
7. 完成截圖、隱私標籤、年齡分級與審核備註後送 TestFlight。
