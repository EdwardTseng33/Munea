"""就診摘要（M1 · F2/F3）測試。

這份東西會被遞到醫師手上，所以測的不只是「有沒有算對」，更是「會不會誤導」：
  · 來源有沒有標清楚（自述 vs 機器量的，可信度天差地遠）
  · 有沒有出現任何判定字眼（偏高／異常／建議）＝紅線，出現就是把我們推向醫材認定
  · 截斷有沒有誠實回報（悄悄截斷 → 醫師以為這就是全部）
  · 沒資料時會不會生一份看起來很豐富的假摘要

跑法：python3 engine/test_visit_summary.py
"""

import datetime
import unittest

import visit_summary


TODAY = datetime.date(2026, 7, 28)


def day(offset):
    """offset 天前的 YYYY-MM-DD。"""
    return (TODAY - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")


def memory(content, offset, confidence=0.9, mtype="health_context"):
    return {
        "type": mtype, "content": content, "confidence": confidence,
        "createdAt": day(offset) + "T09:00:00Z",
    }


def dose(name, offset, status):
    return {"medName": name, "scheduledDate": day(offset), "status": status}


def steady_log(days=30, **fields):
    """一段平穩的量測紀錄，用來當基線。"""
    base = {"bpSys": 128, "bpDia": 80, "hr": 72, "sleepHours": 6.8}
    base.update(fields)
    return {day(i): dict(base) for i in range(1, days + 1)}


class PeriodTest(unittest.TestCase):
    def test_only_four_options_accepted(self):
        for period in visit_summary.PERIOD_DAYS:
            self.assertEqual(visit_summary.build(period, today=TODAY)["periodDays"], period)

    def test_bogus_period_falls_back_instead_of_crashing(self):
        # 前端傳來壞值不該炸掉，也不該默默給一個誰也不知道多長的期間
        for bogus in (0, -5, 999, "abc", None):
            self.assertEqual(
                visit_summary.build(bogus, today=TODAY)["periodDays"],
                visit_summary.DEFAULT_PERIOD,
            )

    def test_bounds_are_inclusive_of_today(self):
        start, end = visit_summary.period_bounds(7, TODAY)
        self.assertEqual(end, TODAY)
        self.assertEqual((end - start).days, 6, "7 天應含今天共 7 天，不是 8 天")


class SymptomTest(unittest.TestCase):
    def test_symptom_text_is_verbatim_not_rewritten(self):
        # 改寫＝替長輩發言。醫師看到的必須是他自己講的話。
        said = "上下樓梯會卡住還有聲音"
        out = visit_summary.build(14, memories=[memory(said, 3)], today=TODAY)
        row = [e for e in out["timeline"] if e["kind"] == "symptom"][0]
        self.assertEqual(row["text"], said)

    def test_symptom_marked_as_self_reported(self):
        out = visit_summary.build(14, memories=[memory("膝蓋痠", 3)], today=TODAY)
        row = [e for e in out["timeline"] if e["kind"] == "symptom"][0]
        self.assertEqual(row["source"], "長輩自己說的",
                         "自述沒標來源＝拿 AI 聽到的話冒充臨床事實")

    def test_low_confidence_extraction_dropped(self):
        # AI 沒把握的句子不該遞到醫師面前
        out = visit_summary.build(14, memories=[memory("好像有點喘", 3, confidence=0.3)], today=TODAY)
        self.assertEqual(out["timeline"], [])

    def test_non_health_memories_never_leak_in(self):
        # 「喜歡看歌仔戲」是記憶，但不是就診資料。混進去等於洩漏無關的私事給醫師。
        noise = [
            memory("喜歡看歌仔戲", 3, mtype="topic_interest"),
            memory("孫子叫小宇", 3, mtype="relationship"),
            memory("心情有點低落", 3, mtype="emotion"),
        ]
        out = visit_summary.build(14, memories=noise, today=TODAY)
        self.assertEqual(out["timeline"], [])

    def test_outside_period_excluded(self):
        out = visit_summary.build(7, memories=[memory("三週前的事", 20)], today=TODAY)
        self.assertEqual(out["timeline"], [])
        out30 = visit_summary.build(30, memories=[memory("三週前的事", 20)], today=TODAY)
        self.assertEqual(len(out30["timeline"]), 1)

    def test_broken_timestamps_do_not_crash(self):
        junk = [
            {"type": "health_context", "content": "沒有時間", "confidence": 0.9},
            {"type": "health_context", "content": "壞時間", "confidence": 0.9, "createdAt": "not-a-date"},
            {"type": "health_context", "content": "", "confidence": 0.9, "createdAt": day(1)},
            "not-a-dict",
        ]
        out = visit_summary.build(14, memories=junk, today=TODAY)
        self.assertEqual(out["timeline"], [])


class VitalTest(unittest.TestCase):
    def test_deviation_day_appears_with_own_baseline(self):
        log = steady_log()
        log[day(3)] = {"bpSys": 158, "bpDia": 95}
        out = visit_summary.build(14, health_log=log, today=TODAY)
        rows = [e for e in out["timeline"] if e["kind"] == "vital"]
        self.assertTrue(rows, "偏離平常的那天應該出現在時間軸")
        self.assertEqual(rows[0]["date"], day(3), "必須帶時間點，醫師要知道哪天")
        self.assertIn("158/95", rows[0]["text"])
        self.assertIn("平常", rows[0]["detail"], "只給當天數字而不給他自己的平常＝沒有比較基準")

    def test_steady_days_do_not_flood_the_page(self):
        # 每天都正常就不該有任何一天被挑出來，否則一頁會被灌爆
        out = visit_summary.build(14, health_log=steady_log(), today=TODAY)
        self.assertEqual([e for e in out["timeline"] if e["kind"] == "vital"], [])

    def test_baseline_note_always_present(self):
        # 60 天的摘要裡「平常」仍是近兩週的平常——不標會讓醫師誤以為是整段平均
        out = visit_summary.build(60, health_log=steady_log(), today=TODAY)
        self.assertIn("14", out["baselineNote"])
        self.assertIn("不做任何醫學比對", out["baselineNote"])


class MedicationTest(unittest.TestCase):
    def test_counts_whole_period_not_just_today(self):
        # 14 天的視窗＝今天(offset 0)往前數 13 天，所以 offset 0..13 才在窗內。
        # 用 1..14 會有一筆掉出去——這正是邊界該被測到的地方。
        doses = [dose("降血壓藥", i, "taken") for i in range(0, 10)]
        doses += [dose("降血壓藥", i, "missed") for i in range(10, 14)]
        doses += [dose("降血壓藥", 14, "taken")]  # 窗外一筆，不該被算進去
        out = visit_summary.build(14, doses=doses, today=TODAY)
        row = out["medication"][0]
        self.assertEqual((row["scheduled"], row["taken"], row["missed"]), (14, 10, 4))

    def test_no_adherence_percentage(self):
        # 百分比看起來像評分，評分是判定。只給次數。
        doses = [dose("藥", i, "taken") for i in range(1, 8)]
        out = visit_summary.build(7, doses=doses, today=TODAY)
        self.assertNotIn("rate", out["medication"][0])
        self.assertNotIn("adherence", out["medication"][0])

    def test_occasional_miss_stays_out_of_timeline(self):
        doses = [dose("藥", i, "taken") for i in range(1, 7)] + [dose("藥", 7, "missed")]
        out = visit_summary.build(7, doses=doses, today=TODAY)
        self.assertEqual([e for e in out["timeline"] if e["kind"] == "med"], [],
                         "偶爾漏一次是常態，不該占用一頁的位置")

    def test_repeated_misses_surface(self):
        doses = [dose("止痛藥", i, "missed") for i in range(1, 6)]
        out = visit_summary.build(7, doses=doses, today=TODAY)
        rows = [e for e in out["timeline"] if e["kind"] == "med"]
        self.assertEqual(len(rows), 1)
        self.assertIn("5 次", rows[0]["text"])


class OnePageTest(unittest.TestCase):
    def test_cap_and_honest_disclosure(self):
        many = [memory(f"第{i}件事情發生了", i) for i in range(1, 26)]
        out = visit_summary.build(30, memories=many, today=TODAY)
        self.assertEqual(len(out["timeline"]), visit_summary.MAX_TIMELINE)
        self.assertEqual(out["timelineOmitted"], 25 - visit_summary.MAX_TIMELINE,
                         "被截掉的筆數必須誠實回報，不能悄悄消失")

    def test_symptoms_win_the_scarce_slots(self):
        # 血壓數字長輩自己看得到；症狀是醫師問不出來的東西，稀缺位置留給它
        log = steady_log()
        for i in range(1, 21):
            log[day(i)] = {"bpSys": 158, "bpDia": 95}
        memories = [memory(f"第{i}個症狀變化", i) for i in range(1, 6)]
        out = visit_summary.build(30, memories=memories, health_log=log, today=TODAY)
        kinds = [e["kind"] for e in out["timeline"]]
        self.assertEqual(kinds.count("symptom"), 5, "症狀不該被大量量測資料擠掉")

    def test_timeline_displayed_in_date_order(self):
        memories = [memory(f"事件{i}", i) for i in (1, 9, 4, 12, 2)]
        out = visit_summary.build(14, memories=memories, today=TODAY)
        dates = [e["date"] for e in out["timeline"]]
        self.assertEqual(dates, sorted(dates), "挑選之後要按日期排回去，醫師是照時間讀的")


class RedLineTest(unittest.TestCase):
    """紅線：這份東西不可以有任何一個字像醫療判斷。"""

    FORBIDDEN = [
        "偏高", "偏低", "過高", "過低", "異常", "不正常", "需注意", "警告", "危險",
        "建議就醫", "可能是", "導致", "引起", "因為", "相關", "疑似", "診斷", "評估",
        "正常值", "標準值", "嚴重",
    ]

    def _all_text(self, summary):
        parts = [summary.get("baselineNote", "")]
        for event in summary["timeline"]:
            parts += [event.get("text", ""), event.get("detail", ""), event.get("source", "")]
        for row in summary["medication"]:
            parts.append(row.get("name", ""))
        parts += list(summary.get("vitals", []))
        return "".join(parts)

    def test_no_judgement_words_anywhere(self):
        log = steady_log()
        log[day(2)] = {"bpSys": 168, "bpDia": 101, "hr": 110, "sleepHours": 3.0}
        summary = visit_summary.build(
            30,
            memories=[memory("胸口悶而且會喘", 2), memory("膝蓋痛到走不動", 5)],
            health_log=log,
            doses=[dose("止痛藥", i, "missed") for i in range(1, 8)],
            today=TODAY,
        )
        text = self._all_text(summary)
        for word in self.FORBIDDEN:
            self.assertNotIn(word, text, f"摘要出現判定字眼「{word}」＝越過醫材紅線")

    def test_same_day_events_are_listed_not_linked(self):
        # 同一天的症狀與數據只能並排，不可連成因果——並列是事實，連線是判讀
        log = steady_log()
        log[day(3)] = {"bpSys": 165, "bpDia": 99}
        summary = visit_summary.build(
            14, memories=[memory("那天特別頭暈", 3)], health_log=log, today=TODAY,
        )
        same_day = [e for e in summary["timeline"] if e["date"] == day(3)]
        self.assertEqual(len(same_day), 2, "兩件事都要在")
        self.assertEqual({e["kind"] for e in same_day}, {"symptom", "vital"})
        for event in same_day:
            self.assertNotIn("因", event["text"] + event["detail"])


class EmptyStateTest(unittest.TestCase):
    def test_no_data_reports_empty_instead_of_inventing(self):
        out = visit_summary.build(14, today=TODAY)
        self.assertFalse(out["hasData"], "沒資料就要誠實說沒有，不生一份看起來很豐富的假摘要")
        self.assertEqual(out["timeline"], [])
        self.assertEqual(out["medication"], [])

    def test_period_is_always_stated_even_when_empty(self):
        # 邊界要印在紙上，醫師才知道這份涵蓋到哪、該追問什麼
        out = visit_summary.build(60, today=TODAY)
        self.assertEqual(out["to"], "2026-07-28")
        self.assertEqual(out["from"], "2026-05-30")


if __name__ == "__main__":
    unittest.main(verbosity=2)
