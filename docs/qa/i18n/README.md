# Munea 多語系驗收證據格式

這個資料夾只接受當次精確 App build 的證據。目錄名稱固定為：

```text
docs/qa/i18n/
  zh-TW/
  en/
  ja/
  es/
```

不得先建立假 PASS 檔案。`scripts/i18n-release-readiness.js` 會在檔案不存在、格式不完整、截圖不存在或 `result != pass` 時保持發布 Gate 關閉。

## 共用資料安全證據

四個語系共用兩份資料層證據，放在 `docs/qa/i18n/` 根目錄，不複製到各語系資料夾：

- `locale-context-data-audit.json`：由 `scripts/locale_context_data_audit.py` 對正式環境的唯讀、去識別化匯出執行。不得包含姓名、Email、電話或原始資料庫 ID；所有 active record 必須具備完整 LocaleContext，且 account/person 關聯不可錯置。
- `member-data-isolation-e2e.json`：由 `scripts/member_data_isolation_probe.py` 對獨立的非正式 Supabase staging project 執行。它會從 A/B 兩個預先建立的測試家庭，分別驗證直連 Supabase RLS 與 Brain service-role handler 都無法讀取另一個家庭。

會員隔離探針只送唯讀請求，且程式會硬拒絕東京正式 project `fespbkdwafueyonppzwq`、回滾 project `uhmpmystjjdqqxlpsthc` 與正式 Brain 網址。執行前需用環境變數提供：

- staging 目標：`MUNEA_I18N_STAGING_SUPABASE_URL`、`MUNEA_I18N_STAGING_SUPABASE_PROJECT_REF`、`MUNEA_I18N_STAGING_SUPABASE_PUBLISHABLE_KEY`、`MUNEA_I18N_STAGING_BRAIN_URL`、`MUNEA_APP_KEY`
- A/B 測試家庭：各自的 bearer token、account ID、person ID、family ID
- 已移除成員：`MUNEA_I18N_REMOVED_MEMBER_TOKEN`

token 與 ID 只從 process environment 讀取，不可寫進指令列、repo 或證據檔。探針輸出只保存 HTTP status、row count、staging revision 與布林結果，不保存 API 回應內容。執行形式：

```powershell
python scripts\member_data_isolation_probe.py `
  --exact-commit <40字元commit> `
  --evidence-reference <內部驗收編號> `
  --fixture-lifecycle-reference <staging測試帳號管理紀錄> `
  --output docs\qa\i18n\member-data-isolation-e2e.json
```

產出 `pass` 後仍需人工確認 `docs/MEMBER-DATA-ISOLATION-READINESS.json` 的證據來源，再把 status 改為 `approved`；探針本身不會自動開啟市場。

## 全畫面文案契約

`web/src/i18n/app-surface-copy-manifest.json` 是畫面到文案的可執行對照表。它必須與 `app-surface-manifest.json` 的 38 個 shipping states 完全一致，並讓四語 catalog 的每一個 key 至少歸屬一個實際畫面。`scripts/test-app-surface-copy-manifest.js` 會驗證：

- 38 個 state 不缺漏、不重複。
- 每個 state 至少有 3 個可驗收的文案 key。
- 所有 catalog key 在繁中、英文、日文、西班牙文都存在且非空白。
- 英文與西班牙文沒有中文字殘留。
- 健康、安全、同意、用藥與通知隱私的高風險聲明被明確列為必要文案。

這份契約只證明文案已備妥，不代表 DOM／動態 renderer 已接線，也不能取代母語審稿與 456 張 exact-build 畫面驗收。

## native-review.json

母語審稿不能只在 manifest 寫 `approved`。每個語系需由實際審稿者建立：

