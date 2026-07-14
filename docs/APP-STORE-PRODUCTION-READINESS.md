# Munea App Store 上線狀態

更新：2026-07-14

> 本文件是 `1.0.3` 上線狀態的唯一摘要。舊成本、定價與原型文件只保留決策歷史，不可覆蓋目前 App、`web/src/version.js`、StoreKit 對應及 Edward 的最新定案。帳單細則以 `docs/BILLING-CREDITS-ENTITLEMENT-v1.md` 為準。

目前方案：Free / Plus / Pro。

## 目前版本

| 項目 | 現況 |
|---|---|
| App 版本 | `1.0.3` |
| Build | `7`（最新真機開發驗收包；App Store IPA 仍為 Build 6） |
| Bundle ID | `net.munea.app` |
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

- ✅ PASS：`smoke:no-api`、`test:launch`、完整 `release:check`。
- ✅ PASS：Google／Apple 登入原生跳轉、PKCE 回跳處理與公開 Supabase 設定契約。
- ✅ PASS：Supabase Auth health；Google、Apple、Email provider 均已啟用。
- ✅ PASS：StoreKit 購買驗證、防重複入帳、恢復購買與 Apple 訂閱管理契約。
- ✅ PASS：現行訂閱與點數包在 App、管理後台、StoreKit、後端測試中的對應一致。
- ✅ PASS：`1.0.3 (Build 7)` 已完成 Capacitor sync、Xcode 真機編譯，成品包含相機與照片圖庫用途說明。
- ✅ PASS：`1.0.3 (Build 7)` 已覆蓋安裝到 Edward iPhone 15 Pro；版本查詢、一般啟動與程序存活通過。
- ✅ PASS：前一版 Build 6 的簽章 Archive、App Store IPA、Bundle ID、HealthKit entitlement、免加密聲明及登入回跳網址均已驗證。
- ✅ PASS：正式 npm 依賴已知漏洞為 0。

## 尚未通過

- ❌ FAIL：最新公開 Web 尚未部署 `auth-config.js`，`app.munea.net` 的 Google／Apple 登入仍要等本次版本上線。
- ❌ FAIL：Repo 的 Apple 點數發放新對應尚未部署到唯一 Cloud Run，也尚未用真交易驗證。
- ❌ FAIL：尚未在 iPhone 用真實 Apple／Google 帳號完成登入、登出與重登全流程。
- ❌ FAIL：Build 7 尚未由 Edward 實際點「拍照」確認相機畫面可開啟；自動檢查與安裝已通過，但不能代替實體相機操作。
- ❌ FAIL：尚未完成 StoreKit Sandbox 購買、取消、續訂與恢復購買。
- ❌ FAIL：資料匯出目前只建立申請，尚未完成實際檔案產出與交付工作。
- ❌ FAIL：雲端帳號永久刪除已有實作，但 Mac 缺正式後台憑證，尚未用測試帳號做端到端驗收。
- ❌ FAIL：HealthKit 同意／拒絕、通知、麥克風、藍牙音訊、長通話及重裝後資料恢復尚未逐項人工驗收。
- ❌ FAIL：Build 7 尚未重新產生正式 Archive／IPA，也尚未確認 App Store Connect 的 Build 號可用性。

## 上傳決策

目前 **不可送審**。簽章與 IPA 已通過，但公開登入設定、Cloud Run 點數對應、真實登入、Sandbox 金流及資料權利仍有未通過項目。

## 下一步

1. 合併並部署本次 App／Web 修正，確認公開登入設定生效。
2. 以 canary 部署 Cloud Run 點數對應，驗證後再升 100% 流量。
3. 在 Edward iPhone 完成登入、金流、HealthKit、通知、音訊與資料恢復矩陣。
4. 完成資料匯出交付流程與帳號刪除端到端測試。
5. 完成登入修正後重做 Build 7 Archive／IPA，查 App Store Connect Build 號可用性後再上傳。
6. 完成截圖、隱私標籤、年齡分級與審核備註後送 TestFlight。
