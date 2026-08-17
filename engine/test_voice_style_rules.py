#!/usr/bin/env python3
"""語音說明書風格規則契約（Edward 2026-07-15 · 1.0.11 實測）：
①句尾不要一直反問 ②故事要有寓意、有收尾 ③內容預設台灣在地。
規則若被改掉或誤刪，這裡會亮紅燈。"""
import os
import importlib
import re
import sys
import tempfile
import unittest

SRC = os.path.join(os.path.dirname(__file__), "live_voice_server.py")
PERSONA_DIR = os.path.join(os.path.dirname(__file__), "persona")
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("MUNEA_DATABASE_PROVIDER", "json")


def _voice_style_book(locale):
    path = os.path.join(PERSONA_DIR, f"voice-style.{locale}.txt")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _voice_sections_book(locale):
    path = os.path.join(PERSONA_DIR, f"voice-sections.{locale}.txt")
    if not os.path.exists(path):
        return ""
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
        # 2026-08-13 分節搬遷：剩下寫死在程式碼裡的中文段落也搬進 voice-sections.<語系>.txt
        #（原因：英文／西文說明書裡本來夾著兩千多個中文字，因為這些段落沒有分語系）。
        # 這支守的東西沒變（規則被刪就要亮紅燈），只是現在要連書一起看——
        # 兩邊合起來當作「說明書的全文」。
        with open(SRC, encoding="utf-8") as f:
            self.src = f.read() + _voice_style_book("zh-TW") + _voice_sections_book("zh-TW")

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

    def test_turn_taking_waits_for_unfinished_thoughts_and_chunks_long_answers(self):
        """GPT Live 對齊：不把沉默一律當句點；長回答要像說話，不像朗讀稿。"""
        self.assertIn("未完線索", self.src)
        self.assertIn("把短暫沉默當成他還在想", self.src)
        self.assertIn("先說結論", self.src)
        self.assertIn("口語路標", self.src)
        self.assertIn("對方一插話就停", self.src)
        self.assertIn("不硬把原稿講完", self.src)

    def test_prosody_follows_acoustic_emotion_without_forced_fillers(self):
        self.assertIn("[即時語音韻律與情緒]", self.src)
        self.assertIn("不要只看逐字內容", self.src)
        self.assertIn("聲量柔一級、語速慢一級", self.src)
        self.assertIn("每個重點之間要有可接話的空隙", self.src)
        self.assertIn("不要戲劇化模仿情緒", self.src)
        self.assertIn("不要固定塞", self.src)

    def test_realtime_contract_is_single_and_labeled(self):
        """Realtime 行為只留一份短契約，避免多組人格例句互相拉扯。"""
        self.assertEqual(1, self.src.count("[即時通話互動契約]"))
        for action in ("一次只推進一件事", "一次問一件", "不要猜他做了什麼", "消化成口語"):
            self.assertIn(action, self.src)

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
    """已授書的每一國，語音風格的七節都必須在。

    授書＝用另一種語言重寫一整套口語規則。漏抄一節不會有錯誤訊息——
    電話照樣打得通，只是那一國的長輩會遇到一個講太多、一直反問、
    一接通就很high 的她。所以逐本檢查骨架。
    """

    SECTIONS_BY_LOCALE = {
        "zh-TW": ("[即時語音話量上限]", "[即時語音能量]", "[即時語音韻律與情緒]", "[開場升溫]",
                  "[句尾收法]", "[說故事與在地內容]", "[接住情緒與陪伴引導]"),
        "ja": ("[リアルタイム音声・話す量の上限]", "[リアルタイム音声・声の温度]", "[リアルタイム音声・韻律と感情]",
               "[話しはじめの温度]", "[文の終わり方]", "[話と、その土地のこと]",
               "[気持ちを受けとめ、寄り添って導く]"),
        "en": ("[Live speech · how much to say]", "[Live speech · energy]", "[Live speech · prosody and emotion]",
               "[Warming up at the start]", "[How to end a sentence]",
               "[Stories and local things]", "[Holding a feeling and walking with them]"),
        "es": ("[Voz en directo · cuánto hablar]", "[Voz en directo · energía]", "[Voz en directo · prosodia y emoción]",
               "[El arranque, de menos a más]", "[Cómo terminar una frase]",
               "[Historias y cosas de aquí]", "[Sostener lo que siente y acompañarle]"),
    }

    def test_every_book_keeps_the_seven_sections(self):
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


