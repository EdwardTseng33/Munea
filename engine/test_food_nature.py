#!/usr/bin/env python3
"""食物寒熱與藥食同源契約（2026-07-31 · 知識庫廣度第三批）。

**這一層的靈魂**：長輩用「寒／燥／毒」決定吃不吃，我們把民俗語言翻譯成真實風險
——傳統觀點誠實呈現（不嘲笑）、實證講到哪裡（不硬拗）、真正該注意的人點出來。

例：香蕉「很寒」→ 真正要節制的是腎不好的人（高鉀），不是人人。
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import health_kb
import health_selector as hs

TOPIC = "TW-EDU-32"


class RoutingTest(unittest.TestCase):
    def test_food_questions_reach_the_food_topic(self):
        for said in ("香蕉是不是很寒", "芒果很毒不能吃嗎", "荔枝可以多吃嗎",
                     "白蘿蔔跟人蔘會相沖嗎", "粽子可以吃嗎", "枸杞紅棗茶好嗎"):
            self.assertEqual(health_kb.match_topics(said)[:1], [TOPIC], said)

    def test_constitution_language_still_belongs_to_the_tcm_layer(self):
        """「我最近很燥」是體質語言、歸中醫層——食物層不搶。"""
        self.assertEqual(health_kb.match_topics("我最近很燥")[:1], ["TW-EDU-30"])


class TranslationTest(unittest.TestCase):
    """民俗語言 → 真實風險的翻譯，每條都要三段齊：傳統怎麼說＋實證＋誰真的要注意。"""

    def _say(self, sid):
        return next(s for s in hs.TOPICS[TOPIC]["solutions"] if s["id"] == sid)["say"]

    def test_banana_translates_cold_into_potassium(self):
        say = self._say("food-banana")
        self.assertIn("鉀", say)
        self.assertIn("腎", say)

    def test_mango_translates_poison_into_peel_allergy(self):
        say = self._say("food-mango")
        self.assertIn("皮", say)
        self.assertIn("過敏", say)

    def test_lychee_carries_the_real_hypoglycemia_warning(self):
        """荔枝空腹大量→低血糖是醫學上真的有記載的——這條不是民俗、不能軟。"""
        say = self._say("food-lychee")
        self.assertIn("低血糖", say)
        self.assertIn("空腹", say)

    def test_radish_ginseng_myth_is_gently_debunked_without_mocking(self):
        say = self._say("food-radish-ginseng")
        self.assertIn("沒有明確的科學依據", say)
        self.assertIn("照他的醫囑吃", say, "破除迷思的同時要尊重開方的中醫師")

    def test_the_frame_entry_promises_translation_not_mockery(self):
        say = self._say("food-nature-frame")
        self.assertIn("不會笑", say)
        self.assertIn("翻譯", say)


class WarningCarrierTest(unittest.TestCase):
    """警告的載體不能被安全過濾藏掉——腎不好的人正是最需要聽到青草茶警告的人。"""

    def test_dialysis_patient_still_hears_the_herbal_tea_warning(self):
        prof = {"audience": "elder", "conditions": ["洗腎"]}
        picked = hs.pick(TOPIC, "我在洗腎可以喝青草茶嗎", prof, 15)["solutions"]
        self.assertEqual(picked[0]["id"], "food-herbal-tea")
        self.assertIn("腎不好的人最好避開", picked[0]["say"])

    def test_referral_covers_allergy_and_lychee_hypoglycemia(self):
        ref = hs.pick(TOPIC, "香蕉很寒嗎", {"audience": "elder"}, 15)["referral"]
        self.assertIn("119", ref["say"])
        self.assertIn("低血糖", ref["say"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
