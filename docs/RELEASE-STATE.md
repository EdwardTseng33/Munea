# Munea Release State

## 2026-08-10 21:18 台灣｜聊聊卡頓／重複／自行斷線 P0 候選

- **失敗實證**：正式 App 診斷自報 `1.0.60`（Build 尚未取得），2026-08-10 約 20:39–20:43 台灣時間走 production Gateway／Voice／GLOWS `tw-06`。觀測到喇叭殘響 RMS `0.051`、僅 2 個 post-duck frame 就被接受為插話；同線臉聲 lead `2652ms` 後 App 自動降級並關閉 Avatar WebRTC，Avatar component release 令整張 paired lease 變成 `stale_lease`，之後使用者失去麥克風且通話自行結束。
- **正式止血**：`origin/main@9a0308a6`／production Voice `munea-voice-00101-yog@9a0308a6` 已把 Voice→Avatar direct route 預設關閉，回到 App relay。這是服務端 kill switch，不等於 App 故障已永久修好。
- **App 候選**：`codex/fix-call-audio-state-p0-20260810`。降級只隱藏／靜音 Avatar 並切回本地聲音，不再關閉 paired transport；插話改為至少 3 個新鮮 post-duck frame，並用上一輪真人 RMS 學習回音門檻；`speechActive()` 只信 Voice PCM 播放水位，不再讓 Avatar idle 音軌底噪長時間關閉麥克風；iOS 短暫 hidden 改為 5 秒 grace。
- **自動驗收**：插話／回音、啟動、Avatar direct kill switch、通話儀表、UI 契約與可執行狀態機均 PASS。正式 App 本地播放排程以 80 個 200ms PCM chunk、147ms 到貨間隔重播：`0 underrun`、`0 scheduling gap`；Avatar idle RMS `0.04` 連續模擬 3 分鐘：麥克風守門阻擋 `0` 次。
- **完整套件例外**：`npm run test:launch` 在既有 `test_flashhead_router_core.py` Windows Bash dry-run 失敗；該測試與輸入檔均未被本分支修改，針對性與後續 UI 測試全綠。
- **狀態**：`tested / App E2E pending`。尚未合併、尚未包版、尚未送審。Chrome 外掛診斷顯示本機 native-host manifest 缺失，無法用已登入 Chrome 代替 iPhone Gate；也不能把桌面／合成／文字稿證據宣稱成 iPhone 真實聽感通過。

本文件是 App、source、runtime、DB 與營運後台的 current release snapshot。品質分數看 [`PRODUCT-QUALITY-CONFIDENCE.md`](./PRODUCT-QUALITY-CONFIDENCE.md)；歷史活動看 `STATUS.md` 與協作看板。

Snapshot time: `2026-08-10 19:18 Asia/Taipei`（production Voice 為 `munea-voice-00099-him@e7fd0159`；App Store review lane 為 `1.0.55 (Build 529) WAITING_FOR_REVIEW`；current source 候選為 Build 530；installed-iPhone lane 尚無 Build 530 證據）

Source reconciliation baseline: `origin/main@e7fd0159`; latest uploaded App Build 529 的 exact source commit 尚未由 IPA 回讀，不能推定等於 current source

## 2026-08-10 開場卡頓／假斷線修復

- Production Voice 已切到 `munea-voice-00099-him`（`1.0.54@e7fd0159`）100%；上一版 `munea-voice-00097-sag` 可一鍵回滾。
- 正式 Gateway→Voice→GLOWS Avatar 實際音訊鏈重跑兩次，Voice→Avatar direct status `ready`、Avatar ACK `true`，missing speech runs 皆 `0`、max missing speech 皆 `0ms`；這證明服務端傳輸連續，不等於舊 App 已修好。
- App Store Connect 的 Build 529 上傳於 03:38 UTC，早於同日 `5db648a6` echo 修復與 `32ac2aac` 直連修復，確定未包含完整客戶端半邊。下一個唯一候選為 `1.0.55 (Build 530)`。
- Build 530 尚未 Mac Archive／上傳／安裝，最高狀態是 `tested source + deployed service`，仍不可稱 exact-build App verified。

