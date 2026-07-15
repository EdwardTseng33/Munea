# Munea Supabase 東京搬遷 Canary 與正式切換

更新時間：2026-07-15 12:28 CST

## 專案與安全邊界

- 來源：`uhmpmystjjdqqxlpsthc`（Sydney / `ap-southeast-2`）
- 目的：`fespbkdwafueyonppzwq`（Tokyo / `ap-northeast-1`）
- 方案：Supabase Pro，東京專案 Healthy、nano compute、排程備份已啟用
- 正式 App／Web source：已切換至東京 URL／publishable key
- 正式 backend：本機 production env 已切換至東京 service role；未找到可識別的正式 Brain hosted target。Cloud Run Gateway `munea-call-control` 直接使用 Supabase control-plane，東京 revision `00008-bek` 已通過 Canary 並在 Edward 明確批准後切為 100% 正式流量
- 雪梨專案：保留且未修改、未刪除
- RunPod／GLOWS：主機、模型、卡片與流量完全未操作；migration 010 只建立 Supabase control-plane schema 與 RPC

## 已完成與驗證

| 項目 | 結果 | 證據 |
|---|---|---|
| migrations 001–015 | PASS（東京） | 已依序執行 repo 內全部 SQL；因歷史上有兩份 `011`，001–013 實際共 14 個檔案；014 修復 vitals constraint；015 補齊 migrated public schema 的 backend `service_role` 權限與 default privileges |
| public schema | PASS | 雪梨／東京皆為 44 tables |
| RLS | PASS | 44/44 tables 啟用，設定逐項相同 |
| policies | PASS | 40 條，定義逐項相同 |
| RPC | PASS | 10 個 `munea_*` functions，名稱、參數與 security-definer 設定一致；`munea_grant_free_signup_trial` 以 `service_role` 在 transaction 內連跑兩次，確認冪等只產生 1 wallet／1 transaction／1 ledger、餘額 5，之後 rollback |
| Database 資料 | PASS（搬遷基線） | Canary 寫入前 44 tables 筆數全部相符、14 個非空 tables 的 row JSON 逐列完全一致；Canary 完成後東京 `account_members` 預期新增 2 位 active owner |
| Auth database | PASS | 搬遷基線為 `auth.users` 1、`auth.identities` 1，排除 generated columns 後與雪梨逐列完全一致；Apple Canary 後東京另新增 1 位 Apple Auth user／identity，為預期的 E2E 測試結果，未刪除 |
| Storage | PASS（空集合） | buckets 0、objects 0，來源與目的相同 |
| 記憶 | PASS | 原始 `memory_items` 0、`perception_snapshots` 0；Google、Apple 兩種 authenticated 身分都完成 memory insert/read，測試 rows rollback 後回 0 |
| 訂閱 | PASS（資料與 RLS 讀取） | `subscription_ledger` 24；來源與東京逐列一致，Google、Apple authenticated RLS 都可讀 24；但全部仍是 inactive，無 live entitlement 可驗 |
| 點數 | PASS | 原始 `credit_wallets` 0、`credit_transactions` 0、`credit_ledger` 0、`usage_ledger` 6 一致；點數 RPC 與冪等 Canary 通過，測試資料已 rollback 回 0 |

主要非零筆數：`audit_events` 13、`subscription_ledger` 24、`usage_ledger` 6、`family_state_entries` 3、`companion_persona_templates` 6、`entitlement_policy_versions` 3。

目前有效 entitlement policy 為 version 3，plan order 是 `free / plus / pro`；舊 version 1–2 已停用。

## Canary 驗證與切換注意事項

### 1. Google／Apple provider 設定與登入 E2E：PASS（Auth backend）

- 東京 Supabase：Google、Apple 都已 enabled；provider client 設定已從雪梨安全複製，未寫入 repo。
- 東京 Auth redirect allowlist 已加入 `munea://auth/callback`；Site URL 保持 `http://localhost:3000`，未用它取代正式 App URL。
- Google Cloud OAuth client 已保留雪梨 callback，並新增 `https://fespbkdwafueyonppzwq.supabase.co/auth/v1/callback`。
- Google 真實 OAuth Canary 通過：東京 Auth 使用者 `Last signed in` 更新為 2026-07-15 01:56 CST，provider 顯示 Google enabled。
- Apple Developer Service ID `net.munea.app.signin` 已保留雪梨設定，並新增東京 domain／return URL；儲存確認顯示共 4 個 Website URLs（雪梨、東京各一組 domain／return URL）。
- 東京 Apple provider 的兩個 Client IDs 都保留，但已把 Service ID 排在 Bundle ID 前面；OAuth authorize 已確認使用 `client_id=net.munea.app.signin` 並正確帶入東京 callback。
- Apple OAuth Canary 已通過：東京 Auth Log 於 2026-07-15 02:14 CST 記錄 `Login` 與 `/callback | request completed`，東京 Auth Users 新增 1 位 Apple provider user，Created／Confirmed／Last signed in 均為 02:14。
- Apple 同意頁曾顯示「發生錯誤」，但 Supabase callback、Login 與 Apple identity 均已成功；桌面瀏覽器無法完整接手 `munea://auth/callback` 的視覺流程，仍應在 iPhone 真機做最終 native deep-link QA，但不影響本次 Auth backend Canary 判定。
- 東京仍使用不同 JWT secret；即使後續切換，既有雪梨 session token 預設會失效，使用者需重新登入，除非另行評估 JWT secret 遷移。

