#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""說明書語系隔離：一通電話只能吃一本書，四本不可以同時上場、也不可以互相串。

為什麼要有這支（2026-08-10 Edward 指定檢查「AI 不會同時跑 4 份語言說明書、或亂串」）：
2026-07-31 踩過一次——角色個性固定讀繁中版，於是英文說明書中間夾著中文的個性描述，
實跑抓到她整段用中文回答英文用戶。當時修好了，但沒有留下守門，
下次有人新增區塊時忘記帶語系，一樣會再犯，而且只有真的講外語才看得出來。

這支盯三件事：
  1. 每個語系的說明書只含自己那一本的內容，不含別語系的專屬標記
  2. 四本不會被串在一起（總長度不該是單本的數倍）
  3. 每一種說明書零件（core / red / voice-style / lookup）都真的備齊四語，
     不是靠退回中文版撐場面
"""

import os
import sys
import unittest

os.environ.setdefault("GEMINI_API_KEY", "persona-locale-isolation-test-key")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chat_engine as eng
import localization
import live_voice_server as lvs

LOCALES = ["zh-TW", "en", "ja", "es"]

# 各語系口語風格書裡「只會出現在自己那本」的區塊標題。用來抓交叉污染：
# 英文那本若出現中文標題，就是串到了。
#
# ⚠ 挑指紋要挑「口語風格書自己的區塊標題」。說明書裡另有幾個四語共用的英文標題
# （例如 [Live language switching]、[Verified locale context]、[Regional safety]），
# 那些是給模型看的技術指令、每個語系都會有，拿來當英文指紋會誤判——2026-08-10 first try 就踩到。
FINGERPRINTS = {
    "zh-TW": ["[接住情緒與陪伴引導]", "[即時語音話量上限]"],
    "en": ["[Holding a feeling and walking with them]", "[Live speech · how much to say]"],
    "ja": ["[気持ちを受けとめ、寄り添って導く]", "[リアルタイム音声・話す量の上限]"],
    "es": ["[Sostener lo que siente y acompañarle]", "[Voz en directo · cuánto hablar]"],
}


def build_prompt(locale):
    profile = localization.voice_session_locale_profile({"conversationLocale": locale})
    return lvs.system_instruction(locale_profile=profile)


class PersonaBookCoverageTests(unittest.TestCase):
    def test_every_book_kind_has_all_four_locales(self):
        """任何一種零件缺語系版本，就會靜靜退回中文版——外語用戶讀到中文卻沒人知道。"""
        for kind in ("core", "red", "voice-style", "lookup-online", "lookup-offline"):
            for locale in LOCALES:
                path = os.path.join(eng.PERSONA_DIR, f"{kind}.{locale}.txt")
                self.assertTrue(
                    os.path.exists(path),
                    f"缺少 {kind}.{locale}.txt——這一國會靜靜退回中文版",
                )

    def test_persona_loader_returns_one_book_not_concatenation(self):
        """讀一本就是一本。回傳長度若接近四本相加，代表被串起來了。"""
        texts = {loc: eng._persona_text("voice-style", loc) for loc in LOCALES}
        longest = max(len(t) for t in texts.values())
        total = sum(len(t) for t in texts.values())
        for loc, text in texts.items():
            self.assertLess(
                len(text), total * 0.6,
                f"{loc} 的口語風格書長度接近四本相加，疑似被串在一起",
            )
            self.assertGreater(len(text), 200, f"{loc} 的口語風格書短得不合理")
        self.assertLess(longest, total, "單一語系不該等於全部語系加總")


class PromptLocaleIsolationTests(unittest.TestCase):
    def test_each_locale_prompt_carries_only_its_own_fingerprints(self):
        """一通電話只吃一本書：別語系的招牌句不准出現。"""
        for locale in LOCALES:
            prompt = build_prompt(locale)
            for other, marks in FINGERPRINTS.items():
                if other == locale:
                    continue
                for mark in marks:
                    self.assertNotIn(
                        mark, prompt,
                        f"{locale} 的說明書裡出現了 {other} 的內容「{mark}」——語系串了",
                    )

    def test_no_block_is_pasted_twice(self):
        """同一本書不可以被貼兩次——這才是「串」的直接證據。

        不要改用「跨語系比長度」來抓：拉丁語系用字母，同樣內容的字元數本來就是
        中文的 2.5～3 倍（2026-08-10 實測：中文 16,743／英文 46,029／西文 47,253），
        那是語言特性不是重複。要抓重複就直接數招牌句出現幾次。
        """
        for locale in LOCALES:
            prompt = build_prompt(locale)
            for mark in FINGERPRINTS[locale]:
                self.assertEqual(
                    prompt.count(mark), 1,
                    f"{locale} 的說明書裡「{mark}」出現 {prompt.count(mark)} 次——同一本被貼了不只一次",
                )

    def test_prompt_is_not_empty_for_any_locale(self):
        lengths = {loc: len(build_prompt(loc)) for loc in LOCALES}
        for loc, n in lengths.items():
            self.assertGreater(n, 3000, f"{loc} 的說明書短得不合理：{lengths}")

    def test_switching_locale_actually_switches_the_book(self):
        """換語系要真的換到另一本，不是回同一份。"""
        zh = build_prompt("zh-TW")
        en = build_prompt("en")
        self.assertNotEqual(zh, en, "換成英文之後說明書完全沒變——語系沒吃到")


if __name__ == "__main__":
    unittest.main()
