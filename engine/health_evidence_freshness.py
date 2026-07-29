# -*- coding: utf-8 -*-
"""保健品證據的保鮮期把關（2026-07-29）。

**為什麼這支存在**：方案池裡每一條保健品（L3）都寫了 `verifiedAt`——那是「我們最後
一次去查文獻是哪天」。但一直沒有任何東西在看那個日期。營養學的建議兩三年就會翻盤：
鎂那條引的是 2025 年的新試驗，明年可能就不是最新的說法了。過期的健康建議不會自己
壞掉、也不會報錯，它只會一直用篤定的語氣講下去——這是最難察覺、也最傷人的那種錯。

原本想掛定時任務去提醒，但 7/16 Edward 已經把定時任務全刪了。所以改成掛在出貨閘門上：
每次跑 test:launch 都順手算一次年紀。到期了會擋、快到期會念，不需要任何人記得。

兩道線：
  WARN（12 個月）  提醒該排重查了，不擋
  FAIL（18 個月）  擋下來——超過一年半沒查證的保健品建議，不該還在對長輩講

要展延不是改這裡的數字，是真的去把文獻重查一遍、更新 `evidence` 與 `verifiedAt`。
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
POOL_PATH = os.path.join(HERE, "health_solutions.json")

WARN_DAYS = 365          # 一年沒查＝該排進待辦
FAIL_DAYS = 365 + 182    # 一年半沒查＝擋出貨


def _load(path=None):
    with open(path or POOL_PATH, encoding="utf-8") as f:
        return json.load(f)


def audit(today=None, path=None):
    """回傳 (過期清單, 快到期清單, 沒寫日期清單)。每筆是 dict，方便直接印。"""
    today = today or datetime.date.today()
    doc = _load(path)
    expired, aging, undated = [], [], []
    for topic_id, topic in (doc.get("topics") or {}).items():
        for sol in topic.get("solutions") or []:
            if sol.get("riskLevel") != "L3":
                continue
            row = {"topicId": topic_id, "solutionId": sol.get("id"),
                   "label": sol.get("label"), "verifiedAt": sol.get("verifiedAt")}
            raw = sol.get("verifiedAt")
            try:
                checked = datetime.date.fromisoformat(str(raw))
            except (TypeError, ValueError):
                undated.append(row)
                continue
            row["ageDays"] = (today - checked).days
            if row["ageDays"] >= FAIL_DAYS:
                expired.append(row)
            elif row["ageDays"] >= WARN_DAYS:
                aging.append(row)
    key = lambda r: -r.get("ageDays", 0)
    return sorted(expired, key=key), sorted(aging, key=key), undated


def report(today=None, path=None):
    """印出人看得懂的結果。回傳 True＝可以出貨。"""
    expired, aging, undated = audit(today, path)
    if undated:
        print("⛔ 有保健品沒寫查證日期（不知道多久沒查＝當作沒查過）：")
        for r in undated:
            print("   %s / %s（%s）" % (r["topicId"], r["solutionId"], r["label"]))
    if expired:
        print("⛔ 這些保健品建議超過一年半沒重查文獻，不該還在對長輩講：")
        for r in expired:
            print("   %s / %s（%s）最後查證 %s、已經 %d 天"
                  % (r["topicId"], r["solutionId"], r["label"], r["verifiedAt"], r["ageDays"]))
        print("   要解掉不是改門檻，是真的去重查一遍、更新 evidence 與 verifiedAt。")
    if aging:
        print("⚠ 這些快滿一年了，該排進待辦（先不擋）：")
        for r in aging:
            print("   %s / %s（%s）最後查證 %s、已經 %d 天"
                  % (r["topicId"], r["solutionId"], r["label"], r["verifiedAt"], r["ageDays"]))
    if len(expired) + len(aging) >= 5:
        # 這批是同一天一起建的，所以會同一天一起到期。真的排重查時順手把日期錯開，
        # 不然每隔一年半就會有一天「全部一起紅」，那時候誰都不想動。
        print("   （這幾條到期日擠在一起——重查時順手把日期錯開，別讓下次又一次全紅）")
    ok = not (expired or undated)
    if ok and not aging:
        print("✅ 保健品證據全部在保鮮期內")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if report() else 1)
