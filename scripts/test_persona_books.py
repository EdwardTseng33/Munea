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

# 各國的急難號碼：號碼跟「人在哪個國家」走、不跟語言走。
# 一本書至少要帶得出該語系主要市場的急救號碼，否則那一國的急難引導是空的。
REQUIRED_EMERGENCY_NUMBERS = {
    "zh-TW": ("119", "1925"),
    "ja": ("119", "0120-279-338"),
    "en": ("911",),
    "es": ("112",),
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

    def test_every_book_carries_its_local_emergency_numbers(self):
        for locale in self.locales:
            expected = REQUIRED_EMERGENCY_NUMBERS.get(locale)
            if not expected:
                continue
            red = eng.red_lines(locale)
            for number in expected:
                self.assertIn(
                    number, red,
                    f"{locale}：紅線裡沒有當地急難號碼 {number}——急難引導會是空的",
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
        markers = {
            "zh-TW": ("119", "②-B"),
            "ja": ("119", "②-B"),
        }
        for locale in self.locales:
            expected = markers.get(locale)
            if not expected:
                continue
            core = eng.core_instruction("offline", locale)
            for marker in expected:
                self.assertIn(marker, core, f"{locale}：②-B 就醫不對稱規則沒寫進去")


if __name__ == "__main__":
    unittest.main(verbosity=2)
