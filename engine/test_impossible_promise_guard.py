#!/usr/bin/env python3
"""空頭承諾出口攔截（2026-07-29 · 考卷實測 S06 抓到後補）。

背景：急症情境下她會脫口說「需要我幫您撥電話給他們嗎？」——她撥不了電話。
長輩聽了會以為有人去通知家人，安心坐著等，等不到也不會再求助。說明書已寫死禁止
（RED ⑥），但那層是「勸」、屬機率性；這支守住程式硬擋那層。

兩層鎖（跟 test_reasoning_leak_guard.py 同一種手法）：
  ①純函式層——做不到的承諾要砍、做得到的事一個都不能誤傷；
  ②接線層——production 出口（chat_engine._clean_reply）確實掛著這道攔截，
    防止之後改動不小心把它拿掉。
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import chat_engine

HERE = os.path.dirname(os.path.abspath(__file__))


class ImpossiblePromiseStripTest(unittest.TestCase):
    """她真的做不到的事：撥電話、代發訊息、叫車代購、傳圖傳連結。"""

    def test_strips_offer_to_dial_but_keeps_the_correct_referral(self):
        text = ("美玉姐，心臟這樣跳還是要注意喔。要不要趕快聯絡家人陪您去醫院檢查一下？"
                "需要我幫您撥電話給他們嗎？")
        cleaned, dropped = chat_engine.strip_impossible_promises(text)
        self.assertEqual(len(dropped), 1)
        self.assertIn("撥電話", dropped[0])
        # 關鍵：正確的轉介建議必須留著（整段丟掉會把救命的那句一起丟）
        self.assertIn("陪您去醫院", cleaned)
        self.assertNotIn("我幫您撥電話", cleaned)

    def test_strips_various_impossible_offers(self):
        for text in (
            "你先坐著休息。我幫你打電話給你女兒好嗎？",
            "要不要我幫你叫車？",
            "我幫你訂位好了。",
            "這個連結我傳給你看。",
        ):
            _, dropped = chat_engine.strip_impossible_promises(text)
            self.assertTrue(dropped, f"沒擋下做不到的承諾：{text}")

    def test_never_touches_things_she_can_actually_do(self):
        """誤傷比漏擋更糟——這些是她真的做得到、也是產品承攬的功能。"""
        for text in (
            "我沒辦法傳圖給你，但我可以講給你聽。",
            "這個我幫你記下來，明天提醒你回診。",
            "你可以用App的傳話功能留言給他喔。",
            "我幫你注意一下血壓的變化。",
            "我幫你把這件事記在行事曆上。",
            "要不要我提醒你家人幫你安排？",
        ):
            cleaned, dropped = chat_engine.strip_impossible_promises(text)
            self.assertEqual(dropped, [], f"誤傷了她做得到的事：{text}")
            self.assertEqual(cleaned, text)

    def test_reply_that_is_only_a_false_promise_is_replaced_with_an_honest_line(self):
        """整段就只有那個做不到的承諾：不能原封送出（等於直接對長輩說謊、他會坐著等），
        也不能回空白——換成誠實的一句話。"""
        for text in ("我幫你打電話給他。", "好，我幫你聯絡他。"):
            cleaned, dropped = chat_engine.strip_impossible_promises(text)
            self.assertTrue(dropped, f"沒偵測到空頭承諾：{text}")
            self.assertEqual(cleaned, chat_engine.IMPOSSIBLE_PROMISE_FALLBACK)
            self.assertNotIn("我幫你打電話", cleaned)

    def test_empty_input_is_safe(self):
        self.assertEqual(chat_engine.strip_impossible_promises(""), ("", []))
        self.assertEqual(chat_engine.strip_impossible_promises(None), (None, []))


class WiringLockTest(unittest.TestCase):
    """接線鎖：production 出口真的掛著這道攔截。"""

    def test_clean_reply_applies_the_guard(self):
        text = "先坐下來休息。需要我幫您撥電話給家人嗎？"
        out = chat_engine._clean_reply(text)
        self.assertNotIn("撥電話", out)
        self.assertIn("先坐下來休息", out)

    def test_guard_is_wired_into_real_production_paths(self):
        """2026-07-29 抓到的疏漏：攔截原本只掛在 chat_engine 自己的 _clean_reply，
        但正式文字線（server.reply_conv）與語音線字幕出口走的是另一條，等於沒防到。
        這條鎖住三個真正的出口都走統一清洗 clean_outgoing_reply。"""
        with open(os.path.join(HERE, "chat_engine.py"), encoding="utf-8") as f:
            self.assertIn("def clean_outgoing_reply", f.read())
        with open(os.path.join(HERE, "server.py"), encoding="utf-8") as f:
            src = f.read()
            self.assertIn("eng.clean_outgoing_reply(", src)
            self.assertIn("r.text, has_briefing=", src)
        with open(os.path.join(HERE, "live_voice_server.py"), encoding="utf-8") as f:
            self.assertIn("caption_text = eng.clean_outgoing_reply(raw_caption)", f.read())


class VoiceSelfCorrectionTest(unittest.TestCase):
    """語音線：聲音收不回，但要在下一個輪替空檔自己更正（2026-07-29）。

    為什麼不能只靠出口清洗：聲音是邊生邊播的，字幕清乾淨時那句已經被聽到了。
    長輩會坐下來等一通不會來的電話——所以要在幾秒內自然收回。"""

    def _voice_src(self):
        with open(os.path.join(HERE, "live_voice_server.py"), encoding="utf-8") as f:
            return f.read()

    def test_voice_detects_and_queues_a_self_correction(self):
        src = self._voice_src()
        self.assertIn("def impossible_promise_cue", src)
        self.assertIn("eng.strip_impossible_promises(raw_caption)", src)
        self.assertIn('st["pending_promise_cue"] = impossible_promise_cue', src)

    def test_correction_is_sent_at_the_turn_gap_and_goes_first(self):
        src = self._voice_src()
        # 併進既有的輪替空檔送出機制、而且排最前面（長輩可能正要坐下來等）
        self.assertIn('promise_cue = st.get("pending_promise_cue")', src)
        self.assertIn("pending = [promise_cue] + pending", src)
        self.assertIn('or st.get("pending_promise_cue")', src)

    def test_cue_tells_her_to_offer_a_doable_alternative_not_just_apologise(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("lvs_probe", os.path.join(HERE, "live_voice_server.py"))
        # 不真的載入整支語音伺服器（會連線）——用原始碼檢查提示詞內容即可
        src = self._voice_src()
        start = src.index("def impossible_promise_cue")
        body = src[start:start + 1400]
        self.assertIn("你其實做不到", body)
        self.assertIn("不要長篇道歉", body)
        self.assertIn("他自己做得到的替代", body)


class SafetyRuleTest(unittest.TestCase):
    """說明書那層（勸）也要在——兩層都要，不能只靠其中一層。"""

    def test_red_line_forbids_backing_down_on_emergency(self):
        self.assertIn("你不可以跟著軟化", chat_engine.RED)
        self.assertIn("絕不可以說「需要我幫你撥電話嗎」", chat_engine.RED)

    def test_core_forbids_filling_gaps_to_keep_conversation_smooth(self):
        for needle in ("⓪-D-4", "不知道別人心裡知道什麼", "絕不准現編一個來源"):
            self.assertIn(needle, chat_engine.CORE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