> ✅ **版號回填缺口已補（2026-08-06 · Edward「app 與送審都已經是 1.0.54，你們自己要同步更新好」）**：這次不用估——直接用 App 管理鑰匙唯讀問 App Store Connect。權威回答：**`1.0.54` 狀態 `WAITING_FOR_REVIEW`、綁 Build 524**（上傳 2026-08-01 09:41 UTC ＝台灣 8/1 17:41），釋出方式 `AFTER_APPROVAL`；商店上架中的仍是最早的 `1.0`（Build 49）。repo 先前停在 `1.0.53 (Build 523)`——523 於台灣 8/1 06:59 上傳，**同一天就被 524 取代、從未送審、沒有任何使用者跑過**，所以把 1.0.53 的更新說明併進 1.0.54（使用者會看到的就是這一份），並補上 Build 523→524 之間 12 筆裡使用者看得到的三件事。
>
> 🔴 **同時抓到：四個「叫手機重讀檔案」的記號從 1.0.45 之後就沒再動過**。`web/index.html` 裡 styles.css／version.js／auth.js／app.js 的 `?v=` 記號一路停在 `v1045`，而程式版號已經走到 1.0.53——`scripts/test-release-settings.js` 這道守門因此**在 clean main 上一直是紅的**（不是本次改壞的，已在 main 上重現）。後果：從 1.0.45 更新上來的手機，網頁層可能仍拿快取裡的舊檔，看不到新版的東西。本次已對齊 `v1054`；**但送審中的 Build 524 帶的是舊記號，改不了**。

Maintenance role: `Release / Platform` (`unassigned`)

## 2026-08-06 GPT Live 互動優化正式部署

- 最高可支持狀態：`deployed`。服務鏈與聲畫預檢已通過，但 exact installed-iPhone media E2E 尚未執行，因此整體仍標記 `App E2E pending`，不宣稱 `verified` 或 release-ready。
- Source：`origin/main@7b0bac35c750bc46ddae2c6fd5d27d0f345c10e0`，package `1.0.53`；互動優化 PR #520 與 Avatar call-token／slot routing 修正 PR #522 均已合併。
- Production Voice：Cloud Run revision `munea-voice-00087-suw` 已切 100% 流量；公開 `/version` 回報 `1.0.53@7b0bac35`。保留舊 revision `munea-voice-00085-nef`，回滾指令為 `gcloud run services update-traffic munea-voice --region asia-east1 --project gen-lang-client-0229303523 --to-revisions munea-voice-00085-nef=100`。
- Production Avatar：RunPod Pod `ejs3atc7md425x`／Gateway worker `runpod-ejs3atc7md425x`，映像鎖定 digest `sha256:b5a97299d9b8b8805dea16d3d2431889113d2921164119c5c4faebd01850cb8d`；2 processes／2 seats，驗證時 `active=0`、`available=true`。舊 Pod `fclawd117hu2ay` 已終止，故 Avatar 回滾需由前版映像重新起 Pod，不是即時 traffic rollback。
- Production service-chain evidence（2026-08-06 Asia/Taipei）：拋棄式真實 Supabase session → production Gateway lease／signed call token → production Voice tagged revision `voice_ready` 2360 ms → Avatar legacy health 與 call-token health → Gateway release；測試 account／user／wallet 清理皆 PASS。這次探針的 `real_device_media_gate=SKIP`。
- Avatar media precheck：隔離 WebRTC 驗收 a05／a06 均收到 640×640 影像與音訊；a05 為 298 video frames／593 audio packets／聲畫差 -0.42 s，a06 為 284／564／-0.20 s。base worker token 僅能依 signed `slot_id` 到正確 process；錯誤 slot 與外來 worker 均 fail closed。
- 剩餘 release gate：安裝 exact App build／production profile，在 iPhone 完成真麥克風、Auth／credits、Gateway、Voice＋Avatar ready、AI 開場、真實語音上行、可聽／可見 AI 回應、掛斷與 capacity release，並記錄裝置、build、時間與 evidence reference。

## Status vocabulary

