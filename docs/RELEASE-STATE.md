# Munea Release State

## 2026-08-11 21:15 台灣｜1.0.64 實機回報後的 Avatar 512 原生推論修復

- **1.0.64 實機紅燈**：使用者確認開頭需重複多次 HELLO 才回應，且聲音再次比嘴巴快；因此 1.0.64／535 不得沿用舊 synthetic PASS 稱為穩定版或直接送審。開頭漏聽與嘴型是兩個獨立根因。
- **嘴型根因**：正式 Avatar 原先以 640 執行超出 FlashHead 官方 512 原生推論尺寸。640 的 Voice 音訊、direct route、RTP 與 underrun 都正常，但部分回合前 750ms 的實際嘴部 ROI 幾乎沒有動態；把 motion latent 改成跨輪保留仍失敗，已回退。切回 512 後嘴部動態恢復，GPU 首批畫格約 `689–823ms`，並保留 220ms video lead／220ms audio prebuffer。
- **正式 3×3 Gate**：production Gateway→Vertex Voice→Glows Avatar 連續 3 通、每通 3 輪全數 PASS。9 輪首聲 `797–1766ms`，聲嘴偏移 `−93～+250ms`；Voice／Avatar 音訊缺口、RTP gap、Avatar underrun、自主重播與斷線皆 0，多輪內容沒有再問「吃飯了沒」。Glows 持久環境現為 `MUNEA_FH_FRAME_SIZE=512`；`/root/munea-face.env.rollback-frame640-20260811` 與 server/core rollback 檔均保留。
- **Voice 供應者復原**：原 Gemini Developer API 正式與 staging 金鑰均回報 `prepayment credits are depleted`，已將 production Voice 100% 切到 `munea-voice-00113-zok` 的 Vertex AI `gemini-live-2.5-flash-native-audio`；舊 revision 保留 0%。正式多輪 Gate 無 provider 斷線，但這是故障復原，不等於 GPT Live 體驗已達標。
- **放行邊界**：Avatar 與 Voice 服務 precheck 已通過；1.0.64 的開頭漏聽仍未由已安裝 App 修復。App 端等待靜音裁切修正需新 build，完成 source／CI／服務 Gate 後才可通知 Mac 包版；exact-build iPhone 真麥克風、喇叭、首句、三輪、查詢對嘴與掛斷釋位通過前仍為 `App E2E pending`。

## 2026-08-11 台灣｜1.0.64 Build 535 聊聊穩定候選

