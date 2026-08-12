#!/usr/bin/env python3
"""機智問答由寧寧當場出題——把關層（Edward 2026-08-01 拍板 B 案）

為什麼這支測試存在：讓 AI 當場產內容給長輩玩，好處是題目永遠新鮮、能配合他的興趣與
所在地；風險是她可能出到不該問的題（政治、宗教、醫療診斷）或格式壞掉的題。

所以這裡驗的不是「她出得好不好」——那是模型的事——而是**壞的題目一定進不來**：
逐題驗形狀與禁區，並且只要有一題不合格就整份退回 App 內建題庫。
寧可玩到重複的老題目，也不要玩到一題怪的：長輩對 App 的信任掉了就回不來。
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "quiz-unit-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402


def q(text="一天走多少步比較有活力？", opts=None, a=2):
    return {"q": text, "opts": opts or ["500 步", "2000 步", "7000 步左右", "50000 步"], "a": a}


class QuizQuestionShapeTests(unittest.TestCase):
    """形狀壞掉的題目不能進畫面——四個選項、答案指得到、長度合理。"""

    def test_accepts_a_well_formed_question(self):
        self.assertTrue(server.quiz_question_ok(q()))

    def test_rejects_wrong_option_count(self):
        self.assertFalse(server.quiz_question_ok(q(opts=["甲", "乙", "丙"], a=0)))
        self.assertFalse(server.quiz_question_ok(q(opts=["甲", "乙", "丙", "丁", "戊"], a=0)))

    def test_rejects_duplicate_options(self):
        # 選項重複＝實際上少一個選項，答對機率被偷偷改掉
        self.assertFalse(server.quiz_question_ok(q(opts=["甲", "甲", "乙", "丙"], a=0)))

    def test_rejects_answer_out_of_range_or_not_an_int(self):
        self.assertFalse(server.quiz_question_ok(q(a=9)))
        self.assertFalse(server.quiz_question_ok(q(a=-1)))
        self.assertFalse(server.quiz_question_ok(q(a="2")))

    def test_rejects_empty_or_overlong_text(self):
        self.assertFalse(server.quiz_question_ok(q(text="   ")))
        self.assertFalse(server.quiz_question_ok(q(text="字" * (server.QUIZ_Q_MAX_CHARS + 1))))
        self.assertFalse(server.quiz_question_ok(q(opts=["字" * (server.QUIZ_OPT_MAX_CHARS + 1), "乙", "丙", "丁"], a=1)))

    def test_rejects_non_dict(self):
        self.assertFalse(server.quiz_question_ok("這是一句話不是一題"))
        self.assertFalse(server.quiz_question_ok(None))


class QuizForbiddenTopicTests(unittest.TestCase):
    """機智問答是全家一起玩的。這幾類不是「答錯」，是不該問。"""

    def test_blocks_politics_religion_ethnicity(self):
        for text in ("哪一位是現任總統？", "下次選舉是什麼時候？", "拜哪個神明求平安？"):
            self.assertFalse(server.quiz_question_ok(q(text=text, a=0)), text)

    def test_blocks_medical_and_money(self):
        for text in ("這個症狀的病因是什麼？", "這個藥一次吃幾毫克？", "哪一支股票比較穩？"):
            self.assertFalse(server.quiz_question_ok(q(text=text, a=0)), text)

    def test_blocks_forbidden_words_in_the_options_too(self):
        # 題目乾淨、選項藏禁區，一樣要擋——長輩看到的是整張卡不是只有題目
        self.assertFalse(server.quiz_question_ok(
            q(text="下面哪一個是節日？", opts=["端午節", "總統就職", "中秋節", "春節"], a=0)))

    def test_blocks_in_the_other_three_locales(self):
        for text in ("Who won the last election?", "この症状の診断は？", "Cual es la religion mayoritaria?"):
            self.assertFalse(server.quiz_question_ok(q(text=text, a=0)), text)


class QuizInstructionTests(unittest.TestCase):
    """出題規則寫死在指示裡，不靠模型自由發揮。"""

    def setUp(self):
        self.text = server.quiz_question_instruction("zh-TW", ["懷舊老歌", "園藝花草"], "台北市南港區", 10)

    def test_states_difficulty_and_shape(self):
        self.assertIn("一定知道", self.text)
        self.assertIn("四個選項", self.text)

    def test_states_the_forbidden_topics(self):
        for word in ("政治", "宗教", "醫療", "金錢"):
            self.assertIn(word, self.text)

    def test_requires_local_versions_not_translations(self):
        # 台灣問「哪個節日吃湯圓」，西班牙版不能翻譯過去、要換成當地的題
        self.assertIn("翻譯過來", self.text)

    def test_carries_interests_and_place(self):
        self.assertIn("懷舊老歌", self.text)
        self.assertIn("台北市南港區", self.text)


class QuizResponseTests(unittest.TestCase):
    """整份的取捨：全部合格才給，有一題壞就退回內建題庫。"""

    def _reply(self, payload):
        class R:
            text = json.dumps(payload, ensure_ascii=False)
        return R()

    def _run(self, payload, count=3):
        with patch.object(server.eng.client.models, "generate_content", return_value=self._reply(payload)):
            return server.quiz_questions_response({"count": count, "locale": "zh-TW"})

    def test_returns_questions_when_every_item_passes(self):
        out = self._run({"questions": [q(), q(text="睡前喝哪一種比較不好睡？", a=0), q(text="過馬路前先做什麼？", a=0)]})
        self.assertTrue(out["ok"])
        self.assertEqual(out["source"], "ai")
        self.assertEqual(len(out["questions"]), 3)

    def test_one_bad_item_drops_the_whole_batch(self):
        # 刻意不做「挑好的留下」：挑剩的題數會變少、健康與文化的配比也跑掉
        out = self._run({"questions": [q(), q(text="哪一位是現任總統？", a=0), q(text="過馬路前先做什麼？", a=0)]})
        self.assertFalse(out["ok"])
        self.assertEqual(out["source"], "fallback")
        self.assertEqual(out["questions"], [])

    def test_too_few_questions_is_a_fallback_not_a_short_game(self):
        out = self._run({"questions": [q()]}, count=3)
        self.assertFalse(out["ok"])

    def test_broken_json_falls_back_quietly(self):
        class R:
            text = "抱歉，我出不出來"
        with patch.object(server.eng.client.models, "generate_content", return_value=R()):
            out = server.quiz_questions_response({"count": 3})
        self.assertFalse(out["ok"])
        self.assertEqual(out["source"], "fallback")

    def test_model_failure_falls_back_quietly(self):
        with patch.object(server.eng.client.models, "generate_content", side_effect=RuntimeError("boom")):
            out = server.quiz_questions_response({"count": 5})
        self.assertFalse(out["ok"])
        self.assertEqual(out["questions"], [])

    def test_count_is_clamped_to_a_sane_range(self):
        captured = {}

        def fake(**kwargs):
            captured["contents"] = kwargs.get("contents")
            class R:
                text = json.dumps({"questions": []})
            return R()

        with patch.object(server.eng.client.models, "generate_content", side_effect=fake):
            server.quiz_questions_response({"count": 999})
        self.assertIn(str(server.QUIZ_MAX_COUNT), captured["contents"])


if __name__ == "__main__":
    unittest.main()
