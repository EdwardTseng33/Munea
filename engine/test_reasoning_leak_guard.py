#!/usr/bin/env python3
"""回覆出口防禦性清洗——內部推理標記（<thinking>...</thinking>）防洩漏（2026-07-25 三修③）。

背景：手動煙霧測試曾撞過一次 <thinking>...</thinking> 內部推理文字直接混進使用者
看得到的回覆裡，走的是跟正式文字線一模一樣的 server.reply_conv()（見
docs/聊天品質基準-第一輪-2026-07-25.md 第四節）。這支測試守住兩層：
  ①純函式層級——各種洩漏型態都被正確清乾淨、正常文字不受影響，殘缺（只有
    開頭沒結尾）也要清乾淨；
  ②production 出口確實掛上這道清洗（文字線 server.reply_conv、語音線
    live_voice_server 的 caption 出口），防止之後改動不小心把這道防禦拿掉
    （跟 test_lookup_model_chain.py 的「source-level 鎖」同一種手法）。

跑法：python engine/test_reasoning_leak_guard.py（不需要網路或真鑰匙）
"""
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "reasoning-leak-guard-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import chat_engine as eng  # noqa: E402
import server  # noqa: E402


class StripReasoningArtifactsTests(unittest.TestCase):
    """純函式層級：engine/chat_engine.py 的 strip_reasoning_artifacts()。"""

    def test_well_formed_block_is_removed(self):
        raw = "<thinking>要不要先提醒她吃藥、還是先聊近況</thinking>雅雯上禮拜有留言說這週會回來喔。"
        self.assertEqual(
            eng.strip_reasoning_artifacts(raw),
            "雅雯上禮拜有留言說這週會回來喔。",
        )

    def test_unclosed_tag_strips_to_end_of_string(self):
        """殘缺情形：只有開頭標記、沒有對應的結尾標記——安全起見把後面全部當推理垃圾砍掉。"""
        raw = "好，我來想一下要怎麼回。<thinking>阿嬤可能會擔心雅雯的安全，我要不要先問"
        self.assertEqual(
            eng.strip_reasoning_artifacts(raw),
            "好，我來想一下要怎麼回。",
        )

    def test_case_insensitive_and_alternate_tag_names(self):
        self.assertEqual(
            eng.strip_reasoning_artifacts("<THINK>內部推理</THINK>沒問題，我陪你聊。"),
            "沒問題，我陪你聊。",
        )
        self.assertEqual(
            eng.strip_reasoning_artifacts("<reasoning>分析中</reasoning>好啊，我在聽。"),
            "好啊，我在聽。",
        )
        self.assertEqual(
            eng.strip_reasoning_artifacts("<scratchpad>草稿</scratchpad>晚安喔。"),
            "晚安喔。",
        )

    def test_tag_in_the_middle_leaves_surrounding_text_intact(self):
        raw = "阿嬤晚安喔<thinking>要不要提醒吃藥</thinking>，記得吃藥喔。"
        cleaned = eng.strip_reasoning_artifacts(raw)
        self.assertNotIn("<thinking>", cleaned)
        self.assertNotIn("</thinking>", cleaned)
        self.assertIn("阿嬤晚安喔", cleaned)
        self.assertIn("記得吃藥喔。", cleaned)

    def test_plain_text_without_tags_is_unchanged(self):
        raw = "阿嬤，妳最近身體還好嗎？"
        self.assertEqual(eng.strip_reasoning_artifacts(raw), raw)

    def test_empty_and_none_are_safe(self):
        self.assertEqual(eng.strip_reasoning_artifacts(""), "")
        self.assertIsNone(eng.strip_reasoning_artifacts(None))


