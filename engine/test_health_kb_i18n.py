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
        prof = {"audience": "elder"}
        for tid in ("TW-EDU-01", "TW-EDU-18", "TW-EDU-16", "TW-EDU-03"):
            zh = [s["id"] for s in hs.pick(tid, "", prof, 22)["solutions"]]
            for loc in locales_with_overlay():
                got = [s["id"] for s in hs.pick(tid, "", prof, 22, locale=loc)["solutions"]]
                self.assertEqual(got, zh, f"{loc}/{tid} 挑的方案跟中文不一樣")

    def test_safety_removal_still_works_in_every_locale(self):
        """禁忌是硬剔除——出國之後也一樣，不能只有中文那條線在守。"""
        prof = {"audience": "elder", "conditions": ["腎功能異常"]}
        for loc in locales_with_overlay():
            ids = [s["id"] for s in hs.pick("TW-EDU-01", "", prof, 23, locale=loc)["solutions"]]
            self.assertNotIn("sleep-magnesium-supplement", ids, f"{loc}：腎功能異常還端出鎂")


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