### 2. 登入後 RLS 帳號連結：PASS

- 雪梨的 `account_members` 仍為 0；經 Edward 明確授權，東京已把 Google、Apple 兩個 Auth users 都加入同一個 account，角色為 `owner`、狀態為 `active`。
- 東京最終核對：`active_members=2`、`owners=2`。沒有建立第二個 account、person、family group 或 companion profile。
- Munea backend 實際依 `account_members.user_id` 找到 account，再載入該 account 的 primary person；因此兩種登入共用同一份人物、家庭、記憶與訂閱資料，不需要把兩個 Auth IDs 硬塞進單值 `persons.auth_user_id`。
- 分別以 Google、Apple JWT subject 切換為 `authenticated` role：兩者都可讀 accounts 1、family state 3、subscription 24、usage 6、credit wallets 0，並各自完成 memory insert/read。
- RLS Canary memory rows 已 rollback；最終 `memory_items=0`。正式保留的 Canary 寫入只有 2 筆 owner membership。

### 3. 健康 vitals 寫入：PASS（東京）

- migration 008 加入 `vitals`，但後續 `011_family_invitation_integrity.sql` 重建 constraint 時又移除 `vitals`。
- 雪梨仍只允許 `circle / activities / familyFeed / meds / visit / routine / wallet`；東京已套用 `014_family_state_circle_vitals_integrity.sql`，同時保留 `circle` 與 `vitals`。
- 現有 `family_state_entries` 3 筆 keys 是 `activities / familyFeed / wallet`，沒有健康 vitals 資料可對帳。
- 已在東京 transaction 內插入並讀回 `vitals` Canary row，之後 rollback；再次核對正式 `vitals_rows=0`。

### 4. 訂閱 live 狀態：WARN

- 24 筆 ledger 全部是 `inactive`；舊資料仍含 `premium` 名稱（21 筆），另有 `free` 3 筆。
- 新政策 version 3 已改用 `pro`，但尚無 active StoreKit／RevenueCat entitlement 可做 live 驗證。

### 5. iOS 東京 Canary 與正式 source：BUILD PASS／真機登入待驗

- 已加入 Capacitor `@capacitor/app@8.1.0`、`@capacitor/browser@8.0.3`，以外部瀏覽器啟動 OAuth，並由 `appUrlOpen` 接回 `munea://auth/callback`；PKCE callback 會執行 `exchangeCodeForSession`。
- iOS `Info.plist` 已註冊 `munea` URL scheme；native callback bridge smoke PASS，完整 `smoke:no-api` PASS。
- 東京專用 Simulator App BUILD PASS，產物內確認只指向東京 project ref；Edward 批准正式搬遷後，`web/src/auth-config.js` 已改為東京 production public config，且不含 backend／provider secrets。
- 東京專用 signed archive BUILD PASS：`/private/tmp/munea-tokyo-canary-501/archives/Munea.xcarchive`；Bundle ID `net.munea.app`、Team `V77L5245MR`、東京 project marker、`munea` scheme 均確認存在。此 archive 未上傳 TestFlight／App Store。
- Edward iPhone 15 Pro 已覆蓋安裝並啟動 `net.munea.app` version `1.0.10 (15)` 東京開發驗收包；包內東京 marker、雪梨 marker 排除、相機／相簿、Privacy Manifest、Apple 登入與 HealthKit entitlement、後端 secret 零洩漏均 PASS。此包含 Pro、1,000 點、家人假資料及 Voice canary 直連，真 Google／Apple 登入仍需另以關閉自動登入的真機包由 Edward 完成。
- 已把東京 Canary 安裝並啟動於本機 iPhone 17 Pro Simulator，不影響實體 iPhone。App 啟動畫面、設定頁與登入 sheet 正常；Google 外部登入已開到 `accounts.google.com`，畫面明確顯示繼續使用東京 `fespbkdwafueyonppzwq.supabase.co`；Apple 外部登入已開到 `appleid.apple.com` 並顯示「Munea Sign In」。未輸入帳密；OAuth 完成後 deep-link 回 App／session 建立仍待 Edward 親自登入確認。

