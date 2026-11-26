# 語音引擎 A/B 實測:gemini-3.1-flash-live-preview vs Gemini 2.5 Flash Native Audio

- 日期:2026-07-25
- 執行:卡西法(Munea 城堡技術實測)
- 探針:`engine/voice_native_audio_ab_probe.py`(獨立檔案,直連 Gemini Live API,不經 Munea 橋接層 `live_voice_server.py`,不改語音線程式、不部署)
- 完整結構化結果:`voice-samples/native-audio-ab/report.json`(本機路徑,音檔樣本同資料夾,`.wav` 依專案慣例不入 git)
- 背景:7/24 調研結論——非阻塞工具呼叫(NON_BLOCKING + WHEN_IDLE/SILENT/INTERRUPT)、affective dialog、proactive audio 三件套只在 Gemini 2.5 Flash Native Audio 系列,現用 gemini-3.1-flash-live-preview 只有同步工具呼叫。本次實測驗證這些差異是否成立、能否支撐「要不要換引擎」的決定。

## 結論先講

**有條件可行,不建議整體換引擎,建議針對性混用。**

- ❌ **不建議把整條語音線從 3.1 換成 2.5 native audio**:首音延遲穩定慢 ~1.9 秒(5 輪零離群值),且 2.5 native audio 系列**不支援顯式指定 `language_code`**(試過 cmn-TW / cmn-CN / zh-TW / yue-CN 全被拒),等於失去 7/12 那次修「馬來腔」用的台灣腔鎖點,只能靠自動語言偵測,腔調風險未經人耳驗證。
- ✅ **「邊講邊查」的非阻塞工具呼叫在 2.5 native audio 上是真的**:3/3 次都在等工具的 4 秒空檔開口講一句自然過場話(3.1 則是 3/3 次全程死寂)。**如果之後要重新打開即時查詢功能(現在 `MUNEA_VOICE_LIVE_LOOKUP` 預設關),查詢這條路徑可以考慮專門切 2.5 native audio**,不用整條語音線都換。
- 🟡 **affective_dialog 在 2.5 native audio 上可用**,情緒句測試文字稿讀起來確實更貼情緒(先覆述情緒再問),但這把鑰匙(Developer API,非 Vertex)**不接受 `proactivity`(proactive audio)欄位**——7/24 調研講的「三件套」裡,proactive audio 這件在目前的整合路徑上其實用不了,不是全都到位。
- 兩顆模型在 Developer API(ai.google.dev,不是 Vertex)上**都標示 Preview**,7/24 調研提到的「Vertex 上已 GA」跟 Munea 實際用的整合路徑(Developer API key)無關,不能當作穩定性保證。
- 語音輸出/輸入的單價**完全相同**($3/1M in、$12/1M out),換不換引擎在音訊這塊(通話的成本大頭)沒有省錢或變貴的差別。

## 1. 模型可用性(connectivity)

用 Munea 現行的 Developer API 鑰匙(`munea-gemini-key-staging`,GCloud 保險箱)查 `client.models.list()`,對這把鑰匙可見、支援 `bidiGenerateContent`(Live API)的模型:

| 模型 | 連線 | 備註 |
|---|---|---|
| `gemini-3.1-flash-live-preview`(現用) | ✅ OK,吃 `language_code=cmn-TW` | 235ms 連線 |
| `gemini-2.5-flash-native-audio-preview-12-2025` | ✅ OK,**但拒 `cmn-TW`**,退無 language_code 才連得上 | 93ms 連線,本次深入測試用這顆 |
| `gemini-2.5-flash-native-audio-preview-09-2025` | ✅ OK,同樣拒 `cmn-TW` | 94ms |
| `gemini-2.5-flash-native-audio-latest` | ✅ OK,同樣拒 `cmn-TW` | 110ms |

沒查到官方文件常提到的 `gemini-2.5-flash-preview-native-audio-dialog` 這個名字——這把鑰匙看到的是 `-preview-12-2025` / `-preview-09-2025` / `-latest` 三個日期化命名,判斷是 2026-07 時間點的最新排法,不是我記錯或漏找。

**language_code 限制(關鍵發現)**:2.5 native audio 三顆全部拒絕顯式指定語言碼,試過 `cmn-TW`、`cmn-CN`、`zh-CN`、`zh-TW`、`yue-CN` 都回 `APIError 1007 Unsupported language code`,只有完全不帶 `language_code` 才連得上(交給模型自動偵測)。3.1 則正常吃 `cmn-TW`(就是正式站現在用的那個,2026-07-12 修過的台灣腔鎖點)。