| Status | Meaning |
|---|---|
| `coded` | 只存在分支或 source |
| `tested` | 指定自動測試通過 |
| `merged` | 可由 `origin/main` 到達 |
| `packaged` | 已綁定精確 App Build／成品 |
| `deployed` | 已部署到具名環境與 revision |
| `verified` | 需求所需的 live／human gate 已通過 |
| `unknown` | 權威來源無法證明 |

狀態不得向上推論：`tested ≠ merged ≠ packaged ≠ deployed ≠ verified`。

## App lanes

| Lane | Version / Build | State | Evidence | Last verified |
|---|---|---|---|---|
| Latest source | `1.0.55 (Build 530)` | 下一個唯一候選 Build；包含 speaker echo 防誤判、Voice→Avatar 直連與 2026-08-10 正式 Voice revision。WebView cache identity 已更新為 `v1055`，避免舊 App bundle 沿用 Build 529 的語音程式 | `package.json`; `package-lock.json`; `web/src/version.js`; `web/index.html`; Xcode project | 2026-08-10 19:18 +08:00 |
| Latest uploaded App | `1.0.55 (Build 529)` | App Store Connect 唯讀查得 `VALID`，上傳 2026-08-10 03:38 UTC；早於 2026-08-10 15:42 +08:00 的 echo 修復與 18:51 +08:00 的直連修復，因此不能代表 current source | App Store Connect API（權威）；Git commit timestamps | 2026-08-10 19:18 +08:00 |
| App Store selected review lane | `1.0.55 (Build 529)` | `appStoreState=WAITING_FOR_REVIEW`；尚未核准、尚未公開。Build 530 尚未 Archive／上傳／選入審查，不能把 source-ready 當作 submitted | App Store Connect API | 2026-08-10 19:18 +08:00 |
| Edward iPhone install lane | `1.0.44 (Build 492)` | iPhone 15 Pro 安裝與啟動成功，`devicectl` 從手機回讀版本；使用 Development signing＋production config，未注入 direct／gateway QA fixture。安裝成功不等於正式 App Store binary 或真人通話 Gate | `devicectl` install／launch／app inventory | 2026-07-28 17:25 |
| Draft call／purchase／QA fixes | #174 → #175 → #188，目標 `1.0.43 (Build 48)` | 三張 Draft 目前 merge state CLEAN 且 CI 綠；#175 stacked on #174、#188 stacked on #175。這仍只代表可整合，尚未 merged／packaged／iPhone verified | PR #174; PR #175; PR #188 | 2026-07-20 |

## Runtime services

| Environment | Service | Serving identity observed from public endpoint | Interpretation | Evidence time |
|---|---|---|---|---|
| production | Brain | `1.0.53@2d5afa7d`, `munea-brain-00164-yuw` | `/healthz` 200、`ai.state=ok`。落後 main 的 11 筆全是語音／臉機／測試／App 端檔案，**管家腦自己的程式已是最新**，不需重新部署 | 2026-08-06 02:5X |
| production | Voice | `1.0.53@7b0bac35`, `munea-voice-00087-suw` | `/healthz` 200。**與 main 同步**（main 只多兩筆純文件）；GPT Live 互動優化與 Avatar slot routing 修正皆在內。舊 App 仍走保留的 0.6 秒熱門檻插話判法，不會壞 | 2026-08-06 02:5X |
| production | Call Control / Gateway | `munea-call-control-00015-dob` | 服務在；公開 `/health` 無憑證回 401，auth boundary 正常。release identity 未由公開端點證明 | 2026-08-06 02:5X |
| production | Avatar (RunPod) | Pod `ejs3atc7md425x`，映像 digest `sha256:b5a97299…` | 2 processes／2 seats；02:16 隔離 WebRTC 驗收 a05／a06 皆收到 640×640 影像與音訊。回滾需由前版映像重起 Pod，不是即時切流量 | 2026-08-06 02:16 |
| production | RunPod capacity controller | `munea-runpod-controller-00012-5xt` | `/health` `state=ok`、`mode=active`、`last_error` 空 | 2026-08-06 02:5X |
| staging | Brain | `1.0.53@89eb2fa7`, `munea-brain-staging-00122-zow` | `/healthz` 200；`89eb2fa7` 在 main 裡但較舊 | 2026-08-06 02:5X |
| staging | Voice | `1.0.53@f806406c`, `munea-voice-staging-00098-non` | ⚠ 吃流量那版跑的是**未合併的分支版**（`f806406c` 不在 main）；另有較新的 `munea-voice-staging-00102-bap` 已 Ready 但 0% 流量。下次拿測試機驗東西前要先收乾淨 | 2026-08-06 02:5X |

