#!/usr/bin/env python3
"""語音說明書風格規則契約（Edward 2026-07-15 · 1.0.11 實測）：
①句尾不要一直反問 ②故事要有寓意、有收尾 ③內容預設台灣在地。
規則若被改掉或誤刪，這裡會亮紅燈。"""
import os
import unittest

SRC = os.path.join(os.path.dirname(__file__), "live_voice_server.py")


class VoiceStyleRulesTest(unittest.TestCase):
    def setUp(self):
        with open(SRC, encoding="utf-8") as f:
            self.src = f.read()

    def test_ending_question_restraint_rule_present(self):
        self.assertIn("[句尾收法]", self.src)
        self.assertIn("不要每句話的結尾都反問", self.src)
        self.assertIn("陳述句自然收尾", self.src)

    def test_story_moral_rule_present(self):
        self.assertIn("[說故事與在地內容]", self.src)
        self.assertIn("寓意", self.src)
        self.assertIn("不要講一半沒收尾", self.src)

    def test_taiwan_first_content_rule_present(self):
        self.assertIn("預設以台灣為主", self.src)
        self.assertIn("俗諺", self.src)
        self.assertIn("不確定的史實先用即時查詢確認", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
