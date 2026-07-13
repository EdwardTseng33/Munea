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


if __name__ == "__main__":
    unittest.main()
