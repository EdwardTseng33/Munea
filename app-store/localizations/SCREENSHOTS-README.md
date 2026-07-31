# App Store 上架截圖——四語版在哪、能不能直接上

> 2026-07-31 蘇菲整理。Edward 當晚拍板：**四語一起上架、圖片先沿用現有的、下一版再調整**。

## 檔案在哪

| 語言 | 位置 | 張數 | 狀態 |
|---|---|---|---|
| 繁中 | `E:\Claude\image-assets\munea-appstore-localized-20260728\zh-TW-v2-rgb\` | 5 | **本次上架用**（Edward 7/31 指定換這組） |
| 英文 | `…\munea-appstore-localized-20260728\en-US\` | 5 | **本次上架用** |
| 日文 | `…\munea-appstore-localized-20260728\ja-JP\` | 5 | **本次上架用** |
| 西班牙文 | `…\munea-appstore-localized-20260728\es-MX\` | 5 | **本次上架用**（⚠ 見下方地雷 2） |
| 繁中（舊版） | `App store pic/*.png`（本程式庫內） | 5 | 現在 App Store 上的、這次會被換掉 |

**繁中為什麼要換**：v2 版主標改成「全家人的健康陪伴 AI 照護管家」，跟 Edward 7/21 拍板的
核心定位一致（舊版是「溫暖陪伴的 AI 健康夥伴」）。Codex 的改版方向：拿掉重複的 App 圖示、
把產品畫面放大、減少行銷文字、依「產品差異化」重排順序。`-rgb` 是色彩空間校正過的版本，
上傳用這個。

規格：1242 × 2688（iPhone 6.5 吋直式），全部符合。原始產出者是 Codex，2026-07-28。
文案對照表在同資料夾的 `COPY-MANIFEST.md`（四語各五句主標＋副標）。

**為什麼放 E 槽不放程式庫**：四套共 89 MB。程式庫裡放這種重檔，之後每個人下載都要背，
而且永遠刪不掉。城堡既有規矩就是重素材放 `E:\Claude\image-assets\`（跟影片素材同一套做法）。

## 品質：好的

日文版整張都是日文，連手機畫面裡的介面都是（おはようございます／今日のやること／
気分のモニタリング／家族の健康サークル）。主標也是各國重寫、不是硬翻。

⚠ 別跟 `docs/qa/i18n/local-browser-precheck/` 那 678 張搞混——那批是 **7/29** 拍的，
而文案是 **7/31** 才搬完，所以檔名寫 `ja__home` 但畫面上只有底部導覽列是日文、其餘全中文。
**那批不能當「各國畫面驗過了」的證據，也不能當素材。**

## 三個地雷（Edward 已知，決定先上）

### 1. 繁中版角色叫「佩佩豬」
中文圖裡陪伴角色名字是「佩佩豬」（「佩佩豬的觀察」「和佩佩豬聊聊」）——**別人的卡通角色
商標**，看起來是測試帳號名字沒清掉。舊版有、**這次要換上去的 v2-rgb 也還有**。

已經在 App Store 上的舊版就有這個問題，所以不是新增的曝險；但這次是「重新上傳一次」，
不是「放著不動」。Edward 7/31 知情後決定先上、下一版換圖時清掉。
（Codex 的英日西版沒有這個問題，那邊角色叫 Munea。）

### 2. 西班牙文做的是墨西哥版
Edward 7/31 拍板**只上架西班牙**，但這套圖是 es-MX。第一張就有兩個墨西哥用語：
- 「¿Platicamos hoy?」→ 西班牙會說 Charlamos／Hablamos
- 「Munea está al pendiente」→ 西班牙是 estar pendiente（沒有 al）

其餘讀起來是中性西語。圖是平面檔、沒有原始檔，改這兩個字等於整張重畫，故本次沿用。

### 3. 角色名字對不上 App
圖裡她叫「Munea」，但 App 裡照語系顯示 **ニンニン**（日）／**Ningning**（英西）。
Edward 拍板 **A：以 App 的各國名字為準**（有名字的人比叫產品名的東西更像陪伴者），
所以 **App 不用改**，是圖之後要跟上。

## 下一版換圖時要做的

1. 清掉「佩佩豬」，改用各國名字（ニンニン／Ningning）。
2. 西班牙版改成 es-ES 用語。
3. 建議把版型改成網頁做（文字吃四國文案表），日後改字不用重畫，也不會有翻譯錯字。
4. 手機畫面用**重拍後**的各國實拍圖（現有那 678 張是 7/29 的，已過期）。

## Codex 自己標的限制（照抄，不要略過）

繁中 v2 那份改版說明裡寫著：

> The product UI is derived from generated raster artwork. Some small in-app labels and
> character names may not match the production app exactly.
>
> Before App Store upload, rebuild the approved direction with real production screenshots
> and deterministic text layers, then run a final proofreading pass.

白話：**圖裡的手機畫面是「畫出來的」、不是真的 App 截圖**，所以小字和角色名字可能跟正式
App 對不上（上面地雷 3 就是這個）。他建議上傳前用真實截圖重做一次。Edward 7/31 決定先上、
下一版再照這個做法重建。

## Codex 自己留的另一句話（照抄）

> Do not upload a non-Chinese set until the matching in-app UI, voice, safety, legal,
> privacy, and support experience has passed locale-specific QA.

他同時標了「這是視覺草稿，不是最終上傳版」。Edward 7/31 知情後決定先上、下一版調整。
