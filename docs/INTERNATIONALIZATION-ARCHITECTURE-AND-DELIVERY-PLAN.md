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

Phase 1d（2026-07-28）補齊可共用的語言品質底盤：

- 核心四語 catalog 擴充至至少 90 個 App 共用狀態，包含登入、首頁、健康、心情、家庭、通話排隊、設定、訂閱、回饋與用藥。
- locale runtime 增加 `Intl` 複數、日期、數字、清單與相對時間格式，避免日期／單位／複數靠中文字串拼接。
- `review-manifest.json` 將 catalog coverage、母語審稿、視覺 QA、語音 E2E、區域安全／法律、App Store metadata 與市場開放設為逐語系必要核准；任何一項未核准都不能開 runtime 或 binary gate。

Phase 1e（2026-07-28）：App 全畫面狀態契約

- `web/src/i18n/app-screen-manifest.json` 將 App WebView 的 10 個必要畫面狀態與 profile／data／font 三個必要 modal，映射到 112 個具語意的 catalog key，讓「全畫面」有可追蹤的完成定義。
- 設定、登入、帳號、家庭、健康安全、個人資料、資料匯出／刪除與字體顯示的四語文案已備妥；英文與西班牙文會被測試阻擋中文字殘留。
- `app-binding-manifest.json` 再把現有 DOM anchor、動態 renderer 與需要 markup refactor 的容器對到 27 個靜態接線、7 個動態狀態及 5 個結構改造，讓 #247／#270／#273 合併後可依清單接線，不靠人工搜尋中文字。
- release readiness 新增 `appUiIntegration` Gate；只要 screen／binding manifest 尚未明確標記 `integrated`，即使 catalog、審稿或截圖狀態被誤改為通過，也不得開放任一語系。
- manifest 明確保持 `pending-main-screen-integration` 與 `visualQaPending=true`；catalog 備妥不等於畫面已接線，也不能解除 exact-build 截圖與實機 Gate。
- `scripts/test-app-screen-localizations.js` 與 `scripts/test-app-i18n-binding-manifest.js` 驗證畫面狀態與 inventory 完全一致、四語 key 齊全、DOM anchor／renderer 存在且每個狀態至少有五個驗收項目，並納入 UI contract suite。

Phase 1f（2026-07-28）：全畫面遷移工作表與排版壓力測試

- `scripts/i18n-migration-worklist.js` 從正式 shipping surface 即時計算穩定 worklist；目前 App WebView 有 1,727 個繁中文案出現位置、1,211 個唯一來源字串，不再用「catalog 已有 111 keys」誤稱全畫面完成。
- 每筆工作項目保留檔案、行號、來源型態與穩定 hash key，並區分 static text、attribute、runtime/interpolated copy 與必須先拆 HTML 的 markup refactor。
- `scripts/i18n-pseudo-catalog.js` 產生保留 placeholder 的 35% 擴張壓力文案；主畫面接線後，必須先用 pseudo locale 跑完窄螢幕與 Dynamic Type，再進入四語正式截圖。
- 這兩個工具只讀來源並在測試記憶體內產生資料，不改 shipping catalog、不切 runtime locale，也不影響正式服務。

Phase 1g（2026-07-28）：先接上無衝突的健康與陪伴角色模組

- Apple 健康的連接、解除、同步狀態與系統授權說明已改用四語 catalog；舊版繁中 runtime 不認識新 key 時仍使用原繁中 fallback，現行行為不變。
- 陪伴角色的後端 `backendChar` 與 template id 保持不變，只有顯示名稱與角色描述跟隨 App Language；使用者自訂名稱永遠保留，未自訂的預設名稱換語言時會同步更新。
- 對應測試驗證 HealthKit 連接／解除與 refresh 去重不回歸，也驗證換語言不會改角色後端身分或覆蓋自訂名稱。
- 角色名稱會進入通話人設，屬 chat-call path risk；目前只有 coded + tested，仍為 `App E2E pending`，沒有部署。

