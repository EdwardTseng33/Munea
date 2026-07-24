#!/usr/bin/env python3
"""B2 衛教知識庫契約（2026-07-24 拍板 · 混合式）：
①21 題策展題庫齊全、每題有觸發字／注入文／出處 ②常駐保命紅線（中風FAST／心梗／
低血糖／急性譫妄＋褪黑激素法規）真的進了 chat_engine.RED ③關鍵字比對命中該命中的、
不亂命中 ④注入量有上限（衛教是配菜、不淹沒安全紅線）⑤語音線／文字線接線點都在。
資料庫內容被改壞、接線被誤刪，這裡會亮紅燈。"""
import os
import re
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import health_kb

HERE = os.path.dirname(os.path.abspath(__file__))


class HealthTopicsDataTest(unittest.TestCase):
    def test_21_topics_all_present_with_unique_ids(self):
        self.assertEqual(len(health_kb.TOPICS), 21)
        ids = [t["id"] for t in health_kb.TOPICS]
        self.assertEqual(len(set(ids)), 21)
        self.assertEqual(sorted(ids), [f"TW-EDU-{n:02d}" for n in range(1, 22)])

    def test_every_topic_has_required_fields(self):
        for t in health_kb.TOPICS:
            self.assertTrue(t["title"], t["id"])
            self.assertIn(t["category"], ("保健品期待型", "必須嚴管轉介型", "純生活型"), t["id"])
            self.assertTrue(t["keywords"], t["id"])
            self.assertTrue(t["source"], t["id"])
            # 注入文有內容、也有上限：衛教是配菜，太長會淹沒安全紅線（拍板：單次 500-700 字含包裝）
            self.assertGreaterEqual(len(t["inject"]), 120, t["id"])
            self.assertLessEqual(len(t["inject"]), 650, t["id"])

    def test_category_balance_matches_curated_script(self):
        """雙審裁決：三類各 7 題、不讓任一類過半。"""
        counts = {}
        for t in health_kb.TOPICS:
            counts[t["category"]] = counts.get(t["category"], 0) + 1
        self.assertEqual(counts, {"保健品期待型": 7, "必須嚴管轉介型": 7, "純生活型": 7})

    def test_strict_referral_topics_carry_referral_language(self):
        """嚴管轉介型 7 題：注入文必須帶轉介／就醫／119 方向，不能只有生活建議。"""
        for t in health_kb.TOPICS:
            if t["category"] != "必須嚴管轉介型":
                continue
            self.assertTrue(
                any(k in t["inject"] for k in ("就醫", "119", "轉介", "醫師")),
                f"{t['id']} 嚴管題缺轉介語言")

    def test_no_simplified_chinese_in_injects(self):
        """注入文會變成寧寧的話（字幕給長輩看）：一個簡體字都不行。"""
        simplified = "个没发药风见问长张medical".replace("medical", "") + "护记忆疗诊断压检说话请谢"
        for t in health_kb.TOPICS:
            for ch in simplified:
                self.assertNotIn(ch, t["inject"], f"{t['id']} 含簡體字「{ch}」")
        for ch in simplified:
            self.assertNotIn(ch, health_kb.resident_rules(), f"常駐紅線含簡體字「{ch}」")

    def test_no_dosage_numbers_in_injects(self):
        """三條不變紅線之一：不報劑量。注入文自己就不能出現毫克／毫升劑量。"""
        for t in health_kb.TOPICS:
            self.assertIsNone(re.search(r"\d+\s*(毫克|mg|毫升|ml|顆|錠)", t["inject"]),
                              f"{t['id']} 注入文疑似出現劑量")


class ResidentRulesTest(unittest.TestCase):
    def test_resident_covers_four_emergencies_and_melatonin(self):
        r = health_kb.resident_rules()
        for needle in ("臉歪", "119", "心肌梗塞", "低血糖", "方糖或含糖飲料", "急性譫妄",
                       "褪黑激素在台灣是處方藥"):
            self.assertIn(needle, r)

    def test_resident_rules_flow_into_chat_engine_red(self):
        """常駐紅線併進 RED＝文字線（server /chat）、語音線（live system_instruction）、
        主動開口、評測 gen_reply 全部自動帶上——這條斷了等於整包白裝。"""
        import chat_engine
        self.assertIn("褪黑激素在台灣是處方藥", chat_engine.RED)
        self.assertIn("急性譫妄", chat_engine.RED)


