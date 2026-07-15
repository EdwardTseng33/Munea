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

    def test_priority_contract_present_and_first(self):
        """優先權契約（五層、小者優先）必須存在，且在說明書組裝的最前面。"""
        self.assertIn("本說明書優先權契約", self.src)
        self.assertIn("層級數字小的一律優先", self.src)
        self.assertLess(self.src.index("本說明書優先權契約"),
                        self.src.index("[接住情緒與陪伴引導]"))

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

    def test_emotion_holding_three_steps_present(self):
        """接住→引導歸因→量身建議 三步流程與六種情緒接法（Edward 2026-07-15）。"""
        self.assertIn("[接住情緒與陪伴引導]", self.src)
        for kw in ("第一步「接住」", "第二步「找到問題所在」", "第三步「量身的建議與關懷」"):
            self.assertIn(kw, self.src)
        for emo in ("孤單", "低落", "焦慮", "崩潰", "難過", "生氣"):
            self.assertIn(emo + "→", self.src)
        self.assertIn("讓他自己說出原因", self.src)
        self.assertIn("有沒有別的可能", self.src)

    def test_canned_advice_banned_and_boundary_present(self):
        self.assertIn("罐頭話", self.src)
        for banned in ("出去走走", "看看海", "想開一點", "不要想太多"):
            self.assertIn(banned, self.src)
        self.assertIn("1925", self.src)
        self.assertIn("醫療紅線與危機處理規則永遠優先", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
