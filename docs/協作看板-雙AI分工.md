# 沐寧 Munea · 雙 AI 協作看板

> 目的：Claude/城堡與 Codex 可能同時協作同一個 repo。這份看板不是限制誰只能做哪一塊，而是避免兩邊重複開發、覆蓋檔案、或讓產品決策漂移。
> 動手前先讀這頁 + `docs/00-總綱-從這裡開始.md`，並更新下方「現在誰在做什麼」。

---

## 協作原則

| 原則 | 說明 |
|---|---|
| SSOT 優先 | 任何產品/技術調整先對齊 `docs/00-總綱-從這裡開始.md`，再讀該主題權威文件。 |
| 任務先登記 | 開發前在看板填寫自己正在做的任務、預計動到的檔案、狀態。 |
| 檔案要避讓 | 若對方正在改同一檔，先等對方推完或明確拆分段落。 |
| 小步提交 | 每批改動要小、可讀、可驗證，完成後盡快 commit/push。 |
| 不 force push | 不用覆蓋式上傳，不重置對方提交，不刪對方未確認的內容。 |
| 文件要回寫 | 產品邏輯、AI 架構、帳務、資料庫、上架策略有變動時，同步回寫權威文件與 `STATUS.md`。 |

---

## 角色定位

| 協作者 | 可負責範圍 | 特別注意 |
|---|---|---|
| Claude / 城堡 | 產品規格、後端、資料、安全、AI 服務設計、測試、文件盤點、程式開發 | 若整理文件或調整架構，需保持 SSOT 清楚，不新增互相打架的規格。 |
| Codex | CTO/技術設計師、全端開發、App/UIUX、AI 串接、Avatar/runtime、資料與 API、文件落檔、GitHub 同步 | 不被限制在單一模組；但每次動手前要遵守看板登記與小步推進。 |

---

## 現在誰在做什麼

| 誰 | 在做什麼 | 預計動到哪些檔 | 開始時間 | 狀態 |
|---|---|---|---|---|
| Claude / 城堡 | #10 危機偵測行為測試（`engine/test_guardian_crisis.py` 20/20 過）＋ #5 子女授權 RLS 設計與待決文件 | `engine/test_guardian_crisis.py`、`docs/RLS-子女授權同意分層-設計與待決-2026-07-01.md`、排程、本看板 | 2026-07-01 | ✅ 完成、本次推 GitHub。#5 卡 Edward 決定（可見度預設偏向）+ 跟 Codex 對 schema |
| Codex | 健檢修復排程 P0-4：正式模式下點數/訂閱改帳防偽造，分離 Bearer 使用者 auth、Admin token、Provider webhook token，並寫入 audit | `engine/server.py`、`engine/supabase_adapter.py`、`docs/BACKEND-ARCHITECTURE-v1.md`、`docs/BILLING-CREDITS-ENTITLEMENT-v1.md`、`docs/健檢修復排程-2026-07-01.md`、`STATUS.md`、`scripts/smoke.ps1` | 2026-07-01 | 完成，待推 GitHub |

> 📋 **開發排程**見 [健檢修復排程-2026-07-01](健檢修復排程-2026-07-01.md)（健檢三方發現的問題已排 P0/P1/核心＋認領欄）。**認領前先看、避免重複。**
>
> 💬 **同步紀錄（2026-07-01 · Codex）**：usage/credits admin API 已由 `b291a6d` 推上 GitHub；城堡本次 Guardian 中文危機詞庫由 Codex 接手同步提交，避免本機與 repo 漂移。
>
> 💬 **給城堡自己 & Codex**：健檢排程 P0 還有「後端全端點驗身份、點數搬 Supabase、子女授權 RLS」跟你正在做的 usage/credits admin 高度相關——認領這幾項前先看排程 #3#4#5，順著你的後台一起做最省、別各做一半。

---

## 常用開工流程

1. 先同步最新版：`git pull --rebase`。
2. 讀 `docs/00-總綱-從這裡開始.md` 與本次任務相關權威文件。
3. 在本看板登記任務與檔案範圍。
4. 小步開發，避免一次跨太多主題。
5. 跑可用的檢查；若環境不能跑完整測試，需在回報中明確說明。
6. 更新 `STATUS.md`、`CURRENT-DEVELOPMENT-PLAN.md` 或對應權威文件。
7. commit/push，回報 commit hash 與下一步。

---

## 衝突處理

- 若 Git 顯示同一檔衝突，不直接覆蓋，先保留雙方意圖再合併。
- 若產品方向衝突，以 Edward 最新明確決策為最高優先，再回寫 SSOT。
- 若文件與程式衝突，以目前已實作且已推上 main 的程式行為為事實基準，再補文件。
- 若涉及帳務、醫療安全、個資、App Store 上架風險，先收斂架構與風險，再進功能開發。