**這代表什麼**:如果換 2.5 native audio,沒辦法像現在一樣用 `language_code=cmn-TW` 明講「講台灣腔、不要馬來腔」,只能靠模型自己從輸入音檔判斷語言與腔調。7/12 那次事故(`自己`唸成`jì-jǐ`)就是靠這個參數修的,換引擎等於把這個修復點拔掉,腔調品質要重新人耳驗證,探針測不出腔調準不準。

## 2. 基礎延遲 A/B(每模型 5 輪,同一句「早安,今天天氣真好,晚點要不要一起去公園走走?」)

輸入音檔用 `gemini-3.1-flash-tts-preview` 合成、resample 到 16kHz,兩模型用同一份輸入,公平比較。

| 指標 | 3.1(現用) | 2.5 native audio | 差異 |
|---|---|---|---|
| 連線耗時(median) | 156ms | 94ms | 2.5 略快,差距小,不是重點 |
| **首音延遲**(講完到聽到第一個聲音,median) | **1625ms** | **3516ms** | **2.5 慢約 1.9 秒**,5 輪都在 3219-3718ms 區間,零離群值,是穩定現象不是雜訊 |
| 總回應時長(median) | 9984ms | 8563ms | 2.5 略短,但差距不足以抵掉首音延遲的落差 |

5 輪明細(3.1):first_audio 1609-1641ms(幾乎沒有變異)、total 6594-16094ms(內容長短造成的自然波動)。
5 輪明細(2.5 native):first_audio 3219-3718ms、total 7625-9907ms。

**原因線索**:SDK 對 2.5 native audio 的回應丟出一個警告——回應內容裡混了 `text` 跟 `thought`(思考)部分,只回傳資料部分。對照模型清單資訊(`thinking=True`),判斷 2.5 native audio 預設會先做一段內部思考再開口,這解釋了首音延遲多出的 ~1.9 秒。3.1 沒有這個警告,幾乎是聽完立刻開口。

**對產品的意義**:首音延遲是使用者最容易感知的指標(「她聽到我了嗎」的焦慮),尤其對長輩用戶更敏感。2.5 native audio 多出將近 2 秒的空白,在一般開場閒聊場景是體驗倒退,除非有東西可以填這段空白(見下一節「非阻塞工具呼叫」,那是有解的場景;但一般閒聊沒有工具呼叫可以觸發過場話,這 1.9 秒就是純空白)。

## 3. ⭐ 非阻塞工具呼叫(NON_BLOCKING + WHEN_IDLE)——「邊講邊查」正版驗證

模擬情境:宣告一個假查詢工具,故意 sleep 4 秒才回 `FunctionResponse`(模擬 Munea 正式機實測「查一次 8-9 秒常逾時」的縮小版),問「幫我查一下,巷口那家水餃店最近好像有換老闆,你知道嗎?」,3.1 用同步(BLOCKING,現行預設寫法)、2.5 native audio 用 `behavior=NON_BLOCKING` + `FunctionResponseScheduling.WHEN_IDLE`,各跑 3 輪。

| | 3.1(BLOCKING) | 2.5 native audio(NON_BLOCKING+WHEN_IDLE) |
|---|---|---|
| 工具被呼叫 | 3/3 | 3/3 |
| **等待期間有開口**(spoke_during_tool_wait) | **0/3(全程死寂 4 秒)** | **3/3(每次都講一句過場話)** |

3.1 三輪逐字稿(工具回來後才開口,之前完全沉默):
- 「對啊,換老闆了。不過聽說水餃的味道還是一樣好吃,生意好像還不錯喔!你有去吃過新老闆煮的嗎?」
- 「我也幫你查了一下,那間水餃店老闆真的換人了,不過聽說味道倒是沒什麼變,生意還是很不錯喔!你有打算去試試看嗎?」
- 「欸,對耶!我幫你查了一下,那間水餃店老闆真的換人了。不過聽說味道好像沒什麼改變,生意還是蠻好的。你有要去吃看看嗎?」

2.5 native audio 三輪過場話(工具呼叫後 ~0.5-1 秒內開口,講完約 1-1.5 秒的短句就停,剩下的等待仍是沉默,直到工具回應送達才接上最終答案):
- 「好的,我查看一下。」
- 「我幫你查一下喔,因為這種消息可能需要時間查證。」
- 「等我一下,我查查看。」