- **候選內容**：App 移除開場假零聲音回合，只做接收端預備並設定 160ms WebRTC jitter buffer；另由 PR #571 修正 Voice `ready` 前第一句被靜音守門丟棄：只在手機本地保留有持續人聲證據的短預捲（上限 2.2 秒），ready 後依序送出，並立即顯示「我聽見了」。Voice 將 watchdog 恢復後的晚到 PCM／字幕隔離，且 AI 輸出不再建立隱藏守護追問；Avatar 啟用 Opus FEC、40ms 影像提前與 1／8 安靜音素防閃門檻。正常插話仍由 Voice 單一裁決，沒有為首句放寬 barge-in。
- **正式 runtime**：Voice `munea-voice-00110-gak@c5c8d8e2` 已承接 100% traffic；Glows `tw-06` Avatar 使用同一 component commit，健康資料回報 `av_video_lead_ms=40`、`antiflicker_lo/hi=1/8`、`opus_fec=true`、`opus_expected_packet_loss_pct=10`。
- **正式短輪 Gate**：App 預設 production URL 連續 3/3 PASS，首聲 `812–828ms`，嘴聲偏移 `0／+15／−16ms`；缺音、RTP gap、underrun、自主重播、斷線皆 0，三輪上下文正確。
- **正式長輪 Gate**：同一修復元件通話 `388.984s`（6 分 29 秒）／12 輪 12/12 PASS；11/12 首聲不超過 1.33 秒，單一慢輪 2.203 秒；12/12 嘴聲 `−16～+16ms`。Avatar／Voice underrun、RTP gap、波形缺音、自主重播與斷線皆 0，音訊連續相關 `0.9648`；最後仍正確保留發燒、痰、呼吸、胸痛與晚餐狀態。
- **App 版號理由**：`web/src/app.js` 的開場、首句保留與接收緩衝皆屬 App 內 WebView 資產；現有 1.0.63／534 不包含它。Build 535 尚未 Archive，因此 PR #571 直接納入同一個 `1.0.64 (Build 535)` 候選，不為這次修復再多包一版。
- **放行邊界**：目前最高可證明 `source tested + PR #571 merged + staging 0% Voice canary true-service 3/3 PASS + production services deployed for the earlier A/V fixes + App not packaged + App E2E pending`。staging 三通完整真人錄音的 ASR 均為 1.0，首個可聽回覆 `609／610／703ms`、聲嘴 `0／+15／+15ms`，缺音、speech RTP gap、underrun、重播、斷線皆 0；這證明服務鏈未回歸，但不能替代 App ready 前的本地首句保留。首句 App 路徑尚沒有 exact Build 535 的真機證據；Archive／安裝後須以第一聲 HELLO 只說一次、立即收到回饋、回話不被重複 HELLO 撞斷，再覆蓋真喇叭回音、三輪上下文、查詢後對嘴、六分鐘連線及掛斷釋位。通過前不得送審或稱 release-ready。

## 2026-08-11 13:35 台灣｜1.0.63 多輪上下文與五分鐘 Avatar 停止 P0

- **實機根因證據**：安裝版 `1.0.63 (Build 534)` 正式通話 `c17` 在約 3 分鐘內，provider 每輪漏 `turn_complete` 後都走 `finish_and_reconnect`；共建立 9 條新的 Gemini Live session，全部沒有 resumption handle，最後達 `reconnect_limit_reached attempts=9` 並觸發 Gateway `avatar_disconnected`。因此模型每輪忘記前文、反覆問「吃飯了沒」，額度耗盡後只剩聲音而 Avatar 不動。
- **修復**：PR #567／Voice commit `3341f961` 將漏訊號改為同一 Live session 內補 App／Avatar 回合收尾，晚到的 provider `turn_complete` 去重，下一塊 PCM 等舊 Avatar 回合收乾淨再進；不再清除 resumption handle，也不消耗真正 GoAway 的重連額度。每通新增 `provider_turn_recoveries` 與逐輪最大供給空檔證據。
- **三輪真人音訊 Gate**：0% production candidate `munea-voice-00107-jiy` 經正式 Gateway／Call Token／tw-06 Avatar，連續三輪送入同一份 7.16 秒 QA 真人 WAV；ASR 3/3 完整、首聲 `594／766／531ms`、Voice source underrun 0、Avatar 有聲 RTP gap／缺波形／underrun 0、包絡相關 `0.9746`、自主重播與斷線 0。
- **五分鐘上下文 Gate**：同一張 lease／同一 Voice socket／同一 Avatar 連續 `354.093s`、15 輪，每輪後留 20 秒安靜監測；15/15 收到聲音與 turn complete，首聲 `578–891ms`，自主音訊／字幕重播 0、斷線 0、Avatar underrun／有聲 RTP gap／缺波形 0、包絡相關 `0.9733`。provider 仍漏了 9 次 turn complete，但全部記為 `turn_complete_recovered_in_place session_preserved=True`，`session_reconnected`／`reconnect_limit_reached`／`avatar_disconnected` 皆 0；第 15 輪仍正確回答「晚餐吃外送便當，藍色毛巾在沙發上」。
- **放行邊界**：PR #567 最新 Smoke／Product alignment CI 全綠；候選仍為 0% 流量，待合併後才可依 exact tag 升為 production。此修復只改 Voice server，正式切換後現有 `1.0.63` 不需重包。它證明多輪失憶與五分鐘 Avatar 停止的服務根因已修，不代表開頭第一句卡頓或輕微嘴慢已由 iPhone 真機通過；後兩項仍為 `App E2E pending（Codex ownership）`。