- `schema`: `munea.i18n-native-review.v1`
- `locale`、`contentVariant`
- 40 字元 `exactCommit`、ISO 8601 `reviewedAt`
- 不含個資的 `reviewerReference` 與 `reviewerRole`
- 目前 catalog 原始檔的 `catalogSha256`
- 完整 key 清單的 `reviewedKeyCount` 與 `reviewedKeysSha256`
- `openIssues: 0`
- `checks` 全部為 `true`：語意保留、文法自然、語氣合宜、文化脈絡、placeholder 上下文，以及實際朗讀語音文案

只要 catalog 內容或 key 清單後續改變，既有母語審稿證據就會失效，必須重審受影響版本。不得填入審稿者姓名、Email 或其他直接個資。

執行 `node scripts/i18n-native-review-worklist.js --locale ja > <工作檔>.json` 可產生涵蓋單一語系所有 catalog key 的工作檔。審稿者必須逐筆把 `result` 改為 `pass`，並把六個 `checks` 全部改為布林值 `true`；若翻譯與繁中來源完全相同且未在日文共用詞 allowlist，還必須留下 `reviewerNote`。工作檔根節點另需填入：

```json
{
  "review": {
    "exactCommit": "<40字元commit>",
    "reviewedAt": "<ISO 8601>",
    "reviewerReference": "<不含個資的內部審稿編號>",
    "reviewerRole": "native-language-reviewer"
  }
}
```

完成後用 `node scripts/i18n-native-review-evidence.js --input <工作檔>.json --output docs/qa/i18n/ja/native-review.json` 編譯證據。只要少一個 key、少一項檢查、catalog bytes 改變、placeholder 或翻譯被工作檔竄改，compiler 都會拒絕建立 PASS。compiler 不會自行把 `review-manifest.json` 改成 approved。

## app-store-native-review.json

App Store 主頁文案、五張商店截圖文案與八個內購項目必須由母語審稿者一起驗收，不能只把 manifest 狀態改成 `approved`。每個上架目標固定包含 32 筆人工檢查：

- App Store 主頁文案 6 筆
- 五張截圖的標題與說明共 10 筆
- 八個內購項目的名稱與說明共 16 筆

執行 `node scripts/app-store-native-review-worklist.js --locale en > <工作檔>.json` 可產生單一目標的工作檔。可用目標為 `zh-TW`、`en`、`ja`、`es-ES`、`es-MX`；西班牙文必須選擇實際市場變體，不能用未定市場的 `es` 代替。

審稿者需逐筆將 `result` 設為 `pass`，並將六項 `checks` 全部設為布林值 `true`。工作檔根節點另需填入：

```json
{
  "review": {
    "exactCommit": "<40 字元 commit>",
    "reviewedAt": "<ISO 8601>",
    "reviewerReference": "<不含個資的內部審稿編號>",
    "reviewerRole": "native-language-store-reviewer"
  }
}
```

完成後執行 `node scripts/app-store-native-review-evidence.js --input <工作檔>.json --output docs/qa/i18n/en/app-store-native-review.json`。證據會綁定 App Store 地區路由、該語系完整 metadata、截圖尺寸／順序／文案、八個 IAP 商品事實與該語系完整 IAP copy 的 SHA-256；文案、商品事實或地區規則改動後，舊證據會自動失效，單純把人工審核狀態從 `draft` 改成 `approved` 不會要求重審文案。西班牙市場證據分別放在 `docs/qa/i18n/es-ES/` 或 `docs/qa/i18n/es-MX/`。

## app-store-connect-audit.json

Repo 文案完成不代表 App Store Connect 已上傳、商品已在正確國家販售或價格已存在。正式候選版前必須用唯讀 App Store Connect API 匯出正規化快照，再執行：

`node scripts/app-store-connect-i18n-evidence.js --input <唯讀快照>.json --output docs/qa/i18n/app-store-connect-audit.json`

驗證器會拒絕以下情況：

