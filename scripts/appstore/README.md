# App Store Connect 商店截圖工具（2026-07-31 建）

四語商店截圖上架那晚寫的三支工具。下次換圖不用再手動點。

## 為什麼要有這些

**瀏覽器點不了**：Claude 的瀏覽器工具有一道檔案安全限制，只准上傳「使用者直接貼進對話的
檔案」——E 槽素材庫、程式庫、暫存區全部被拒。所以只能走蘋果的接口。

## 鑰匙在哪

保險箱（Google Secret Manager）：

| 用途 | 名稱 |
|---|---|
| 私鑰 | `munea-asc-appmanager-key` |
| 金鑰編號 | `munea-asc-key-id`（`2NUPSQ2XQL`） |
| 發行者編號 | `munea-asc-issuer-id` |

⚠ 這把是 **App 管理** 權限（能改 App、能送審），不是唯讀。另一把 `munea-appstore-api-key`
（`U224SD67V5`「Munea Admin Metrics」）只能看報告與銷售，**傳不了圖**——別拿錯。

取出來用：

```bash
gcloud secrets versions access latest --secret=munea-asc-appmanager-key > /tmp/asc.p8
export ASC_KEY_ID=$(gcloud secrets versions access latest --secret=munea-asc-key-id)
export ASC_ISSUER_ID=$(gcloud secrets versions access latest --secret=munea-asc-issuer-id)
export ASC_PRIVATE_KEY_PATH=/tmp/asc.p8
```

用完記得刪掉 `/tmp/asc.p8`。

## 三支工具

### `strip-alpha.py` — 先跑這支
```
python strip-alpha.py <來源資料夾> <輸出資料夾>
```
**蘋果不收帶透明圖層的截圖**（錯誤碼 `IMAGE_ALPHA_NOT_ALLOWED`）。7/31 日文與西班牙文那兩組
就是這樣被打回、畫面上變成五個紅色驚嘆號。這支把圖疊在白底上再存一次，畫面完全一樣、
檔案還小一半。

> 中文那組之所以有 `-rgb` 版本，就是之前有人踩過同一個坑。**上傳前一律先跑這支**。

### `asc-upload-screenshots.mjs` — 上傳
```
node asc-upload-screenshots.mjs <locale> <資料夾> [--dry-run]
```
locale 用蘋果的寫法：`zh-Hant` / `en-US` / `ja` / `es-ES`。

蘋果傳圖是**三步**，缺一不可：① 先登記要傳多大的檔 → 它回一組上傳網址 ② 把內容 PUT 上去
③ 回頭蓋章並附 md5 讓它核對。只做①②的話，那張圖會永遠卡在半成品狀態。

這支會**先清掉該語言原有的圖**再放新的（避免新舊混在一起）。`--dry-run` 只印計畫不動任何東西。

### `asc-check-screenshots.mjs` — 驗收
```
node asc-check-screenshots.mjs
```
印出四語每張圖的處理狀態與錯誤原因。**傳完一定要跑這支**：上傳成功 ≠ 蘋果收下，
它要另外處理一輪才會變 `COMPLETE`，失敗的會顯示錯誤碼。

## 素材在哪

`E:\Claude\image-assets\munea-appstore-localized-20260728\`
（`ja-JP-rgb` / `es-MX-rgb` 是去過透明的版本，上傳用這兩個）

89 MB 沒放進程式庫——重素材照城堡規矩放 E 槽，見 `app-store/localizations/SCREENSHOTS-README.md`。

### `asc-read-release-state.mjs` — 版號別再用估的

```
node scripts/appstore/asc-read-release-state.mjs
```

**唯讀**，問蘋果「現在到底是哪一版、哪個 Build、什麼狀態」。

為什麼要有這支：Edward 那端打包會自己升版號，而那個號**常常沒有回寫程式庫**
（1.0.46～1.0.50、以及 1.0.54 都發生過）。以前只能寫「Build 520 是留空間的估計值」，
下一個 session 讀到的就是錯的。現在直接問權威來源，三十秒就有答案：

```
== 蘋果那邊的版本 ==
  1.0.54  狀態=WAITING_FOR_REVIEW  建立=2026-07-28T00:33
== 上傳過的 Build（新到舊）==
  Build 524  VALID  上傳=2026-08-01T09:41