Phase 1h（2026-07-28）：Browser／iOS App Language bootstrap

- `web/src/i18n.js` 啟動時載入 catalog manifest、catalog runtime、DOM localizer 與四語 catalog；不再把 runtime 永久寫死為繁中。
- 正式模式只會選擇 manifest 中 `runtimeEnabled=true` 的裝置 App Language；目前 en／ja／es gate 關閉，所以正式 App 仍安全回退繁中。
- 開發設定必須同時有 `MUNEA_DEV_CONFIG.enabled=true` 與 `i18nPreviewLocale` 才能預覽 development locale；`setLocale()` 不接受使用者指定值，也不寫 localStorage。
- bootstrap 完成會送出 `munea:locale-ready`，供待 #247／#270 合併後的 App 初始化等待；載入失敗則保留繁中並回報 fallback，不阻斷 App 啟動。
- 目前只有靜態 `data-i18n`、已接線模組與開發 preview 能反映裝置語言；大量 `index.html`／`app.js` 動態文案尚未遷移，不能宣稱全畫面完成。

Phase 1i（2026-07-28）：iOS permission localization parity

- 四個 `InfoPlist.strings` 都具備 App 名稱、麥克風、相機、照片、語音辨識、通知、本機網路、HealthKit 讀取與預留寫入共 9 個相同 key。
- 自動測試會阻擋缺 key、空字串，以及英文／西班牙文權限提示混入漢字。
- Xcode variant group、`knownRegions` 與 `CFBundleLocalizations` 仍只有 `zh-Hant`；en／ja／es 必須等全畫面、語音與 exact-build gates 通過後才一起註冊，避免 IPA 過早宣告支援。
- 此階段只補齊未打包草稿與靜態契約，未執行 Xcode build、archive、upload 或 App Store Connect 變更。

Phase 1j（2026-07-28）：38 個 shipping states 的完整四語文案契約

- 四個 App catalog 已擴充到 430 個一致 key，補齊連接裝置、問答、家庭活動、興趣、安全、陪伴角色、報告、家庭圈、邀請／加入、預約、歷史、同意、版本、用藥管理、通知設定／收件匣與文字聊天。
- `web/src/i18n/app-surface-copy-manifest.json` 將 38 個 shipping states 逐一綁定文案群組與高風險必要 key；測試要求 38 個 state 與畫面盤點完全一致，且 430 個 key 全部至少歸屬一個實際畫面。
- 安全、同意、健康連接與用藥畫面採不依語言推定國家的通用緊急／醫療聲明；所在地緊急號碼仍只能由後端核定的 `safetyRegion` 決定。
- `catalogCoverage` 發布 Gate 現在同時要求母語審稿核准與完整畫面文案 mapping，避免只審核心畫面就誤開語系。
- 這一批是 catalog + contract + automated tests，尚未修改被 #247／#270／#273 佔用的主 App 檔案；全畫面接線、456 張截圖與 exact-build iPhone 驗收前仍為 `App E2E pending`。

Phase 1k（2026-07-28）：動態畫面的自動本地化接線

- `web/src/i18n/dom-localizer.js` 以 `MutationObserver` 監看新增節點與經審核的 `data-i18n*` 屬性，通知設定、收件匣、錯誤狀態及執行期 modal 在插入 DOM 後能自動套用目前 App Language。
- Observer 只寫入 `textContent` 與 aria-label／placeholder／title／value 白名單，不接受 HTML；非瀏覽器或不支援 Observer 的環境則安全略過，不阻斷 App 啟動。
- `web/src/i18n.js` 在 catalog 初始化與初次套用後才啟動 observer，語系來源仍只跟隨 iOS App Language 或明確開發預覽，沒有新增使用者語言切換器。
- `appUiIntegration` Gate 現在也要求動態 observer 已整合；這只完成動態接線底盤，#270 內的通知 renderer 仍須在合併後補上實際 key，故整體狀態仍為 `App E2E pending`。