- 西班牙市場尚未在 manifest 選定 `es-ES`、`es-MX` 或兩者
- 快照超過 72 小時、來自非唯讀流程、含 secrets 或執行任何 production write
- Bundle ID／App Store app ID 不符
- 任一目標地區沒有開放 App
- App Store metadata 與 repo 審稿版本不一致，或少於五張截圖
- 八個 IAP 商品缺漏、類型不符、沒有 App Review 截圖
- 任一目標地區未開放某個 IAP，或缺 StoreKit 當地幣別／`displayPrice`
- IAP 名稱與說明和 repo 審稿版本不一致

輸出證據只保留來源參考、雜湊與結果，不保存 API 私鑰、JWT、使用者資料或交易資料。`app-store/connect-audit-requirements.json` 是時效、唯讀方式與證據路徑的發布契約；任何人工把 manifest 改成 `verified` 的操作，都不能取代這份新鮮快照證據。

## visual-qa.json

必要欄位：

- `schema`: `munea.i18n-visual-qa.v1`
- `locale`
- `appVersion`、`build`、40 字元 `captureCommit`、64 字元 `binarySha256`、正整數 `binaryBytes`
- ISO 8601 `capturedAt`
- `profiles` 必須恰好包含 `iphone-small-standard`、`iphone-standard`、`iphone-dynamic-type-large`
- `screens` 必須完整覆蓋 `web/src/i18n/app-surface-manifest.json` 的 38 個 shipping states，包括主頁、通話各狀態、連接裝置、全部 modal／reader，以及動態建立的通知設定與通知收件匣
- 每個 screen 的每個 profile 都要有獨立、實際存在、尺寸有效且 SHA-256 相符的 PNG 與 `result: pass`，並確認：
  - `noOverflow`
  - `noClipping`
  - `noUntranslatedCopy`
  - `layoutAccepted`

因此每個語系至少需要 38 states × 3 profiles = 114 張 App 驗收圖，四語合計 456 張；不能以同一張圖重複充當不同 state 或 profile。新增 shipping surface 時，manifest 與截圖需求會同步增加。

執行 `node scripts/i18n-visual-qa-worklist.js` 可產生完整 456 筆 capture worklist；使用 `--locale en` 等參數可只列出單一語系的 114 筆。每筆都包含實際 App state、profile、來源 anchor、預定 PNG 路徑與四項人工檢查，初始狀態固定為 `pending`。

worklist 不會自動開啟畫面、不會建立假截圖，也不會把任何項目改成 PASS。每張圖必須來自同一個 exact installed iPhone build，並在當次驗收中實際開啟、儲存與檢查。發布驗證會拒絕路徑重用，也會拒絕把相同 PNG 內容複製成不同檔名充當另一個 state 或 profile。

擷取前先把單一語系 worklist 存成工作檔，填妥 `buildIdentity` 的 commit、IPA SHA-256、IPA bytes、App version、build，以及根節點 `review.capturedAt`、不含個資的 `reviewerReference`、`reviewerRole`。每張實機圖需依 worklist 的 `workspacePath` 儲存，人工確認四個 checks 後把該 entry 設為 `result: pass`。

完成 114 張後執行 `node scripts/i18n-visual-qa-evidence.js --input <工作檔>.json --output docs/qa/i18n/en/visual-qa.json --ipa <同一個候選版.ipa>`。compiler 會重新雜湊實體 IPA，確認 SHA-256 與 bytes 都和工作檔一致，並驗證：

- 38 states × 3 profiles 完整且順序未漂移。
- PNG 路徑留在該語系證據資料夾內，symlink 也不能跳出去。
- PNG 必須具備完整且 CRC 正確的 `IHDR`、`IDAT`、`IEND` chunk；截斷檔、壞檔或只偽造標頭的檔案一律拒絕。
- 小尺寸／標準／Dynamic Type profile 的圖片尺寸符合 1x、2x 或 3x iPhone capture。
- 114 張圖的 SHA-256 全部不同，不能複製同一張圖充數。
- 四項人工檢查全為布林 `true`，且 evidence 綁定同一 commit、IPA、version、build。

compiler 不會截圖、不會自行勾選人工檢查，也不會把 review manifest 改成 approved。

