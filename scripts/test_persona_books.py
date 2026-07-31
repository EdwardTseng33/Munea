"""證據測試：每一本已授的人設說明書，保命規則與誠實紅線都真的在。

為什麼需要這支：說明書分國之後，「授書」＝把一整本 10KB 的規則用另一種語言重寫。
漏抄一段的後果不是文字醜，是**那一國的長輩少一層保護**（例如少了「不可以跟著他一起
放棄就醫」那條）。而漏抄不會有任何錯誤訊息——書照樣載得起來、電話照樣打得通。

所以這裡逐本檢查「必須存在的東西」：
  ① 佔位符已填（查詢段沒接上＝她會拿到一段沒意義的標記）
  ② 每一節的編號都在（⓪ ⓪-B … ⑦-B）——編號是章節骨架，缺號＝整節不見
  ③ 當地的急難號碼在紅線裡（號碼跟國家走、不跟語言走）
  ④ 沒有殘留別國的專屬內容（日文版不該出現台灣的專線號碼）

執行：python scripts/test_persona_books.py（也掛在 npm run test:launch 底下）
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))
os.environ.setdefault("GEMINI_API_KEY", "persona-book-contract-test")

import chat_engine as eng  # noqa: E402

# 章節骨架：這些編號在每一本書裡都必須出現（缺一個＝那一節整段漏抄）
REQUIRED_SECTIONS = (
    "⓪", "⓪-B", "⓪-C", "⓪-D", "⓪-D-1", "⓪-D-2", "⓪-D-3", "⓪-D-4",
    "⓪-E", "⓪-F", "①", "②", "②-B", "③", "④", "④-B", "④-C",
    "⑤", "⑥", "⑥-VISIT", "⑦", "⑦-B",
)

# 紅線的章節骨架
REQUIRED_RED_SECTIONS = ("①", "②", "③", "④", "⑤", "⑥")

# 2026-07-31 Edward 拍板翻面：**人設書裡不准出現寫死的急難號碼。**
# 原本每本書都硬寫自己母國的號碼（日文書寫 119、西班牙文書寫 112），
# 但語言不等於國家——講西班牙文的人可能在墨西哥（是 911），講英文的可能在英國。
# 現在號碼的唯一來源＝經過核定的「當地安全指引」（localization.regional_safety_instruction），
# 書裡只留規則：不知道他在哪就問一句，或說「打當地的緊急電話」，絕不自己猜一個數字。
FORBIDDEN_HARDCODED_NUMBERS = ("119", "911", "112", "110", "1925", "1995", "113",
                               "988", "024", "016", "0120-279-338", "1-800-677-1116")

# 每本書都必須留著「不准憑空報號碼」那條規則的關鍵字
REQUIRED_NO_GUESS_RULE = {
    "zh-TW": ("不准憑空講一個號碼", "你現在人在哪裡"),
    "ja": ("番号を自分で思い出して言ってはいけません", "今どちらにいらっしゃいますか"),
    "en": ("never state a number from your own memory", "Where are you right now"),
    "es": ("nunca diga un número de memoria", "¿Dónde se encuentra ahora?"),
}

# 別國專屬內容不得殘留（授書時整段複製貼上最容易犯）
FOREIGN_LEAKS = {
    "ja": ("台灣", "1925", "1995", "健保", "繁體中文"),
    "en": ("台灣", "1925", "1995"),
    "es": ("台灣", "1925", "1995"),
}


class PersonaBookContractTests(unittest.TestCase):
    def setUp(self):
        self.locales = eng.persona_locales()

    def test_at_least_the_home_locale_is_shipped(self):
        self.assertIn("zh-TW", self.locales, "繁中版是所有語系的退路，不能不在")

    def test_every_book_fills_its_lookup_slot(self):
        for locale in self.locales:
            for mode in ("offline", "online"):
                core = eng.core_instruction(mode, locale)
                self.assertNotIn(
                    "&&LOOKUP_SECTION&&", core,
                    f"{locale}／{mode}：查詢段沒接上，她會讀到一段沒意義的標記",
                )
                self.assertTrue(core.strip(), f"{locale}／{mode}：說明書是空的")

    def test_every_book_keeps_the_full_section_skeleton(self):
        for locale in self.locales:
            core = eng.core_instruction("offline", locale)
            for section in REQUIRED_SECTIONS:
                self.assertIn(
                    section, core,
                    f"{locale}：說明書缺了第 {section} 節——那一國的長輩少一層保護",
                )

    def test_every_book_keeps_the_safety_red_lines(self):
        for locale in self.locales:
            red = eng.red_lines(locale)
            self.assertTrue(red.strip(), f"{locale}：安全紅線是空的")
            for section in REQUIRED_RED_SECTIONS:
                self.assertIn(section, red, f"{locale}：紅線缺了第 {section} 條")

    def test_no_book_hardcodes_an_emergency_number(self):
        """書裡不准寫死號碼——語言不等於國家，寫死就會叫錯人撥錯號碼。"""
        for locale in self.locales:
            red = eng.red_lines(locale)
            for number in FORBIDDEN_HARDCODED_NUMBERS:
                self.assertNotIn(
                    number, red,
                    f"{locale}：紅線裡寫死了急難號碼 {number}。"
                    f"號碼只能來自經過核定的當地安全指引，書裡不可以有",
                )

    def test_every_book_keeps_the_never_guess_rule(self):
        """規則本身必須在：不知道他在哪就問一句，絕不自己猜一個數字。"""
        for locale in self.locales:
            markers = REQUIRED_NO_GUESS_RULE.get(locale)
            if not markers:
                continue
            red = eng.red_lines(locale)
            for marker in markers:
                self.assertIn(
                    marker, red,
                    f"{locale}：少了「不准憑空報號碼／不知道就問」那條規則（{marker}）",
                )

    def test_no_book_leaks_another_countrys_content(self):
        for locale in self.locales:
            leaks = FOREIGN_LEAKS.get(locale)
            if not leaks:
                continue
            whole = eng.core_instruction("offline", locale) + eng.red_lines(locale)
            for token in leaks:
                self.assertNotIn(
                    token, whole,
                    f"{locale}：書裡殘留了別國的內容「{token}」（授書時整段複製貼上最容易犯）",
                )

    def test_escalation_asymmetry_survives_translation(self):
        """②-B「只往上推、永不往下擋」是安全面最重的一條，逐本確認它真的被寫進去。"""
        for locale in self.locales:
            core = eng.core_instruction("offline", locale)
            self.assertIn("②-B", core, f"{locale}：②-B 就醫不對稱規則沒寫進去")



# 每一國「有人設書」就必須「有安全區」——2026-07-31 實測抓到的真洞：
# 英文書裡寫了 911，但通話時的急難句沒設 US，於是美國長輩出事時她只會說
# 「請聯絡當地緊急服務」，不會講 911。書寫對了不等於接上了。
LOCALE_TO_MARKET = {"zh-TW": "TW", "ja": "JP", "en": "US", "es": "ES"}
MARKET_MUST_SAY = {"TW": "119", "JP": "119", "US": "911", "ES": "112"}


class SafetyRegionWiringTests(unittest.TestCase):
    """授了一國的書，那一國的急難句也要真的設好（不然落到沒有號碼的通用句）。"""

    def test_every_shipped_locale_has_a_wired_safety_region(self):
        import localization

        for locale in eng.persona_locales():
            market = LOCALE_TO_MARKET.get(locale)
            if not market:
                continue
            self.assertIn(
                market, localization._REGIONAL_EMERGENCY_GUIDANCE,
                f"{locale} 有人設書、但 {market} 沒有設急難句——"
                f"那一國的長輩出事時只會聽到「聯絡當地緊急服務」，沒有號碼",
            )

    def test_the_wired_region_actually_says_the_number(self):
        """號碼的唯一來源＝當地安全指引，所以這裡必須講得出來（書裡已經沒有了）。"""
        import localization

        for locale in eng.persona_locales():
            market = LOCALE_TO_MARKET.get(locale)
            expected = MARKET_MUST_SAY.get(market)
            if not expected:
                continue
            # 四種語言都要講得出那個號碼——介面英文的人在日本，也要聽到 119
            for language in ("zh-TW", "en", "ja", "es"):
                instruction = localization.regional_safety_instruction(language, market)
                self.assertIn(
                    expected, instruction,
                    f"{market} 的急難句（{language}）裡沒有 {expected}",
                )

    def test_an_unknown_region_gives_no_number_at_all(self):
        """不知道他在哪的時候，指引裡一個號碼都不准有——她要改用問的。"""
        import localization

        for language in ("zh-TW", "en", "ja", "es"):
            instruction = localization.regional_safety_instruction(language, None)
            for number in FORBIDDEN_HARDCODED_NUMBERS:
                self.assertNotIn(
                    number, instruction,
                    f"安全區不明時，{language} 的指引卻給了號碼 {number}——那是猜的",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
