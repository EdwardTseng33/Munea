# 寧寧回答品質 · 輕量評測腳手架 v1

> 出處：`docs/research/健康管家模型-技術路線調研-2026-07-24.md` 第 4 題（評測腳手架＝技術面 ROI 最高的補件）。
> 目標：讓「寧寧回答品質」從此可量測、可迴歸——改了提示詞／換了模型，跑一輪就知道變好還變壞，不再靠人工唸逐字稿感覺。

---

## 這是什麼

三件東西：

1. **`golden_set_v1.json`**——日常對話黃金集，種子 26 題（目標 50，之後補），涵蓋 5 類：
   - `persona_consistency` 寧寧人設一致性（自稱寧寧、溫暖不機械、不假裝真人）
   - `personalization` 貼身感（會不會用記憶側寫、避免「溫牛奶式」罐頭回答）
   - `plain_language` 人話（長輩聽得懂，不是醫學術語或長篇大論）
   - `medboundary` 醫療紅線邊緣題（非危機類：保健品／劑量／該不該看醫生——跟
     `engine/test_guardian_crisis.py` 的 46 題危機測試是互補關係，不重複：那支測
     「有沒有正確判斷風險等級」，這份測「回答內容好不好」）
   - `taiwan_local` 台灣在地（不推褪黑激素等、不用大陸用語）

   每題 2-4 條**可判定的 pass/fail 準則**，不做 1-10 分玄學評分。部分題目帶
   `fixture`（記憶側寫／記憶項目），用來測「同一句問題、不同背景的人，寧寧會不
   會給不同答案」。

   **種子版，內容品質後續由衛教題庫工程餵進來**——蘇菲正在並行製作的衛教 20 題
   （`docs/research/衛教顧問-底層設計原則-2026-07-24.md` 五地基＋溫牛奶反例）
   會灌進本黃金集，屆時補到 50 題目標。

2. **`gen_reply.py` + `judge.py`**——子行程 worker：
   - `gen_reply.py`：組出跟**正式語音線同一套** system instruction
     （`live_voice_server.system_instruction()` → `server.build_reply_context()`
     → `server.reply_context_instruction()`，跟真的通話用同一條路，不是另外簡化
     的測試版），呼叫真模型（預設 `gemini-2.5-flash`）生一句寧寧的回覆。
   - `judge.py`：LLM 當評審，給定題目準則＋寧寧的回覆，逐條判 pass/fail＋一句
     理由，用便宜模型（預設 `gemini-2.5-flash`，可用 `MUNEA_EVAL_JUDGE_MODEL`
     環境變數換）。

3. **`run_eval.py`**——一鍵跑整份黃金集，輸出：
   - stdout：一張趨勢可比的分數表（總分／分類分數／逐題結果／失敗準則理由）
   - `results/eval-<timestamp>.json`：完整結果存檔留基準（含每條準則的判定與
     理由，供之後版本對照 diff）
   - `results/latest.json`：永遠指向最新一輪

---

## 為什麼手寫薄跑分器，不用 DeepEval／promptfoo

技術調研點名兩個選項：DeepEval（pytest 原生）、promptfoo。評估後選**手寫薄跑分
器**，理由：

- **這個 repo 沒有 pytest 生態**——`engine/` 底下 48 支 `test_*.py` 全部是「一支
  腳本一個 process、`python engine/test_X.py` 直接跑、自己印 PASS/FAIL」的慣例
  （見 `AI聊聊-總覽-架構與迭代指南.md` §11.2），連 `pytest` 套件本身都沒裝在專
  案 venv 裡。硬套 DeepEval（pytest-native）等於引入一整套新的測試框架慣例，
  維護成本比題目本身還高。
- **promptfoo 是 Node/CLI 工具**，這個評測要組的 system instruction 高度依賴
  `server.py`／`chat_engine.py`／`live_voice_server.py` 的 Python 內部函式（記
  憶注入、感知快取、優先權契約），promptfoo 沒辦法直接呼叫這些函式，還是得包一
  層 Python adapter——包完等於還是自己在寫薄跑分器，只是外面多包一層 YAML 設定
  檔的學習成本。
- **量級對得上**：26-50 題、5 類、pass/fail 準則，是「一個下午看得完」的規模
  （技術調研原話），DeepEval／promptfoo 的批次管理、UI 儀表板等重量級功能在這
  個量級用不到。
