# 給 Mac：打包 1.8.0 上 TestFlight ＋ avatar 真機驗收（2026-07-09 · Windows 蘇菲 A 交辦）

> 背景：Edward 手機看不到「會動的臉」。原因＝App 畫面是**打包當下凍結**進去的（capacitor.config.json 是 webDir bundle、無 server.url），
> 而目前 TestFlight 只有 **1.2.7**（早於 avatar 的 1.3.0）。1.3.0→1.8.0 的臉/待機動態/數據同步/示範拆除全部還沒進真機。
> iOS 專案 MARKETING_VERSION 已是 1.8.0（我改好了）、但沒 archive 上傳＝等於沒進手機。
>
> 這張單自帶所有步驟，照做即可。這是 Mac 地盤（原生/打包），Windows 不碰 ios/。

---

## A. 打包前置（重要、漏了會壞）

1. `git pull`（拿今天全部：1.8.0 web + 008 SQL + gen-auth-config.py）
2. **生真帳號公開鑰匙檔**（不入庫、每台自己生）：
   ```bash
   python scripts/gen-auth-config.py
   ```
   → 產出 `web/src/auth-config.js`。沒有它＝App 走訪客模式（不會壞、但真登入點不亮）。
3. 雲端資料櫃跑 **008 遷移**（家人健康數據同步要它）：Supabase Dashboard → SQL Editor → 貼上 `supabase/sql/008_family_vitals_state.sql` 執行。
   （沒跑：vitals 會安靜退回引擎本子、不炸，但雲端不落地。）
4. 版號對齊確認：`web/src/version.js` current = 1.8.0、`package.json` = 1.8.0、iOS MARKETING_VERSION = 1.8.0（三處我已對齊）。**CURRENT_PROJECT_VERSION（build number）記得 +1** 否則 TestFlight 會拒同號。

## B. 打包上傳

```bash
npm run cap:sync          # 把最新 web/ 灌進 iOS 殼（關鍵：沒 sync = 還是舊畫面）
npm run cap:open:ios      # 開 Xcode
```
Xcode 內：選 Team V77L5245MR → Product → Archive → Distribute → App Store Connect → Upload。
上傳後 App Store Connect 等蘋果處理（10–30 分）→ TestFlight → 內部測試 → Edward 手機更新。

## C. ⚠ avatar 在 iPhone 上的兩個專屬坑（打包時一起處理，否則就算 1.8.0 進去了臉還是不動）

### C1. iPhone 網頁引擎擋自動播放（最可能）
臉是 `<video id="faceVid">`（WebRTC 即時影像）＋待機動態也是 `<video>`。iOS WKWebView 預設**擋非用戶手勢的影片自動播**。
- Capacitor iOS 要放行：在 iOS 專案讓 WKWebView `mediaTypesRequiringUserActionForPlayback = []`（等於「影片可自動播」）。
- Capacitor 8 作法：`capacitor.config.json` 加
  ```json
  "ios": { "limitsNavigationsToAppBoundDomains": false },
  "plugins": {}
  ```
  這個 key 不直接控自動播——**真正要改的是原生**：`ios/App/App/` 找 WKWebViewConfiguration 設定處（或用 Capacitor 的 `allowsInlineMediaPlayback` 已預設 true），把 `mediaTypesRequiringUserActionForPlayback` 設空集合。若 Capacitor 版本沒暴露此設定，在 `AppDelegate`/自訂 WKWebView config 補一行。
- 驗法：真機進聊聊頁，待機動態（寧寧輕微動）會不會自己播？會＝自動播沒被擋、faceVid 也會通；不會＝就是這個坑。

### C2. 手機行動網路連不到雲端臉（4G/5G）
臉的影像走 WebRTC，家用 Wi-Fi 多半直連 OK；**行動網路常要走 TURN 中繼**。目前 web 端已加公開中繼備援（openrelay），但實測不穩。
- 真機驗收：先用**家用 Wi-Fi** 測（應該會動）；再用**行動網路**測（可能連不上）。
- 若行動網路不通＝確認是 TURN 缺口（Windows 這邊列了待辦：要自架 coturn 或用託管 TURN；Cloud Run 沒 UDP 不能當 TURN）。這關**不擋 Wi-Fi 驗收**。

## D. 真機驗收清單（Edward 或 Mac 拿 iPhone 跑一次）

1. 手機設定頁版本顯示 **1.8.0** ✅
2. 進聊聊頁：待機動態會自己播（驗 C1）
3. 按「開始通話」：**寧寧的臉出現、嘴巴跟聲音動**（不是照片飄）＝avatar 成功
4. 換角色（小昀/阿原/阿宏）通話：臉跟著換、也會動
5. 掛斷：臉收乾淨回照片
6. 個人資料填「家人稱呼＝爸爸」→ 通話她開口叫「爸爸」（雲端已部署）
7. 家人頁：沒連家人＝顯示邀請引導（不再有美華/志明/小寶示範）

## E. 回填白板
打包+上傳完，STATUS 的 TestFlight 列改「🟢 1.8.0 已上傳」、註明 C1/C2 驗收結果。avatar 真機能動的話，Edward 的「會動的臉」就正式在手機上成立。

---
*Windows 蘇菲 A 交辦。這張單獨立、不碰 ios/ 原生碼（那是 Mac 地盤）；web/引擎全部已入庫在 main。*