Phase 2a（2026-07-28）將 LocaleContext 接入帳號資料：

- 不以語言推測國家，也不為每個國家另建會員資料庫；沿用 `accounts.locale/preferred_languages` 與 `persons.locale/timezone/region_code/attributes`，分別保存 UI、陪伴對話、國家／時區與安全／法律／資料區域。
- 帳號 bootstrap、JSON fallback、Supabase 新增／更新與營運帳號摘要都回傳同一份 `localeContext`；現有台灣帳號保持原行為。
- 本批碰 Auth／account bootstrap，屬 call-path risk；只有單元與 smoke precheck，仍為 `App E2E pending`，未部署。

Phase 2b（2026-07-28）將收件人的 App 語言接入通知：

- JSON 與 Supabase 通知先取最新有效 iOS 裝置的 UI locale，再回退帳號 UI locale；不使用陪伴聊天語言，也不由語言推測國家。
- 四語 generic、家庭轉達與家庭邀請的鎖定畫面文案由後端產生，健康敏感內容仍固定隱藏；通知 metadata 留下 locale 供 APNs fallback 使用。
- 新增 `027_localized_notification_copy.sql`，目前只在隔離分支接受靜態與測試驗證，尚未套用任何正式資料庫。

Phase 2g（2026-07-28）：用藥時段改用語言無關 ID

- `web/src/i18n/medication-schedule.js` 定義 `after-breakfast`、`after-lunch`、`after-dinner`、`bedtime` 四個 canonical slot ID；顯示文字才由四語 catalog 決定。
- 相容層能讀取舊繁中、英文、日文、西班牙文時段文字及自訂時間，輸出固定排序並去除重複值。
- 新表單接線後採 `slotIds` canonical 欄位，同時保留繁中 `time` 字串雙寫給既有 App；等 exact-build 跨版本資料遷移驗證完成後才移除 legacy 欄位。
- 目前只建立資料契約與測試，尚未修改衝突中的 App 表單／畫面；不會重寫現有用藥資料，也不部署。

Phase 2c（2026-07-28）補齊營運後台的國際使用者狀態：

- 用戶名冊直接顯示國家／地區、App UI 語言與陪伴聊天語言，並可用國碼、語言、時區或資料區域搜尋。
- 用戶明細分別顯示 UI／聊天語言、時區、安全／法律區域與資料區域；不把任一欄位混成單一「地區」推論。
- 後台仍維持內部繁中操作介面；本批只補營運可視性，不等同四語 App 畫面已完成。

Phase 2d（2026-07-28）建立英文、日文、西班牙文法律與客服靜態草稿：

- 新增 privacy、terms、support 的逐語系靜態 HTML 與共用排版；不使用執行期 JavaScript，也不加入 App 內語言切換器。
- 非繁中頁面只提供「當地緊急服務」原則，不帶入台灣 119／1925；緊急資訊最終仍須依後端核定的 `safetyRegion` 接線。
- 英文、日文、西班牙文翻譯與法律審查仍標示 `pending`，在審查、畫面 QA、App reader 接線完成前不可開放 runtime／binary gate。
- 現有繁中服務條款的點數文案已對齊實際 call gate：點數不足時不開始新語音／虛擬形象通話，不再宣稱會自動切換免費通話。
- 目前只建立 repo 內草稿與自動護欄，沒有部署；待 #270 合併後，App reader 才依已核准的 UI locale 選擇對應靜態頁面。
- `scripts/build-app-site-legal-localizations.js` 將三語來源可重現地產生到 Firebase 的 `app-site/legal/`；未核准頁面自動加入 `noindex,nofollow`，測試確保公開產物不引用未部署的 `web/src/` 路徑。本批仍未執行 Firebase deploy。

Phase 2e（2026-07-28）建立 App Store 多語 metadata 與可用地區閘門：

