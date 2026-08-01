"""心情陪伴語的防線測試。

Edward 2026-08-01 拍板讓 AI 生這句話，但立了兩條線：
不准提 AI 的名字、不准編使用者沒做過的事。

同一天稍早的舊文案寫死成「今天心情平穩，膝蓋的痠有記著」——使用者根本沒說過膝蓋痛。
長輩看到會以為 App 在亂記他的事。這支測試就是防這件事再發生。

這裡測的是「回來之後的檢查」那一層（不需要真的呼叫 AI）。
另外兩層是：提示裡明講規則、以及**完全不餵使用者資料**（沒有資料就編不出細節）。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server  # noqa: E402


class MoodLineGuardTests(unittest.TestCase):
    def check(self, text, locale="zh-TW", word="生氣", names=("寧寧", "阿宏")):
        return server.mood_line_is_safe(text, locale, word, list(names))

    # ---- 該放行的 ----

    def test_good_line_passes(self):
        self.assertEqual(self.check("生氣是正常的，我陪著你"), "生氣是正常的，我陪著你")

    def test_quotes_are_trimmed(self):
        self.assertEqual(self.check("「生氣也沒關係」"), "生氣也沒關係")

    def test_english_line_passes(self):
        got = self.check("Angry is fair. I'm right here.", locale="en", word="Angry")
        self.assertEqual(got, "Angry is fair. I'm right here.")

    def test_japanese_line_passes(self):
        self.assertEqual(self.check("怒りも当然です", locale="ja", word="怒り"), "怒りも当然です")

    def test_spanish_line_passes(self):
        got = self.check("Enfado es normal. Aquí estoy.", locale="es", word="Enfado")
        self.assertEqual(got, "Enfado es normal. Aquí estoy.")

    # ---- 該擋下的：編造使用者做過的事 ----

    def test_rejects_invented_behaviour_zh(self):
        # 這就是舊文案犯的錯——他只是點了一個表情
        self.assertIsNone(self.check("生氣了嗎？剛剛還哼著歌呢"))
        self.assertIsNone(self.check("生氣的時候你說想出去走走"))
        self.assertIsNone(self.check("生氣，膝蓋的痠我也記著"))

    def test_rejects_invented_behaviour_en(self):
        self.assertIsNone(self.check("Angry? You said you wanted a walk.", locale="en", word="Angry"))
        self.assertIsNone(self.check("Angry — you were humming earlier.", locale="en", word="Angry"))

    def test_rejects_invented_behaviour_ja(self):
        self.assertIsNone(self.check("怒り、さっき鼻歌を歌っていましたね", locale="ja", word="怒り"))

    def test_rejects_invented_behaviour_es(self):
        self.assertIsNone(self.check("Enfado; ayer tarareabas una canción.", locale="es", word="Enfado"))

    # ---- 該擋下的：提到角色名字 ----

    def test_rejects_companion_name(self):
        self.assertIsNone(self.check("生氣沒關係，寧寧在這裡"))
        self.assertIsNone(self.check("生氣沒關係，阿宏在這裡"))

    def test_rejects_companion_name_case_insensitive(self):
        self.assertIsNone(self.check("Angry is fair, NINA is here.",
                                     locale="en", word="Angry", names=("Nina",)))

    # ---- 該擋下的：沒複述他點的那個心情 ----

    def test_rejects_when_mood_word_missing(self):
        self.assertIsNone(self.check("沒關係的，我陪著你"))

    # ---- 該擋下的：格式不對 ----

    def test_rejects_too_long(self):
        self.assertIsNone(self.check("生氣" + "好" * 40))

    def test_rejects_multiline(self):
        self.assertIsNone(self.check("生氣是正常的\n我陪著你"))

    def test_rejects_empty(self):
        self.assertIsNone(self.check(""))
        self.assertIsNone(self.check("   "))

    # ---- 提示本身不可以夾帶使用者資料 ----

    def test_instruction_carries_no_user_data(self):
        """提示裡只有心情詞，沒有任何使用者資訊——沒有資料就編不出細節。"""
        text = server.mood_line_instruction("zh-TW", "生氣")
        # 只挑「會帶進使用者資料」的詞。「語氣像家人」是在描述口吻、不是資料，不列入。
        for leak in ("步數", "心率", "睡眠", "血壓", "服藥", "姓名", "生日", "地址"):
            self.assertNotIn(leak, text, f"提示不該提到「{leak}」")

    def test_instruction_covers_four_locales(self):
        for loc, word in (("zh-TW", "生氣"), ("en", "Angry"), ("ja", "怒り"), ("es", "Enfado")):
            text = server.mood_line_instruction(loc, word)
            self.assertIn(word, text, f"{loc} 的提示沒帶到心情詞")
            self.assertGreater(len(text), 80, f"{loc} 的提示太短，規則可能沒寫全")

    def test_bad_mood_id_is_refused(self):
        out = server.mood_line_response({"mood": "ecstatic", "moodWord": "狂喜"})
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