## voice-e2e.json

必要欄位：

- `schema`: `munea.i18n-voice-e2e.v1`
- `locale`、`conversationLocale`
- `appVersion`、`build`、`profile`、`environment`、`device`
- 40 字元 `exactCommit`、64 字元 `binarySha256`、正整數 `binaryBytes`、ISO 8601 `testedAt`
- `serviceRevisions`: `brain`、`voice`、`gateway`、`avatar`
- `steps` 全部為 `true`：
  - `openingInLocale`
  - `microphoneAudioUnderstood`
  - `assistantResponseAudible`
  - `assistantResponseVisible`
  - `mixedLanguageTurn`
  - `temporaryVoiceSwitch`
  - `permanentPreferenceConfirmed`

## installed-app-e2e.json

必要欄位：

- `schema`: `munea.i18n-installed-app-e2e.v1`
- `locale`
- `appVersion`、`build`、`profile`、`environment`、`device`
- 40 字元 `exactCommit`、64 字元 `binarySha256`、正整數 `binaryBytes`、ISO 8601 `testedAt`
- `serviceRevisions`: `brain`、`voice`、`gateway`、`avatar`
- 從按下通話、權限、Auth、帳號、點數、Gateway、Voice、Avatar、真實麥克風上行、AI 聲音與畫面，到掛斷釋放容量，所有 `steps` 都必須為 `true`

瀏覽器、模擬器、單元測試、synthetic probe、developer-direct 或不同 build 的成功紀錄都不能代替 installed App E2E。

## 精確版本證據鏈

同一語系的 `visual-qa.json`、`voice-e2e.json`、`installed-app-e2e.json` 與 `purchase-e2e.json` 必須指向同一個 source commit、App version、build、IPA SHA-256 與 IPA bytes；四份證據少一份 binary identity 或不一致都不得通過。語音證據與安裝版的 Brain／Voice／Gateway／Avatar revisions 也必須一致，購買 backend revision 必須對上安裝版 Brain revision。任一份證據來自其他 build 都會讓 `exactBuildEvidenceChain` Gate 失敗。

## purchase-e2e.json

必要欄位：

- `schema`: `munea.i18n-purchase-e2e.v1`
- `locale`、`storeLocale`
- `appVersion`、`build`、`profile`、`environment`、`device`、`backendRevision`
- 40 字元 `exactCommit`、64 字元 `binarySha256`、正整數 `binaryBytes`、ISO 8601 `testedAt`
- `steps` 必須確認登入、8 商品載入、免費會員不得購買點數、取消與未驗證交易不入帳，以及有效訂閱還原
- `products` 必須恰好覆蓋 4 個訂閱與 4 個點數包；每項都要在實體 iPhone 的 StoreKit Sandbox 確認：
  - 顯示名稱符合該語系
  - 價格由 StoreKit 回傳並顯示
  - Apple 付款視窗可開啟
  - 後端驗證交易
  - 正確方案或點數入帳
  - transaction 完成且 App 狀態刷新

測試不得記錄 Sandbox Apple ID、付款資料或完整交易 JWS。模擬器、假交易與不同 build 的結果不能代替本證據。

## 一次完成 App、語音與購買驗收

每個語系先建立一份不可直接通過的驗收清單：

```powershell
node scripts/i18n-app-e2e-evidence.js `
  --locale en `
  --template <安全工作目錄>\en-app-e2e-worklist.json
```

把同一個已安裝 iPhone build 的 commit、IPA SHA-256、IPA bytes、版號、build、裝置、環境與 Brain／Voice／Gateway／Avatar revision 填入後，實際完成：

- App 通話全路徑：麥克風、Auth、帳號、點數、Gateway、Voice、Avatar、開場、真實語音、AI 回覆、掛斷釋放容量。
- 語音語系：指定語言開場、混合語言、單次切換，以及使用者確認後的永久偏好。
- StoreKit Sandbox：8 個產品的在地名稱、系統價格、購買 sheet、伺服器驗證、權益套用、transaction finish、取消／未驗證／恢復購買路徑。

