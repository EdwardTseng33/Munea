# FlashHead 授權鏈覆核（沙利曼 Gate 5 前置 · 2026-07-10）

> Verdict：**⚠ 可商用帶條件（GO-with-conditions）**。授權 PDF 原文已存證（session tool-results）。
> 本文為 `avatar-模型優化深度調研-2026-07-10.md` §2.2 授權欄的正式更正與補充。

## 核心更正（對調研報告初判）

初判「FlashHead 授權鏈全 Apache 乾淨」**部分錯誤**：

| 元件 | 實際授權 | 初判 |
|---|---|---|
| SoulX-FlashHead 主程式＋Soul-AILab 權重 | Apache 2.0 ✅ | ✅ 正確 |
| wav2vec2-base-960h（聽聲） | Apache 2.0 ✅ | ✅ 正確 |
| mediapipe（找臉） | Apache 2.0 ✅ | ✅ 正確 |
| **LTX-Video VAE（Lite 版蒸餾來源）** | **程式碼 Apache 2.0；權重＝LTXV Open Weights License（自訂、帶條件）** | ❌ 初判誤標 Apache |
| VividHead 訓練資料集 | CC-BY-4.0＋明文非商用（綁資料集、不綁權重）| 新發現 |

**關鍵法律事實**：LTXV 授權 §1.4 明文把「蒸餾（distillation）」列入 Derivative 定義 → **FlashHead-Lite 整體被 LTXV Open Weights License 管到**，不是「借零件另計」。

## 對沐寧的實際約束

- ✅ **現在可免費商用**：年營收 < US$10M 免費、SaaS 部署明文允許（§3）。
- 🟡 **未來觸發線**：年營收達 US$10M 前必須向 Lightricks（ltxv-licensing@lightricks.com）簽商用協議；踩線罰應付金額 ×2。→ 寫進產品護照成長觸發點。
- 🔴 **Attachment A 使用限制（不分營收、現在就生效）**：
  1. **禁提供醫療建議／判讀醫療結果**——對長輩陪伴 App 是產品邊界紅線：avatar 可陪聊、生活提醒（吃藥時間 OK），不可給醫療建議或解讀檢查報告。（與既有 CORE 專業邊界「告警三步驟、不診斷」精神一致、需在 ToS 正式化）
  2. 禁利用年齡等脆弱性操縱行為致傷害——內購設計不得對認知退化長輩誘導性設計。
  3. 必須明示內容為 AI／機器生成。
  4. 禁非合意仿冒真人（deepfake）。
- ⚠ VividHead 殘留風險：訓練資料源自網路影片、權重 "AS IS" 無侵權擔保——業界同類模型通病、記錄不設閘。

## 徹底甩掉條件的退路

FlashHead **Base/Pro 版走 Wan2.1 VAE＝純 Apache 2.0 無任何門檻**——代價是不即時（4090 僅 10.8FPS、需雙 5090）。以沐寧現況（遠低於門檻＋需要即時），**走 Lite 划算、門檻是可預管理的未來事件**。

---

## ⭐ 自研斷奶路線圖（2026-07-11 03:30 Edward 拍板長期戰略 · 憲法級留檔）

> 背景：Edward 問「閉源自己優化、稱自研優化引擎，將來營收到門檻前把帶條款的零件換掉，就徹底乾淨？」——蘇菲 CFO ＋ 沙利曼 Trust 判定：**方向成立、是最乾淨的路，但有一個技術陷阱與若干注意事項必須留底**。

### 現在就能做、且合法的（無須躲）
- **閉源自己優化 = Apache 2.0 明文允許**：微調、角色特訓、工程層全部可私有、可當商業機密、不強制公開。
- **對外可稱「沐寧自研優化的臉引擎」**：微調/特訓/工程層確實自研＝誠實表述。唯一義務＝法律頁角落保留原作者 NOTICE（不上行銷、使用者不會看）。
- ⚠ **不可做**：對外宣稱「底模從零自研發明」（不實）；剝除 attribution NOTICE（違 Apache）；藏 provenance 躲條款（投資/併購/上架盡調翻出＝公司級死法，見下「為什麼不躲」）。

### 斷奶三步（把「借來的底」變「真正自己的」）
1. **短期（現在起）**：Lite 底模照用 ＋ 我們的微調/特訓/工程私有＝實務上已是「自己的服務」，別人拿同底也做不出我們的效果。
2. **中期（換零件）**：把帶條款的 LTX VAE 零件換成純淨 Wan2.1 VAE（Base/Pro 路）或自養——LTXV 的營收門檻＋Attachment A 使用限制**只綁在這顆零件上，換掉即消失**。
3. **長期（自養一顆）**：用 LTX 公開的**方法/技巧**（方法不受著作權保護、可自由學）自己重蒸餾/重訓一顆替代 VAE ＝ 100% 自有、零 LTXV 附帶。