- 四語 metadata 以 repo 草稿保存並檢查 Apple 欄位限制：名稱／副標各 30 字元、推廣文字 170 字元、描述 4,000 字元、關鍵字 100 bytes；描述維持純文字。
- metadata 語系、Xcode binary 語系、App／IAP 可用國家是三個獨立狀態；任何一項存在都不能推定另外兩項已上線。
- 現有五張 1242×2688 圖只記為繁中未審截圖；英文、日文、西班牙文截圖仍為 `missing`，不得沿用繁中圖宣稱完成畫面驗收。
- 西班牙文先保留中性翻譯草稿，但 App Store locale 與可用地區維持空值，必須先選定 `es-ES` 或 `es-MX` 再做母語、法規、客服與截圖審核。
- `appAvailability` 與 IAP availability 只以 App Store Connect 為權威，目前 repo 一律記為 `unverified`、`changeAuthorized=false`；本批不操作 App Store Connect。
- Apple 目前將西班牙（`es-ES`）與墨西哥（`es-MX`）列為不同 App Store localization；兩個候選值明列於 manifest，但產品／法規市場決策前不代選、不開地區。
- Apple 現行欄位與在地化規則參考：<https://developer.apple.com/help/app-store-connect/reference/app-information/app-information>、<https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information>、<https://developer.apple.com/help/app-store-connect/manage-app-information/localize-app-information>；可用地區參考：<https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/manage-availability-for-your-app-on-the-app-store>。

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

Phase 3a（2026-07-28）先建立 signed call claim 的解析護欄：

- call token 只允許一個完整的 `locale_context` 巢狀 claim，不接受頂層 `locale`、`countryCode` 或 `safetyRegion` 別名，避免下游把 UI 語言或 App 候選值當成可信政策。
- LocaleContext 版本必須明確為 v1；未知版本直接拒絕，不能靜默降級成台灣規則。
- rollout 期間，沒有 locale claim 的既有已簽 token 仍可得到繁中／台灣相容預設；Gateway、Voice 與實機 E2E 通過後切為 `allow_legacy=false`。
- 本批只加入共用解析與單元測試，尚未改 Gateway 簽發或 Voice 使用方式；待 #258／#270 合併後再接線，正式 call path 不變。

Phase 3b（2026-07-28）建立混合語言與語音切換狀態規則：

- `engine/localization.py` 將已儲存的 `baseLocale`、本通使用的 `sessionLocale`、待確認的 `pendingPermanentLocale` 分開，絕不把語言變化帶到 `countryCode`、`safetyRegion` 或資料區域。
- 單一輪偵測到不同語言時，可以用當輪主要語言回覆，但不自動改寫 session 或會員偏好；中英夾雜本身不是永久切換指令。
- 「這通改用日文」只改 session；「以後都用日文」先暫時切換並要求確認，確認後才回傳可寫入帳號的 `persistedLocale`。
- 狀態模組只接受 ASR／模型產生的結構化語言與切換意圖，不用脆弱的關鍵字規則猜測使用者意思；正式 Voice 接線仍等待 #270。

Phase 3c（2026-07-28）建立 Live Voice 共用語系設定包：

- `voice_session_locale_profile()` 將可信 `LocaleContext` 一次轉成 session／response／caption locale、ASR/TTS language code、開場、重試、語言 prompt 與區域安全提示，避免 `live_voice_server.py` 各處自行寫死語系。
- `voice_turn_locale_profile()` 接續混語狀態機：單輪中英／日英混講可用主要語言回覆，但不改會員偏好；暫時切換只改 session，永久切換仍要確認。
- 緊急號碼只由後端核定的 `safetyRegion` 選擇，絕不由 UI／對話語言推測。`TW` 才能帶 119／1925；其他或未知區域使用該回覆語言的「聯絡所在地緊急服務」通用文字。
- 四語 profile 與跨語回合測試已建立；目前尚未改 #270 佔用中的 `live_voice_server.py`，所以只是 coded + tested 的接線前置，仍為 `App E2E pending`。

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

