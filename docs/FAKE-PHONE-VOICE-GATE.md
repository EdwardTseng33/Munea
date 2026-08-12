# 聊聊「假手機」發布守門

目的：每一個會影響聊聊通話的版本，先由自動客戶端打一通真實服務鏈；假手機未過，不交給 Edward，也不進 iPhone 候選。

## 它真的做什麼

1. 建立隔離測試帳號、點數錢包並向正式 Gateway 取得 lease／call token。
2. 連上指定的無流量 Voice canary 與 Gateway 指派的 Avatar。
3. 預設模擬現役 App relay：Voice PCM 由假手機轉送 Avatar `/audio` WebSocket。
4. 以即時 20ms 節奏送入一份已知逐字稿的真人 PCM16 mono WAV。
5. 錄下 Voice reference 與 Avatar WebRTC 聲音，完成後刪除測試帳號並釋放席位。

## 必過條件

- ASR 字元召回率 `>= 0.80`。
- 使用者說完到第一段 Voice PCM `<= 4500ms`。
- Avatar 回傳聲音 `>= 1000ms`。
- Voice PCM 模擬播放的單次供給缺口 `<= 250ms`。
- Voice reference 對 Avatar WebRTC：沒有 `>=40ms` 的缺字段。
- `turn_complete` 後 3 秒內，沒有新使用者輸入時不得再出現 AI PCM 或 AI 字幕。
- Voice WebSocket 必須保持連線；Gateway lease 最後要成功釋放。

任一條失敗，程序回非零並輸出 `result.json`、`voice-reference.wav`、`avatar-webrtc.wav`。原始使用者錄音不複製到 evidence 目錄。

## 真人錄音規格

- 由團隊成員一次錄製，不能再讓 Edward 當測試員。
- 錄音者明確同意作為內部 QA；句子不得含姓名、電話、地址或健康個資。
- WAV：mono、PCM16，建議 16kHz、4–8 秒。
- 固定逐字稿需與檔案一同由受控的 CI／測試機保管；不得用本輪 ASR 結果反推逐字稿再自我評分。
- 至少兩份：正常語速與長輩較慢／較小聲語速。

## 執行

每次執行也會保存 Avatar 服務內部的 `audio_underrun` 前後快照與 GPU 生成耗時；該輪
underrun 增量必須為零，不能只靠 Voice 來源音訊看起來連續就判定通過。
WebRTC RTP 跳號會保存發生時間；只有與實際助理說話波形重疊才擋版，開口前或句尾的
待機靜音封包空洞保留為診斷，不得冒充句中卡頓。
正式入口 `fake_phone_e2e.py` 預設連打三通，三通必須連續全數通過；任何一通失敗就擋版。

```powershell
python scripts/fake_phone_e2e.py `
  --voice-canary https://<zero-traffic-voice-tag> `
  --gateway https://munea-call-control-fiu65jd4da-de.a.run.app `
  --transport relay `
  --mic-wav <consented-human-fixture.wav> `
  --expected-text <known-transcript> `
  --out <evidence-directory>
```

Supabase service role 只能由 Secret Manager／CI 注入；不可寫入命令、文件或 evidence。

## 守門順序

`程式測試 → 無流量 Voice canary → 假手機真人 WAV PASS → 合併候選 → exact-build iPhone App E2E → 才可包版／送審`

假手機能驗真 Gateway／Voice／Avatar 與現役 relay 協定，但不能驗 iOS 麥克風權限、WebView、擴音回音消除與實體喇叭聽感，因此不能取代最後的 exact-build iPhone Gate。