**時間軸細節(以第 1 輪為例)**:工具呼叫在 t=12.75s 收到,過場話文字/音訊在 t=13.34-13.7s 之間講完(約 1 秒),接著沉默到 t=16.77s 我方送出工具回應,模型才接上最終回答——實際填住的是 4 秒空檔裡的前 1 秒,後面約 3 秒仍是空白,但體感上「她有回應、知道在查」跟 3.1「完全沒反應像當機」是質的差異。

**可靠度提醒**:這次受控測試(n=3)兩邊 tool_call_seen 都是 3/3(100%)。但正式跑這支探針之前,有一次獨立單輪測試(非本報告 n=3 的一部分)2.5 native audio 面對同樣問句選擇反問「可以提供更多關鍵字嗎」而沒有呼叫工具——顯示 2.5 native audio 對「要不要呼叫工具」這件事不是每次都保證觸發,措辭稍微婉轉一點(例如用問句結尾)可能會讓它選擇追問而非查詢。正式導入前建議多測幾輪不同措辭,不要只信這次的 3/3。

## 4. affective_dialog / proactive_audio 接受度

| | 3.1 | 2.5 native audio |
|---|---|---|
| `enable_affective_dialog=True` | ❌ 拒絕(`APIError 1011 Internal error encountered`) | ✅ 接受,連線正常 |
| `proactivity=ProactivityConfig(proactive_audio=True)` | ❌ 拒絕(`Unknown name "proactivity" at 'setup': Cannot find field`) | ❌ **同樣拒絕**(一模一樣的錯誤) |

**重要修正 7/24 調研的一個假設**:調研原本認為「非阻塞工具呼叫、affective dialog、proactive audio」三件套都綁在 2.5 native audio 上、只要換模型就三個一起拿到。實測結果:**proactive audio 這個欄位在目前的整合路徑(Developer API,`google.genai.Client(api_key=...)`,非 Vertex)上,連 2.5 native audio 都用不了**——不是模型不支援,是這條 API 路徑(可能要 `v1alpha` 版本,或者只有 Vertex AI 才開放)沒開放這個欄位。真正能用的只有「非阻塞工具呼叫」+「affective dialog」兩件,proactive audio 目前用不到,若要驗證是否為 API 版本問題需要額外查證(不在本次範圍內)。

### affective_dialog 情緒句簡測(2.5 native audio,同一句「我今天心情有點不好,家裡的事讓我很煩,不知道該怎麼辦。」)

| | 關閉 | 開啟 |
|---|---|---|
| 逐字稿 | 「拍拍,秀秀。遇到煩心事真的很難受。要不要聊一下?說出來可能會比較好過一點。」 | 「聽到你這樣說,我覺得你現在一定很難受。家裡的事真的很煩人。你願意多跟我說說看嗎?說出來也許會好一點。」 |
| 音訊長度 | 9.08s | 13.32s |
| 語速(字/秒) | 5.95 | 6.16 |

開啟後回應明顯更長、更先覆述使用者的情緒再問問題(「聽到你這樣說,我覺得你現在一定很難受」),比較貼近說明書裡「先接住情緒、不要罐頭安慰語」的要求;關閉版本比較像制式安慰句(「拍拍,秀秀」+ 罐頭問句)。這只是文字稿的質化比對,真正的語氣/停頓/溫度差異要聽 `emotion_affective0_*.wav` / `emotion_affective1_*.wav` 兩個音檔樣本人耳比對才準。

## 5. 成本

2026-07-25 從 `ai.google.dev/gemini-api/docs/pricing` 實抓(Developer API,不是 Vertex 定價):

| | 3.1 Flash Live Preview | 2.5 Flash Native Audio(12-2025) |
|---|---|---|
| 輸入 text | $0.75 / 1M tokens | $0.50 / 1M tokens |
| 輸入 audio/video | $3.00 / 1M(或 $0.005/min) | $3.00 / 1M(無 per-min 選項) |
| 輸出 text(含 thinking) | $4.50 / 1M | $2.00 / 1M |
| 輸出 audio | $12.00 / 1M(或 $0.018/min) | $12.00 / 1M(無 per-min 選項) |

**通話成本的大頭是 audio in/out,兩者單價完全一樣**($3/1M in、$12/1M out)。文字 token(system prompt、transcription)2.5 比較便宜,但這在一通語音電話的總 token 量裡佔比很小,實際帳單差異可忽略。**換不換引擎在成本上是中性的,不是決策因素。**