## 2026-08-11 台灣｜1.0.63 Build 534 聲音裁決與 Avatar 同步候選

- **1.0.62 實機結論**：使用者確認仍有開場自我打斷、嘴型落後、查詢有聲無嘴，以及畫面仍在通話中但失去說話能力；因此 1.0.62 不得送審，也不沿用先前 synthetic PASS 作為品質結論。
- **App 根因與修正**：舊版在 Voice 裁決插話前已先把 AI 音量壓到 6%，擴音回音即使最後被拒絕也已造成每句可聽中斷；現在候選期只蒐集證據，只有 Voice 明確接受後才停聲。慢起音／短暫停頓不再觸發 voice-only fallback，避免查詢回報把 Avatar 關掉。
- **Avatar 根因與修正**：待機 GPU 工作可能在真 PCM 抵達後才完成，把舊待機幀排到新嘴型之前，並錯誤吃掉該輪 first-frame 標記；現在真 PCM 會使待機工作失效、清除舊視覺 queue 且保留原始 PCM 與共同播放時鐘。`/health` 新增負延遲計數與 idle invalidation，正式 Gate 必須確認負延遲為 0。
- **正式 Gate 抓到並回退**：PR #563 已合併至 `main@414762e6`；第一次 Avatar 部署後，真 PCM 抵達時清空了模型必須維持固定長度的 `audio_dq`，第一輪即觸發 CUDA index out-of-bounds、slot unhealthy。正式三輪 Gate 因 Avatar 無有效語音能量而 FAIL，線上已立即回退至部署前 `flashhead_engine_core.py` SHA-256 `f530a1e8…` 並恢復雙槽 Ready。
- **Hotfix**：`codex/fix-avatar-idle-context-p0-20260811` 保留固定長度中性 pre-roll，只使晚完成的待機輸出失效；新增回歸斷言，清空歷史的舊寫法會直接失敗。狀態為 `source hotfix tested + Avatar production rollback healthy + package/production synthetic/App E2E pending`。App source 候選仍為 `1.0.63 (Build 534)`；不得稱已修好或可送審。
- **Hotfix 單輪正式證據**：PR #564 已合併並部署至 Avatar `c2cd4c2a…`；完整 7.2 秒真人錄音單輪 PASS：ASR `1.0`、首聲 `516ms`、Avatar 音訊 `18.78s`、包絡相關 `0.9697`、句中缺音／underrun／重複／斷線皆 `0`，且無 CUDA fault。監測仍出現不可能的 `-112ms` round latency，定位為舊 GPU chunk 在完成後誤吃新 round 起點；`codex/fix-avatar-round-marker-p0-20260811` 使新 marker 等到自己的 chunk 才計時。三輪 Gate 仍 pending。
- **最終 Avatar hotfix 與正式多輪 Gate**：PR #565 已合併至 `main@a0a06e5f`，Avatar production 已部署 `flashhead_engine_core.py` SHA-256 `421200d3…`。同一張正式 Gateway lease／同一條 Voice WebSocket 連續三輪完整 7.2 秒真人錄音 PASS：首聲 `485／812／782ms`、ASR `1.0`、Avatar 有效音訊 `19.0s`、包絡相關 `0.9757`；缺音、Voice source underrun、Avatar underrun、有聲 RTP gap、自主重複與意外斷線皆 `0`。六筆 round latency `742.7–1282.5ms` 且全為正值，無 CUDA fault／slot unhealthy。
- **查詢型長等待聲畫 Gate**：正式 Gateway／Voice／Avatar 以兩輪查詢型長回覆驗證，首聲 `610／1312ms`，中途最長接收等待約 `2.6s`，後續仍分別輸出 `11.72／12.50s` Avatar 說話畫面；包絡相關 `0.9683／0.9662`，缺嘴、underrun、有聲 RTP gap、重複與斷線皆 `0`。但 Voice 診斷的 `native_searches=0`，表示模型沒有留下真正搜尋工具事件；這兩輪只證明「長等待後恢復語音仍有嘴型」，不得冒充真搜尋資料 Gate。
- **放行邊界**：`source merged + Avatar production deployed + repository/CI PASS + production service prechecks PASS + App E2E pending`。`1.0.63 (Build 534)` 現在可進 Mac Archive／安裝候選，但不可直接送審；只有 exact Build 534 在 iPhone 完成真喇叭回音、開場、三輪真麥克風、查詢後聲畫、掛斷釋位後，才能稱修好與 release-ready。