```

**包版前、回填狀態文件前先跑這支**。鑰匙取法見上面那段（用完刪掉 `/tmp/asc.p8`）。

## 一鍵更版（2026-10-29 建：不用 Mac，雲端打包＋送審）

GitHub → Actions → **iOS release (manual)** → Run workflow：

| 欄位 | 填什麼 |
|---|---|
| version | 新版號，例如 `1.0.70` |
| build | 新 Build 號，純數字，例如 `541`（問蘋果現況用 `asc-read-release-state.mjs`） |
| submit | `false`＝只打包上傳＋把這版準備好（不送審，留給人工看一眼）；`true`＝上傳完直接送出 App Review |
| signing_mode | 留 `auto`（用 ASC API 鑰匙雲端簽章）。`manual` 是備援路，目前還沒配好 secret，先不要選 |
| xcode_version | 留 `latest-stable` 即可，除非蘋果出新 Xcode 導致專案建置失敗才需要鎖版本 |

跑多久：約 25-45 分鐘（Xcode archive 10-20 分、export+上傳 5-10 分、等 ASC 處理 build 5-15 分）。

跑完會發生什麼：
1. 版號寫進 `package.json`／`package-lock.json`／`web/src/version.js`／Xcode 專案，`check-release-consistency.js --strict-ios` 卡關
2. 這筆版號回寫會被 commit 推回你跑這條線的那個分支；如果那個分支不是 `main`，流程會自動幫你開一張 PR 準備合併
3. `xcodebuild archive` → `-exportArchive` 直接上傳到 App Store Connect（走雲端自動簽章，不用 Mac 本機的憑證／描述檔）
4. 等 build 處理完成（`processingState=VALID`），把這個 build 綁到 `version` 那個 App Store 版本
5. 四語 whatsNew 從 `app-store/localizations/*.json` 填進去
6. 建立 reviewSubmission；`submit=true` 才會真的按下送出審查那一步

失敗了看哪裡：
- GitHub Actions 這次執行的 log，一步步往下找第一個紅字的 step
- `xcodebuild` 的 log 若有留下，會在失敗時自動上傳成 workflow 的 artifact（`ios-release-logs-<version>-<build>`）
- 最常見卡點：ASC API 鑰匙權限不夠建立 distribution 的佈建描述檔（見 `.github/workflows/ios-release.yml` 開頭註解）——這不是程式碼問題，是蘋果那邊的角色權限，要去 App Store Connect 加鑰匙權限

⚠ **現況尚未真跑過一次**：這條線是新建的，還沒在真的 GitHub Actions macOS runner 上跑過（不包含在這次改動的驗證範圍）。第一次跑建議 `submit=false`，人工在 App Store Connect 看一眼版本／build／whatsNew 都對了再手動跑一次 `submit=true`，或直接在 App Store Connect 網頁上按送出。

### 另一條路：`signing_mode=manual`（還沒配好，先別選）

如果 ASC API 鑰匙權限卡住、又不想加鑰匙權限，可以改用傳統 p12＋描述檔手動簽章。
要先手動建立這幾個 Secret Manager 項目才能用：

```bash
# 從 Keychain 匯出 Distribution 憑證（.p12，帶密碼）
gcloud secrets create munea-ios-distribution-p12 --data-file=dist.p12 --project gen-lang-client-0229303523
gcloud secrets create munea-ios-distribution-p12-password --project gen-lang-client-0229303523
# 從 Apple Developer 下載對應的 App Store 描述檔（.mobileprovision）
gcloud secrets create munea-ios-distribution-profile --data-file=munea.mobileprovision --project gen-lang-client-0229303523
```

填完後還要編輯 `scripts/appstore/ios-export-options-manual.plist` 裡的 `CHANGEME-munea-distribution-profile-name`，
改成描述檔裡登記的真實名稱（`security cms -D -i munea.mobileprovision` 可以解開看）。這條路目前完全沒跑過，
是「如果 auto 卡住」的備案，不是推薦路徑。

### 執行這條線前要先確認的一件事：GCP 服務帳號讀不到 ASC 鑰匙

`firebase-hosting-deployer@gen-lang-client-0229303523.iam.gserviceaccount.com`
（workflow 借用官網部署既有的 Workload Identity）目前對 `munea-asc-appmanager-key`／
`munea-asc-key-id`／`munea-asc-issuer-id` 這三個 secret **沒有任何存取權**（2026-10-29 查證，
secret 層級與專案層級 IAM 都查過，空的）。沒有 Edward 手動跑過這段，整條線第一步抓鑰匙就會
403 失敗：

```bash
for SECRET in munea-asc-appmanager-key munea-asc-key-id munea-asc-issuer-id; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project gen-lang-client-0229303523 \
    --member="serviceAccount:firebase-hosting-deployer@gen-lang-client-0229303523.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```
