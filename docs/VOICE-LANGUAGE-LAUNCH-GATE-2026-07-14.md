# 沐寧首發語音／語言 Gate

更新：2026-07-14

## 上線決策

- 首發只承諾台灣華語（國語），不承諾台語／臺灣閩南語。
- 台語聽與說必須在代表性真人語料中各自達到至少 80% 才可開啟；任一項未達即維持關閉。
- 現行供應商沒有提供可對應此門檻的台語正式支援或驗證分數，因此程式中的已驗證分數為 `0.0`，功能 fail closed。
- 使用者說台語而模型無法非常確定完整意思時，只能用台灣華語請對方改用國語，不可猜意思、亂翻譯或拼湊發音。

## 為什麼 `cmn-TW` 不等於台語

- 現行 Gemini Live 語音設定使用 `cmn-TW`，意思是 Mandarin Chinese (Taiwan)，也就是台灣華語。
- Gemini Live 官方支援清單列出 Chinese (`zh`)，未列 Taiwanese Hokkien。
- Google Cloud Speech-to-Text 的台灣項目是 Chinese, Mandarin (Traditional, Taiwan) (`cmn-Hant-TW`)，同樣不是臺灣閩南語。

官方來源：

- https://ai.google.dev/gemini-api/docs/live-api/capabilities
- https://ai.google.dev/gemini-api/docs/live-api/best-practices
- https://docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages

## 台灣華語驗收

程式面必須同時滿足：

1. 語音語言碼維持台灣華語，不切成中國大陸華語。
2. Prompt 要求繁體台灣中文、台灣用詞與簡短口語。
3. 不主動混入台語；聽不清楚時誠實澄清。
4. 寧寧與阿宏維持低暖、穩定、稍慢、句尾完整，不突然升高音量或加速。

人工聽感 Gate 不能由文字測試取代。每個正式聲線至少由台灣母語者各聽 10 句，逐項評分：

- 台灣腔自然度
- 聲調與咬字
- 台灣用詞
- 語速與句尾完整度
- 長輩在手機喇叭下的可懂度

任一角色的平均可懂度未達 80%，就不能作為首發正式聲線。

教育部國語辭典的「垃圾」讀音為 `ㄌㄜˋ ㄙㄜˋ`，可列入台灣華語發音抽測：

- https://dict.concised.moe.edu.tw/dictView.jsp?ID=13230&la=1&powerMode=0

## 台語未來開啟條件

評測集至少包含 100 句、10 位不同年齡與性別的台語母語者，並分開記錄：

- ASR 完整語意理解率
- 回答是否針對原問題
- TTS 母語者可懂度
- 發音自然度
- 國台語混用與快速切換
- 手機喇叭、一般室內噪音與行動網路情境

ASR 與 TTS 都達 80%，且危機／用藥語句沒有高風險誤解後，才可修改 `TAIWANESE_HOKKIEN_VALIDATED_SCORE` 並經程式審查開啟。