## 2026-08-11 04:30 台灣｜1.0.62 回報後的正式聊聊 P0 修復

- **使用者回報**：已安裝的 production `1.0.62 (Build 533)` 仍出現開場卡住、整句斷續／重複、講一講後不能再說但畫面仍在通話中。這是修復前的 exact App 實機失敗證據，不能用先前單輪假手機 PASS 覆蓋。
- **三個服務端根因已修**：正式 Voice 原先未啟用 Voice→Avatar direct route；Avatar 音訊 sender 在事件迴圈變慢後會用 burst 追趕，接收端可能丟棄過晚 RTP；Gemini 偶發輸出聲音後不送 `turn_complete`，使 App 留在 AI 說話狀態。PR #561 已合併到 `main@556dfd5d`；Voice 現在只在真的送出至少 200ms 聲音、連續 2.5 秒無新聲音且不是工具／查詢／插話時，補發回合結束並以新 session 背景重連，不關閉 App socket 或 Gateway lease。
- **正式 runtime**：Voice `munea-voice-00105-roh@556dfd5d` 已承接 100% traffic，`MUNEA_VOICE_FACE_DIRECT=1`；Glows `tw-06` Avatar PID `304535` 跑 `ca614434`、protocol 3。Voice 上一版 `munea-voice-00103-suy` 保留為即時回滾目標；本次是服務端修復，**不需要重新包 App**。
- **單輪正式服務 Gate**：zero-traffic production candidate 連續 `6/6 PASS`，切 100% 後再由正式 service URL `3/3 PASS`。切流量後第一聲 `516／453／500ms`；三通 ASR 字元召回 `1.0`，Voice source underrun、Avatar WebRTC 有聲區 RTP gap、缺波形、Avatar underrun、自主重複與意外斷線全為 `0`。
- **新增同線多輪 Gate**：同一張 Gateway lease／同一條 Voice WebSocket 連續送三次完整 7.16 秒真人 PCM；三輪 ASR 皆完整，第一聲 `547／500／469ms`，三輪皆收到聲音與 `turn_complete`，source underrun `0`、有聲區 RTP gap `0`、缺波形 `0`、自主重複 `0B`、連線保持。證據：`.tmp/fake-phone-direct-f97deaba/evidence-prod-serving-556dfd5-multiturn-full/summary.json`。驗收工具已新增 `--turns` 與 `all_turns_completed`，以後不得再用單輪成功推論「後面仍可講話」。
- **狀態邊界**：`source merged + Voice/Avatar deployed + production synthetic audio 10 calls / 12 turns PASS + App E2E pending`。自動客戶端已驗正式 Gateway／Voice／Avatar 的真人 PCM、實際回傳聲音與三輪狀態；尚未在修復後的 exact installed iPhone 取得真麥克風／喇叭／WebView 證據，因此仍不稱 fully verified 或 release-ready，也不把使用者當人工驗收員。