`/version` 是 runtime identity authority。上述 5 個公開 target 的 safe observation、target-config hash、capture time 與 capture source commit 保存在 [`RELEASE-EVIDENCE-LATEST.json`](./RELEASE-EVIDENCE-LATEST.json)，以 [`RELEASE-EVIDENCE-TARGETS.json`](./RELEASE-EVIDENCE-TARGETS.json) 及 `npm run release:evidence:check`（= `python scripts/release_evidence.py check --max-age-hours 24 --strict-version`）驗 freshness 與版號對齊；上線前跑這一條。CI 常駐的 `python scripts/release_evidence.py check`（無 `--strict-version`）只擋真漂移：sourceVersion 缺值、看不懂、或超前 package version。證據落後 package version 是版號跳了還沒重擷的正常開發狀態，只給 warning，重擷用 `npm run release:evidence:capture`。Cloud Run Ready、0% canary、source equivalence或 App 預設 URL 都不能替代 serving identity 與真實 client trace。

## Database and billing policy

| Item | Current state | Interpretation |
|---|---|---|
| Repo migration head | `019` | `019_pricing_plus100_pro200.sql` 存在；本輪補入 migration manifest。這只證明 source governance |
| Environment deployment ledger | `supabase/deployment-ledger.json` | 東京 27 支 migration 逐支對應 manifest checksum；17 筆 historical claim、4 筆 unknown（`020`／`021`／`022`／`026`）、3 筆 blocked（`017`／`018`／`019`）、3 筆 verified read-only-probe（`023`／`024`／`025`，2026-07-24）；`verifiedHead=null`（`001` 起未形成連續 verified chain） |
| Tokyo applied `017` | `blocked / HTTP 404` | 07:12 UTC GET-only probe 對正確東京 project 發出請求，`notification_settings` 不可到達；需核准套用後重驗 |
| Tokyo applied `018` | `blocked / partial photo-key=0` | destructive cleanup 仍需 approval、backup、完整 data-image pre-check／post-check；單一欄位零筆不能升格 |
| Tokyo applied `019` | `blocked / policy mismatch` | policy table 可查，但沒有符合 active v4 Plus 100／Pro 200 的資料；需核准套用後重驗 |
| Latest Tokyo probe attempt | `blocked after read-only requests` | target／observed project 都是東京 `fespbkdwafueyonppzwq`；使用 Cloud Run 現行 Secret reference，沒有顯示密鑰、個資或執行寫入 |
| App Store product prices / descriptions | `unknown` | STATUS 記錄為 Build 47 送審前置；App Store Connect 才是權威 |

任何 SQL 檔、manifest、CI PASS、historical claim 或文件聲明都不能標成 live applied。台帳由 [`supabase/deployment-ledger.json`](../supabase/deployment-ledger.json) 管理，更新規則見 [`docs/supabase/DEPLOYMENT-LEDGER.md`](./supabase/DEPLOYMENT-LEDGER.md)。

## Operations console

| Item | Current state | Interpretation |
|---|---|---|
| URL | staging `/admin.html` 回 200；body hash 與必要 asset tokens 已進 manifest | shell reachable；不代表 privileged data 正確 |
| Serving identity | 跟隨 staging Brain `1.0.40@fa14e4c` | admin shell 公開 hash／headers PASS；與 latest source `1.0.41` 不同版，privileged data 仍未證明 |
| Browser security | `nosniff`、`DENY`、`no-referrer` 已進 manifest；9 個 console read endpoints 無 token 均回 403 | delivery 與未授權拒絕 PASS；不代表具名 RBAC／MFA |
| Privileged APIs / data source / freshness | source contract `merged`；runtime `unknown` | #183 已加入 provenance／fallback／freshness unknown metadata，但 staging Brain 尚未部署；不能把空值當成零事件 |
| Operator security | per-operator identity／MFA／RBAC `unknown` | shared secret 或登入畫面本身不等於可稽核權限 |

