# 營運後台換網址 admin.munea.net · 設定單（2026-10-26）

> Edward 10/26 拍板「後台網址換 admin.munea.net，設定先備好、DNS 我自己動」。
> 取代 7/11 那份 `admin網址設定-admin.munea.net-turnkey-2026-07-11.md`（那份寫的是走 Vercel——官網後來已搬到 Firebase，而且它說「asia-east1 不支援 Cloud Run 網域綁定」查證是錯的）。

> ✅ **2026-10-28 20:15 已完成**：`https://admin.munea.net/admin.html` 通了（憑證 Google 簽好）。實際踩到的坑：① GoDaddy 的 admin 子網域有舊「轉址」（指測試機），它會自動產生兩筆 A 記錄、CNAME 加不進去——先刪轉址 ② Google 第一次查 DNS 沒看到 CNAME 時會把重查排到 24 小時後，用 `remove` 再 `apply` 可立刻重查。

---

## 0. 走哪條路、為什麼

| 路 | 做法 | 評語 |
|---|---|---|
| **A · Cloud Run 直接綁網域** ✅ 採用 | 把 `admin.munea.net` 綁在正式大腦 `munea-brain` 上，DNS 加一筆 CNAME | 最少零件：不改官網、不多一跳、憑證 Google 自動簽與續期；舊 run.app 網址照常。Google 地區表確認 asia-east1 在支援清單（[Cloud Run locations](https://cloud.google.com/run/docs/locations)） |
| B · Firebase Hosting 多站轉送 | 官網的 Firebase 再開一個站、全部轉到大腦 | 多一跳、多一個站要維護、月報下載等 POST 流量也過 CDN；沒有比 A 多拿到什麼 |
| C · 負載平衡器＋Google 登入（IAP） | 網域掛在 Google 負載平衡器、前面擋 Google 帳號登入 | **唯一能給「第二道鎖＋個人身分」的路**，也是機構端 SaaS 要的地基（誰看過什麼才記得住）；約 US$18＋／月、設定多一截。**建議下一步、不是這一步** |

**沙利曼 7/11 的 P1 提醒仍然成立**：網址變好記、更容易被找到，後台裝著全體用戶個資、目前只靠一組通行碼。路 A 本身**沒有**第二道鎖；這一步先把網址換好，第二道鎖走 C（另開工單）。在那之前，後台通行碼請維持只在 Edward 手上。

---

## 1. Edward 要做的三步（約 10 分鐘＋等憑證）

### 第 1 步 · 登入 gcloud（用驗證過 munea.net 的那個 Google 帳號）
```bash
gcloud auth login
```
> 官網 `app-site/googleaa0c51d3d9781eb5.html` 就是那次網域驗證留下的檔，所以驗證應該在你的帳號名下。小工具會先幫你確認；沒有的話它會告訴你怎麼補驗證（加一筆 TXT 到 GoDaddy）。

### 第 2 步 · 跑一鍵小工具
```bash
bash deploy/cloudrun/admin-domain-mapping.sh plan
```
看沒問題再：
```bash
bash deploy/cloudrun/admin-domain-mapping.sh apply
```
它會建立綁定，然後**印出要去 GoDaddy 加的 DNS 紀錄**（一般是一筆：`CNAME  admin → ghs.googlehosted.com`）。

### 第 3 步 · GoDaddy 加 DNS
GoDaddy → munea.net → DNS → 新增紀錄：類型 `CNAME`、名稱 `admin`、值照小工具印的（預期 `ghs.googlehosted.com`）、TTL 預設。
存檔後等 DNS 傳播＋Google 簽憑證：通常 15 分鐘內，最慢 24 小時。

### 驗證
```bash
bash deploy/cloudrun/admin-domain-mapping.sh status
```
看到「✅ 通了」就開 `https://admin.munea.net/admin.html`，用原本的帳密登入即可（後台程式這次已把 `admin.munea.net` 列進允許清單與跨來源白名單，不需再改）。

### 退回
```bash
bash deploy/cloudrun/admin-domain-mapping.sh remove
```
解除綁定、run.app 網址一直都在、不影響 App。

---

## 2. 這次程式這邊改了什麼（PR 內）

- `deploy/cloudrun/admin-domain-mapping.sh`（新）：plan／apply／status／remove 四個動作、先查登入與網域驗證、印 DNS 紀錄、打 `/version` 驗通。
- `web/src/admin.js`：`KNOWN_ADMIN_HOSTS` 加 `admin.munea.net`；環境標籤把它顯示成「正式後台」。
- `engine/server.py`：跨來源白名單加 `https://admin.munea.net`（同網域其實用不到，備著給「後台頁在新網址、資料指舊網址」的過渡情況）。
- 7/11 舊設定單檔頭標「已被本單取代」；看板 7/11 那列對應更新。

---

## 3. 換完之後要順手改的地方

- 書籤／Slack 釘選／交接文件裡的後台網址換成 `https://admin.munea.net/admin.html`。
- `scripts/admin-smoke.ps1` 跑冒煙時 `-BaseUrl https://admin.munea.net`（舊網址也還能跑）。
- 官網／對外文件**不要**放後台網址。

---

## 4. 下一步（另開工單）：第二道鎖＝路 C

負載平衡器＋IAP（Google 帳號登入）擋在 `admin.munea.net` 前面：只有名單上的 Google 帳號開得進後台頁、而且大腦能從標頭拿到「是誰」——這就是機構端 SaaS 評估報告裡「誰看過什麼」稽核的第一塊地基。估約 US$18–25／月、城堡半天到一天。
