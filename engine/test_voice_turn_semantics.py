import os
import pathlib
import sys
import unittest


ENGINE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

import voice_turn_semantics as semantics


class VoiceTurnSemanticsTests(unittest.TestCase):
    def test_zh_tw_unfinished_signals_are_conservative(self):
        cases = {
            "嗯": "short_filler",
            "我想一下…": "explicit_hold",
            "讓我想一下。": "explicit_hold",
            "我今天其實是因為": "trailing_connector",
            "還有，": "open_punctuation",
        }
        for transcript, reason in cases.items():
            with self.subTest(transcript=transcript):
                hint = semantics.classify_turn_end(transcript, "zh-TW")
                self.assertTrue(hint.supported)
                self.assertEqual("hold", hint.decision)
                self.assertEqual(reason, hint.reason)

    def test_complete_phrases_are_not_held(self):
        for transcript in (
            "因為下雨，所以我今天沒去。",
            "我想吃麵",
            "然後我就回家了",
            "可以幫我查一下嗎？",
        ):
            with self.subTest(transcript=transcript):
                self.assertEqual(
                    "respond",
                    semantics.classify_turn_end(transcript, "zh-Hant-TW").decision,
                )

    def test_unsupported_locale_does_not_pretend_to_be_smart_turn(self):
        hint = semantics.classify_turn_end("because", "en-US")
        self.assertFalse(hint.supported)
        self.assertEqual("unsupported_locale", hint.reason)

    def test_hint_never_contains_transcript(self):
        secret = "我的私人健康資料"
        hint = semantics.classify_turn_end(secret, "zh-TW")
        self.assertNotIn(secret, repr(hint))
        self.assertEqual({"decision", "reason", "supported"}, set(hint.__dict__))

    def test_shadow_toggle_defaults_on_and_supports_explicit_off(self):
        previous = os.environ.pop("MUNEA_VOICE_SEMANTIC_TURN_SHADOW", None)
        try:
            self.assertTrue(semantics.semantic_turn_shadow_enabled())
            for value in ("0", "false", "OFF", "no"):
                self.assertFalse(semantics.semantic_turn_shadow_enabled(value))
            self.assertTrue(semantics.semantic_turn_shadow_enabled("1"))
        finally:
            if previous is not None:
                os.environ["MUNEA_VOICE_SEMANTIC_TURN_SHADOW"] = previous

    def test_live_server_wiring_is_finished_only_and_privacy_safe(self):
        source = (ENGINE_DIR / "live_voice_server.py").read_text(encoding="utf-8")
        self.assertIn('getattr(it_pre, "finished", False)', source)
        self.assertIn('"node.semantic_turn_shadow"', source)
        self.assertIn("provider_finished=True", source)
        self.assertIn('semantic_turn_holds=st["semantic_turn_shadow_holds"]', source)
        self.assertNotIn('node.semantic_turn_shadow", transcript=', source)


if __name__ == "__main__":
    unittest.main()
