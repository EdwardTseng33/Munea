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