## Critical feature rollout states

| Capability | Current state | Missing proof |
|---|---|---|
| Google login | fallback code 已進 Build 47；post-Build 47完整真人紀錄未找到 | 選帳 → callback → session → 登出／重登 → 真 token call |
| 0-credit call preflight | #174 `tested`, Draft，base 落後 main | rebase／merge → package next candidate → 0 點 iPhone 不得顯示「撥通中」 |
| Developer purchase / Apple account mismatch UX | #175 `tested`, Draft，stacked on #174 | 整合後包版；TEST 不觸發 Apple；真帳號 mismatch 不重複扣款 |
| Dedicated QA account | 正式 Supabase password sign-in、account bootstrap 與 Brain balance readback 已驗證；purchased balance `505`（免費 5＋授權測試 500），帳密只存 Secret Manager，事件排除營運分析 | #188 合併後由 Mac 安全載入 Secret，包一個開發版完成 iPhone 登入與 credited chat-call；後端帳號存在不等於 App Gate 通過 |
| Subscription / points purchase | Build 47 使用者回報身份與購買後續無法完成 | Sandbox Apple ID、server verification、entitlement／wallet refresh E2E |
| Authenticated chat call | 凍結 commit `72a0bd46` 的 Build 492 已通過 App Call Control 15/15 與 Avatar render contract，手機已安裝／啟動 | `App E2E pending`：仍需針對該 exact Build＋production Gateway／Voice／Avatar 完成真麥克風、AI 聲畫回應與掛斷釋位；post-package source 不承接結果 |
| Pricing policy v4 | source／uploaded Build 47／production Brain 已對齊；Apple Product ID 維持原值，Brain 實際 grant mapping 為點數包 100／300／600／1000、Plus 100、Pro 200 | App Store price／description、Tokyo `019` 與登入後 Sandbox purchase／wallet refresh 真人驗收；DB policy mismatch 不參與目前 `/apple/transaction` 的 `verified.points` 入帳路徑，但仍需治理對焦 |
| Managed-cloud `/chat-test` | #182 已合併，source 預設 404 | Voice 尚未部署；production／staging live GET 仍須重新驗證 404 |

## Chat-call App E2E release gate

任何可能影響 App、Auth、bootstrap、點數、Gateway、Voice、Avatar／GPU、環境設定或部署的改動，最後必須由安裝版 iPhone App 通過：

`按通話 → 麥克風 → Auth/account/credits → Gateway lease → Voice＋Avatar ready → AI 開場 → 真實上行 → AI 聲音／畫面回來 → 掛斷 → lease/GPU release`

紀錄必須包含 App version/build、package profile、裝置、環境、Brain／Voice／Gateway／Avatar identity、驗證時間、結果與 diagnostic reference。developer-direct、瀏覽器、CI、health 或 synthetic probe 均不能把此 gate 標為 `verified`。

## Unknowns that block 90

- App Store Connect selected Build、商品價格／描述與 review state。
- Latest source／next candidate 四條關鍵旅程的 installed-iPhone acceptance。
- Production Gateway／Avatar release identity 與真實 client trace。
- Tokyo ledger 已存在且 live blocker 已具名；`017`／`018`／`019` 都是 blocked，verified head 仍為 null。
- Admin privileged source／freshness／RBAC evidence。
- 7 日以上登入、購買、call setup、通話中斷、扣點、API latency/error 與資料 freshness SLO。

## Update rules

1. Git 管 source；App Store Connect 管 selected Build／review／商品；Cloud Run 與 `/version` 管 runtime；approved ledger＋live probe 管 DB。
2. 易變事實超過 24 小時，發版前重新驗證。
3. FAIL 或 unknown 不得用舊文件、口頭推測或不同 Build 的成功覆蓋。
4. upload、deploy、traffic shift、migration、rollback 或真機 Gate 發生時，必須在同一交接更新本文件。
5. 不在此檔保存 token、secret、使用者資料或 privileged response payload。
