#!/usr/bin/env python3
"""衛教庫一國一庫契約（2026-07-31 · Edward 拍板「B 就是開始做」）。

**為什麼**：產品已是四國版（人設書一國一本），但衛教庫的觸發字全是繁中——
日英西用戶等於拿到「沒有健康大腦的寧寧」；而內容裡的 1925／1966／健保 全是台灣的，
萬一被觸發，會把台灣的自殺防治專線講給美國人聽。

這支守三件事，任何一條紅了都不准出貨：
1. **敗向安全**：沒疊層＝不出手；某方案沒翻＝不端出來；**轉介卡沒翻＝整題不上**
   （安全話術絕不退回中文）。
2. **號碼不准串門**：每一國只准出現自己查證過的號碼。
   美國人在低潮時聽到 1925 是最壞的一種錯。
3. **中文不准漏進外語**：翻好的說法裡出現中日韓字＝那句沒翻乾淨。
"""
import os
import re
import unittest

os.environ.setdefault("GEMINI_API_KEY", "dummy-for-contract-test")

import health_i18n_layer as i18n
import health_kb
import health_selector as hs

CJK = re.compile(r"[一-鿿぀-ヿ]")

# 各國自己的號碼（查證紀錄：docs/ 四國急難號碼）＋別國的號碼（絕不准出現）
OWN = {
    "en": {"911", "988"},
    "ja": {"119", "110", "#7119", "0120-279-338"},
    "es": {"112", "024", "061"},
}
FOREIGN = {
    "en": ["1925", "1966", "112", "024", "0120-279-338", "#7119"],
    "ja": ["1925", "1966", "911", "988", "112", "024"],
    "es": ["1925", "1966", "911", "988", "#7119"],
}


def locales_with_overlay():
    return [loc for loc in ("ja", "en", "es") if i18n.overlay(loc)]


class ArchitectureTest(unittest.TestCase):
    def test_chinese_behaviour_is_untouched(self):
        """zh-TW＝主庫本身，一國一庫上線後行為必須零改變。"""
        self.assertIsNone(i18n.overlay("zh-TW"))
        self.assertEqual(health_kb.match_topics("我睡不好")[:1], ["TW-EDU-01"])
        picked = hs.pick("TW-EDU-01", "我睡不好", {"audience": "worker"}, 23)["solutions"]
        self.assertTrue(picked)

    def test_a_locale_without_an_overlay_stays_silent(self):
        """沒建疊層的語系＝衛教整個不出手，不是拿中文字去比對外語。"""
        self.assertEqual(health_kb.match_topics("Ich kann nicht schlafen", locale="de"), [])

    def test_missing_referral_takes_the_whole_topic_down(self):
        """轉介卡沒翻＝整題不上（安全話術不能是外語）。"""
        sols = [{"id": "a", "riskLevel": "L1", "say": "中文"},
                {"id": "r", "riskLevel": "L5", "say": "中文轉介"}]
        real = i18n.overlay
        i18n.overlay = lambda loc: {"T": {"solutions": {"a": {"say": "translated"}}}}
        try:
            self.assertEqual(i18n.localized_solutions("T", sols, "en"), [])
        finally:
            i18n.overlay = real

    def test_untranslated_solutions_are_dropped_not_shown_in_chinese(self):
        sols = [{"id": "a", "riskLevel": "L1", "say": "中文A"},
                {"id": "b", "riskLevel": "L1", "say": "中文B"},
                {"id": "r", "riskLevel": "L5", "say": "中文轉介"}]
        real = i18n.overlay
        i18n.overlay = lambda loc: {"T": {"solutions": {
            "a": {"say": "translated A"}, "r": {"say": "translated refer"}}}}
        try:
            out = i18n.localized_solutions("T", sols, "en")
            self.assertEqual([s["id"] for s in out], ["a", "r"])
            self.assertTrue(all(not CJK.search(s["say"]) for s in out))
        finally:
            i18n.overlay = real

    def test_chinese_askedfor_never_leaks_into_a_foreign_overlay(self):
        """中文的點名觸發字在外語對話裡永遠比不到——疊層沒給就要清空。"""
        sols = [{"id": "a", "riskLevel": "L1", "say": "中文", "askedFor": ["葡萄糖胺"]},
                {"id": "r", "riskLevel": "L5", "say": "中文轉介"}]
        real = i18n.overlay
        i18n.overlay = lambda loc: {"T": {"solutions": {
            "a": {"say": "translated"}, "r": {"say": "refer"}}}}
        try:
            out = i18n.localized_solutions("T", sols, "en")
            self.assertEqual(out[0]["askedFor"], [])
        finally:
            i18n.overlay = real


