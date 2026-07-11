# 營運後台改網址 admin.munea.net · Turnkey（給 Mac / 動 Vercel 與 DNS 的人）

- 日期：2026-07-11 · Edward 拍板用 `admin.munea.net`
- 現況：後台在 `https://munea-brain-staging-491603544409.asia-east1.run.app/admin.html`（Cloud Run brain 服務，已上真資料版 rev 00024）
- 目標：改成 `https://admin.munea.net`
- 為什麼走 Vercel：munea.net 的 DNS 在 GoDaddy、apex 指向 Vercel（76.76.21.21）、官網 = `app-site/`（Vercel 專案）。子網址掛同一個 Vercel 專案最順、免動 Cloud Run 網域綁定（asia-east1 不支援）。

---

## 三步（Mac 執行，約 5-10 分）

### 1. Vercel 後台：把 `admin.munea.net` 加進 app-site 專案
- Vercel → app-site 專案 → Settings → Domains → Add → 輸入 `admin.munea.net`。
- Vercel 會提示要加一條 DNS：`CNAME  admin → cname.vercel-dns.com`。

### 2. GoDaddy DNS：加那條 CNAME
- GoDaddy → munea.net → DNS → 新增紀錄：
  - 類型 `CNAME`、名稱 `admin`、值 `cname.vercel-dns.com`、TTL 預設。
- 存檔後等幾分鐘～1 小時傳播；Vercel 會自動配 SSL（https 綠鎖）。

### 3. 加轉址：admin.munea.net 的請求代理到 Cloud Run 後台
在 `app-site/vercel.json` 加 host 條件轉址（**只對 admin.munea.net 生效、不影響 munea.net 本站**）：

```json
{
  "cleanUrls": true,
  "trailingSlash": false,
  "rewrites": [
    { "source": "/(.*)", "has": [{ "type": "host", "value": "admin.munea.net" }],
      "destination": "https://munea-brain-staging-491603544409.asia-east1.run.app/$1" }
  ]
}
```
- 效果：瀏覽器打 `admin.munea.net/admin.html` → Vercel 代理到 Cloud Run 的後台；後台呼叫的 `/admin/*` 也走同一個網址、同源，不會有跨網域問題。
- `has: host` 條件確保只有 `admin.munea.net` 被代理，`munea.net` 本站照常。
- 部署 app-site 後生效。

> 上線正式站時把 destination 換成正式 brain 網址即可（現在指試營運）。

---

## ⚠️ 資安：上線前務必加「第二道鎖」（沙利曼 P1）

後台裝著**全體用戶個資**，目前只靠一組通行碼擋。換成好記的公開網址 `admin.munea.net` 後更容易被找到——**強烈建議加第二道鎖**，擇一：

- **A（推薦·最簡）Vercel Edge 基本驗證**：在 app-site 加一個 middleware，對 `host = admin.munea.net` 要求 HTTP Basic Auth（一組帳密）。任何人打開 admin.munea.net 先跳一個帳密框，過了才看得到後台頁（再加原本的通行碼＝雙層）。
- **B IP 白名單**：只允許 Edward 家／常用 IP 開得進 admin.munea.net（Vercel middleware 判 IP）。
- 需要的話蘇菲可提供 middleware 程式碼（judge host + basic-auth / IP）。

**建議順序**：第二道鎖跟換網址一起上，不要先開公開網址、之後才補鎖。

---

## 蘇菲這邊已備好
- Cloud Run 後台已是真資料版（rev 00024）、`/admin.html` 200、通行碼保護中。
- 轉址 destination 網址、DNS 值、第二道鎖方案都在上面。
- Mac 做完 1-3（＋資安鎖）即生效；有需要 middleware 程式碼跟蘇菲要。