Phase 5a（2026-07-28）將發布判定改為證據驅動：

- `scripts/i18n-release-readiness.js` 以 catalog、review、法律、App Store manifest 與 `docs/qa/i18n/<locale>/` 的實際證據即時計算四語狀態，不以人工寫一句「完成」代替。
- 每個語系都必須同時通過 catalog、App UI 接線、runtime、binary、母語審稿、視覺截圖、真實語音、區域法律、商店文案、8 項內購本地化、商店截圖、市場／價格可用性、exact-build installed App E2E、StoreKit Sandbox 購買 E2E 與精確版本證據鏈共 15 道 gate。
- `--strict` 只有四語全部有現行證據才回傳成功；目前四語都會明確顯示 `NOT READY`，這是正確護欄，不是測試失敗。
- 母語審稿、視覺、語音與實機證據的固定入口分別為 `native-review.json`、`visual-qa.json`、`voice-e2e.json`、`installed-app-e2e.json`；檔案不存在、JSON 無效或 `result` 不是 `pass` 都視為未完成。
- `native-review.json` 必須綁定目前 catalog 原始檔與完整 key 清單的 SHA-256；翻譯或 key 變更後，舊審稿證據會自動失效。
- `web/src/i18n/app-surface-manifest.json` 直接盤點正式 App 38 個 shipping states：主頁、狀態、家人、設定、連接裝置、通話各狀態、全部 modal／reader，以及動態通知設定與收件匣；發布 gate 不再只看核心 13 畫面。
- `visual-qa.json` 必須覆蓋上述 38 states，且每個畫面都要有小螢幕、標準螢幕、放大字體三份獨立 PNG；每語系 114 張、四語共 456 張，重複路徑或缺任一 profile 都不通過。
- `exactBuildEvidenceChain` 再確認視覺、語音、安裝版與 8 商品購買證據來自同一 commit／version／build／IPA SHA-256；四份證據都必須帶 binary identity，服務 revisions 不一致時也不得混用證據。

Phase 5b（2026-07-28）：App Store 五張圖故事板

- `app-store/localizations/screenshot-plan.json` 固定繁中、英文、日文、西班牙文的五張圖順序、對應 App 畫面與短文案，避免各市場截出不同產品承諾。
- 每張圖必須來自 exact approved build 與 synthetic QA account，禁止使用正式會員資料；必須確認沒有未翻譯文字、溢位或裁切。
- 目前只有故事板與文案草稿，沒有把計畫當成截圖證據；各語系 `screenshotStatus` 仍維持 missing 或 existing-unreviewed。
- 西班牙文仍必須先決定 `es-ES` 或 `es-MX`；決策前不得送審或開市場。

Phase 5c（2026-07-28）：8 項內購四語契約與實機驗收

- `app-store/in-app-purchases/manifest.json` 是 4 個訂閱與 4 個點數包的 repo 草稿單一來源；Product ID 保持既有不可變值，商品名稱只顯示實際 100／300／600／1,000 點，不把歷史 suffix 當權益。
- 繁中、英文、日文與中性西班牙文草稿都遵守 Apple 的 Display Name 2–30 字元、Description 最多 45 字元限制；repo 文案禁止寫死幣別與價格，畫面價格只使用 StoreKit 的在地化 `Product.displayPrice`。
- 點數包文案明確限定 Plus／Pro 會員，不改變「免費會員不能購買點數」的產品規則；訂閱月繳／年繳的每月點數與家庭人數都對齊 server-owned billing facts。
- 每個商品仍需 App Store Connect 身分、可售地區、價格與 App Review screenshot 的現況證據；目前全部維持 `unverified`，不操作正式商店。
- `purchase-e2e.json` 要求 exact build 在實體 iPhone 的 StoreKit Sandbox 逐項完成 8 個商品，確認在地名稱、StoreKit 價格、付款視窗、後端驗證、正確入帳、transaction finish、畫面刷新，另驗證取消／未驗證交易不入帳與訂閱還原。
- 原生 `StorePlugin.getProducts` 與 `MuneaStore.getProducts()` 已把 Apple 回傳的 `displayName`、`description`、`displayPrice` 正規化並快取；待衝突中的購買畫面合併後，只能使用這份 StoreKit 資料渲染，不得把台灣價格複製到海外語系。
- 這一批只增加草稿、測試與發布閘門，未打包、未上傳、未扣款，也不影響現有正式服務；在實機證據完成前狀態固定為 `App E2E pending`。