class NoForeignNumbersTest(unittest.TestCase):
    """別國的號碼絕不准串門——美國人在低潮時聽到 1925 是最壞的一種錯。"""

    @staticmethod
    def _mentions_number(text, number):
        """號碼要當成獨立的一串數字比對——「2024年」裡面有「024」不算西班牙的專線。"""
        return re.search(r"(?<!\d)" + re.escape(number) + r"(?!\d)", text or "") is not None

    def test_each_locale_only_carries_its_own_numbers(self):
        for loc in locales_with_overlay():
            blob = "\n".join(
                sol.get("say", "")
                for entry in i18n.overlay(loc).values()
                for sol in (entry.get("solutions") or {}).values())
            for bad in FOREIGN[loc]:
                self.assertFalse(self._mentions_number(blob, bad),
                                 f"{loc} 的內容出現了別國的號碼 {bad}")

    def test_escalation_is_never_lost_in_translation(self):
        """**翻譯不准把急救指示弄丟。**

        主庫那張卡如果叫人打 119，翻出來就必須給當地的急難號碼；
        主庫本來只說「儘快去看醫生」的（例如吃保健品後不舒服），不必硬塞號碼
        ——硬塞會變成把普通不適升級成危機，那跟急症紅線的設計互相打架。
        """
        import json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "health_solutions.json"), encoding="utf-8") as f:
            master = json.load(f)["topics"]
        for loc in locales_with_overlay():
            for tid, entry in i18n.overlay(loc).items():
                zh = {s["id"]: s for s in (master.get(tid) or {}).get("solutions", [])}
                for sid, sol in (entry.get("solutions") or {}).items():
                    zh_say = zh.get(sid, {}).get("say") or ""
                    # 「叫救護車」跟「打119」是同一件事——只認數字會漏掉半數的急救卡
                    if "119" not in zh_say and "救護車" not in zh_say:
                        continue                      # 主庫沒有急救指示＝不必有
                    self.assertTrue(any(self._mentions_number(sol.get("say", ""), n)
                                        for n in OWN[loc]),
                                    f"{loc}/{tid}/{sid}：主庫叫人打119，翻出來卻沒有當地急難號碼")