## 2026-08-11 00:49 台灣｜聊聊三邊協議版 1.0.62 Build 533

- **三邊一起換的根因**：1.0.61 實機當時連到舊 production Voice、新 Avatar 與未具版本握手的 App／Gateway，造成開場自我插話、paired lease 被 Avatar component release 提前結束，以及聲音已播放但嘴型 GPU queue 落後。版本字串本身無法證明三邊程式一致。
- **正式服務已對齊**：Gateway `munea-call-control-00016-jeh@52a21fb7`、Voice `munea-voice-00103-suy@52a21fb7` 均為 100% traffic 且要求 signed `call_protocol=3`；Glows `tw-06` Avatar runtime 為 `23fe64ca`、`call_protocol=3`。component release 不再有權結束整張 paired lease，只有 App 明確掛斷或 45 秒 reaper 可收線。
- **唯一 App 候選**：`1.0.62 (Build 533)`。App 會帶 native version／build／protocol，並拒絕 Gateway 或 Voice 協議不符；WebView cache identity 為 `20260811-callprotocol-b533-v1062`。App Store Connect 唯讀實查：最新上傳為 `1.0.61 (Build 532)`；目前 `WAITING_FOR_REVIEW` 的版本其實是 `1.0.55`，選用 `1.0.55 (Build 525)`，不是 1.0.61。
- **自動實聲 Gate**：正式候選三邊 3/3 PASS，第一聲 `922／828／921ms`；Voice underrun、Avatar 助理說話區 RTP gap、缺波形、自主重複、意外斷線皆 `0`。升為正式預設入口後另跑 1/1 PASS，第一聲 `890ms`、同五項皆 `0`，連線保持。兩輪非說話區各觀察到單一 `100ms` video PTS gap，不影響助理有聲區，但保留追蹤。
- **狀態邊界**：`services deployed + source merged at main@c4477ae3 + App 1.0.62 Build 533 not packaged + App E2E pending`。尚未有 exact IPA／安裝版 iPhone 真麥克風與聲畫證據，因此不得稱 fully verified、release-ready 或已送審。

## 2026-08-10 21:18 台灣｜聊聊卡頓／重複／自行斷線 P0 候選