`npm run ios:archive` 只接受乾淨 worktree，並會在 App bundle 內建立 `public/src/build-identity.json`。在已安裝的候選 App 上用 Safari Web Inspector 執行 `fetch('src/build-identity.json').then(r => r.json()).then(console.log)`，把回報的 schema、Bundle ID、commit、version、build 填入 `installedApp.runtimeIdentity`。這份資料不含帳號或裝置個資；compiler 會拒絕 runtime identity 與候選 IPA 不一致的驗收結果。

所有步驟都由驗收人員標為 `true`、每個產品標為 `pass` 後，才可編譯三份 release gate 證據：

```powershell
node scripts/i18n-app-e2e-evidence.js `
  --input <安全工作目錄>\en-app-e2e-worklist.json `
  --output-dir docs\qa\i18n\en `
  --ipa <安全工作目錄>\Munea-candidate.ipa
```

工具會重新雜湊輸入的實體 IPA、不覆寫既有證據，且只接受非敏感的 ticket／證據引用；不得放入個資、Apple ID、原始音訊、token、JWS 或 transaction payload。西班牙文在 `app-store/in-app-purchases/manifest.json` 正式選定 `es-ES` 或 `es-MX` 前，編譯器必須拒絕產生通過證據。

## 本機 catalog 預覽

`tools/i18n-preview.html?locale=ja` 可在本機 HTTP server 中查看繁中、英文、日文、西班牙文的代表性 catalog 元件、登入、設定、個人資料、資料匯出／刪除、字體、訂閱方案、點數包、StoreKit 價格格式與購買錯誤狀態，並用 `125% text` 按鈕先檢查長字串換行。

這個頁面：

- 不連正式 API、不讀會員資料、不保存語言。
- 價格是 QA 用的各地格式範例，不是正式售價，也不會開啟 Apple 付款。
- 只證明 catalog bootstrap 與代表性元件能渲染。
- 不代表完整 App 畫面、App Store 截圖、實機 Dynamic Type 或 installed App E2E 通過。

## 本機 App 畫面預檢

`scripts/app-status-i18n-browser-precheck.js` 與
`scripts/app-notification-i18n-browser-precheck.js` 只啟動綁定
`127.0.0.1` 的 fixture server，並封鎖瀏覽器對 loopback 以外的請求。
目前的狀態頁與通知中心四語截圖、雜湊及檢查結果放在：

- `docs/qa/i18n/local-browser-precheck/status-2026-07-29/`
- `docs/qa/i18n/local-browser-precheck/notification-2026-07-29/`
- `docs/qa/i18n/local-browser-precheck/full-surface-standard-2026-07-29/`

`full-surface-standard-2026-07-29` 是 loopback-only 的 38 states × 4 locales
標準 iPhone viewport 預檢，共 152 張獨立截圖。它會阻擋外部 browser request，
檢查空白狀態、runtime error、可見系統文案殘留來源語言與水平溢位，並以
`scripts/test-app-full-surface-i18n-browser-precheck.js` 驗證畫面集合與每張 PNG
checksum。家人傳話、家人姓名、藥名等使用者內容可保留原語言，不得被 UI
localizer 強制翻譯。

這份預檢仍是 `releaseEvidence: false`。HTML date/time 原生控制項可能依測試機
作業系統的區域格式顯示；App Language 與 iOS 原生 picker 的最終一致性必須在
exact-build installed-iPhone gate 驗證。它也不取代 small iPhone、Dynamic Type
Large、StoreKit、Gateway、Voice、Avatar 或 App Store Connect 驗收。

這些報告固定標記 `releaseEvidence: false`，只可作為開發預檢；不能替代
同一候選 IPA 在實體 iPhone 上完成的 456 張 visual QA、APNs、通話及購買驗收。
