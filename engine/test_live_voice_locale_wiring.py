import os
import types
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

    def test_lookup_tts_uses_each_response_locale_language_code(self):
        expected = {
            "zh-TW": "cmn-TW",
            "en": "en-US",
            "ja": "ja-JP",
            "es": "es-ES",
        }

        class FakeModels:
            def __init__(self):
                self.configs = []

            def generate_content(self, model, contents, config):
                self.configs.append(config)
                inline_data = types.SimpleNamespace(
                    data=b"pcm", mime_type="audio/pcm;rate=24000",
                )
                part = types.SimpleNamespace(inline_data=inline_data)
                content = types.SimpleNamespace(parts=[part])
                return types.SimpleNamespace(
                    candidates=[types.SimpleNamespace(content=content)],
                )

        models = FakeModels()
        client = types.SimpleNamespace(models=models)
        with patch.object(
            live_voice_server, "_pick_client", return_value=(0, client),
        ):
            for locale, speech_code in expected.items():
                with self.subTest(locale=locale):
                    self.assertEqual(
                        live_voice_server._gemini_tts_pcm(
                            "locale cue", "寧寧", locale,
                        ),
                        b"pcm",
                    )
                    self.assertEqual(
                        models.configs[-1].speech_config.language_code,
                        speech_code,
                    )

    def test_lookup_audio_cache_is_isolated_by_locale(self):
        with (
            patch.dict(live_voice_server._LOOKUP_CUE_PCM, {}, clear=True),
            patch.object(
                live_voice_server,
                "_gemini_tts_pcm",
                side_effect=(b"english", b"japanese"),
            ) as synth,
        ):
            self.assertEqual(
                live_voice_server._lookup_cue_pcm(
                    "寧寧", "same text", "en",
                ),
                b"english",
            )
            self.assertEqual(
                live_voice_server._lookup_cue_pcm(
                    "寧寧", "same text", "ja",
                ),
                b"japanese",
            )
            self.assertEqual(
                live_voice_server._lookup_cue_pcm(
                    "寧寧", "same text", "en",
                ),
                b"english",
            )
        self.assertEqual(synth.call_count, 2)


if __name__ == "__main__":
    unittest.main()