class TranslationQualityTest(unittest.TestCase):
    def test_no_chinese_residue_in_foreign_overlays(self):
        for loc in locales_with_overlay():
            for tid, entry in i18n.overlay(loc).items():
                for sid, sol in (entry.get("solutions") or {}).items():
                    for field in ("say", "label"):
                        val = sol.get(field) or ""
                        self.assertFalse(CJK.search(val) and loc != "ja",
                                         f"{loc}/{tid}/{sid} 的 {field} 還留著中文")

    def test_keywords_are_in_the_local_language(self):
        """觸發字必須是那一國長輩真的會講的話——留中文＝永遠觸發不到。"""
        for loc in locales_with_overlay():
            if loc == "ja":
                continue                       # 日文本來就用漢字，另外驗
            for tid, entry in i18n.overlay(loc).items():
                for kw in entry.get("keywords") or []:
                    self.assertFalse(CJK.search(kw), f"{loc}/{tid} 的觸發字還是中文：{kw}")

    def test_latin_locales_ignore_capitalisation(self):
        """「No puedo dormir」大寫開頭也要叫得出來——中文沒有大小寫，這個坑出國才踩到。"""
        for loc in locales_with_overlay():
            if loc == "ja":
                continue
            for tid, entry in i18n.overlay(loc).items():
                kws = entry.get("keywords") or []
                if not kws:
                    continue
                self.assertIn(tid, health_kb.match_topics(kws[0].capitalize(), locale=loc),
                              f"{loc}/{tid}：首字母大寫就叫不出來")
                self.assertIn(tid, health_kb.match_topics(kws[0].upper(), locale=loc),
                              f"{loc}/{tid}：全大寫就叫不出來")

    def test_a_latin_keyword_must_start_at_a_word(self):
        """拉丁語系的觸發字要從詞頭開始比。

        西班牙版回報：「tos（咳嗽）」被「hidra*tos*（醣類）」叫起來，問醣類的人
        會收到感冒衛教。中文沒有詞的空隙、必須用純包含比對，這個坑出國才踩到。
        只綁詞頭、不綁詞尾——「aliment」還是要命中「alimentación」，
        那正是我們要求觸發字寫詞根的原因。
        """
        self.assertNotIn("TW-EDU-19",
                         health_kb.match_topics("los hidratos de carbono", locale="es"))
        self.assertIn("TW-EDU-19", health_kb.match_topics("tengo mucha tos", locale="es"))
        self.assertIn("TW-EDU-19", health_kb.match_topics("TOS SECA", locale="es"))
        # 中文與日文不受影響：句中任何位置都要叫得出來
        self.assertIn("TW-EDU-01", health_kb.match_topics("我最近都睡不好"))
        self.assertIn("TW-EDU-01", health_kb.match_topics("最近よく眠れないんです", locale="ja"))

    def test_spanish_red_yeast_carries_the_eu_age_warning(self):
        """歐盟規定紅麴標示必須寫「逾 70 歲不得食用」——我們的用戶正好就是那群人。

        寫死句子這件事只用在這種反向守門：這句掉了，就是我們比包裝上的字還不謹慎。
        """
        es = i18n.overlay("es")
        if not es or "TW-EDU-16" not in es:
            self.skipTest("西班牙版還沒有保健品題")
        card = es["TW-EDU-16"]["solutions"]["supp-red-yeast"]
        self.assertIn("70", card["say"])
        self.assertIn("70", card.get("dailyCap", ""))

    def test_every_translated_topic_actually_fires(self):
        """有疊層就要叫得出來——翻了卻觸發不到等於沒做。"""
        for loc in locales_with_overlay():
            for tid, entry in i18n.overlay(loc).items():
                kws = entry.get("keywords") or []
                if not kws:
                    continue
                hit = health_kb.match_topics(kws[0], locale=loc)
                self.assertIn(tid, hit, f"{loc}/{tid} 用自己的觸發字卻叫不出來")


class SelectionParityTest(unittest.TestCase):
    """疊層只准換「說法」，不准換「挑哪幾個」。

    同一個人、同一個時間，各國挑出來的方案必須一模一樣——打分欄位（風險級／時效／
    禁忌／專屬度）本來就是語言中立的。哪天各國分歧了，代表有人在疊層裡動了不該動的。
    """

    def test_same_person_same_hour_picks_the_same_solutions(self):
        """沒略過任何卡的題目，四國挑出來的必須一字不差。

        有略過卡的題目（例如穴位按摩在美西沒有文化錨點）本來就會少一張、
        第三格由下一名遞補——那是敗向安全的正常結果，不是排序被動了手腳。
        所以這裡只對「完整翻譯」的題目要求嚴格一致，那才抓得到真的重排。
        """
        import json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "health_solutions.json"), encoding="utf-8") as f:
            master = json.load(f)["topics"]
        prof = {"audience": "elder"}
        checked = 0
        for loc in locales_with_overlay():
            for tid, entry in i18n.overlay(loc).items():
                have = set((entry.get("solutions") or {}).keys())
                all_ids = {s["id"] for s in (master.get(tid) or {}).get("solutions", [])}
                if all_ids - have:
                    continue                      # 這一國略過了幾張，不適用嚴格比對
                zh = [s["id"] for s in hs.pick(tid, "", prof, 22)["solutions"]]
                got = [s["id"] for s in hs.pick(tid, "", prof, 22, locale=loc)["solutions"]]
                self.assertEqual(got, zh, f"{loc}/{tid} 挑的方案跟中文不一樣＝排序被動了")
                checked += 1
        self.assertGreater(checked, 20, "完整翻譯的題目太少，這條守門等於沒在守")

    def test_every_served_card_is_a_translated_one(self):
        """略過的卡不准偷偷用中文補位——那是敗向安全的底線。"""
        prof = {"audience": "elder"}
        for loc in locales_with_overlay():
            for tid, entry in i18n.overlay(loc).items():
                have = set((entry.get("solutions") or {}).keys())
                for s in hs.pick(tid, "", prof, 22, locale=loc)["solutions"]:
                    self.assertIn(s["id"], have, f"{loc}/{tid} 端出了沒翻的 {s['id']}")

    def test_safety_removal_still_works_in_every_locale(self):
        """禁忌是硬剔除——出國之後也一樣，不能只有中文那條線在守。"""
        prof = {"audience": "elder", "conditions": ["腎功能異常"]}
        for loc in locales_with_overlay():
            ids = [s["id"] for s in hs.pick("TW-EDU-01", "", prof, 23, locale=loc)["solutions"]]
            self.assertNotIn("sleep-magnesium-supplement", ids, f"{loc}：腎功能異常還端出鎂")