- **失敗實證**：正式 App 診斷自報 `1.0.60`（Build 尚未取得），2026-08-10 約 20:39–20:43 台灣時間走 production Gateway／Voice／GLOWS `tw-06`。觀測到喇叭殘響 RMS `0.051`、僅 2 個 post-duck frame 就被接受為插話；同線臉聲 lead `2652ms` 後 App 自動降級並關閉 Avatar WebRTC，Avatar component release 令整張 paired lease 變成 `stale_lease`，之後使用者失去麥克風且通話自行結束。
- **正式止血**：`origin/main@9a0308a6`／production Voice `munea-voice-00101-yog@9a0308a6` 已把 Voice→Avatar direct route 預設關閉，回到 App relay。這是服務端 kill switch，不等於 App 故障已永久修好。
- **App 候選**：`codex/fix-call-audio-state-p0-20260810`。降級只隱藏／靜音 Avatar 並切回本地聲音，不再關閉 paired transport；`speechActive()` 只信 Voice PCM 播放水位，不再讓 Avatar idle 音軌底噪長時間關閉麥克風；iOS 短暫 hidden 改為 5 秒 grace。App 插話邏輯降級為「候選觸發＋duck＋送證據」，不得自行停止 AI；只有 Voice 的 `decide_speaker_evidence()` 可以接受／拒絕，且不採信 App 傳來的 RMS 門檻。
- **假手機 Gate**：新增 `python scripts/fake_phone_e2e.py`，預設走現役 App relay，取得真 Gateway lease／call token，連 Voice＋Avatar WebRTC，送入固定 PCM16 WAV，核對 ASR 字元召回、第一聲、Voice PCM 供給缺口、Avatar WebRTC 連續性、turn complete 後無自主第二段與連線保持。2026-08-10 首次用既有合成 WAV 做「不計分管線自測」時，現役 staging 在 `turn_complete` 後無新輸入又送出 `319230` bytes 及第二段字幕；假手機因此正確判 FAIL，證明 Gate 能攔下自主重複。
- **升流量前 canary 實證**：Voice revision `munea-voice-staging-00114-yuf@3ebd91d4`（tag `stg-0810-220410-3ebd91d`）在 0% traffic 階段三次兩階段插話皆 PASS：Voice 裁決 ACK `15–16ms`、AI 停聲 `110–125ms`、送入證據 `200ms`、舊聲外漏 `0B`。canary 也已壓住 routine health 自主第二輪，五次假手機皆為 `unsolicited_audio_bytes=0`、連線保持；通過後才升為預設入口 100%。
- **間歇卡頓已由假手機重現**：正式入口預設連打三通；2026-08-10 22:33 台灣的三通管線驗證只過 `1/3`。失敗兩通 Voice 來源 queue 均為 `0 underrun`，但 Glows Avatar 內部 `audio_underrun` 分別增加 `3`／`2`，波形缺口最長 `140ms`／`200ms`；WebRTC RTP timeline 無跳號。根因位於 FlashHead 把原始 PCM 等到每塊嘴型 GPU 完成後才推入播放 queue，GPU 區塊抖動會直接抽乾聲音。
- **Avatar 修復已部署**：`flashhead_engine_core.py` 改成原始 Voice PCM 抵達即進連續音訊 queue，第一批嘴型 ready 後只開一次共同起播門；後續 GPU 慢只允許畫面停格，不得再阻塞聲音。輸入 EOF 立即關閉已解耦音訊，避免自然句尾被誤算 underrun。2026-08-10 已在 Glows `tw-06` 現役 worker 重啟；`flashhead_server.py` SHA-256 `8521f883…d6aa`、`flashhead_engine_core.py` SHA-256 `1bac6c77…ab84`，回退備份保留在 worker。
- **正式 App 測試入口實證**：staging Voice `munea-voice-staging-00114-yuf@3ebd91d4` 已承接預設 URL 100% 流量；以正式 Gateway lease／call token、App relay、現役 Avatar WebRTC 連打三通，`3/3 PASS`。第一聲 `906／1140／953ms`；Voice 來源 underrun、Avatar 內部 underrun、實際助理說話區段 RTP gap、波形缺字、無輸入自主重複、通話自行斷線均為 `0`。證據：`.tmp/fake-phone-app-entry-final-00114-avatar-3455609d/summary.json`。
- **自動驗收**：插話／回音、啟動、Avatar direct kill switch、通話儀表、UI 契約、假手機契約與可執行狀態機均 PASS。正式 App 本地播放排程以 80 個 200ms PCM chunk、147ms 到貨間隔重播：`0 underrun`、`0 scheduling gap`；Avatar idle RMS `0.04` 連續模擬 3 分鐘：麥克風守門阻擋 `0` 次。`smoke:no-api`、UI contracts、Voice chain contracts 全綠。
- **完整套件例外**：`npm run test:launch` 在既有 `test_flashhead_router_core.py` Windows Bash dry-run 失敗；該測試與輸入檔均未被本分支修改，針對性與後續 UI 測試全綠。
- **狀態**：`Voice staging deployed / live Avatar deployed / App-entry fake-phone 3/3 PASS / main@c4477ae3 / App E2E pending`。服務端卡頓、重複與連線保持 Gate 已通過；PR #558 已合併，尚未包新 App。既有合成 WAV 只能證明整條聲音管線連續，不能冒充真人聲 ASR 或 exact-build iPhone PASS；仍需由 exact-build iPhone 自動／實機 Gate 驗真麥克風與喇叭。

