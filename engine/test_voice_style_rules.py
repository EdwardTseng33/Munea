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
        # 2026-07-16 Edward「回話少一點反問」：要有硬規矩、不能只有「大多數」
        self.assertIn("不准連續兩輪都用問題收尾", self.src)

    def test_opening_ramp_rule_present(self):
        """2026-07-16 Edward「最剛開始聊話不要太多、太熱情」：開場升溫必須無條件生效。"""
        self.assertIn("[開場升溫]", self.src)
        self.assertIn("前三輪每輪最多一句話", self.src)
        self.assertIn("不要一接通就高能量歡迎", self.src)
        self.assertIn("不管你們多熟", self.src)

    def test_video_call_persona_frame_present(self):
        """2026-07-16 Edward「像與真實世界的人視訊聊天」：相處框架要在、且是行為比喻不是身分宣稱。"""
        self.assertIn("真實世界裡兩個人的視訊聊天", self.src)
        self.assertIn("像一個自然、有人味的人", self.src)
        self.assertIn("不是你表演、他觀看", self.src)
        # 只准「像真人」、不准「是真人」：身分誠實紅線在底層 CORE，這裡不得出現身分宣稱
        self.assertNotIn("你是真人", self.src)
        self.assertNotIn("你是一個真人", self.src)

    def test_name_addressing_restraint(self):
        """2026-07-16 Edward「回話會一直叫用戶名稱」：名字要用對、頻率要像真人。"""
        self.assertIn("打招呼時用一次就好", self.src)
        self.assertIn("大多數回合直接說話、不加稱呼", self.src)
        self.assertIn("每一句都叫他的名字非常不自然", self.src)
        # 舊的過頭寫法（模型讀成「每句都要叫」）不得回歸
        self.assertNotIn("整段對話都用", self.src)

    def test_voice_only_reality_rule(self):
        """2026-07-16 Edward 抓到「怎麼突然傳貼圖」幻覺：純語音現實邊界必須封死。"""
        self.assertIn("現實邊界", self.src)
        self.assertIn("純語音通話", self.src)
        self.assertIn("沒有貼圖", self.src)
        self.assertIn("不要猜測他做了什麼動作", self.src)

    def test_story_moral_rule_present(self):
        self.assertIn("[說故事與在地內容]", self.src)
        self.assertIn("寓意", self.src)
        self.assertIn("不要講一半沒收尾", self.src)

    def test_taiwan_first_content_rule_present(self):
        self.assertIn("預設以台灣為主", self.src)
        self.assertIn("俗諺", self.src)
        # 2026-07-17 通話中即時查詢預設關掉後，「先查證再講史實」已經做不到。
        # 但這條守的原意沒變——**不要編史實**——只是改成「不確定就不要講、讓他自己講」。
        self.assertIn("不確定的史實就不要講", self.src)
        self.assertIn("也不要編", self.src)

    def test_live_search_is_server_controlled_and_observable(self):
        """即時查詢預設已關（2026-07-17 Edward 拍板），但程式全留著、一個環境變數就回來。
        本條守的是「**萬一開回來**，那條路仍然必須是伺服器控制、先出聲、可觀測」——
        契約不變，只是工具改成有條件掛載。"""
        self.assertIn("Voice 伺服器會先替你播放", self.src)
        self.assertIn("禁止先沉默查詢", self.src)
        self.assertNotIn("先安靜查一下再回", self.src)
        # 舊寫法 tools = [_LIVE_LOOKUP_TOOL]（無條件掛）→ 改成有條件掛
        self.assertIn("if live_lookup_enabled():", self.src)
        self.assertIn("tools.append(_LIVE_LOOKUP_TOOL)", self.src)
        self.assertIn("if function_name == live_lookup.TOOL_NAME", self.src)
        tool_flow = self.src[self.src.index("if function_name == live_lookup.TOOL_NAME"):]
        self.assertLess(tool_flow.index("response = await _run_live_lookup"),
                        tool_flow.index("else:"))
        self.assertLess(tool_flow.index("else:"), tool_flow.index('"type": "action"'))
        flow = self.src[self.src.index("async def _run_live_lookup"):]
        self.assertLess(flow.index("await _send_lookup_cue()"),
                        flow.index("search_current_information(_cli"))
        for event in ("node.lookup_started", "node.lookup_cue_sent", "node.lookup_done",
                      "node.lookup_failed", "node.lookup_answer_audio"):
            self.assertIn(event, self.src)
        self.assertIn("asyncio.wait_for(", flow)
        self.assertIn('lookups=st["lookup_count"]', self.src)

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
