#!/usr/bin/env python3
"""效果飛輪契約（2026-07-29）。

**為什麼這支存在**：21 題衛教劇本每一題都寫了「幾天後回訪」，但程式一行都沒實作——
她推薦完就結束了，同一個人問第二次拿到的還是一模一樣的三個方案。
「陪伴即追蹤」是護城河，這支守住它真的在轉：

    推薦 → 記下來 → 到期主動問 → 記效果 → 下次挑選時用得上

釘住的是**程式層**行為（確定性、不會今天對明天錯），不是模型講話的品質。
"""
import os
import tempfile
import time
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")
os.environ["MUNEA_HEALTH_FOLLOWUP_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="munea-followup-test-"), "health_followups.json")

import health_followup as hf
import health_selector as hs

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = 86400
WORKER = {"audience": "worker"}


def _reset():
    hf._write({})


def _sol(sid, label, time_to="一週"):
    return {"id": sid, "label": label, "timeToEffect": time_to}


class RecordTest(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_recommendation_is_recorded_with_a_due_date(self):
        added = hf.record_recommendation("p1", "TW-EDU-01", [_sol("s1", "睡前泡腳", "今晚")])
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["solutionId"], "s1")
        # 今晚檔＝3 天後問（太早問他還沒感覺、太晚問他忘了）
        self.assertAlmostEqual(added[0]["dueAt"] - added[0]["recommendedAt"], 3 * DAY, delta=5)

    def test_due_days_follow_time_to_effect(self):
        for time_to, days in (("今晚", 3), ("一週", 7), ("慢養", 14)):
            _reset()
            row = hf.record_recommendation("p1", "T", [_sol("s", "x", time_to)])[0]
            self.assertAlmostEqual(row["dueAt"] - row["recommendedAt"], days * DAY, delta=5)

    def test_same_unanswered_solution_is_not_recorded_twice(self):
        hf.record_recommendation("p1", "T", [_sol("s1", "泡腳")])
        again = hf.record_recommendation("p1", "T", [_sol("s1", "泡腳")])
        self.assertEqual(again, [])

    def test_empty_inputs_are_safe(self):
        self.assertEqual(hf.record_recommendation("", "T", [_sol("s", "x")]), [])
        self.assertEqual(hf.record_recommendation("p1", "T", []), [])


class DueTest(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_not_due_yet_is_not_surfaced(self):
        hf.record_recommendation("p1", "T", [_sol("s1", "泡腳", "一週")])
        self.assertEqual(hf.due_followups("p1"), [])

    def test_due_is_surfaced_oldest_first(self):
        now = time.time()
        hf.record_recommendation("p1", "T", [_sol("s1", "早的", "今晚")], now=now - 10 * DAY)
        hf.record_recommendation("p1", "T", [_sol("s2", "晚的", "今晚")], now=now - 5 * DAY)
        due = hf.due_followups("p1", now=now, limit=2)
        self.assertEqual([r["solutionId"] for r in due], ["s1", "s2"])

    def test_very_old_followups_are_dropped_not_asked(self):
        """超過一個月才問「上次那個怎麼樣」很怪——他早忘了。"""
        now = time.time()
        hf.record_recommendation("p1", "T", [_sol("s1", "很久以前的", "今晚")], now=now - 40 * DAY)
        self.assertEqual(hf.due_followups("p1", now=now), [])

    def test_answered_ones_stop_being_asked(self):
        now = time.time()
        hf.record_recommendation("p1", "T", [_sol("s1", "泡腳", "今晚")], now=now - 5 * DAY)
        hf.record_outcome("p1", "s1", hf.OUTCOME_WORKED)
        self.assertEqual(hf.due_followups("p1", now=now), [])


class OutcomeTest(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_outcome_is_stored_and_readable(self):
        hf.record_recommendation("p1", "T", [_sol("s1", "泡腳")])
        hf.record_outcome("p1", "s1", hf.OUTCOME_WORKED)
        self.assertEqual(hf.outcomes_for("p1"), {"s1": "worked"})

    def test_invalid_outcome_is_rejected(self):
        hf.record_recommendation("p1", "T", [_sol("s1", "泡腳")])
        self.assertIsNone(hf.record_outcome("p1", "s1", "隨便亂寫"))
        self.assertEqual(hf.outcomes_for("p1"), {})

    def test_outcomes_are_per_person_not_shared(self):
        hf.record_recommendation("p1", "T", [_sol("s1", "泡腳")])
        hf.record_recommendation("p2", "T", [_sol("s1", "泡腳")])
        hf.record_outcome("p1", "s1", hf.OUTCOME_NO_EFFECT)
        self.assertEqual(hf.outcomes_for("p2"), {})


class FlywheelTest(unittest.TestCase):
    """整個飛輪：記了效果之後，下次推薦真的不一樣。"""

    def setUp(self):
        _reset()

    def test_what_did_not_work_stops_being_recommended(self):
        first = hs.pick("TW-EDU-01", "我睡不好，快受不了", WORKER, 23)["solutions"]
        hf.record_recommendation("p1", "TW-EDU-01", first)
        hf.record_outcome("p1", first[0]["id"], hf.OUTCOME_NO_EFFECT)
        prof = dict(WORKER, outcomes=hf.outcomes_for("p1"))
        second = hs.pick("TW-EDU-01", "我還是睡不好", prof, 23)["solutions"]
        self.assertNotIn(first[0]["id"], [s["id"] for s in second],
                         "他說沒效的方法又被端出來了——再講一次很傷信任")

    def test_what_worked_is_offered_first(self):
        first = hs.pick("TW-EDU-01", "我睡不好，快受不了", WORKER, 23)["solutions"]
        hf.record_recommendation("p1", "TW-EDU-01", first)
        hf.record_outcome("p1", first[1]["id"], hf.OUTCOME_WORKED)
        prof = dict(WORKER, outcomes=hf.outcomes_for("p1"))
        second = hs.pick("TW-EDU-01", "我還是睡不好", prof, 23)["solutions"]
        self.assertEqual(second[0]["id"], first[1]["id"], "他說有效的方法沒排第一")

    def test_safety_still_wins_over_a_good_outcome(self):
        """就算他說鎂很有效，腎功能異常還是要整個拿掉——安全永遠翻不了。"""
        prof = {"audience": "worker", "conditions": ["腎功能異常"],
                "outcomes": {"sleep-magnesium-supplement": "worked"}}
        picked = hs.pick("TW-EDU-01", "我睡不好，快受不了", prof, 23)["solutions"]
        self.assertNotIn("sleep-magnesium-supplement", [s["id"] for s in picked])

    def test_followup_cue_is_gentle_and_never_read_aloud(self):
        row = hf.record_recommendation("p1", "T", [_sol("s1", "睡前泡腳", "今晚")])[0]
        cue = hf.followup_cue(row)
        self.assertIn("絕不把這段唸出來", cue)
        self.assertIn("睡前泡腳", cue)
        self.assertIn("問一句就好", cue)
        self.assertIn("別催", cue)


class WiringTest(unittest.TestCase):
    """接線鎖：做了但沒接上正式線＝白做（2026-07-29 已經犯過兩次）。"""

    def _read(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_selector_actually_uses_outcomes(self):
        src = self._read("health_selector.py")
        self.assertIn('outcome = (flags.get("outcomes") or {}).get(sol.get("id"))', src)

    def test_text_line_passes_outcomes_and_person(self):
        src = self._read("server.py")
        self.assertIn("health_followup.outcomes_for(_person_id)", src)
        self.assertIn('"personId": _person_id', src)

    def test_recommendations_are_recorded_when_injected(self):
        src = self._read("health_kb.py")
        self.assertIn("health_followup.record_recommendation(pid, tid, chosen)", src)

    def test_proactive_opening_surfaces_due_followups(self):
        src = self._read("server.py")
        self.assertIn("health_followup.due_followups(person_id, limit=1)", src)
        self.assertIn("health_followup.followup_cue(_due[0])", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
