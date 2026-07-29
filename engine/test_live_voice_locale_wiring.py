import os
import unittest
from unittest.mock import patch


os.environ.setdefault("GEMINI_API_KEY", "unit-test-key")

try:
    from engine import localization
    from engine import live_voice_server
except ModuleNotFoundError:
    import localization
    import live_voice_server


class LiveVoiceLocaleWiringTests(unittest.TestCase):
    def test_live_config_uses_each_verified_session_language(self):
        expected = {
            "zh-TW": ("cmn-TW", ["cmn-Hant-TW"]),
            "en": ("en-US", ["en-US"]),
            "ja": ("ja-JP", ["ja-JP"]),
            "es": ("es-ES", ["es-ES"]),
        }
        with patch.object(
            live_voice_server,
            "system_instruction",
            return_value="locale wiring test",
        ):
            for locale, (speech_code, hints) in expected.items():
                profile = localization.voice_session_locale_profile({
                    "conversationLocale": locale,
                })
                config = live_voice_server.live_config(
                    demo_mode=True,
                    locale_profile=profile,
                )
                self.assertEqual(config.speech_config.language_code, speech_code)
                self.assertEqual(
                    config.input_audio_transcription.language_hints.language_codes,
                    hints,
                )
                self.assertEqual(
                    config.output_audio_transcription.language_hints.language_codes,
                    hints,
                )

    def test_non_taiwan_policy_is_the_final_prompt_contract(self):
        profile = localization.voice_session_locale_profile({
            "uiLocale": "en",
            "conversationLocale": "es",
            "preferredLanguages": ["es", "en"],
            "countryCode": "ES",
            "timeZone": "Europe/Madrid",
            "currency": "EUR",
            "safetyRegion": "ES",
            "legalRegion": "ES",
            "dataRegion": "eu-primary",
        })
        prompt = live_voice_server.system_instruction(
            demo_mode=True,
            locale_profile=profile,
        )
        tail = prompt[-1600:]
        self.assertIn("Conversation locale: es", tail)
        self.assertIn("Country: ES", tail)
        self.assertIn("Safety region: ES", tail)
        self.assertIn("llama al 112", tail)
        self.assertIn("never changes country", tail)
        self.assertNotIn("llama al 119", tail)


if __name__ == "__main__":
    unittest.main()