本文件是 App、source、runtime、DB 與營運後台的 current release snapshot。品質分數看 [`PRODUCT-QUALITY-CONFIDENCE.md`](./PRODUCT-QUALITY-CONFIDENCE.md)；歷史活動看 `STATUS.md` 與協作看板。

Snapshot time: `2026-08-11 Asia/Taipei`（production Voice 為 `munea-voice-00110-gak@c5c8d8e2`；Gateway 為 `munea-call-control-00016-jeh@52a21fb7`；App Store review lane 為 `1.0.55 (Build 525) WAITING_FOR_REVIEW`；current source 候選為 `1.0.64 (Build 535)`；installed-iPhone lane 尚無 Build 535 證據）

Source reconciliation baseline: `origin/main@c4477ae380df8a8f908b5383577b9f3df5591239`; latest uploaded App Build 532 的 exact source commit 尚未由 IPA 回讀，不能推定等於 current source

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
| Latest source | `1.0.64 (Build 535)` | 下一個唯一候選；移除 App 開場假音訊回合、加入 WebRTC 接收緩衝，並保持 Voice／Avatar 聲畫連續。WebView cache identity 已更新為 `20260811-livefix-b535-v1064` | `package.json`; `package-lock.json`; `web/src/version.js`; `web/index.html`; Xcode project | 2026-08-11 +08:00 |
| Latest uploaded App | `1.0.61 (Build 532)` | App Store Connect 唯讀查得 `VALID`，上傳 2026-08-10 08:35 UTC；不含本輪三邊協議握手，不能代表 current source | App Store Connect API（權威） | 2026-08-11 00:49 +08:00 |
| App Store selected review lane | `1.0.55 (Build 525)` | `appStoreState=WAITING_FOR_REVIEW`；權威 API 回讀 selected build 為 App 1.0.55 Build 525。1.0.61 Build 532 只有 uploaded／VALID，並未被這個審核版本選用 | App Store Connect API | 2026-08-11 00:49 +08:00 |
| Edward iPhone install lane | `1.0.44 (Build 492)` | iPhone 15 Pro 安裝與啟動成功，`devicectl` 從手機回讀版本；使用 Development signing＋production config，未注入 direct／gateway QA fixture。安裝成功不等於正式 App Store binary 或真人通話 Gate | `devicectl` install／launch／app inventory | 2026-07-28 17:25 |
| Draft call／purchase／QA fixes | #174 → #175 → #188，目標 `1.0.43 (Build 48)` | 三張 Draft 目前 merge state CLEAN 且 CI 綠；#175 stacked on #174、#188 stacked on #175。這仍只代表可整合，尚未 merged／packaged／iPhone verified | PR #174; PR #175; PR #188 | 2026-07-20 |

## Runtime services

| Environment | Service | Serving identity observed from public endpoint | Interpretation | Evidence time |
|---|---|---|---|---|
| production | Brain | `1.0.53@2d5afa7d`, `munea-brain-00164-yuw` | `/healthz` 200、`ai.state=ok`。落後 main 的 11 筆全是語音／臉機／測試／App 端檔案，**管家腦自己的程式已是最新**，不需重新部署 | 2026-08-06 02:5X |
| production | Voice | `munea-voice-00103-suy@52a21fb7` | 100% traffic；`MUNEA_CALL_PROTOCOL_REQUIRED=3`；正式預設入口假手機第一聲 `890ms`，underrun／重複／意外斷線皆 `0` | 2026-08-11 00:4X |
| production | Call Control / Gateway | `munea-call-control-00016-jeh@52a21fb7` | 100% traffic；簽發 `call_protocol=3`；component release 不再終止 paired lease | 2026-08-11 00:4X |
| production | Avatar (Glows) | worker `glows-tw06-resident`，runtime `23fe64ca` | 2 slots；`call_protocol=3`；音訊為 master clock，嘴型追到 audible PCM，跨停頓不重設 timeline | 2026-08-11 00:4X |
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
