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

## visual-qa.json

必要欄位：

- `schema`: `munea.i18n-visual-qa.v1`
- `locale`
- `appVersion`、`build`、40 字元 `captureCommit`
- ISO 8601 `capturedAt`
- `viewports` 至少包含 `iphone`、`dynamic-type-large`
- `screens` 覆蓋 `docs/I18N-SURFACE-INVENTORY.json` 的全部 App WebView states
- 每個 screen 都要有實際存在、尺寸有效且 SHA-256 相符的 PNG、`result: pass`，並確認：
  - `noOverflow`
  - `noClipping`
  - `noUntranslatedCopy`
  - `layoutAccepted`

## voice-e2e.json

必要欄位：

- `schema`: `munea.i18n-voice-e2e.v1`
- `locale`、`conversationLocale`
- `appVersion`、`build`、`profile`、`environment`、`device`
- 40 字元 `exactCommit`、ISO 8601 `testedAt`
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
- 40 字元 `exactCommit`、64 字元 `binarySha256`、ISO 8601 `testedAt`
- `serviceRevisions`: `brain`、`voice`、`gateway`、`avatar`
- 從按下通話、權限、Auth、帳號、點數、Gateway、Voice、Avatar、真實麥克風上行、AI 聲音與畫面，到掛斷釋放容量，所有 `steps` 都必須為 `true`

瀏覽器、模擬器、單元測試、synthetic probe、developer-direct 或不同 build 的成功紀錄都不能代替 installed App E2E。

## 精確版本證據鏈

同一語系的 `visual-qa.json`、`voice-e2e.json`、`installed-app-e2e.json` 與 `purchase-e2e.json` 必須指向同一個 source commit、App version 與 build。安裝版與購買證據的 IPA SHA-256 必須一致；語音證據與安裝版的 Brain／Voice／Gateway／Avatar revisions 也必須一致，購買 backend revision 必須對上安裝版 Brain revision。任一份證據來自其他 build 都會讓 `exactBuildEvidenceChain` Gate 失敗。

## purchase-e2e.json

必要欄位：

- `schema`: `munea.i18n-purchase-e2e.v1`
- `locale`、`storeLocale`
- `appVersion`、`build`、`profile`、`environment`、`device`、`backendRevision`
- 40 字元 `exactCommit`、64 字元 `binarySha256`、ISO 8601 `testedAt`
- `steps` 必須確認登入、8 商品載入、免費會員不得購買點數、取消與未驗證交易不入帳，以及有效訂閱還原
- `products` 必須恰好覆蓋 4 個訂閱與 4 個點數包；每項都要在實體 iPhone 的 StoreKit Sandbox 確認：
  - 顯示名稱符合該語系
  - 價格由 StoreKit 回傳並顯示
  - Apple 付款視窗可開啟
  - 後端驗證交易
  - 正確方案或點數入帳
  - transaction 完成且 App 狀態刷新

測試不得記錄 Sandbox Apple ID、付款資料或完整交易 JWS。模擬器、假交易與不同 build 的結果不能代替本證據。

## 本機 catalog 預覽

`tools/i18n-preview.html?locale=ja` 可在本機 HTTP server 中查看繁中、英文、日文、西班牙文的代表性 catalog 元件、登入、設定、個人資料、資料匯出／刪除、字體、訂閱方案、點數包、StoreKit 價格格式與購買錯誤狀態，並用 `125% text` 按鈕先檢查長字串換行。

這個頁面：

- 不連正式 API、不讀會員資料、不保存語言。
- 價格是 QA 用的各地格式範例，不是正式售價，也不會開啟 Apple 付款。
- 只證明 catalog bootstrap 與代表性元件能渲染。
- 不代表完整 App 畫面、App Store 截圖、實機 Dynamic Type 或 installed App E2E 通過。