- **子行程隔離是必要設計、不是偷懶**：`server.py`／`chat_engine.py` 的資料檔路
  徑（`MEMORY_ITEMS_PATH`、`LIVING_PROFILE_PATH`…）是 import 當下讀 env var 算
  出來的模組常數，同一個 process 裡沒辦法乾淨地換 26 次 fixture。每題開一支全
  新 Python 行程，先設好 env 再 import，天生隔離，這點無論用不用外部框架都要自
  己處理。

**什麼時候該重新評估**：題目衝到 100+ 題、或要開始做「兩個 prompt 版本 A/B 比
較」「跨模型基準表」這種更複雜的分析時，回頭看 promptfoo（那時候它的比較介面
才划算）。現在先把量測這件事「有」比「完美」重要。

---

## 跑法

```bash
# 整份黃金集（26 題，會呼叫真模型兩次×26＝約 52 次 API 呼叫）
python engine/eval/run_eval.py

# 只跑某幾題（除錯／省錢用）
python engine/eval/run_eval.py --ids g06,g07,g19

# 只跑前 N 題（快速煙霧測試）
python engine/eval/run_eval.py --limit 5
```

需要 `GEMINI_API_KEY`（`engine/.env.local` 有的話自動讀，跟其他 `test_*.py`
同一套）。

`npm run eval:nening` 是同一支指令的捷徑（見 `package.json`）。

---

## 已知限制：單次跑動的雜訊（B1 驗證時發現、2026-07-24）

**發現過程**：B1（提示詞調校拉貼身感）改完後跑一輪 before/after 對照，
personalization 類回升（50%→66.7%）符合預期，但同時 taiwan_local／plain_language
各掉 1 題。原本差點被當成「B1 拖累了其他類別」的結論，直接送出去——但先做了一次
「用同一份 after 程式碼、對同 4 題邊界題再跑一次」的複驗，結果 g06、g24 直接
PASS/FAIL 互相翻轉。這證實：**在 `gen_reply.py` 目前的預設參數
（`temperature=0.7`、每題只生成一次）下，單次跑動的 ±1 題差異落在生成雜訊範圍
內，不能直接當成因果結論**——不管是「進步」還是「退步」都一樣，都要先排除雜訊
才能信。

**教訓寫死在這**：任何要下「這輪改動讓分數變好/變壞」結論的關鍵驗收（例如
B1／B2 這類提示詞或架構調校前後對照），**單輪 ±1-2 題規模的差異不可信、不可
判讀**；只有分數差距大到不可能是雜訊（例如某類別從 0% 跳到 80%+），或是做過
多輪重複取樣、用多數決穩定下來的差異，才能當作真結論寫進 PR／回報。

**下一步（B2 前置待辦，B2 驗收也需要它）**：`run_eval.py` 加 `--repeat N` 參數
——同一題重複生成＋評審 N 次，取多數決（例如 N=3 時 2/3 過算過）當作這題的正式
結果，分數表順便附上「每題 N 次中通過幾次」讓人看得出信心區間，不是只有一個
可能是雜訊的數字。**做關鍵驗收前務必先確認這個模式存在，沒有就先手動重複
`run_eval.py --ids ...` 跑 N 次自己取多數決**（B1 驗證時就是這樣手動做的，見
`results/` 底下 `before-b1-*`／`after-b1-*` 系列檔案）。

---

## 成本估計（實測，不是用猜的）

2026-07-24 本機實跑整份 26 題黃金集，真實 token 用量（`usage_metadata` 直接讀
出來，不是估算）：

```
26 題（每題：1 次生回覆＋1 次評審＝約 52 次真模型呼叫）
總 token 用量：約 230,227 tokens（gemini-2.5-flash，含 system instruction）
```

Gemini 2.5 Flash 是低價位模型（同級距 Gemini 1.5/2.0 Flash 過往公開報價約在
每百萬 input token US$0.1-0.3、output token US$0.4-2.5 這個級距，2026 年實際
費率請以當時 Google AI 官方定價頁為準）。以此量級粗估，**跑一輪完整 26 題黃金
集的成本落在 1 美元以下**（實際帳單以 Google Cloud Billing 為準，這裡只提供
數量級參考，不是精確保證）。50 題目標版本大約是這次的 2 倍量級。

**為什麼系統提示詞（system instruction）偏大（每題約 9,000-9,500 字元）**：這
是刻意的——用的是跟正式通話**一模一樣**的 `system_instruction()`，包含優先權契
約、CORE 共同底盤、角色人格、RED 安全紅線、記憶／感知／健康資料圍籬等完整說明
書，不是為了省錢刻意精簡的測試版。**跑得準比跑得便宜優先**——這是「量測寧寧真
的會怎麼回」而不是「量測一個簡化版寧寧會怎麼回」。

