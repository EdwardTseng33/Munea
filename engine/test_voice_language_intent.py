import unittest

try:
    from engine.voice_language_intent import parse_spoken_language_intent
except ModuleNotFoundError:
    from voice_language_intent import parse_spoken_language_intent


class VoiceLanguageIntentTests(unittest.TestCase):
    def test_explicit_switch_commands_cover_all_four_languages(self):
        cases = {
            "請幫我改用英文": "en",
            "Please speak Japanese": "ja",
            "西班牙語で話してください": "es",
            "Habla en chino, por favor": "zh-TW",
        }
        for transcript, expected in cases.items():
            with self.subTest(transcript=transcript):
                intent = parse_spoken_language_intent(transcript)
                self.assertEqual(intent["kind"], "switch")
                self.assertEqual(intent["switchLocale"], expected)
                self.assertFalse(intent["permanent"])

    def test_permanent_markers_request_confirmation_in_multiple_languages(self):
        cases = (
            "Please speak Japanese from now on",
            "以後都改用日文",
            "これから日本語で話してください",
            "Habla siempre en japonés",
        )
        for transcript in cases:
            with self.subTest(transcript=transcript):
                intent = parse_spoken_language_intent(transcript)
                self.assertEqual(intent["kind"], "switch")
                self.assertEqual(intent["switchLocale"], "ja")
                self.assertTrue(intent["permanent"])

    def test_language_mentions_and_translation_questions_are_not_switches(self):
        cases = (
            "我剛剛一下中文一下 English",
            "英文怎麼說？",
            "How do you say thank you in Japanese?",
            "日本語を勉強しています",
            "¿Cómo se dice gracias en chino?",
            "I speak English with my daughter.",
            "我用英文回覆客戶。",
            "先生は日本語で話してくださいと言った。",
        )
        for transcript in cases:
            with self.subTest(transcript=transcript):
                self.assertEqual(
                    parse_spoken_language_intent(transcript)["kind"],
                    "none",
                )

    def test_confirmation_and_cancel_only_apply_while_change_is_pending(self):
        self.assertEqual(
            parse_spoken_language_intent("yes, confirm", pending_permanent=True)["kind"],
            "confirm",
        )
        self.assertEqual(
            parse_spoken_language_intent("no, cancel", pending_permanent=True)["kind"],
            "cancel",
        )
        self.assertEqual(
            parse_spoken_language_intent("yes, confirm")["kind"],
            "none",
        )
        self.assertEqual(
            parse_spoken_language_intent("no, cancel")["kind"],
            "none",
        )

    def test_permanent_marker_can_precede_the_switch_command(self):
        cases = (
            "From now on, speak Japanese",
            "以後都改用日文",
            "これから日本語で話してください",
        )
        for transcript in cases:
            with self.subTest(transcript=transcript):
                intent = parse_spoken_language_intent(transcript)
                self.assertEqual(intent["kind"], "switch")
                self.assertEqual(intent["switchLocale"], "ja")
                self.assertTrue(intent["permanent"])


if __name__ == "__main__":
    unittest.main()
