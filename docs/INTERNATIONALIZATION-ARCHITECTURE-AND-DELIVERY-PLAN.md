# Munea 國際化架構與開發計畫

狀態：2026-07-28 最後定案，開始分階段開發

首批產品語言：繁體中文、英文、日文、西班牙文

目前正式環境：維持繁體中文，不在本階段切換流量

## 1. 最後定案

### App 與對話語言

- App 不提供站內語言切換器。UI 跟隨 iOS 的 App Language，未支援的語言回退繁體中文。
- App Store 上架國家不直接決定 App 語言。使用者即使在日本下載，也可能把 iOS App Language 設成英文。
- 語音對話預設跟隨 App Language，但允許同一段對話自然混用中文、英文、日文或西班牙文。
- 聊聊依每一輪實際語音判斷主要語言，不因使用者偶爾說一個外語詞就切換整個 App。
- 使用者可直接說「接下來講英文」等指令，僅切換這通對話；只有「以後都用英文」這類明確永久指令才寫入會員偏好。
- 語音切換只影響對話，不改 UI、國家、法規、安全規則或資料存放區。

### 國家、法規與資料

- 語言不是國家。`uiLocale`、`conversationLocale`、`countryCode`、`timeZone`、`safetyRegion`、`legalRegion`、`dataRegion`、單位與幣別必須分開管理。
- 不為每個國家複製一套資料表。會員與家人資料以同一份 schema、tenant/user 邊界及 Row Level Security 隔離。
- 是否建立不同區域資料庫，以資料落地、法規與營運需求決定，不以語言決定。若啟用區域資料平面，同一會員固定歸屬一個 `dataRegion`，跨區服務不可直接查另一區的個資。
- `safetyRegion`、`legalRegion`、`dataRegion` 必須由後端帳號/市場設定確認並簽入呼叫權杖；不得只信任 App 傳入值，也不得從語音猜測。

### 前後台內容

- 前端 UI、Onboarding、錯誤訊息、通知、Email、App Store metadata 與客服文案全部使用語系資源鍵，不在程式中散落硬編碼文字。
- 後端資料分兩類：
  - 結構化事實只存一份，例如日期、藥名、關係、狀態與數值。
  - 需要給人閱讀的內容保存來源語言及翻譯版本；AI 摘要要標示生成語言與版本，不能覆寫原文。
- 管理後台使用單一入口，能依市場、UI 語言、對話語言、法規區與資料區篩選。後台不建立四套。
- 翻譯更新採 key/version 管理；缺少翻譯時可觀測並回退，不讓半翻譯內容靜默上線。

### UI 與語意品質

- 翻譯不是逐字替換。英文、日文與西班牙文都要做母語審校、長字串/換行、Dynamic Type、VoiceOver、日期時間、數字、單位與幣別 QA。
- 日文需特別驗證字級、行高、敬語與長輩易讀性；西班牙文需先決定首發市場版本（建議先選 `es-ES` 或 `es-MX`，不可混用法規與客服資訊）。
- 每次語系資源更新要跑 pseudo-localization、截圖差異與關鍵流程測試；正式發布前仍需實機人工驗收。

## 2. LocaleContext v1

所有 App、Gateway、Voice、Brain、通知與後台未來都共用下列語意，不再只傳一個 `locale`：

```json
{
  "version": 1,
  "uiLocale": "ja",
  "conversationLocale": "ja",
  "preferredLanguages": ["ja", "en"],
  "countryCode": "JP",
  "timeZone": "Asia/Tokyo",
  "units": "metric",
  "currency": "JPY",
  "safetyRegion": "JP",
  "legalRegion": "JP",
  "dataRegion": "jp-primary"
}
```

欄位來源與信任邊界：

| 欄位 | 主要來源 | 是否可由語言推定 |
| --- | --- | --- |
| `uiLocale` | iOS App Language | 不適用 |
| `conversationLocale` | UI 初始值、語音偵測或明確語音指令 | 不推定國家 |
| `preferredLanguages` | 對話觀測加上會員明確偏好 | 不推定國家 |
| `countryCode` | App Store/account 市場與會員確認 | 否 |
| `timeZone` | iOS 裝置設定，後端驗證格式 | 否 |
| `units`、`currency` | 市場設定或會員偏好 | 否 |
| `safetyRegion`、`legalRegion` | 後端核定政策 | 否 |
| `dataRegion` | 後端資料路由 | 否 |

本階段在 `engine/localization.py` 只加入正規化契約與舊版台灣預設值，尚未接到 Gateway、Voice 或正式流量。這使目前未攜帶 LocaleContext 的服務仍維持原本繁中/台灣行為；未支援的 App Language 可回退繁中，但明確傳入的非法政策/區域值會直接被拒絕，不會靜默套用台灣規則。

## 3. 服務架構

```text
iOS App Language ──> UI resource catalog
         │
         └──> LocaleContext candidate ──> Gateway/account verification
                                              │
                                              ├──> signed call token
                                              ├──> Brain prompt/content locale
                                              ├──> Voice ASR/TTS + code-switch
                                              ├──> safety/legal policy
                                              └──> regional data router

Admin ──> market/language/region filters ──> regional aggregates (no raw cross-region PII)
```

必須遵守：

1. Gateway 是呼叫時 LocaleContext 的信任邊界。
2. Voice 可逐輪偵測語言，但只有明確語音指令能更新 session/account 偏好。
3. 安全求助資訊依 `safetyRegion`，不能依 `conversationLocale`。
4. 資料庫路由依 `dataRegion`，不能依 App Store 國家或 UI 語言即時切換。
5. 各服務 logs/metrics 記錄非個資的 locale/region 維度，避免把語音逐字稿當觀測標籤。

