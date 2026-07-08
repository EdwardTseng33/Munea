# ☁️ 沐寧引擎 · 雲端搬家配方（Google Cloud Run · 台灣機房）

> 2026-07-08 蘇菲備。目標：聊聊引擎從「家裡電腦」搬進 Google 台灣機房（彰化 asia-east1），成為正式服務。
> 雲端專案已就位：**Munea**（編號 `gen-lang-client-0229303523`、帳單與 NT$500 警戒已設）。
>
> **搬家觸發條件（不是日期、是狀態）**：
> ① Mac 把雲端資料櫃（Supabase 表）建好、記憶改存雲端——不然引擎上雲＝重開機就失憶
> ② 鑰匙上雲前過沙利曼信任關卡（鑰匙只進 Google 保險箱、不進程式庫）
> ③ Edward 在場跑第一次（要他的 Google 登入授權）
> 三個條件到齊 → 照下面指令一路跑完，約 30 分鐘。

---

## 第 0 步 · 裝指揮工具＋登入（一次性，Edward 在場）

```powershell
# Windows（或 Mac 用 brew install google-cloud-sdk）
winget install Google.CloudSDK
gcloud auth login            # 跳瀏覽器、Edward 按同意
gcloud config set project gen-lang-client-0229303523
```

## 第 1 步 · 開通需要的服務（一次性）

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com
```

## 第 2 步 · 鑰匙進保險箱（過沙利曼關卡後執行）

```bash
# 鑰匙從 .env.local 直灌保險箱——不貼畫面、不進指令歷史、不落檔（沙利曼 Gate 5 條件）
# 測試/正式各一把：staging 帶後綴、正式另建 munea-gemini-key-prod
grep -m1 '^GEMINI_API_KEY=' engine/.env.local | cut -d= -f2- | tr -d '

"' |   gcloud secrets create munea-gemini-key-staging --data-file=- --replication-policy=automatic
```

> 🔒 沙利曼 Gate 5 硬條件（缺一不部署）：① 鑰匙在 Google 後台設**每日/每分鐘用量上限**（唯一真煞車——網址被掃到也燒不穿）② 測試/正式鑰匙分開命名 ③ 鑰匙不出現在畫面與指令歷史。
> 上鎖時點：**送審前** staging 改 `--no-allow-unauthenticated`（藍圖 §7）。

## 第 3 步 · 部署兩個服務（在程式庫根目錄執行）

```bash
# 管家腦（聊天/記憶/簡報/守護 · HTTP）
gcloud run deploy munea-brain-staging --source . --region asia-east1 \
  --set-secrets GEMINI_API_KEY=munea-gemini-key-staging:latest \
  --memory 1Gi --min-instances 0 --max-instances 3 --allow-unauthenticated

# 語音橋（即時通話 · WebSocket；門牌自動吃 PORT）
gcloud run deploy munea-voice-staging --source . --region asia-east1 \
  --set-secrets GEMINI_API_KEY=munea-gemini-key-staging:latest \
  --command sh "--args=-c,python engine/live_voice_server.py" \
  --timeout 3600 --session-affinity --memory 1Gi \
  --min-instances 0 --max-instances 5 --concurrency 40 --allow-unauthenticated
```

打包內容由根目錄 `.gcloudignore` 控制（素材、簡報、示範夾都不上車）；映像配方 `deploy/cloudrun/Dockerfile`。

## 第 4 步 · App 指到新住址（不用改程式）

部署完成會得到兩個網址（例）：
- 管家腦 `https://munea-brain-xxxx-de.a.run.app`
- 語音橋 `https://munea-voice-xxxx-de.a.run.app`

App 端兩個設定值（打包時寫入或設定頁隱藏開關）：
- `munea.brainUrl` → 管家腦網址（App 所有聊天/記憶/提醒請求自動改走這裡；1.1.2 起支援）
- `munea.liveVoiceUrl` → `wss://munea-voice-xxxx-de.a.run.app`（注意 wss）

## 第 5 步 · 驗收（照聊聊主文件 §11）

1. 探針打雲端網址問「桃園哪裡好玩」→ 真地名回來
2. 守護紅線 13 條全跑
3. 手機連 4G（不同網路）通話 3 分鐘：多輪、插話、斷線接回
4. 帳單頁看一眼：費用有記到 Munea 專案

## 回滾（上錯了怎麼辦）

Cloud Run 每次部署都留完整舊版本——控制台點兩下就切回上一版，秒級生效、不用重建。

## 已知邊界

- **記憶存本機 JSON 的期間不要上正式**（容器重開＝失憶）→ 觸發條件 ① 的由來
- 語音橋單通電話最長 60 分鐘（雲端上限）→ 對點數制（1 點≈1 分鐘）綽綽有餘
- 沒人用時不計費（min-instances 0）；正式熱線期可把語音橋調 min-instances 1 消掉冷啟動

---

## 實戰排雷紀錄（2026-07-09 首搬實錄 · 照抄配方即可避開）

1. **配方要放根目錄**：打包配方在子資料夾雲端不認、會自動亂猜 → 已放 `/Dockerfile`
2. **曾被亂猜過的服務**：改用配方部署要帶 `--clear-base-image`
3. **材料清單路徑**：在 `engine/requirements.txt`、配方已寫對
4. **門向**：管家腦本機只開自己家（安全），雲端由配方設 `MUNEA_HOST=0.0.0.0` 開正門
5. **一顆映像兩種身分**：語音橋部署帶 `--set-env-vars MUNEA_SERVICE=voice` 即切換
6. **`/healthz` 這個名字被 Google 大門保留**（請求進不到我們家、回 Google 的 404）→ 監控探活改打 `/`（會回 App 首頁 200）或請 Mac 加一條別名路（例 `/enginez`）
7. **雲端機器讀鑰匙要先發權限**（只讀該把鑰匙）：`發鑰匙權限-點兩下.bat`，本人執行

## 首搬驗收紀錄（staging · 2026-07-09 00:44）

- 管家腦 `https://munea-brain-staging-491603544409.asia-east1.run.app`：對話 ✅（帶記憶回話＋語音生成）
- 語音橋 `https://munea-voice-staging-491603544409.asia-east1.run.app`：**首聲 2.1 秒（比本機測快一倍多）**、答「桃園大溪老街」真景點＋豆干花生糖真名產、興趣話題入腦 ✅
- 兩服務皆鎖門模式（帶通行證才能呼叫）；開門待鑰匙用量上限設定＋Edward 拍板