### 🚨 蒸餾陷阱（最關鍵、白做工警語）
LTXV 授權 §1.4 明文把「distillation／用該模型產生合成資料訓練他模型」都算成 Derivative。**因此自養替代零件時：**
- ✅ **可以**：學它公開的方法、配方、架構思路。
- ❌ **不可以**：拿「舊 LTX VAE 吐出來的輸出/合成資料」當新零件的訓練教材——這樣新零件法律上仍是 LTX 的 Derivative、條款照樣纏著、白做工。
- ✅ **正解**：從乾淨來源訓練替代零件——用純淨授權的 teacher（如 Wan2.1 VAE，Apache）蒸餾，或用我方自有素材從頭訓。
- 一句話：**學它的手藝可以，用它做的菜當食材不行。**

### 殘留但不痛的義務（換掉 VAE 後仍在）
- FlashHead 主模型本體 = Apache 2.0，**永久 NOTICE 義務（不綁營收、不限制任何用途、法律頁一行）**。若要連血脈都零殘留、需另重訓主模型層＝過度投資、不建議（Apache NOTICE 不痛、不影響「自研」表述）。
- 換掉 LTX VAE 後，**Attachment A 使用限制（禁醫療建議等）也隨之解除**——但「不給醫療建議」是健康 App 本就該守的責任底線（免責），實務上照守。

### ⏰ 時間點與觸發（留底）
- **門檻**：LTXV 年營收 **US$10M ≈ NT$3 億**（Edward 口語「3 億台幣」）前免費商用；達標前必簽 Lightricks 商用協議、否則踩線罰應付金額 ×2。
- **安全邊際鐵律**：**營收到 NT$1 億就啟動斷奶工程**（換零件/自養），不是拖到 2.9 億才做——自養一顆 = 幾週到幾個月、幾萬台幣級雲端訓練費，時間/成本邊際極寬（門檻是好幾年後的事），但務必提早、不掐線。
- **產品護照成長觸發點**：NT$1 億營收 → 啟動斷奶；NT$3 億前 → 斷奶完成 or 簽 Lightricks 協議二選一。

### 為什麼「不躲」是 CFO 判斷（非道德說教）
會查 provenance 的不是 Lightricks，是「要把錢給沐寧的人」——App Store 審查、投資人律師、長照機構/政府採購盡調。乾淨合規＝一張紙過關；藏來源被翻出＝投資破局/下架/被告＝公司級死法。用一條命省一張貼紙的錢、帳不划算。斷奶路走完＝**真的**自研、盡調只會加分。

### 執行前守則
正式啟動斷奶工程前，配**沙利曼 Gate 5 ＋ 真人智財律師**覆核一次（本文非法律意見）。

## Gate 5 上線前 checklist（直接收錄）

```
[ ] LTXV-VAE-01 · 年營收 < US$10M 確認；達標前必簽 Lightricks 商用協議（產品護照成長觸發點）
[ ] LTXV-VAE-02 · 隨產品 build ship LTXV 授權原文＋保留 Lightricks 版權標示（§3.2/§3.4）
[ ] LTXV-VAE-03 · Attachment A 使用限制寫進 Munea ToS 並對用戶通知（§3.1 強制）
[ ] LTXV-VAE-04 · 產品邊界鎖：avatar 不提供醫療建議/判讀（A(a)）；內購不操縱認知退化長輩（A(j)）
[ ] LTXV-VAE-05 · UI 明示「AI 虛擬人物／機器生成」（A(e)）
[ ] LTXV-VAE-06 · Lite 正式權重釋出後複核授權標示未變（覆核時標 coming soon）
[ ] VividHead-01 · 記錄訓練資料殘留風險（非商用資料集＋AS IS 無侵權擔保）、接受為業界通病不設閘
```

## 原文出處

LTXV Open Weights License：github.com/Lightricks/LTX-Video（LICENSE=程式碼 Apache）｜huggingface.co/Lightricks/LTX-Video（權重授權檔 LTX-Video-Open-Weights-License-0.X.txt）｜static.lightricks.com/legal/LTXV-2B-Distilled-04-25-Open-Weights-License.pdf｜FlashHead 致謝："[LTX-Video]: the VAE of our Lite-Model"（github.com/Soul-AILab/SoulX-FlashHead）｜Wan2.1 純 Apache：huggingface.co/Wan-AI/Wan2.1-T2V-1.3B｜VividHead：huggingface.co/datasets/Soul-AILab/VividHead

*沙利曼覆核 · 蘇菲落檔 2026-07-10。LTX-Video 0.9.x 與 LTX-2 系兩線皆有 $10M 門檻、無「用舊版繞過」路。*
