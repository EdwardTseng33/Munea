# 陪寧 PeiNing · STATUS（接力檔）

> 銀髮 AI 專屬管家 App · **新 session cold-start 先讀這份**
> 最後更新 2026-06-26（原型 5 分頁 + Elfie 融入 + 設計精修完成）

---

## 現在到哪
**可跑的原型 App 做出來了**（`web/`）—— 5 分頁 + 視訊 + 用藥，瀏覽器就能點來點去。
設計對齊 Claude Design「陪寧 CAREON 配色」設計稿 + 融入 Elfie 行為科學 + 兩輪設計精修。

## 品名 / 角色（本 session 更新）
- 品名：**PeiNing**（英）/ **陪寧**（中）。〔英文定 PeiNing：Edward 6/27 拍板、PAINING 棄用——英文負面義「使人痛苦」+ 與已查證域名/商標不符〕
- 管家：**寧寧**（女）；範例長輩：陳奶奶；子女：美華（女兒）/ 志明（兒子）；孫子：小寶

## App 架構（底部 5 分頁 + 延伸流程）
- **寧寧**（首頁）/ **狀態** / **聊聊**（中央語音鈕）/ **家人** / **設定**
- 延伸流程：首頁 → 視訊通話 → 用藥服務窗
- 「聊聊」中央凸起 = 命脈動作「主動開口」

## 已做的功能（原型）
| 分頁 | 內容 |
|---|---|
| 寧寧 | 管家英雄卡 + 視訊入口 + 「今天一起完成」可勾任務 + 安心存摺條 + 家人留言 |
| 狀態 | 身體數據（血壓/睡眠/用藥/活動）+ 安心存摺卡 + 寧寧觀察 + 回診摘要 + Apple Watch 數據來源標記 |
| 聊聊 | **日常語音陪聊**：寧寧大頭像 + 即時字幕 + 麥克風語音對話（暖色，刻意跟視訊「見面」分開） |
| 家人 | **全家健康圈**：成員切換看每人健康（身體/活動/睡眠/用藥）+ 週月趨勢；多元家庭挑戰 + 發起挑戰（自由邀請·不強制·依人數+能力動態難度）+ 家庭記錄簿 + 成就徽章牆 + 互動回應 |
| 設定 | 連接的裝置（Apple Watch / Apple 健康 / 跌倒求救）+ 一般設定 |
| 視訊通話 | 擬真 avatar（照護員照）+ 字幕/靜音/鏡頭/結束 |
| 用藥服務窗 | 藥卡 + 連續服藥 + 我吃過了/再提醒 |

## 設計
- **CAREON 配色**：療癒綠 `#3AA8A0` + 珊瑚橘 + 奶油底（讀自 careon-site 實際數值）
- 線條圖示（非表情符號）+ Poppins / Noto Sans TC
- 規範：`docs/design-system.md`（哪個位置用哪個圖示都有定）
- App 圖示：`web/icon.svg`
- 人物素材：randomuser（**西方臉示意，正式版換亞洲真人**）

## 重要文件
- 📕 **`docs/規格書-完整-2026-06-27.md`** — **完整專案規格書（一本串全部、先看這本）**
- ⭐ **`docs/產品遠景-核心目標.md`** — **北極星**（Edward 6/27 親訂：avatar 兩軌標竿、聽講像真人、感知、記憶、視訊取捨）。任何設計/實作對齊這份。
- `docs/解決方案與系統骨架-管家版-2026-06-26.md` — 系統架構（三顆腦 + 一張臉，實現上面的遠景）
- `docs/自架成本與PoC計畫-2026-06-26.md` · `docs/擬真avatar授權合規查核-2026-06-26.md` — 自架成本 / 擬真授權（Ditto）
- `docs/design-brief-peining.md` — 產品設計需求
- `docs/design-system.md` — 設計原則規範（顏色/字體/圖示/元件）
- `docs/architecture-elfie-fusion.md` — Elfie 融入 + 家人傳話架構 + Apple 健康 + 家庭遊戲（§一~九）

## 怎麼跑原型
```
python3 -m http.server 8126 --directory web
# 瀏覽器開 localhost:8126，或 open http://localhost:8126/index.html
```

## 技術路線（不變）
Capacitor 把網頁包成 iPhone App；複用 `castle-voice-engine`（台語語音 + 三顆腦 + 擬真 avatar）；iOS 先、Android 後。