class ReplyConvOutputIsCleanedTests(unittest.TestCase):
    """production 文字線整合測試：假造模型真的漏出 <thinking> 標記，確認
    server.reply_conv() 回傳給使用者的文字已經被清乾淨。"""

    def setUp(self):
        server.REQUEST_DATA_IDENTITY.set({"personId": "reasoning-guard-test-person"})

    def test_reply_conv_strips_leak_before_returning(self):
        fake_response = type(
            "FakeResp", (),
            {"text": "<thinking>先想一下怎麼回比較好</thinking>好啊，我在聽你說。"},
        )()
        history = [{"role": "user", "text": "我今天心情不太好"}]
        with patch.object(server.eng.client.models, "generate_content", return_value=fake_response):
            reply = server.reply_conv(history, char="寧寧")
        self.assertNotIn("<thinking>", reply)
        self.assertNotIn("</thinking>", reply)
        self.assertEqual(reply, "好啊，我在聽你說。")

    def test_reply_conv_passes_through_clean_text_unchanged(self):
        fake_response = type("FakeResp", (), {"text": "阿公，今天過得怎麼樣？"})()
        history = [{"role": "user", "text": "我今天心情不太好"}]
        with patch.object(server.eng.client.models, "generate_content", return_value=fake_response):
            reply = server.reply_conv(history, char="寧寧")
        self.assertEqual(reply, "阿公，今天過得怎麼樣？")


class ProductionCallSitesWireTheGuardTests(unittest.TestCase):
    """source-level 鎖：防止之後改動不小心把清洗呼叫拿掉（跟
    test_lookup_model_chain.py 的『source-level 鎖』同一種手法）。"""

    def test_server_reply_conv_calls_strip_reasoning_artifacts(self):
        src_path = os.path.join(os.path.dirname(__file__), "server.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        # 2026-07-29：出口改走統一清洗 clean_outgoing_reply（內含這道剝除＋空頭承諾攔截），
        # 這道防禦沒有被拿掉、只是包進同一支函式，檢查跟著改認新名字。
        # 2026-07-29 這行改成多行呼叫（多帶了 has_briefing）——保證沒變，改驗實質：
        # 文字線出口確實走共用清洗，而且清的是模型回的那段字。
        self.assertIn("eng.clean_outgoing_reply(", src)
        self.assertIn("r.text, has_briefing=", src)

    def test_live_voice_caption_output_calls_strip_reasoning_artifacts(self):
        src_path = os.path.join(os.path.dirname(__file__), "live_voice_server.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn(
            "caption_text = eng.clean_outgoing_reply(raw_caption)",
            src,
        )


class PrefixMonologueTest(unittest.TestCase):
    """2026-07-31 考卷 S01 抓到：她把英文內心獨白直接講出來（「THOUGHT: The user…」）。
    原本的攔截只認 <thinking> 格式標籤、不認前綴式獨白——這一段就是長輩會聽到的英文。"""

    def test_thought_prefix_paragraph_is_stripped(self):
        t = "THOUGHT: The user is excited about the wedding.\n\n哇，這是大喜事欸！"
        self.assertEqual(eng.strip_reasoning_artifacts(t), "哇，這是大喜事欸！")

    def test_lowercase_and_variants_are_caught(self):
        for marker in ("thinking:", "REASONING:", "Analysis：", "internal monologue:"):
            t = marker + " blah blah\n\n好啊。"
            self.assertEqual(eng.strip_reasoning_artifacts(t), "好啊。", marker)

    def test_normal_chinese_sentences_are_never_touched(self):
        for t in ("我在想這件事：你說得對。", "哇，孫子要娶某了！",
                  "計畫是這樣：我們先泡腳再睡。"):
            self.assertEqual(eng.strip_reasoning_artifacts(t), t)


class ThirdPartyFabricationRuleTest(unittest.TestCase):
    """2026-07-31 考卷 S11：她編造「我一直都有跟媽媽說我是AI」——對第三人的過去互動
    同樣不可虛構。說明書要教「設計上」與「歷史上」的分法。"""

    def test_the_rule_is_in_the_prompt(self):
        src = eng.CORE
        self.assertIn("對第三人也一樣", src)
        self.assertIn("設計上", src)
        self.assertIn("歷史上", src)
        self.assertIn("媽媽心裡怎麼理解，我沒辦法替她回答", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