class HonestRefusalsWorkAbroadTest(unittest.TestCase):
    """「他點名了就要答」這件事，不能只有中文那條線做得到。

    2026-07-31 抓到的是同一個病的兩層：主庫 31 張誠實回話卡（褪黑激素、換藥、
    瘦瘦針、排毒、IgG 檢測…）在挑選層被當成整條剔除，一次都沒講出來過；
    修好之後才發現**外語那邊還是死的**——疊層的點名字是敗向安全的（沒給就清空，
    免得中文字跑進外語對話），所以三國各有 29 張叫不出來。
    日本用戶問「メラトニンって飲んでもいいの？」，我們有稿卻拿不到。
    """

    @staticmethod
    def _blocked_ids():
        import json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "health_solutions.json"), encoding="utf-8") as f:
            topics = json.load(f)["topics"]
        return {s["id"]: tid for tid, t in topics.items()
                for s in t["solutions"] if s.get("blocked")}

    def test_every_blocked_card_can_be_named_in_every_locale(self):
        for loc in locales_with_overlay():
            ov = i18n.overlay(loc)
            for sid, tid in self._blocked_ids().items():
                sol = ((ov.get(tid) or {}).get("solutions") or {}).get(sid)
                if sol is None:
                    continue                  # 那一國略過了整張＝敗向安全，不算漏
                self.assertTrue(sol.get("askedFor"),
                                f"{loc}/{tid}/{sid} 沒有點名字＝這張卡在那一國是死的")

    def test_naming_it_serves_it_and_never_first(self):
        prof = {"audience": "elder", "audiences": ["elder"]}
        for loc in locales_with_overlay():
            ov = i18n.overlay(loc)
            for sid, tid in self._blocked_ids().items():
                sol = ((ov.get(tid) or {}).get("solutions") or {}).get(sid)
                if not (sol and sol.get("askedFor")):
                    continue
                said = sol["askedFor"][0]
                got = [s["id"] for s in hs.pick(tid, said, prof, 15, locale=loc)["solutions"]]
                self.assertIn(sid, got, f"{loc}/{tid}：他講了「{said}」還是沒回答")
                if len(got) > 1:
                    self.assertNotEqual(got[0], sid, f"{loc}/{tid}/{sid} 當了第一句")

    def test_capitalisation_never_loses_the_answer(self):
        """語音辨識會寫成「Plavix」「Ventolín」，我們的字典是小寫——比對必須忽略大小寫。"""
        for loc in locales_with_overlay():
            if loc == "ja":
                continue
            ov = i18n.overlay(loc)
            for sid, tid in self._blocked_ids().items():
                sol = ((ov.get(tid) or {}).get("solutions") or {}).get(sid)
                if not (sol and sol.get("askedFor")):
                    continue
                word = sol["askedFor"][0]
                if not word[:1].isalpha():
                    continue
                self.assertTrue(hs.mentions(word, word.upper()),
                                f"{loc}/{sid}：使用者用大寫講「{word}」就比不到了")


class WiringTest(unittest.TestCase):
    """接線鎖：做了但沒接上正式線＝白做（這個病 7 月已經犯過六次）。"""

    def _read(self, name):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name),
                  encoding="utf-8") as f:
            return f.read()

    def test_text_line_passes_locale(self):
        self.assertIn('locale=context.get("locale")', self._read("server.py"))

    def test_voice_line_passes_session_locale(self):
        src = self._read("live_voice_server.py")
        self.assertIn('_kb_locale = (st.get("voice_locale_profile") or {}).get("sessionLocale")', src)
        self.assertIn("match_topics(said, limit=1, exclude=sent, locale=_kb_locale)", src)
        self.assertIn("voice_cue(ids[0], said, _prof, _hour, locale=_kb_locale)", src)

    def test_selector_localizes_before_scoring(self):
        self.assertIn("_i18n.localized_solutions(topic_id, pool, locale)",
                      self._read("health_selector.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
