# -*- coding: utf-8 -*-
"""AI 看得到健康數據 · 防線測試（2026-07-17 · Edward 拍板檔位 2「知道但不多嘴」）

守的線：
  一、沒資料時她必須知道自己不知道——這條最重要。在這之前她的說明書每一輪都
      寫著「你看得到健康告警」、實際上一個數字都到不了她面前，結果就是憑空編一句
      「你今天血壓有點高喔」。沒資料 → 圍籬必須明講「你什麼都看不到、不准編」。
  二、跟自己比、不跟量表比：只有他自己的數字，沒有正常值、沒有分數、沒有紅黃綠燈。
  三、講事實、不講判定：產出的事實裡絕不能出現「偏高」「異常」這種醫生才能說的話。
  四、檔位 2：資料給她、但明令不主動報數字、不主動報警。
  五、雜訊地板不是醫學閾值：差一點點不吵她、差很多才標「跟平常不一樣」。

跑法：python engine/test_health_context.py（純算、不需網路/鑰匙/資料庫）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import health_context as hc  # noqa: E402

FAILS = []


def check(name, cond):
    print(("  OK  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def _log(days):
    """{'2026-07-01': {...}} 造一本健康帳本。"""
    return dict(days)


def _steady_log(field, value, n=20, start_day=1):
    """n 天都同一個值 → 拿來當「他自己平常」。"""
    return {f"2026-06-{start_day + i:02d}": {field: value} for i in range(n)}


# ---- 一、沒資料 = 她必須知道自己不知道（最重要的一條）----
def test_no_data_fence():
    ctx = hc.build(vitals_entry=None, doses=None, mood_trend=None, today="2026-07-17")
    check("沒資料：hasData=False", ctx["hasData"] is False)
    check("沒資料：facts 是空的", ctx["facts"] == [])

    block = hc.instruction_block(ctx)
    check("沒資料：圍籬明講『什麼都看不到』", "什麼都看不到" in block)
    check("沒資料：圍籬禁止編數字", "不要講任何他的健康數字" in block)
    check("沒資料：圍籬點名那句會編的話", "血壓有點高" in block)
    check("沒資料：圍籬給了替代動作（想知道就問他）", "問他" in block)

    # 空帳本、空用藥也一樣要退回圍籬（不是只有 None 才算沒資料）
    empty = hc.build(vitals_entry={"log": {}}, doses=[], mood_trend={}, today="2026-07-17")
    check("空帳本：一樣退回圍籬", empty["hasData"] is False)


# ---- 二、有資料 = 事實 + 他自己的平常 ----
def test_bp_facts():
    log = _steady_log("bpSys", 128, n=18)
    for d in log:
        log[d]["bpDia"] = 80
    log["2026-07-17"] = {"bpSys": 158, "bpDia": 92}   # 今天這筆明顯跟平常不一樣

    ctx = hc.build(vitals_entry={"log": log}, today="2026-07-17")
    facts = "\n".join(ctx["facts"])
    check("血壓：講得出最近一次的真數字", "158/92" in facts)
    check("血壓：講得出他自己平常的數字", "128/80" in facts)
    check("血壓：跟平常差很多 → 標 notable", "bpSys" in ctx["notable"])


def _bp_log(sys_v, dia_v, n=18):
    log = _steady_log("bpSys", sys_v, n=n)
    for d in log:
        log[d]["bpDia"] = dia_v
    return log


def test_baseline_is_personal_not_scale():
    """跟自己比：同一個數字，對平常低的人是『不一樣』、對平常就這樣的人是『沒事』。

    這一組是整支的核心——它證明我們沒有偷偷用量表。同樣是 158/92：
    平常就這樣的人不吵他，平常 118/75 的人才標。
    """
    high_normal = _bp_log(155, 90)                    # 這個人平常就 155/90
    high_normal["2026-07-17"] = {"bpSys": 158, "bpDia": 92}
    ctx_high = hc.build(vitals_entry={"log": high_normal}, today="2026-07-17")
    check("平常就 155/90 的人，今天 158/92 → 不標 notable（跟自己比、不跟量表比）",
          "bpSys" not in ctx_high["notable"])
    check("（但事實照樣講得出來、沒被整段跳過）", "158/92" in "\n".join(ctx_high["facts"]))

    low_normal = _bp_log(118, 75)                     # 這個人平常 118/75
    low_normal["2026-07-17"] = {"bpSys": 158, "bpDia": 92}
    ctx_low = hc.build(vitals_entry={"log": low_normal}, today="2026-07-17")
    check("平常 118/75 的人，今天 158/92 → 標 notable", "bpSys" in ctx_low["notable"])


def test_noise_floor():
    log = _steady_log("hr", 72, n=18)
    log["2026-07-17"] = {"hr": 75}                    # 差 3 下＝雜訊、不值得吵她
    ctx = hc.build(vitals_entry={"log": log}, today="2026-07-17")
    check("心跳差 3 下 → 不標（雜訊地板）", "hr" not in ctx["notable"])

    log2 = _steady_log("hr", 72, n=18)
    log2["2026-07-17"] = {"hr": 95}                   # 差 23 下＝值得她知道
    ctx2 = hc.build(vitals_entry={"log": log2}, today="2026-07-17")
    check("心跳差 23 下 → 標 notable", "hr" in ctx2["notable"])


def test_baseline_not_faked_when_thin():
    """資料不夠就不硬湊一個『平常』出來。

    兩種「不夠」要分開測，不然會有一條是裝飾品：
      a. 天數少到連「最近 3 天」都排不掉 → 前面那道就擋了
      b. 排得掉、但剩下的天數太少（剛裝 App 的新用戶就長這樣）→ 靠 MIN_BASELINE_DAYS 擋
    b 才是真正在用的那道。
    """
    # a. 只有兩天
    thin = {"2026-07-16": {"bpSys": 130, "bpDia": 80}, "2026-07-17": {"bpSys": 158, "bpDia": 92}}
    baseline, _ = hc.baseline_and_recent(thin, "bpSys")
    check("只有兩天資料 → 沒有『平常』（不硬湊）", baseline is None)

    ctx = hc.build(vitals_entry={"log": thin}, today="2026-07-17")
    facts = "\n".join(ctx["facts"])
    check("資料不夠：還是講得出今天的事實", "158/92" in facts)
    check("資料不夠：不假裝知道他平常多少", "平常" not in facts)
    check("資料不夠：不亂標 notable", ctx["notable"] == [])

    # b. 六天：排掉最近 3 天還剩 3 天——排得掉、但不夠算「平常」（剛裝 App 的新用戶）
    six = {f"2026-07-{11 + i:02d}": {"bpSys": 120, "bpDia": 78} for i in range(6)}
    baseline_six, _ = hc.baseline_and_recent(six, "bpSys")
    check("只有六天（排掉最近 3 天剩 3 天）→ 還是不算『平常』", baseline_six is None)

    ctx_six = hc.build(vitals_entry={"log": six}, today="2026-07-16")
    check("新用戶：不假裝知道他平常多少", "平常" not in "\n".join(ctx_six["facts"]))
    check("新用戶：不亂標 notable", ctx_six["notable"] == [])

    # 對照組：夠了就要算得出來（不然上面兩條可能只是永遠回 None 的假通過）
    enough = {f"2026-06-{d:02d}": {"bpSys": 120, "bpDia": 78} for d in range(1, 12)}
    baseline_enough, _ = hc.baseline_and_recent(enough, "bpSys")
    check("對照組：資料夠了就算得出『平常』（證明不是永遠回空）", baseline_enough == 120)


def test_sleep_and_stale_reading():
    log = _steady_log("sleepHours", 7.2, n=18)
    log["2026-07-15"] = {"sleepHours": 4.5}
    ctx = hc.build(vitals_entry={"log": log}, today="2026-07-17")
    facts = "\n".join(ctx["facts"])
    check("睡眠：講得出小時數", "4.5 小時" in facts)
    check("舊資料要標日期（今天沒量就別講得像今天）", "2026-07-15" in facts)


# ---- 三、用藥 ----
def test_medication():
    doses = [
        {"scheduledDate": "2026-07-17", "status": "taken", "slotLabel": "早上"},
        {"scheduledDate": "2026-07-17", "status": "taken", "slotLabel": "中午"},
        {"scheduledDate": "2026-07-17", "status": "scheduled", "slotLabel": "晚上"},
        {"scheduledDate": "2026-07-16", "status": "missed", "slotLabel": "晚上"},   # 昨天的、不該混進來
    ]
    line = hc.summarize_medication(doses, "2026-07-17")
    check("用藥：算對今天排幾次（3 次、不含昨天）", "排了 3 次" in line)
    check("用藥：算對吃了幾次", "吃了 2 次" in line)
    check("用藥：講得出還沒到時間的那次", "晚上" in line)

    check("今天沒排藥 → 不講（不無中生有）", hc.summarize_medication([], "2026-07-17") == "")


def test_medication_missed():
    doses = [
        {"scheduledDate": "2026-07-17", "status": "taken", "slotLabel": "早上"},
        {"scheduledDate": "2026-07-17", "status": "missed", "slotLabel": "中午"},
    ]
    line = hc.summarize_medication(doses, "2026-07-17")
    check("用藥：沒吃的那次講得出來", "1 次沒吃" in line)


# ---- 四、心情用已經算好的那條、不重算 ----
def test_mood_reuses_existing_trend():
    trend = {"baseline": 3.4, "recent": 2.4, "gentleConcern": True}
    ctx = hc.build(vitals_entry={"log": {}}, mood_trend=trend, today="2026-07-17")
    facts = "\n".join(ctx["facts"])
    check("心情：接得到已經算好的趨勢", "安靜" in facts)
    check("心情：掉下來 → 標 notable", "mood" in ctx["notable"])
    check("心情：給的是觀察、不是裸分數（心情系統鐵律：絕無 0-100 分數）",
          "2.4" not in facts and "3.4" not in facts)
    check("心情：明講跟自己比、不代表有事",
          "跟他自己比" in facts and "不代表有事" in facts)

    # 沒掉下來 → 講「差不多」、不標（她知道就好、不用提）
    steady = {"baseline": 3.4, "recent": 3.3, "gentleConcern": False}
    ctx2 = hc.build(vitals_entry={"log": {}}, mood_trend=steady, today="2026-07-17")
    check("心情平穩 → 講『跟平常差不多』、不標 notable",
          "差不多" in "\n".join(ctx2["facts"]) and "mood" not in ctx2["notable"])


# ---- 五、鐵律：事實裡不准有判定、不准有分數 ----
JUDGEMENT_WORDS = ["偏高", "偏低", "過高", "過低", "異常", "不正常", "有問題", "危險",
                   "正常範圍", "標準值", "警告", "高血壓", "低血壓", "憂鬱", "焦慮", "失智"]


def test_no_clinical_judgement_in_facts():
    log = _steady_log("bpSys", 118, n=18)
    for d in log:
        log[d]["bpDia"] = 75
        log[d]["spo2"] = 97
    log["2026-07-17"] = {"bpSys": 185, "bpDia": 110, "spo2": 88}   # 很誇張的數字
    ctx = hc.build(
        vitals_entry={"log": log},
        doses=[{"scheduledDate": "2026-07-17", "status": "missed", "slotLabel": "早上"}],
        mood_trend={"baseline": 3.5, "recent": 1.8, "gentleConcern": True},
        today="2026-07-17",
    )
    facts = "\n".join(ctx["facts"])
    hits = [w for w in JUDGEMENT_WORDS if w in facts]
    check("再誇張的數字，事實裡也不做判定（不出現「偏高」「異常」等）", not hits)
    if hits:
        print("      踩到的字：" + "、".join(hits))
    check("心情不給裸分數（心情系統鐵律：絕無 0-100 分數）",
          "1.8" not in facts and "3.5" not in facts)
    check("很誇張的數字照樣只是事實", "185/110" in facts)


# ---- 六、檔位 2：資料給她、但不准多嘴 ----
def test_gear_two_rules_in_block():
    log = _steady_log("bpSys", 118, n=18)
    for d in log:
        log[d]["bpDia"] = 75
    log["2026-07-17"] = {"bpSys": 158, "bpDia": 92}
    ctx = hc.build(vitals_entry={"log": log}, today="2026-07-17")
    block = hc.instruction_block(ctx)

    check("檔位 2：明講不要主動報數字", "不要一開口就報數字" in block)
    check("檔位 2：明講不主動報警", "不要主動報警" in block)
    check("檔位 2：明講告警是家人的活、不是她的", "家人在看" in block)
    check("檔位 2：他問就答", "他問就照實講" in block)
    check("圍籬：只講上面有的、沒有的不准補", "只講上面有的" in block)
    check("圍籬：不准做評判（那是醫生的事）", "醫生的事" in block)
    check("跟平常不一樣時，明講『這不代表有問題』", "不代表有問題" in block)
    check("說明書不夾英文詞（她的鐵律）",
          not any(c.isascii() and c.isalpha() for c in block))


def main():
    test_no_data_fence()
    test_bp_facts()
    test_baseline_is_personal_not_scale()
    test_noise_floor()
    test_baseline_not_faked_when_thin()
    test_sleep_and_stale_reading()
    test_medication()
    test_medication_missed()
    test_mood_reuses_existing_trend()
    test_no_clinical_judgement_in_facts()
    test_gear_two_rules_in_block()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 項未過：" + "、".join(FAILS))
        sys.exit(1)
    print("✅ 健康脈絡防線全過（沒資料不編、跟自己比、只講事實、檔位 2 不多嘴）")


if __name__ == "__main__":
    main()