## 夜間自治進度（蘇菲 · 6/27 凌晨、Edward 睡後）
- ✅ **擬真 Ditto PoC 成功**（Edward 在 RunPod RTX 4090 親跑通、生出 talking-head 影片、24GB 夠、~12fps 半即時、TRT 預期到即時）→ 一鍵重跑指南 `docs/Ditto-PoC結果與重跑指南-2026-06-27.md`。便宜消費卡自架擬真「跑得動」實證。
- ✅ **子女端 `family.html` 補「寧寧的提醒」**（收通知：回診 7/2／膝蓋痛關懷／天氣轉涼主動關照；沿用設計系統、eval + 截圖驗證）。
- ✅ **底色改單一米黃**（Edward 6/27 回饋：`.app-shell` 拿掉薄荷綠+橘暈光漸層→單一 `--cream`；聊聊頁 `.chat-screen`→單一薄荷綠當區隔底；薄荷綠其餘只當點綴。驗證+雙截圖過）。
- ✅ **串引擎計畫 v2 落實**（讀完 `castle-voice-engine` 程式庫 STATUS/PASSPORT/路由）：① 引擎=Edward 個人語音蘇菲(BeyondVoice、單人)、**陪寧商業多人要自己一套部署** ② **管家腦感知+記憶 API 大半已做好**（`/brain/morning_brief`、`/perception`、`/memory/shared`、`/brain/start_interview`）= 大省 ③ 臉走 **Ditto**(可商用)、**不照抄**引擎 SoulX/Duix/MuseTalk(Track-A/死路) ④ 台語 Breeze PoC 有起點 ⑤ ⚠️ **發現即時語音用 gpt-realtime-2=OpenAI 用量計費**、跟「全自架不付每分鐘費」初衷有一張要算清的帳。詳 `docs/串引擎計畫-castle-voice-engine.md`。

## 6/27 上午（Edward 起床後）
- 🎯 **語言決策拍板**：v1 **只做台灣中文（華語）、先克服華語**；英語+台語往後期（台語＝v2 護城河加深）。→ v1 語音腦 = gpt-realtime-2 單腦、台語「兩顆腦」架構延後。詳規格書 §6 + 串引擎 §6。
- ✅ **深度盤點即時語音模型**（霍爾）：gpt-realtime-2 仍是 2026 即時對話天花板、不換；台語**全市場無即時對話模型**（只有 TTS 朗讀層 Qwen3-TTS/Breeze Taigi）→ 印證台語得自拼 pipeline、延後合理。
- ✅ **子女裝機流程 `onboarding.html` 做出來**（5 步：歡迎→給誰用→挑樣子〔擬真 4 選／2D 4 選 兩軌〕→邀家人→交給媽媽）。補上 MVP 缺的關鍵流程；**avatar 兩軌首次進畫面**；3 張截圖驗證。出口接 `index.html`（長輩端）+ `family.html`（子女端）。
- ✅ **台語 copy 對齊**（app.js [ENGINE] 註解 + family.html 傳話 placeholder：台語→台灣中文/中性，配合 v1 決策）。

## 下一步（接手做這些）
1. ~~子女端畫面~~ ✅ **已做**（`family.html` 儀表板 + `onboarding.html` 子女裝機 5 步流程）；可再串雲端傳話 + 通知推播
2. **亞洲臉真人素材**換上（現為西方臉/示意 avatar）
3. **串真實引擎**（castle-voice-engine：v1 **台灣中文 gpt-realtime-2**；台語/擬真 avatar 後期）
4. **Apple 健康/Watch 真串接** + 跌倒求救
5. **Capacitor 包 iOS**（✅ Apple 開發者帳號已辦 · 個人 Individual · 2026-06-26 付費完成、等 Apple 審開通）

## 立項決策（保留）
- 子女買單、長輩用；台語為核心護城河（**v1 先華語、台語 v2 加深——6/27 拍板分階段**）；全自架不串第三方付費＝指 avatar（已 Ditto 自架解）；語音腦 v1 接 gpt-realtime-2
- 法規紅線：用藥＝鬧鐘不給建議、陪伴不稱諮商/治療、危機＝轉介（1925/119/家人）
- Elfie 借「行為科學的骨」丟「遊戲外觀的皮」；家庭連結是陪寧 vs Elfie 最大差異化

---
*STATUS v2 · 2026-06-26 · 取代舊構想階段版。原型 + 設計 + 架構文件齊備，交棒下一個 session。*
