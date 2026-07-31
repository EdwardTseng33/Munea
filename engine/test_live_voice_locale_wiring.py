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
        # 2026-07-31 人設書分國後，這段尾巴多了「這本書是為哪一國寫的」的說明，
        # 原本抓 1600 字會被擠出去。守的東西沒變、範圍放寬。
        tail = prompt[-2600:]
        self.assertIn("Conversation locale: es", tail)
        self.assertIn("Country: ES", tail)
        self.assertIn("Safety region: ES", tail)
        self.assertIn("llama al 112", tail)
        self.assertIn("never changes country", tail)
        self.assertNotIn("llama al 119", tail)

    def test_book_home_country_override_is_generalised(self):
        """人設書分國之後，「忽略別國號碼」不能只認得台灣。

        每本書是為一個國家寫的（西班牙文書＝西班牙的 112）。講西班牙文的人
        可能在墨西哥（急難是 911），講英文的可能在英國。核定的安全區跟書的母國
        不同時，一定要明白叫模型作廢書裡的號碼——否則墨西哥長輩會被叫去打 112。
        """
        profile = localization.voice_session_locale_profile({
            "uiLocale": "es",
            "conversationLocale": "es",
            "preferredLanguages": ["es"],
            "countryCode": "MX",
            "timeZone": "America/Mexico_City",
            "currency": "MXN",
            "safetyRegion": "MX",
            "legalRegion": "MX",
            "dataRegion": "mx-primary",
        })
        prompt = live_voice_server.system_instruction(
            demo_mode=True,
            locale_profile=profile,
        )
        tail = prompt[-2600:]
        # 說明書的母國（ES）與這通的安全區（MX）都要講明，模型才知道兩者不同
        self.assertIn("written for ES", tail)
        self.assertIn("safety region for this call is MX", tail)
        # 作廢指令要夠硬：不是「參考當地」，是「上面那些號碼對這個人是錯的」
        self.assertIn("ignore all of them", tail)
        # 不確定就別硬報號碼
        self.assertIn("rather than naming a number you are unsure of", tail)
        # 核定的當地指引要真的是墨西哥的
        self.assertIn("llama al 911", tail)

    def test_no_mismatch_warning_when_the_book_matches_the_region(self):
        """兩邊一樣（台灣人用繁中書）＝不貼那段作廢警告。

        2026-08-01 說明書分章第 1 刀：那段約 500 字元的英文警告，只有在
        「書的母國 ≠ 這通核定的安全區」時才有意義；兩邊一樣時它每輪都在重讀、
        卻永遠不會觸發。國家與安全區本身仍要寫明（下面兩行照驗），
        拿掉的只是「上面那些號碼對這個人是錯的」那整段。
        上面 test_the_override_* 那題顧的就是真的不一樣時警告還在。
        """
        profile = localization.voice_session_locale_profile()
        prompt = live_voice_server.system_instruction(
            demo_mode=True,
            locale_profile=profile,
        )
        tail = prompt[-2600:]
        self.assertIn("Country: TW", tail)
        self.assertIn("Safety region: TW", tail)
        self.assertNotIn("written for", tail)
        self.assertNotIn("ignore all of them", tail)

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
