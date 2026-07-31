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