兩顆模型在 Developer API 頁面上**都標示 Preview**(非正式 GA),都提示「rate limit 較嚴」。7/24 調研提到「2.5 native audio 在 Vertex 上已 GA」——但 Munea 語音線用的是 Developer API 鑰匙(`genai.Client(api_key=...)`),不是 Vertex,所以這個 GA 保證目前套不到 Munea 實際的整合路徑上,不能拿來當「2.5 比較穩」的理由。

## 6. 音檔樣本(供人耳比對)

存於 `voice-samples/native-audio-ab/`(本機路徑,依專案慣例 `.wav` 不入 git,可由本探針重新生成):

- `input_greeting_16k.wav` / `input_lookup_16k.wav` / `input_emotion_16k.wav`:三句輸入音檔
- `greeting_gemini-3_1-flash-live-preview_round{1-5}.wav`:3.1 基礎延遲測試 5 輪輸出
- `greeting_gemini-2_5-flash-native-audio-preview-12-2025_round{1-5}.wav`:2.5 native audio 同測試 5 輪輸出
- `lookup_sync_r{1-3}_gemini-3_1-flash-live-preview_tool.wav`:3.1 工具呼叫測試 3 輪(全程死寂 4 秒的版本)
- `lookup_nonblocking_whenidle_r{1-3}_gemini-2_5-flash-native-audio-preview-12-2025_tool.wav`:2.5 native audio 工具呼叫測試 3 輪(有過場話的版本)
- `emotion_affective0_gemini-2_5-flash-native-audio-preview-12-2025.wav` / `emotion_affective1_gemini-2_5-flash-native-audio-preview-12-2025.wav`:affective_dialog 關/開對照

**建議優先聽**:①`greeting` 兩邊各一輪,感受首音延遲的實際體感差距;②工具呼叫兩邊各一輪,感受「死寂 4 秒」vs「先講一句再等」的差異;③2.5 native audio 的 `greeting`/`emotion` 樣本,人耳判斷自動偵測出來的中文腔調是不是台灣腔(這是換引擎最大的未知風險,探針量不出來)。

## 7. 建議

**不建議**:整條語音線從 3.1 直接換成 2.5 native audio。理由三個都是硬傷——首音延遲穩定慢 1.9 秒(一般閒聊沒有東西可以填這段空白)、失去 `language_code=cmn-TW` 台灣腔鎖點(自動偵測腔調未驗證)、Developer API 上兩者都還是 Preview(不是調研原本以為的「2.5 已經 GA 比較穩」)。

**有條件可行**:如果之後要重新打開「通話中即時查詢」這個功能(現在 `MUNEA_VOICE_LIVE_LOOKUP` 預設關,7/17 決定關掉的理由正是「查詢中間空 9 秒像客服」),**查詢這條專屬路徑可以考慮切 2.5 native audio + NON_BLOCKING + WHEN_IDLE**,因為這正是它唯一實測證實、且跟 3.1 有質的差異的場景——3/3 次都主動講過場話,3.1 則 3/3 次死寂。等於用「混合引擎」的方式,一般對話留 3.1(延遲低、腔調穩),查詢場景才切 2.5(邊講邊查)。這個混用架構需要額外評估:兩顆模型的人設 prompt、聲線參數要不要共用一份、切換時機怎麼判斷、值不值得為了這一個場景多養一條模型串接——這些是產品/工程取捨,不是技術可行性問題,技術上串接沒有障礙。

**進一步需要的驗證(在拍板混用架構之前)**:
1. 人耳聽 `greeting_gemini-2_5-*` 樣本,確認自動語言偵測出來的中文是不是台灣腔(不是就整個混用方案作廢)
2. 多測幾種查詢措辭,確認 2.5 native audio 呼叫工具的觸發率不是只在特定問法下才穩
3. 查 proactive_audio 欄位是否真的完全用不到、還是要換 API 版本(`v1alpha`)才能開——如果查得到開法,affective dialog + proactive audio 兩個一起上,對「先講過場話、模型自己判斷何時開口」這個體驗會更完整

**工時估算(若之後要真的做混用查詢架構)**:樂觀版 1.5 天(串接第二個模型 config + 切換邏輯 + 測試),保守版 3 天(含腔調問題除錯、觸發率不穩的 prompt 調整)。

---

*探針:`engine/voice_native_audio_ab_probe.py`(獨立檔案,可重跑;`--rounds` 控制延遲測試輪數、`--tool-rounds` 控制工具呼叫測試輪數)。*
*完整結構化數據:`voice-samples/native-audio-ab/report.json`。*