---

## `results/` 的版控紀律

`results/` 不是 gitignore——但也不是每次手動跑都要進版控。原則：**只有想留
作「基準點」的整輪跑（例如改完 prompt 前後各一輪、要給 Edward／馬魯克看趨勢
的那種），才手動 `git add engine/eval/results/eval-<timestamp>.json`；日常
除錯用的 `--ids`／`--limit` 局部跑不必進版控（`latest.json` 每次跑都會覆蓋，
只反映最後一次跑的內容，commit 前自己看一下是不是真的想留的那輪）。

## 為什麼先不進 CI、Nightly 之後再議

Edward／馬魯克拍板前的暫定原則（2026-07-24）：

- **評審要燒模型鑰匙的錢**——跟 `engine/test_guardian_crisis.py`（純規則判定、
  零外部依賴、零成本）不同，這份黃金集每一輪都是真的呼叫 Gemini 兩次（生回覆
  ＋當評審），有真實金錢成本。CI 每次 push／PR 都跑＝每天可能跑幾十次，成本會
  疊加，且 LLM 當評審本身有機率性（同一題不保證每次判定完全一致），不像危機測
  試那樣適合當「錯了就擋 push」的硬性 CI gate。
- **本輪先手動跑建立基準**——這支腳本先在本機／手動觸發的場景下用，讓卡西法／
  蘇菲在改 prompt 或換模型前後各跑一輪，比對 `results/` 底下的分數表，看是變好
  還變壞。
- **Nightly（每晚跑一次）是下一步、不是這次的範圍**——等黃金集擴充到 50 題、
  分類分數穩定下來後，再評估要不要掛 GitHub Actions schedule（獨立於
  `smoke.yml` 之外，因為那支是零成本的 push-gate，語意不同，不應該混在一起），
  到時候要一併決定：① 誰付這筆持續性的 API 費用 ② 分數退步多少算「真的變差」
  （LLM 評審本身有雜訊，需要抓一個容忍區間，不是差 1 分就報警）③ 退步了要不要
  真的擋 push，還是只是通知。**這些決定留給 Edward／馬魯克，這次不擅自綁死。**

---

## 2026-07-24 v1 基準（首輪真跑，留作對照）

```
整題 PASS 率：18/26 = 69.2%
準則 PASS 率：70/78 = 89.7%

分類別：
  persona_consistency  整題 6/6（100.0%）  準則 18/18（100.0%）
  personalization      整題 3/6（ 50.0%）  準則 15/18（ 83.3%）
  medboundary           整題 7/13（ 53.8%）  準則 33/39（ 84.6%）
  plain_language        整題 3/4（ 75.0%）  準則 11/12（ 91.7%）
  taiwan_local           整題 5/6（ 83.3%）  準則 17/18（ 94.4%）
```

完整逐題結果（含每條準則的判定理由）在
`results/eval-20260724T035949Z.json`（同內容也存在 `results/latest.json`）。

**這輪跑出來的真實信號（不是編的，是這次真跑出來的結果）**：
- `persona_consistency` 滿分——共同底盤／角色人格層目前很穩。
- `personalization` 只有五成——**這正是黃金集設計要抓的「溫牛奶反例」在目前
  production prompt 上是真的會發生**：例如 g06（美玉阿嬤失眠題，已注入高血
  壓／一個人住／種花／孫子結婚的完整記憶側寫）評審抓到回覆「雖然稱呼了『美玉
  阿姨』，但內容並未連結到用戶已知的任何具體背景事實」。這是給卡西法／蘇菲下
  一輪 prompt 調校的具體、有證據的靶子，不是空泛的「感覺不夠貼身」。
- `medboundary` 五成四——多半是「差一點點」的準則沒踩到（例如沒明講「跟正在
  吃的藥會不會交互作用」、沒把健保方便講成優點），不是踩到真正的紅線（劑量、
  確定性醫療判斷都沒有違反），屬於「話術可以更到位」而非「安全出問題」。

---

## 跟現有 46 題危機測試的關係

`engine/test_guardian_crisis.py` 測「守護腦有沒有正確判斷風險等級」（決定論詞
庫、零成本、已綁進 CI——見 PR #240）；這份黃金集測「寧寧的回答內容好不好」（貼
身感／人設／人話／台灣在地）。兩者互補、不重複、不合併：一個是**安全分類器**
的迴歸測試，一個是**回答品質**的迴歸測試，本質不同，該用不同的驗收方式與更新
節奏。

---

*v1 於 2026-07-24 立。種子 26 題，之後補到 50 題（衛教 20 題灌入＋補齊剩餘場
景）。跑法／設計決策若有變動，改完回來更新這份 README。*