class VoicePromptBudgetTest(unittest.TestCase):
    """提示預算與搜尋模式互斥契約。

    這不是把字數當品質；它防止已刪掉的重複規則、例句與互斥搜尋說明悄悄長回來。
    醫療、安全、權限與工具規則仍由上面的行為測試各自守住。

    2026-08-10（Edward 拍板「先分節」）改成**只算內容、不算排版**：
    說明書從一整段長文改成分節條列後，換行讓字數多了約 80——那些是排版、不是新規則。
    照舊寫法，「把長文切成小節」這種只有好處的改動會被守門擋下來，而真正該擋的
    重複規則反而可以靠刪掉幾個空白偷渡進來。改成把空白全部去掉再量，排版怎麼改都
    不影響額度，長回來的規則一個字都躲不掉——比舊寫法更緊，不是更鬆。

    2026-08-13～17 上調 260 字（16200→16460／16500→16760／17900→18160）。
    多出來的是聊天品質複測抓到的六條真實失分，每一條都對應一次她講錯話：
    不主動挖傷心事、轉介求助不要打斷、保住他的面子、保密不能亂答應（紅線⑦）、
    不要用「我看在眼裡」這種眼睛的說法（她只有聲音）、日期不要自己算
    （她編過一個錯的國曆日期，長輩會照著去拜拜）、手上沒有傳話工具就不能說
    「我幫你聯絡家人」。調之前先驗過沒有贅肉可以先砍：把說明書切成 285 個
    句子兩兩比對，只有 7 對高度重疊、合計約 150 字，而且多數是各開關段落
    各自該有的工具規則，砍掉會讓單獨開某個開關時失去規則。
    8/17 再 +50：她跟長輩說「我剛剛這邊有點卡住了」——那是機器在報告自己的狀況，
    對方只會以為是自己的手機壞了。補在「聽不清楚怎麼辦」旁邊，四語一起。
    8/17 再 +110：規則自己打架——⑦說不准替第三人斷言，⑤卻明文鼓勵「幫忙把
    『他其實是關心你』翻譯出來」。她照⑤做了、被⑦判違反。給⑤補上界線：
    翻譯只能用在他自己講過的家人言行上，沒講過的不可以替家人擔保心意。
    8/17 再 +90（只影響有給工具的那通）：她把「時間我幫你改了喔」寫進要傳給
    兒子的話裡——收件人會以為行程真的被改了。傳過去的那句只能有他交代的內容。
    """

    @staticmethod
    def _content_len(prompt):
        """只算真正的內容：空白、換行、縮排一律不計。"""
        return len(re.sub(r"\s+", "", prompt))

    @staticmethod
    def _render(search_enabled, **kwargs):
        # 2026-08-10：量之前先把「今日簡報」隔開。那是**當天的資料**、不是規則，
        # 而且它存在 engine/perception_snapshots.json——同一輪測試裡前面幾支會寫進去，
        # 於是這支量到的長度會跟著前面跑過什麼而變（實測差 202 字），紅燈紅得莫名其妙。
        # 這支守的是「刪掉的重複規則有沒有偷偷長回來」，所以只量規則、不量當天資料。
        #
        # 2026-08-17 補：不只今日簡報。使用者記憶、關係側寫、個人檔案也一樣會被吃進
        # 說明書——本機跑過幾輪聊天品質考卷之後，「長輩今天去復健」「我孫子下個月結婚」
        # 這些留下來的資料就進了說明書，實測讓字數多出 431。跟簡報同一個道理：
        # 那是使用者資料、不是規則。全部指到不存在的暫存檔，閘門就只量規則本身，
        # 誰在這台機器上跑過什麼都不影響。
        _ISOLATED = (
            "MUNEA_PERCEPTION_SNAPSHOTS_PATH",   # 今日簡報（天氣、明天預告）
            "MUNEA_MEMORY_ITEMS_PATH",           # 長期記憶
            "MUNEA_RELATIONSHIP_STATES_PATH",    # 熟識度與關係狀態
            "MUNEA_COMPANION_PROFILE_PATH",      # 陪伴側寫
            "MUNEA_PERSON_PROFILE_PATH",         # 個人資料
            "MUNEA_APP_PROFILE_STORE_PATH",      # App 端側寫
        )
        env_backup = {
            key: os.environ.get(key)
            for key in ("MUNEA_VOICE_LIVE_LOOKUP",) + _ISOLATED
        }
        os.environ["MUNEA_VOICE_LIVE_LOOKUP"] = "1" if search_enabled else "0"
        for key in _ISOLATED:
            os.environ[key] = os.path.join(
                tempfile.gettempdir(), f"munea-prompt-budget-{key.lower()}.json")
        try:
            # server.py 的資料檔路徑是**模組載入時**就決定的（PERSON_PROFILE_PATH = 環境變數 or 預設）。
            # 只重載 live_voice_server 不夠——只要同一輪測試裡有別支先載過 server，
            # 那些常數早就指向本機真實資料檔，上面設的環境變數根本來不及生效，
            # 於是這支單獨跑是綠的、跟別支一起跑就紅（2026-08-13 查了半天的那個怪象）。
            import server
            importlib.reload(server)
            import live_voice_server
            module = importlib.reload(live_voice_server)
            return module.system_instruction(**kwargs)
        finally:
            for key, old in env_backup.items():
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old

    def test_prompt_budget_for_current_production_shape(self):
        prompt = self._render(True)
        self.assertLessEqual(self._content_len(prompt), 16650)
        self.assertEqual(1, prompt.count("[即時通話互動契約]"))
        self.assertEqual(1, prompt.count("[即時資訊｜內建搜尋]"))
        self.assertNotIn("[即時資訊｜無搜尋]", prompt)
        self.assertNotIn("Voice 伺服器會先替你播放", prompt)

    def test_prompt_budget_for_capability_rich_call(self):
        prompt = self._render(
            True,
            allow_reminders=True,
            allow_events=True,
            allow_care_questions=True,
            user="阿明",
            name="寧寧",
        )
        self.assertLessEqual(self._content_len(prompt), 18450)
        for hard_rule in (
            "絕對不准用查到的網路內容回答",
            "只有工具回覆 status=ok 才能說設好了",
            "你是幫他**保管問題**、不是**回答問題**",
        ):
            self.assertIn(hard_rule, prompt)

    def test_no_search_mode_is_explicit_and_non_conflicting(self):
        prompt = self._render(False)
        self.assertLessEqual(self._content_len(prompt), 16950)
        self.assertEqual(1, prompt.count("[即時資訊｜無搜尋]"))
        self.assertNotIn("[即時資訊｜內建搜尋]", prompt)
        self.assertIn("你沒有辦法上網查東西", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
