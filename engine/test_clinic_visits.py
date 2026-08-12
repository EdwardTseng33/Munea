#!/usr/bin/env python3
"""看診前後閉環契約（2026-07-29）。

**為什麼這一層存在**：長輩的健康動線是四段——不舒服 → 看醫生 → 醫生講一堆 →
回家忘一半。她原本只做了第一段。第二、三、四段完全空白，而那正是最需要人幫忙、
市面上也沒人做的地方。

**這一層只做三件事：幫他記、幫他問、幫他想起來。**
不給建議、不解讀醫囑、不評論醫生——這支就是釘住那條界線。
她是陪著去看病、幫忙記筆記的人，不是第二個醫生。
"""
import os
import tempfile
import time
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")
os.environ["MUNEA_CLINIC_VISITS_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="munea-visits-test-"), "clinic_visits.json")

import clinic_visits as cv

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = 86400


def _reset():
    cv._write({})


class DetectTest(unittest.TestCase):
    def test_upcoming_visit_is_heard(self):
        for said in ("我下禮拜要回診", "明天要看醫生", "我掛號了", "禮拜三要去醫院"):
            self.assertEqual(cv.detect_stage(said), cv.STAGE_BEFORE, said)

    def test_finished_visit_is_heard(self):
        for said in ("今天看完醫生了", "醫生說我要多運動", "剛從醫院回來"):
            self.assertEqual(cv.detect_stage(said), cv.STAGE_AFTER, said)

    def test_ordinary_talk_is_not_mistaken_for_a_visit(self):
        for said in ("我睡不好", "膝蓋痛", "今天天氣真好", ""):
            self.assertIsNone(cv.detect_stage(said), said)


class NoteTest(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_opening_twice_reuses_the_same_note(self):
        a = cv.open_visit("p1")
        b = cv.open_visit("p1")
        self.assertEqual(a["id"], b["id"], "同一趟診開了兩張小抄")

    def test_questions_are_capped_at_three(self):
        """超過三個他在診間一個都問不出來——擋住是為了他，不是為了省事。"""
        cv.open_visit("p1")
        for i in range(6):
            cv.add_note("p1", "questions", "問題%d" % i)
        self.assertEqual(len(cv.pending_visit("p1")["questions"]), cv.MAX_QUESTIONS)

    def test_duplicate_notes_are_not_repeated(self):
        cv.open_visit("p1")
        cv.add_note("p1", "symptoms", "膝蓋痛兩個月")
        cv.add_note("p1", "symptoms", "膝蓋痛兩個月")
        self.assertEqual(len(cv.pending_visit("p1")["symptoms"]), 1)

    def test_notes_are_per_person_not_shared(self):
        cv.open_visit("p1")
        cv.add_note("p1", "symptoms", "膝蓋痛")
        self.assertIsNone(cv.pending_visit("p2"))

    def test_a_stale_note_stops_being_brought_up(self):
        """一個半月還沒去看＝這張小抄大概沒用了，別一直提。"""
        now = time.time()
        cv.open_visit("p1", now=now - 60 * DAY)
        self.assertIsNone(cv.pending_visit("p1", now=now))

    def test_empty_person_is_safe(self):
        self.assertIsNone(cv.open_visit("", when="明天"))
        self.assertEqual(cv.cue_for("", "我明天要看醫生"), "")


class FlowTest(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_before_cue_asks_one_thing_at_a_time(self):
        cue = cv.cue_for("p1", "我下禮拜要回診")
        self.assertIn("一次只問一件", cue)
        self.assertIn("不要變成問診表", cue)

    def test_before_cue_shows_what_is_already_recorded(self):
        cv.cue_for("p1", "我下禮拜要回診")
        cv.add_note("p1", "symptoms", "膝蓋痛兩個月")
        cv.add_note("p1", "meds", "血壓藥")
        cue = cv.cue_for("p1", "嗯")
        self.assertIn("膝蓋痛兩個月", cue)
        self.assertIn("血壓藥", cue)

    def test_a_complete_note_reassures_instead_of_asking_more(self):
        cv.cue_for("p1", "我下禮拜要回診")
        for field, text in (("symptoms", "膝蓋痛"), ("meds", "血壓藥"), ("questions", "要不要開刀")):
            cv.add_note("p1", field, text)
        cue = cv.cue_for("p1", "嗯")
        self.assertIn("照著講就好", cue)
        self.assertNotIn("一次只問一件", cue)

    def test_saying_he_went_switches_to_asking_what_the_doctor_said(self):
        cv.cue_for("p1", "我下禮拜要回診")
        cue = cv.cue_for("p1", "今天看完醫生了")
        self.assertIn("醫生後來怎麼說", cue)

    def test_once_he_told_us_we_stop_asking(self):
        cv.cue_for("p1", "我明天要看醫生")
        cv.cue_for("p1", "今天看完醫生了")
        cv.add_note("p1", "doctorSaid", "醫生說先吃藥兩週再看")
        self.assertEqual(cv.cue_for("p1", "嗯"), "", "他已經講了還一直追問")

    def test_what_he_is_talking_about_now_wins_over_an_old_note(self):
        """他明明在講剛看完，不該被拉回還沒去看的那張小抄。"""
        cv.open_visit("p1")
        cue = cv.cue_for("p1", "剛從醫院回來")
        self.assertIn("醫生後來怎麼說", cue)


class RedLineTest(unittest.TestCase):
    """比別層更硬的紅線：她是幫忙記筆記的人，不是第二個醫生。"""

    def setUp(self):
        _reset()

    def test_before_cue_forbids_diagnosing_while_taking_notes(self):
        cue = cv.cue_for("p1", "我下禮拜要回診")
        self.assertIn("不是替他判斷病情", cue)
        self.assertIn("不要因為整理小抄就開始給診斷或建議用藥", cue)

    def test_after_cue_forbids_interpreting_the_doctor(self):
        cv.cue_for("p1", "我明天要看醫生")
        cue = cv.cue_for("p1", "今天看完醫生了")
        for phrase in ("絕不解讀醫囑", "不評論醫生的判斷對不對", "不建議他改藥或加藥"):
            self.assertIn(phrase, cue)

    def test_after_cue_records_verbatim_not_summarised(self):
        cv.cue_for("p1", "我明天要看醫生")
        cue = cv.cue_for("p1", "今天看完醫生了")
        self.assertIn("照原話記下來就好", cue)

    def test_the_prompt_layer_states_the_same_red_lines(self):
        # 2026-07-31 人設書分國：這些規則從程式碼搬進 engine/persona/*.zh-TW.txt。
        # 守的東西沒變（規則被刪就亮紅燈），只是要把程式碼與繁中書合起來看。
        with open(os.path.join(HERE, "chat_engine.py"), encoding="utf-8") as f:
            src = f.read()
        for _kind in ("core", "red", "lookup-offline", "lookup-online"):
            _path = os.path.join(HERE, "persona", _kind + ".zh-TW.txt")
            if os.path.exists(_path):
                with open(_path, encoding="utf-8") as _bf:
                    src += _bf.read()
        self.assertIn("⑥-VISIT", src)
        for phrase in ("絕不解讀醫囑", "絕不評論醫生的判斷對不對",
                       "不是第二個醫生", "最多三個問題"):
            self.assertIn(phrase, src)


class WiringTest(unittest.TestCase):
    """接線鎖：做了但沒接上正式線＝白做（2026-07-29 已經犯過六次）。"""

    def test_the_text_line_actually_calls_it(self):
        with open(os.path.join(HERE, "server.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("import clinic_visits", src)
        self.assertIn('clinic_visits.cue_for(_health_profile.get("personId") or "", last_user)', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