class MatchingTest(unittest.TestCase):
    def test_elder_phrasings_hit_expected_topics(self):
        cases = [
            ("我最近攏睡不著，是不是要吃安眠藥才睡得著", "TW-EDU-01"),
            ("我這個膝蓋一直卡卡的，上下樓梯會痛", "TW-EDU-02"),
            ("我血壓量起來高高低低，是不是要換藥", "TW-EDU-03"),
            ("常常口渴，是不是血糖高", "TW-EDU-04"),
            ("腳趾頭腫一粒紅紅的，是不是痛風", "TW-EDU-05"),
            ("我好幾天沒大號了，肚子脹脹的", "TW-EDU-06"),
            ("站起來眼前黑黑的會頭暈", "TW-EDU-07"),
            ("葉黃素有效嗎？我目睭霧霧的", "TW-EDU-08"),
            ("冬天皮膚癢得受不了，抓到都破皮", "TW-EDU-09"),
            ("晚上爬起來尿好幾次，尿不乾淨", "TW-EDU-10"),
            ("胸口酸酸的想吐酸水，火燒心", "TW-EDU-11"),
            ("流感針要不要打，聽說打了很不舒服", "TW-EDU-12"),
            ("吃東西常常嗆到，要弄很爛才吞得下", "TW-EDU-13"),
            ("話說到一半忘記要說什麼，是不是失智", "TW-EDU-14"),
            ("半夜小腿抽筋痛醒", "TW-EDU-15"),
            ("朋友介紹我吃紅麴，跟血壓藥一起吃可以嗎", "TW-EDU-16"),
            ("醫生說我骨頭空空的，要不要補鈣", "TW-EDU-17"),
            ("最近都提不起勁，什麼都不想做", "TW-EDU-18"),
            ("感冒一直好不了，鼻水流不停", "TW-EDU-19"),
            ("心臟一直咚咚咚跳很快", "TW-EDU-20"),
            ("LINE群組傳的這個是真的假的", "TW-EDU-21"),
            # 7/24 首輪評測抓漏：「群組在傳」「是真的嗎」這種說法原本接不住、謠言資料叫不出來
            ("LINE群組在傳說吃降血壓藥會洗腎，是真的嗎", "TW-EDU-21"),
        ]
        for text, want in cases:
            got = health_kb.match_topics(text)
            self.assertIn(want, got, f"「{text}」應命中 {want}、實際 {got}")

    def test_everyday_smalltalk_hits_nothing(self):
        for text in ("今天天氣真好想去公園走走", "我孫子這次考試考很好", "晚餐想吃什麼好呢",
                     "昨天那齣連續劇很好看"):
            self.assertEqual(health_kb.match_topics(text), [], f"「{text}」不該命中")

    def test_injection_respects_turn_limit_and_length(self):
        # 一句話跨很多題：最多注入 MAX_TOPICS_PER_TURN 題、總長度有上限
        text = "我睡不著、膝蓋痛、血壓又高、還常常便秘跟頭暈"
        ids = health_kb.match_topics(text)
        self.assertLessEqual(len(ids), health_kb.MAX_TOPICS_PER_TURN)
        inj = health_kb.injection_for(text)
        self.assertLessEqual(len(inj), 1500)
        self.assertIn("衛教資料庫命中", inj)

    def test_no_match_returns_empty_string_not_noise(self):
        self.assertEqual(health_kb.injection_for("今天天氣真好"), "")
        self.assertEqual(health_kb.injection_for(""), "")
        self.assertEqual(health_kb.injection_for(None), "")

    def test_exclude_prevents_repeat_injection(self):
        first = health_kb.match_topics("我都睡不著", limit=1)
        self.assertEqual(first, ["TW-EDU-01"])
        again = health_kb.match_topics("我都睡不著", limit=1, exclude=set(first))
        self.assertEqual(again, [])

    def test_voice_cue_never_read_aloud_instruction(self):
        cue = health_kb.voice_cue("TW-EDU-01")
        self.assertIn("不是用戶說的話", cue)
        self.assertIn("絕不把這段提示唸出來", cue)
        self.assertIn("一兩句短話", cue)


class WiringContractTest(unittest.TestCase):
    """接線點契約：誤刪任何一條、這裡亮紅燈。"""

    def _read(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return f.read()

    def test_text_line_injects_on_last_user_message(self):
        src = self._read("server.py")
        self.assertIn("health_kb.injection_for(last_user)", src)

    def test_voice_line_watches_user_captions_and_flushes_at_turn_gap(self):
        src = self._read("live_voice_server.py")
        self.assertIn("health_watch_user_text(cid, st)", src)
        self.assertIn("pending_health_cue", src)
        # 衛教必須排在安全導引之後（安全永遠先講）
        self.assertIn("衛教排在安全導引之後", src)
        # 每通上限：不把通話變衛教講座
        self.assertIn("MAX_TOPICS_PER_CALL", src)

    def test_eval_mirrors_production_injection(self):
        src = self._read(os.path.join("eval", "gen_reply.py"))
        self.assertIn("health_kb.injection_for(case[\"userLine\"])", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