## 4. 開發與發布排程

### Phase 0 — 契約與護欄（本次）

- 完成定案文件。
- 加入 LocaleContext v1 正規化、台灣相容預設與單元測試。
- 不接正式流程、不改 UI、不部署，正式服務零行為變更。

完成條件：既有 localization 測試全過，新測試證明語言不會推定國家、安全、法規或資料區。

### Phase 1 — UI 語系資源

- 建立共用 key catalog、繁中基準、英文/日文/西班牙文檔案及 fallback telemetry。
- 移除首頁、Onboarding、設定、錯誤與訂閱流程的硬編碼文案。
- 加入 pseudo-localization、缺 key 測試、Dynamic Type 與截圖測試。

注意：待目前修改 `web/index.html`、`web/src/app.js`、`web/src/styles.css` 的 PR 合併後再開始，避免競爭修改。

Phase 1a（2026-07-28）先完成不接 runtime 的安全地基：

- 建立四語 core catalog 與 release manifest；英文、日文、西班牙文一律標記 `development`、`runtimeEnabled=false`、`binaryLocalizationEnabled=false`。
- 加入 key 完整性、placeholder、HTML 注入、現有 `data-i18n` 覆蓋與 iOS binary 宣告一致性測試。
- 翻譯來源檔保留在 repo，但在完整 UI/Voice/安全/商店 gate 通過前，不把 en/ja/es `InfoPlist.strings` 加入正式 App target。
- 本次 iOS project 只修正「尚未發布卻先宣告語言」的 packaging 狀態；不包版、不上傳，`App E2E pending`。

Phase 1b（2026-07-28）先完成未接正式頁面的 locale runtime：

- UI 語言候選只來自 iOS/WebView 的 `navigator.languages`／`navigator.language`，不建立 App 內切換器，也不保存手動語言到 localStorage。
- 正式模式只選擇 manifest 中 `runtimeEnabled=true` 的語言；目前 en/ja/es 即使被裝置選中仍回退繁中。

Phase 1c（2026-07-28）建立完整交付面與回歸基準：

- `docs/I18N-SURFACE-INVENTORY.json` 把 App WebView、法律／支援頁、營運後台、官網、LocaleContext、Gateway／Voice、iOS binary 與 App Store 全部納入同一份完成矩陣。
- `scripts/i18n-surface-inventory.js` 掃描正式介面中的繁中文字串候選；遷移期間不得高於基準，正式開放前必須降為零或逐筆審核為非使用者文案。
- 完成不再以「有四個 JSON」判定，而是每個 surface 都要通過 catalog、動態內容、視覺截圖、區域安全、App Store 與實機語音 gate。
- development preview 才能預覽尚未發布的 catalog，方便翻譯與排版 QA，不改正式使用者行為。
- missing-key telemetry 只記錄 key 與 locale，去重後回退繁中；不記翻譯內容、畫面文字或任何使用者輸入。
- runtime 目前是純模組並已進 UI contract tests；等 #247/#270 合併後，才接到 `web/src/i18n.js` 與正式 DOM。

### Phase 2 — 帳號、內容與資料區

- 會員模型加入 UI/對話偏好、country/timezone 與後端核定 region 欄位。
- 建立資料分類、區域路由、RLS、備份、刪除與跨區匿名彙總規則。
- 通知、Email、AI 摘要與 CMS 內容加入語言/version 欄位。

### Phase 3 — Gateway 與即時語音

- Gateway 驗證並簽發 LocaleContext；Voice/Brain 僅接受可信上下文。
- 實作逐輪語言偵測、自然 code-switch、暫時/永久語音切換指令。
- ASR、TTS、開場白、fallback、安全政策與內容檢索全部依獨立欄位選擇。

此階段屬 chat-call path risk。完成程式與自動測試後仍標記 `App E2E pending`，直到使用受影響 profile 的實體 iPhone 完成完整通話驗收。

### Phase 4 — 後台與營運

- 後台增加市場、UI 語言、對話語言、法規區及資料區篩選。
- 建立翻譯覆蓋率、fallback 次數、ASR/TTS 品質、留存、客服與安全事件儀表板。
- 匯總跨區指標時去識別化，不把不同區域原始會員資料集中複製。

### Phase 5 — 商店與分市場發布

- 同一套 App binary 納入三種語系；App Store 文案、截圖、隱私說明與客服頁分市場準備。
- 技術可一次完成英文、日文、西班牙文；公開發布採逐市場開閘。
- 建議順序：`en-US` 小流量 canary → `ja-JP` → 選定的西班牙文市場（`es-ES` 或 `es-MX`）。
- 每一市場只有在翻譯、UI、語音、安全/法規、資料、客服及實機 E2E 都通過後才開放。

## 5. 不影響正式服務的護欄

- 所有新能力先以 additive schema、feature flag 與舊版台灣預設加入。
- DB migration 只先加 nullable/default 欄位，不修改既有欄位語意；區域資料平面另做遷移與回滾演練。
- 服務先接受 LocaleContext、再 shadow 記錄、再內部 canary，最後才分市場開流量。
- Phase 0 不部署。後續每階段獨立 PR、獨立回滾點，不把三個市場同時打開。
- 「程式完成」不等於「可上架」；必須分別記錄 coded、tested、merged、packaged、deployed、verified。
