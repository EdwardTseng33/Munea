#!/usr/bin/env python3
"""語音說明書風格規則契約（Edward 2026-07-15 · 1.0.11 實測）：
①句尾不要一直反問 ②故事要有寓意、有收尾 ③內容預設台灣在地。
規則若被改掉或誤刪，這裡會亮紅燈。"""
import os
import unittest

SRC = os.path.join(os.path.dirname(__file__), "live_voice_server.py")
PERSONA_DIR = os.path.join(os.path.dirname(__file__), "persona")


def _voice_style_book(locale):
    path = os.path.join(PERSONA_DIR, f"voice-style.{locale}.txt")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _shipped_voice_style_locales():
    if not os.path.isdir(PERSONA_DIR):
        return []
    return sorted(
        name[len("voice-style."):-len(".txt")]
        for name in os.listdir(PERSONA_DIR)
        if name.startswith("voice-style.") and name.endswith(".txt")
    )


class VoiceStyleRulesTest(unittest.TestCase):
    def setUp(self):
        # 2026-07-31 口語風格分國：規則從程式碼搬進 engine/persona/voice-style.<語系>.txt。
        # 這支守的東西沒變（規則被刪就要亮紅燈），只是現在要連書一起看——
        # 兩邊合起來當作「說明書的全文」。
        with open(SRC, encoding="utf-8") as f:
            self.src = f.read() + _voice_style_book("zh-TW")

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

    def test_response_length_is_task_adaptive(self):
        """語音預設精簡，但不能把解釋、比較、健康資訊與故事硬砍成兩句。"""
        self.assertIn("短是預設，不是硬上限", self.src)
        for task_shape in ("直接答案", "健康說明", "比較、做法", "故事要講完整", "工具結果"):
            self.assertIn(task_shape, self.src)
        self.assertIn("二十到四十秒", self.src)
        self.assertIn("我的看法是", self.src)
        self.assertIn("嗯，我的看法是", self.src)
        self.assertIn("安靜等他", self.src)
        self.assertNotIn("一般閒聊預設只回答一句", self.src)
        # 2026-08-04 GPT Live 對齊：舊的視訊框架／熟識度規則不能再用全域
        # 「一次一兩句」蓋掉上面的任務式話量。需要短的場景仍由風格書明確指定，
        # 但健康說明、比較、做法與故事要能完整講完。
        for conflicting_rule in (
            "句子短、口語、一次一兩句",
            "一次還是一兩句、問完停下來聽",
            "一次還是一兩句、不長篇",
            "仍別長篇",
        ):
            self.assertNotIn(conflicting_rule, self.src)
        self.assertIn("一次只推進一件事", self.src)
        self.assertIn("對方明確想深入、比較、聽完整說明或故事時再自然展開", self.src)

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
        """2026-07-16 Edward 抓到「怎麼突然傳貼圖」幻覺：純語音現實邊界必須封死。

        2026-07-29 說明書瘦身：原「現實邊界」＋「語音自覺」兩段併成「純語音的現實」
        （同一個現實的兩半：他傳不了給你＋你給不了他），規則一條不丟、只改字面。
        """
        self.assertIn("純語音的現實", self.src)
        self.assertIn("他傳不了任何東西給你", self.src)
        self.assertIn("沒有貼圖", self.src)
        self.assertIn("不要猜他做了什麼", self.src)
        # 2026-07-28 S09：不叫他做任何你看不到的事（「用指的給我看」）——瘦身後仍要在
        self.assertIn("用指的給我看", self.src)

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
        # 2026-07-25 去罐頭化：_send_lookup_cue 改吃 category 參數挑貼題過場話，
        # 呼叫點仍必須在真的打網路查詢之前。
        self.assertLess(flow.index("await _send_lookup_cue(category, response_locale)"),
                        flow.index("search_current_information("))
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

    def test_voice_self_awareness_rule_present(self):
        """2026-07-24 Edward 拍板「語音自覺」：她要知道自己只是聲音，不能講出「傳給你」
        這類空話；查到的資料要先消化成口語，不是唸條列。通用規則，不得綁死長輩措辭。

        2026-07-29 瘦身後這半邊住在「純語音的現實」段（你給不了他任何東西）。"""
        self.assertIn("你也給不了他任何東西", self.src)
        for banned_phrase in ("我傳給你", "你看一下這張圖", "詳見某某網站"):
            self.assertIn(banned_phrase, self.src)
        self.assertIn("一次最多三件事", self.src)
        self.assertIn("消化成口語", self.src)
        # 措辭不得綁死「長輩」——這是純語音通話的通用限制，不是年齡層專屬規則
        self_awareness = self.src[self.src.index("純語音的現實：你們之間只有「聲音」"):
                                   self.src.index("讓他消化或接話。）")]
        self.assertNotIn("長輩", self_awareness)



class EveryShippedVoiceStyleBookTest(unittest.TestCase):
    """已授書的每一國，語音風格的六節都必須在。

    授書＝用另一種語言重寫一整套口語規則。漏抄一節不會有錯誤訊息——
    電話照樣打得通，只是那一國的長輩會遇到一個講太多、一直反問、
    一接通就很high 的她。所以逐本檢查骨架。
    """

    SECTIONS_BY_LOCALE = {
        "zh-TW": ("[即時語音話量上限]", "[即時語音能量]", "[開場升溫]",
                  "[句尾收法]", "[說故事與在地內容]", "[接住情緒與陪伴引導]"),
        "ja": ("[リアルタイム音声・話す量の上限]", "[リアルタイム音声・声の温度]",
               "[話しはじめの温度]", "[文の終わり方]", "[話と、その土地のこと]",
               "[気持ちを受けとめ、寄り添って導く]"),
        "en": ("[Live speech · how much to say]", "[Live speech · energy]",
               "[Warming up at the start]", "[How to end a sentence]",
               "[Stories and local things]", "[Holding a feeling and walking with them]"),
        "es": ("[Voz en directo · cuánto hablar]", "[Voz en directo · energía]",
               "[El arranque, de menos a más]", "[Cómo terminar una frase]",
               "[Historias y cosas de aquí]", "[Sostener lo que siente y acompañarle]"),
    }

    def test_every_book_keeps_the_six_sections(self):
        for locale in _shipped_voice_style_locales():
            sections = self.SECTIONS_BY_LOCALE.get(locale)
            self.assertIsNotNone(
                sections,
                f"{locale}：授了語音風格書卻沒登記章節骨架——這支守不到它，等於沒守",
            )
            book = _voice_style_book(locale)
            for section in sections:
                self.assertIn(section, book, f"{locale}：語音風格缺了 {section} 這一節")

    def test_every_book_forbids_back_to_back_questions(self):
        """「不准連續兩輪都用問題收尾」是 Edward 兩次真機回報後立的硬規矩，每一國都要有。"""
        markers = {
            "zh-TW": "不准連續兩輪都用問題收尾",
            "ja": "二巡続けて質問で終えてはいけません",
            "en": "never end two turns in a row with a question",
            "es": "nunca termine dos turnos seguidos con una pregunta",
        }
        for locale in _shipped_voice_style_locales():
            marker = markers.get(locale)
            if not marker:
                continue
            self.assertIn(marker, _voice_style_book(locale),
                          f"{locale}：少了「不准連續兩輪反問」的硬規矩")


if __name__ == "__main__":
    unittest.main(verbosity=2)