### 6. Web 東京 Canary：PASS

- 已先從 repo 的 `web/` 複製出獨立本機 Canary 站，只在 `/private/tmp` 注入東京 public URL／publishable key，透過 `http://localhost:3000` 驗證；Canary 通過且 Edward 批准正式搬遷後，repo 正式 `web/src/auth-config.js` 才切到東京。
- Google OAuth 沿用 Chrome 既有登入狀態，自動完成東京授權並回到 `http://localhost:3000/index.html?code=...`；Supabase PKCE 隨後成功交換 session，callback query 已自動清除回 `http://localhost:3000/index.html`。
- Munea 設定頁由「訪客模式」更新為「已登入／Google 帳號同步中」並顯示正確登入帳號，證明 Web Auth callback 與 session persistence PASS，Edward 不需再次輸入帳密。
- Canary 階段沒有更動 production URL／keys；後續正式切換結果如下。

### 7. 正式切換結果：App／Web／本機 Backend／Gateway PASS

- 新 project ref：`fespbkdwafueyonppzwq`；App／Web production source 已使用 `https://fespbkdwafueyonppzwq.supabase.co` 與東京 publishable key。
- formal-source iOS Simulator build PASS；bundle 內只找到東京 project marker，native callback URL scheme 為 `munea`。
- backend-only key 已放在 git ignored、mode `0600` 的 `engine/.env.local`；安全掃描確認 service-role／secret key 沒有進入 `web/` 或 iOS public bundle。
- 東京 Data API 以 backend role 唯讀測試 HTTP 200；`npm run supabase:doctor:live` PASS，31/31 tables 可用，`appProfile / companionProfile / billing / privacyRequests` 全部 PASS。
- 本機正式 engine `/healthz` PASS：`authRequired=true`、`backend.provider=supabase`、`backend.enabled=true`、`missing=[]`。
- native OAuth callback smoke PASS、完整 `smoke:no-api` PASS；Google／Apple Auth、RLS、資料、RPC、健康、記憶、訂閱、點數的 Canary 證據仍維持有效。
- 正式 Brain hosted target 仍未識別；本機與未來 backend deployment 必須使用同一組東京 `SUPABASE_URL`／publishable／service-role env。Cloud Run Gateway 原正式 revision 連雪梨，因其直接讀寫通話席位 control-plane，已新增東京 service-role secret v2 並建立 revision `munea-call-control-00008-bek`。
- Gateway 東京 Canary 的 `ok=true`、`mode=durable`、`durable_ready=true`、席位 snapshot 與過期席位清理 RPC 均 PASS；Edward 明確批准後已升為 100% 正式流量。切換後正式網址連續三次 health 與清理 RPC 仍 PASS，Avatar／Voice 容量各 3、active 0。舊雪梨 revision `00006-kav` 與 secret v1 保留作回復。
- repo iOS project 與實體 iPhone 都已對齊 `1.0.10 (15)`；本輪沒有建立 App Store Archive／IPA，也沒有上傳 TestFlight／App Store。東京真機登入、拍照、StoreKit Sandbox 與全語音體驗仍是 release Gate。

## 回復方案

雪梨專案 `uhmpmystjjdqqxlpsthc` 完整保留，沒有刪除或修改。若東京發生阻斷：

1. 將 `web/src/auth-config.js` 的 public URL／publishable key 改回雪梨，重新 build／sync App。
2. 將 backend deployment／`engine/.env.local` 的 `SUPABASE_URL`、publishable key、service-role key 改回雪梨；不要把 backend key放入 App。
3. Gateway 若已升東京正式流量，將 traffic 切回舊雪梨 revision；Secret Manager v1 保留，不刪除東京 v2。
4. Google／Apple callback 保留雪梨與東京兩組設定，回復時不需重建 provider；因兩邊 JWT secret 不同，切回後要求使用者重新登入。
5. 不刪東京或雪梨的 Auth users／資料。若只需撤回東京帳號歸屬，可將東京 2 筆 `account_members` 標為 `removed`；正式 rollback 不以刪資料為手段。

切換後 release follow-up（不阻擋本次 infra 完成）：

1. Web Canary 已完成；使用關閉開發自動登入的真機包完成 Google／Apple native deep-link QA，避免用目前的 fixture 驗收包誤判正式登入狀態。
2. 取得 active StoreKit／RevenueCat entitlement 後補 live 訂閱驗證；目前 24 筆 ledger 都是 inactive。
3. Gateway 已升東京正式流量；使用東京真實登入 token 完成一次 App 撥號、heartbeat 與 release 真人 Gate。
4. 真機 Gate 通過後再產生或上傳正式 release archive。
5. 雪梨至少保留一個觀察期；未經 Edward 另行明確批准，不得刪除雪梨專案。
