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
        # 2026-07-29 兩條線共用同一個組法之後，這幾行搬進 current_health_profile()——
        # 保證沒變（文字線照樣拿到人別鍵與過往效果），只是驗它現在住的地方。
        self.assertIn("health_followup.outcomes_for(person_id) if person_id else {}", src)
        self.assertIn('"personId": person_id', src)
        self.assertIn("_health_profile = current_health_profile()", src)

    def test_recommendations_are_recorded_when_injected(self):
        src = self._read("health_kb.py")
        self.assertIn("health_followup.record_recommendation(pid, tid, chosen)", src)

    def test_proactive_opening_surfaces_due_followups(self):
        src = self._read("server.py")
        self.assertIn("health_followup.due_followups(person_id, limit=1)", src)
        self.assertIn("health_followup.followup_cue(_due[0])", src)


class VoiceLineWiringTest(unittest.TestCase):
    """聊聊是主戰場，飛輪卻只接了文字線（2026-07-29 第三次犯同一類毛病）。

    當時的狀況：語音線讀 st["health_audience"]——那個鍵**從頭到尾沒有任何地方
    寫進去**，所以分齡一直是 None、等於因人挑選在主戰場根本沒生效；推薦也沒入帳，
    同一個人在聊聊講過「那個沒效」，文字線完全不知道。
    """

    def _read(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_voice_no_longer_reads_a_key_nobody_writes(self):
        src = self._read("live_voice_server.py")
        self.assertNotIn('st.get("health_audience")', src,
                         "又在讀沒有人寫入的狀態鍵——分齡等於沒生效")

    def test_voice_actually_fetches_the_profile(self):
        src = self._read("live_voice_server.py")
        self.assertIn("_start_health_profile_fetch(st, memory_scope)", src)
        self.assertIn('"/voice/health-context"', src)

    def test_profile_fetch_never_blocks_the_call_setup_path(self):
        """接通那條路是 async 主幹道，卡 3 秒＝整台機器上所有通話一起卡。"""
        src = self._read("live_voice_server.py")
        # 接通當下只放空的、真的去查是背景執行緒的事
        self.assertIn('st["health_profile"] = {}\n    _start_health_profile_fetch(st, memory_scope)', src,
                      "接通處沒有先放空值＋改派背景查")
        self.assertIn("threading.Thread(target=_fill, daemon=True)", src)
        # 整支檔案只准有這一處真的發出查詢，而且它住在背景那個 _fill 裡
        self.assertEqual(src.count("= _fetch_health_profile(memory_scope)"), 1)
        fill = src.split("def _fill():", 1)[1].split("threading.Thread", 1)[0]
        self.assertIn("_fetch_health_profile(memory_scope)", fill,
                      "查詢跑出背景執行緒外面了＝又擋在接通路徑上")

    def test_voice_uses_the_fetched_profile_when_picking(self):
        src = self._read("live_voice_server.py")
        self.assertIn('_prof = st.get("health_profile") or {}', src)

    def test_voice_recommendations_are_booked_on_the_brain(self):
        voice = self._read("live_voice_server.py")
        self.assertIn('st["pending_health_record"] = (ids[0], said, _prof, _hour)', voice)
        self.assertIn('"/voice/health-recommended"', voice)

    def test_nothing_is_booked_until_she_actually_says_it(self):
        """提示是排在下一個輪替空檔送的；電話先掛就等於沒講過，記了會問空氣。"""
        voice = self._read("live_voice_server.py")
        self.assertIn("if health_cue and health_record:", voice)
        self.assertIn("_record_voice_recommendation(cid, st, *health_record)", voice)
        # 記帳只能發生在「已經送出去」之後
        after_send = voice.split('_diag(cid, "guardian.cue_sent"', 1)[1]
        self.assertIn("_record_voice_recommendation(cid, st, *health_record)", after_send)
        brain = self._read("server.py")
        self.assertIn("def voice_health_recommended_response(data)", brain)
        self.assertIn("health_followup.record_recommendation(person_id, topic_id, solutions)", brain)

    def test_the_new_internal_route_is_registered_and_secret_gated(self):
        src = self._read("server.py")
        self.assertIn('"/voice/health-recommended": voice_health_recommended_response', src)
        # 內部通道一律吃共用密語；漏掛＝任何人都能替別人記帳
        self.assertIn('"/voice/health-recommended")', src)

    def test_brain_hands_the_profile_over_only_when_it_knows_who_it_is(self):
        src = self._read("server.py")
        self.assertIn("profile = current_health_profile() if person else None", src)

    def test_both_lines_build_the_profile_the_same_way(self):
        """一邊有、一邊悄悄沒有——就是這次的病根。共用同一個組法。"""
        src = self._read("server.py")
        self.assertIn("def current_health_profile()", src)
        self.assertEqual(src.count("_health_profile = current_health_profile()"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
