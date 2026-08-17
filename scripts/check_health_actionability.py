#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""她講得出「做法」嗎（2026-08-13 立為常設量尺）。

**為什麼要有這支**：Edward 的原話是「不要講什麼內容都叫別人去看醫生 ＝ 無用 AI」。
這件事一直在量，但每次都是臨時寫的小工具——同一天量出來 40%、53%、52% 三個數字，
因為每支的判準都不一樣。這支把判準寫死、變成唯一的正本，之後只引用它。

判準（只有兩條，寫在這裡就是為了不再各講各的）：

  **有具體做法** ＝ 這張卡講得出「今天照著做」的東西：
      有數字＋單位（三份、20 分鐘、一天兩次、15 公分）
      或有明確的動作指令（每天、每餐、改成、換成、先從、第一件事、步驟）

  **只把人推走** ＝ 這張卡是「我不能建議」類（blocked 或 L4），
      而且**通篇沒有交代他現在可以做什麼**——連「這幾件不用問任何人」都沒有。
      這是我們要清零的東西。拒絕本身不是問題，拒絕之後兩手一攤才是。

轉介卡（L5）不算在內——那張的工作本來就是把人送去該去的地方。

用法：
    python scripts/check_health_actionability.py             # 總表
    python scripts/check_health_actionability.py --topics    # 每題一行
    python scripts/check_health_actionability.py --list      # 列出只推走的卡
    python scripts/check_health_actionability.py --min 45    # 有做法低於幾成就算不合格
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "engine")

# 數字＋單位，或明確的動作指令。兩者都沒有＝這張卡沒有給他能照做的東西。
DOABLE = re.compile(
    r"[0-9０-９一二三四五六七八九十兩半]+\s*(份|杯|顆|粒|克|毫克|公分|cc|毫升|"
    r"分鐘|小時|次|天|秒|週|個月|禮拜|步|句|件|樣|種)"
    r"|每天|每餐|每週|每晚|改成|換成|先從|第一件|第二件|第一句|步驟|照著做"
)
# 就算沒有數字，只要有交代「你現在可以做什麼」，就不算兩手一攤。
# 2026-08-13 補：第一版漏掉「我可以幫你…」「把藥裝一袋帶去」「問這四句」這幾種寫法，
# 把五張其實已經交代得很清楚的卡誤判成兩手一攤——量尺自己先量錯，比沒量還糟。
HANDS_OVER = re.compile(
    r"不用問|可以做的|能做的|先做|這幾件|下面這|你能|你可以|做得到|"
    r"帶去問|帶去給|帶著|裝一袋|這樣問|問對|問這|問三|問四|記在紙上|寫下來|"
    r"我可以幫你|有人可以|可以去問|回報實在|去問"
)


def load():
    with io.open(os.path.join(ENGINE, "health_solutions.json"), encoding="utf-8") as f:
        return json.load(f)["topics"]


def classify(sol):
    """回傳 (算不算在分母, 有沒有做法, 是不是只把人推走)。"""
    if sol.get("riskLevel") == "L5":
        return False, False, False
    say = sol.get("say") or ""
    doable = bool(DOABLE.search(say))
    refusal = bool(sol.get("blocked")) or sol.get("riskLevel") == "L4"
    deflect = refusal and not doable and not HANDS_OVER.search(say)
    return True, doable, deflect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", action="store_true", help="每題一行")
    ap.add_argument("--list", action="store_true", help="列出只把人推走的卡")
    ap.add_argument("--min", type=int, default=45, help="有做法的比例低於幾成就算不合格")
    ap.add_argument("--max-deflect", type=int, default=0,
                    help="允許幾張『拒絕之後兩手一攤』的卡（2026-08-13 起清零，預設 0）")
    args = ap.parse_args()

    topics = load()
    tot = act = defl = 0
    rows, bad_cards = [], []
    for tid in sorted(topics):
        v = topics[tid]
        t_tot = t_act = t_defl = 0
        for s in v["solutions"]:
            counted, doable, deflect = classify(s)
            if not counted:
                continue
            t_tot += 1
            t_act += doable
            t_defl += deflect
            if deflect:
                bad_cards.append((tid, s["id"], s.get("label", "")))
        tot += t_tot
        act += t_act
        defl += t_defl
        rows.append((tid, v["title"], t_tot, t_act, t_defl))

    if args.topics:
        for tid, title, n, a, dfl in rows:
            mark = "  " if a * 2 >= n else "⚠ "
            print(f"{mark}{tid} {title[:18]:<20} {n:>3} 張｜有做法 {a:>3}｜只推走 {dfl}")
        print()

    if args.list and bad_cards:
        print("只把人推走的卡（拒絕之後沒交代他能做什麼）：")
        for tid, sid, label in bad_cards:
            print(f"  {tid} {sid}　{label}")
        print()

    pct = act * 100 // tot if tot else 0
    print(f"全庫（不含轉介卡）：{tot} 張")
    print(f"  有具體做法　{act} 張（{pct}%）")
    print(f"  只把人推走　{defl} 張（{defl * 100 // tot if tot else 0}%）")
    print(f"  題數　{len(topics)}")
    failed = False
    if pct < args.min:
        print(f"⛔ 有做法的比例低於 {args.min}%——這是「無用 AI」的方向")
        failed = True
    if defl > args.max_deflect:
        # 2026-08-13 清零：拒絕本身不是問題，拒絕之後兩手一攤才是。
        # 新加的卡如果又只會說「我不能建議」，這裡會擋下來（用 --list 看是哪張）。
        print(f"⛔ 有 {defl} 張卡拒絕之後沒交代他能做什麼（上限 {args.max_deflect}）")
        failed = True
    if failed:
        return 1
    print("✅ 過關")
    return 0


if __name__ == "__main__":
    sys.exit(main())