Phase 5d（2026-07-28）：訂閱與點數購買流程四語文案契約

- 四個 catalog 已補齊訂閱方案、點數包、登入提示、商品載入、確認付款、等待處理、付款失敗、帳戶不符、恢復購買與管理訂閱等 79 個畫面文案 key。
- 價格相關文案只保留 `{price}` placeholder，必須接 Apple 回傳的 `displayPrice`；測試會拒絕 `NT$`、`US$`、美元、歐元、日圓符號或 ISO 幣別被寫入購買流程翻譯。
- 四語共同鎖定產品規則：免費帳戶只有一次 5 分鐘體驗、每月方案點數不累積、加購點數不會到期，且先扣每月方案點數再扣加購點數。
- `scripts/test-purchase-flow-localizations.js` 驗證四語 key、placeholder、幣別、英文／西文中文字殘留與產品規則，並已納入既有 UI contract suite。
- `web/src/i18n/purchase-flow.js` 把 StoreKit 商品轉成訂閱／點數畫面 View Model；缺少 `displayPrice` 時寧可顯示商店暫時無法使用，也不回退到寫死價格，所有付款與恢復狀態都由同一份錯誤映射提供四語訊息。
- `scripts/test-purchase-flow-view-model.js` 用台灣、英語、日本與西語常見價格格式測試 Apple 價格原樣保留，並覆蓋取消、等待、未驗證、帳戶不符、連線失敗與恢復購買。
- 目前只是可接線的 catalog 與測試；`web/index.html`／`web/src/app.js` 的實際購買畫面要等 #247／#270 合併後再依最新主線接上，避免同檔競爭。接線、四語截圖與 StoreKit Sandbox 實機驗收完成前仍為 `App E2E pending`。

Phase 2f（2026-07-28）：安全 UI 套用與法律頁路由元件

- `web/src/i18n/dom-localizer.js` 只用 `textContent` 與明確允許的 `aria-label`、`placeholder`、`title`、`value` 屬性套用翻譯，不接受 HTML 字串，也不從 DOM 解析插值資料。
- 文件語言由 catalog metadata 設定 `<html lang>` 與 `dir`，讓 VoiceOver、鍵盤與排版引擎取得正確語言。
- `web/src/i18n/legal-routing.js` 將 UI locale 與法律頁選擇接在同一個 release gate：正式模式必須同時滿足 `runtimeEnabled=true` 與 `legalReview=approved`；否則回退繁中。開發預覽可明確傳入 `allowDraft=true` 查看待審稿。
- 元件與 catalog 已有獨立測試；`web/index.html`、`web/src/app.js` 的正式接線仍等待 #247/#270 先合併，避免覆蓋既有 App 與 chat-call 變更。
- 此階段只完成 coded + tested，未部署；`App E2E pending`。

## 5. 不影響正式服務的護欄

- 所有新能力先以 additive schema、feature flag 與舊版台灣預設加入。
- DB migration 只先加 nullable/default 欄位，不修改既有欄位語意；區域資料平面另做遷移與回滾演練。
- 服務先接受 LocaleContext、再 shadow 記錄、再內部 canary，最後才分市場開流量。
- Phase 0 不部署。後續每階段獨立 PR、獨立回滾點，不把三個市場同時打開。
- 「程式完成」不等於「可上架」；必須分別記錄 coded、tested、merged、packaged、deployed、verified。