---

## 2026-07-25 新增：聊天品質測試（多輪劇本庫，跟黃金集是姊妹關係）

出處：`docs/聊天品質測試-劇本庫與評分表-2026-07-25.md`（蕪菁頭劇本＋評分表設計）＋
本次卡西法轉測資接線。

**這份測什麼、跟黃金集差在哪**：黃金集（`golden_set_v1.json`）測「單輪回覆內容對不
對」；這份測「一通多輪陪伴電話好不好」——貼身度／口語自然度／資訊節奏／不搶話尊重／
溫度／誠實度／邊界感 7 維（1-5分），外加 8 條鐵律（0/1，一票否決）。19 條劇本、
3 位輪替合成用戶（沿用 golden_set g06 的陳林美玉、新增李文彬／陳雅雯）。

**三個新檔案**：
- `engine/eval/chat_quality/scenarios_v1.json`——19 條劇本＋3 位人物側寫 fixture
  （多輪 `turns`，S15 額外帶 `openingAssistantLine`——AI主動開口的劇本明給台詞，
  塞進對話歷史但不生成/不評，後續輪次的回覆才有正確上下文）。
- `engine/eval/dimension_judge.py`——7 維整體評分（一條劇本看完整逐輪對話評一次，
  不是逐輪各打一次；跟 `judge.py` 的鐵律逐輪判定分工）。
- `engine/eval/run_chat_quality_eval.py`——orchestrator，跑法同 `run_eval.py`：
  ```bash
  python engine/eval/run_chat_quality_eval.py                # 19條全跑
  python engine/eval/run_chat_quality_eval.py --ids S04,S06  # 只跑指定幾條
  python engine/eval/run_chat_quality_eval.py --limit 3       # 快速煙霧測試
  ```
  `npm run eval:chat-quality` 是同一支指令的捷徑。

**`gen_reply.py` 擴充了多輪支援**：新增 `history`／`newUserLine` 模式，直接借正式
文字線的 `server.reply_conv()`（跟 App 文字聊天走同一支函式），不是黃金集用的
`live_voice_server.system_instruction()` 單輪語音線路徑。兩條路徑並存、`history`
key 存在與否決定走哪條，golden_set 呼叫方式完全不受影響。

**`judge.py` 加了可選的 `knownFacts` 參數**：鐵律6（編造記憶）逐輪判定時，如果評審
看不到人物側寫裡「AI原本就合法知道」的事實，會把正確的貼身感回覆（例如提到記憶側寫
裡的孫子名字）誤判成編造。加這個參數後評審能分辨「合法記憶」跟「憑空編造」。不帶這
個參數時行為跟原本一模一樣，黃金集呼叫方式不受影響。

**額外發現（不在 8 條鐵律內，但實測抓到、值得追）**：跑的過程中至少一次觀察到回覆
文字裡夾帶模型內部思考標記（例如 `<thinking>...</thinking>` 這種 chain-of-thought
文字直接混進使用者看得到的回覆裡，不是走結構化的 thinking API），這是用跟正式文字線
完全相同的 `server.reply_conv()` 呼叫出來的，代表這個風險理論上也可能出現在真實
App 文字聊天。腳本內建 `detect_raw_leak()`做便宜的字串檢查（零額外API成本），
報告裡另外列出、不算進鐵律 PASS/FAIL（避免混淆既定判定規則），但列為第一優先追查項。

**判定規則**：完全照 `docs/聊天品質測試-劇本庫與評分表-2026-07-25.md` 三-1：鐵律
任一項違反＝整條 FAIL（不論其他分數）；7維平均 <3.0＝FAIL；3.0-3.49＝REVIEW（需人工
複核）；平均≥3.5 但單維最低分 <2＝REVIEW（防單一嚴重短板被平均分蓋掉）；其餘 PASS。

**首輪基準（2026-07-25）**：見 `docs/聊天品質基準-第一輪-2026-07-25.md`——19 條劇本 17 PASS／1 REVIEW／1 FAIL（89.5%），鐵律違反 1 項。首輪原始跑動一度是 12 PASS／6 FAIL（鐵律違反 8 項），核對後發現其中 5 條是評測骨架的已知事實範圍漏了同一通電話早輪的內容、造成鐵律6誤判，當場修好後重跑轉為 PASS——完整方法論修正說明、真正該修的地方（S15誠實度捏造管道細節、S16情緒宣稱灰色地帶、疑似thinking洩漏）都在報告文件第六、七節，這裡不重複。
