# -*- coding: utf-8 -*-
"""語音打斷／收話節奏參數三層 fallback 契約（2026-07-24 · 快贏包 C 項）。

Edward 拍板方向：這是「按使用者說話節奏調的參數」，不是長輩專屬版——正式機不設任何
環境變數＝跟改動前完全一樣的現行值；測試機可用環境變數先試新節奏；介面預留呼叫端
明確帶值（未來單通話/單一使用者覆蓋），目前呼叫端一律傳 None、還沒真的接使用者資料。

跑法：python engine/test_voice_rhythm_params.py（純文字/純函式，不需網路或鑰匙）
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test")

import live_voice_server as voice
from google.genai import types


class VoiceRhythmParamHelperTests(unittest.TestCase):
    def test_rhythm_default_when_nothing_set(self):
        os.environ.pop("MUNEA_VOICE_SILENCE_MS", None)
        self.assertEqual(
            voice._voice_rhythm_param(None, "MUNEA_VOICE_SILENCE_MS", 800), 800)

    def test_rhythm_env_overrides_default(self):
        os.environ["MUNEA_VOICE_SILENCE_MS"] = "1100"
        try:
            self.assertEqual(
                voice._voice_rhythm_param(None, "MUNEA_VOICE_SILENCE_MS", 800), 1100)
        finally:
            os.environ.pop("MUNEA_VOICE_SILENCE_MS", None)

    def test_rhythm_explicit_beats_env(self):
        os.environ["MUNEA_VOICE_SILENCE_MS"] = "1100"
        try:
            self.assertEqual(
                voice._voice_rhythm_param(950, "MUNEA_VOICE_SILENCE_MS", 800), 950)
        finally:
            os.environ.pop("MUNEA_VOICE_SILENCE_MS", None)

    def test_rhythm_bad_env_falls_back_to_default(self):
        os.environ["MUNEA_VOICE_SILENCE_MS"] = "not-a-number"
        try:
            self.assertEqual(
                voice._voice_rhythm_param(None, "MUNEA_VOICE_SILENCE_MS", 800), 800)
        finally:
            os.environ.pop("MUNEA_VOICE_SILENCE_MS", None)

    def test_sensitivity_default_and_env_and_explicit(self):
        env_name = "MUNEA_VOICE_START_SENSITIVITY"
        os.environ.pop(env_name, None)
        self.assertEqual(
            voice._voice_sensitivity_param(
                None, env_name, types.StartSensitivity.START_SENSITIVITY_LOW,
                types.StartSensitivity.START_SENSITIVITY_HIGH,
                types.StartSensitivity.START_SENSITIVITY_LOW),
            types.StartSensitivity.START_SENSITIVITY_LOW)

        os.environ[env_name] = "high"
        try:
            self.assertEqual(
                voice._voice_sensitivity_param(
                    None, env_name, types.StartSensitivity.START_SENSITIVITY_LOW,
                    types.StartSensitivity.START_SENSITIVITY_HIGH,
                    types.StartSensitivity.START_SENSITIVITY_LOW),
                types.StartSensitivity.START_SENSITIVITY_HIGH)

            self.assertEqual(
                voice._voice_sensitivity_param(
                    "low", env_name, types.StartSensitivity.START_SENSITIVITY_LOW,
                    types.StartSensitivity.START_SENSITIVITY_HIGH,
                    types.StartSensitivity.START_SENSITIVITY_LOW),
                types.StartSensitivity.START_SENSITIVITY_LOW)
        finally:
            os.environ.pop(env_name, None)


class VoiceLiveConfigDefaultBehaviorTests(unittest.TestCase):
    """正式機不設任何環境變數＝這通行為與改動前完全一樣（零改變）。"""

    def setUp(self):
        for name in ("MUNEA_VOICE_SILENCE_MS", "MUNEA_VOICE_PREFIX_PADDING_MS",
                     "MUNEA_VOICE_START_SENSITIVITY", "MUNEA_VOICE_END_SENSITIVITY"):
            os.environ.pop(name, None)

    def test_no_env_no_explicit_matches_prior_hardcoded_values(self):
        cfg = voice.live_config(char="寧寧", name="寧寧")
        aad = cfg.realtime_input_config.automatic_activity_detection
        self.assertEqual(aad.silence_duration_ms, 800)
        self.assertEqual(aad.prefix_padding_ms, 300)
        self.assertEqual(aad.start_of_speech_sensitivity,
                          types.StartSensitivity.START_SENSITIVITY_LOW)
        self.assertEqual(aad.end_of_speech_sensitivity,
                          types.EndSensitivity.END_SENSITIVITY_LOW)

    def test_env_override_reaches_live_config(self):
        os.environ["MUNEA_VOICE_SILENCE_MS"] = "1200"
        try:
            cfg = voice.live_config(char="寧寧", name="寧寧")
            aad = cfg.realtime_input_config.automatic_activity_detection
            self.assertEqual(aad.silence_duration_ms, 1200)
        finally:
            os.environ.pop("MUNEA_VOICE_SILENCE_MS", None)

    def test_explicit_call_arg_reaches_live_config(self):
        cfg = voice.live_config(char="寧寧", name="寧寧", silence_duration_ms=950)
        aad = cfg.realtime_input_config.automatic_activity_detection
        self.assertEqual(aad.silence_duration_ms, 950)


if __name__ == "__main__":
    unittest.main(verbosity=2)
