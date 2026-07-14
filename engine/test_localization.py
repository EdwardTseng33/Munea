import unittest

import localization


class LocalizationTests(unittest.TestCase):
    def test_normalizes_supported_and_browser_locales(self):
        self.assertEqual(localization.normalize_locale("zh-Hant"), "zh-TW")
        self.assertEqual(localization.normalize_locale("en-GB"), "en")
        self.assertEqual(localization.normalize_locale("ja-JP"), "ja")
        self.assertEqual(localization.normalize_locale("es-MX"), "es")
        self.assertEqual(localization.normalize_locale("de-DE"), "zh-TW")

    def test_speech_codes_are_provider_ready(self):
        self.assertEqual(localization.speech_language_code("zh-TW"), "cmn-TW")
        self.assertEqual(localization.speech_language_code("en"), "en-US")
        self.assertEqual(localization.speech_language_code("ja"), "ja-JP")
        self.assertEqual(localization.speech_language_code("es"), "es-ES")

    def test_non_taiwanese_prompt_never_assumes_taiwan_hotlines(self):
        self.assertIn("Do not use Taiwan-specific hotline numbers", localization.reply_language_instruction("es"))
        self.assertNotIn("Do not use Taiwan-specific hotline numbers", localization.reply_language_instruction("zh-TW"))

    def test_opening_and_retry_messages_follow_locale(self):
        self.assertEqual(localization.opening_message("en").split()[0], "Hi,")
        self.assertIn("conexión", localization.retry_message("es"))

    def test_taiwanese_copy_and_speech_forms_are_separate(self):
        self.assertEqual(localization.speech_text("你卡早捆喔", "zh-TW"), "你早點睡喔")
        self.assertEqual(localization.display_text("你咖紮綑喔", "zh-TW"), "你卡早捆喔")
        self.assertEqual(localization.display_text("你咖 紮 綑喔", "zh-TW"), "你卡早捆喔")
        self.assertEqual(localization.display_text("你卡早 捆喔", "zh-TW"), "你卡早捆喔")
        self.assertEqual(localization.display_text("你較早睏喔", "zh-TW"), "你卡早捆喔")
        self.assertEqual(localization.display_text("卡早 ", "zh-TW"), "卡早")

    def test_taiwanese_pronunciation_is_not_applied_to_other_locales(self):
        self.assertEqual(localization.speech_text("卡早捆", "en"), "卡早捆")
        self.assertEqual(localization.display_text("咖紮綑", "ja"), "咖紮綑")

    def test_live_pronunciation_instruction_is_explicit_and_conservative(self):
        instruction = localization.taiwanese_pronunciation_instruction("zh-TW")
        self.assertIn("卡早捆", instruction)
        self.assertIn("咖紮綑", instruction)
        self.assertIn("不要自行猜音", instruction)
        self.assertEqual(localization.taiwanese_pronunciation_instruction("en"), "")

    def test_taiwanese_hokkien_is_disabled_below_release_threshold(self):
        self.assertFalse(localization.taiwanese_hokkien_release_enabled())
        self.assertLess(
            localization.TAIWANESE_HOKKIEN_VALIDATED_SCORE,
            localization.TAIWANESE_HOKKIEN_MIN_RELEASE_SCORE,
        )

    def test_taiwan_mandarin_launch_instruction_fails_safe(self):
        instruction = localization.taiwan_mandarin_launch_instruction("zh-TW")
        self.assertIn("只能使用自然、清楚的台灣華語", instruction)
        self.assertIn("不要主動講台語", instruction)
        self.assertIn("可以用國語再說一次嗎", instruction)
        self.assertIn("絕對不要猜意思", instruction)
        self.assertEqual(localization.taiwan_mandarin_launch_instruction("en"), "")

    def test_reply_instruction_includes_launch_language_gate(self):
        instruction = localization.reply_language_instruction("zh-TW")
        self.assertIn("繁體台灣中文", instruction)
        self.assertIn("首發語言限制", instruction)


if __name__ == "__main__":
    unittest.main()
