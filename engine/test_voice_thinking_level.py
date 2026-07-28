# -*- coding: utf-8 -*-
"""語音腦「思考深度」旋鈕契約（2026-07-27 · Edward 拍板 A 案）。

背景：gemini-3.1-flash-live-preview 的 thinking_level 出廠預設是 minimal（Google 為最低
延遲調的），但 Google 宣稱「複雜指令遵守領先」的 Audio MultiChallenge 成績是開著 thinking
測的。這支測試鎖住的不是「該用哪一段」，而是**這個旋鈕不會偷偷改變正式機**：

  ① 沒設環境變數 → 完全不送 thinking_config → Live API 出廠預設 → 正式機零改變
  ② 設了才變深，且值要真的送進 Live 設定裡（不能設了沒作用、A/B 比出假結論）
  ③ 寫錯字（typo）一律當沒設，不可以炸掉通話——語音線任何設定錯都不能讓長輩撥不通

跑法：python engine/test_voice_thinking_level.py（純函式，不需網路或鑰匙）
"""
import os
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test")

import live_voice_server as voice
from google.genai import types

ENV = "MUNEA_VOICE_THINKING_LEVEL"


class VoiceThinkingLevelHelperTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop(ENV, None)

    def tearDown(self):
        os.environ.pop(ENV, None)

    def test_unset_returns_none(self):
        """沒設＝None＝不送欄位＝維持出廠預設。"""
        self.assertIsNone(voice._voice_thinking_level())

    def test_env_sets_level(self):
        os.environ[ENV] = "low"
        self.assertEqual(voice._voice_thinking_level(), types.ThinkingLevel.LOW)

    def test_env_is_case_insensitive(self):
        os.environ[ENV] = "  Medium "
        self.assertEqual(voice._voice_thinking_level(), types.ThinkingLevel.MEDIUM)

    def test_explicit_beats_env(self):
        os.environ[ENV] = "high"
        self.assertEqual(
            voice._voice_thinking_level("minimal"), types.ThinkingLevel.MINIMAL)

    def test_typo_falls_back_and_never_raises(self):
        """設錯字不可以炸通話，也不可以硬猜一個值——一律當沒設。"""
        for bad in ("deep", "1", "", "   ", "lowest", None):
            os.environ[ENV] = str(bad)
            self.assertIsNone(voice._voice_thinking_level(), f"bad value: {bad!r}")

    def test_typo_in_explicit_falls_back_to_env(self):
        os.environ[ENV] = "high"
        self.assertEqual(
            voice._voice_thinking_level("nonsense"), types.ThinkingLevel.HIGH)


class VoiceThinkingLevelLiveConfigTests(unittest.TestCase):
    """旋鈕要真的接到 Live 設定上（設了沒作用＝A/B 會比出假結論）。"""

    def setUp(self):
        os.environ.pop(ENV, None)

    def tearDown(self):
        os.environ.pop(ENV, None)

    def test_default_sends_no_thinking_config(self):
        cfg = voice.live_config(char="寧寧", name="寧寧")
        self.assertIsNone(cfg.thinking_config)

    def test_env_reaches_live_config(self):
        os.environ[ENV] = "low"
        cfg = voice.live_config(char="寧寧", name="寧寧")
        self.assertIsNotNone(cfg.thinking_config)
        self.assertEqual(cfg.thinking_config.thinking_level, types.ThinkingLevel.LOW)

    def test_explicit_arg_reaches_live_config(self):
        cfg = voice.live_config(char="寧寧", name="寧寧", thinking_level="medium")
        self.assertEqual(
            cfg.thinking_config.thinking_level, types.ThinkingLevel.MEDIUM)

    def test_typo_env_leaves_config_untouched(self):
        os.environ[ENV] = "deeeep"
        cfg = voice.live_config(char="寧寧", name="寧寧")
        self.assertIsNone(cfg.thinking_config)

    def test_knob_does_not_disturb_other_call_settings(self):
        """轉這個旋鈕不可以順手動到說話節奏、聲線、語言——A 案就是「一次只動一個」。"""
        base = voice.live_config(char="寧寧", name="寧寧")
        os.environ[ENV] = "low"
        deep = voice.live_config(char="寧寧", name="寧寧")
        for cfg in (base, deep):
            aad = cfg.realtime_input_config.automatic_activity_detection
            self.assertEqual(aad.silence_duration_ms, 800)
            self.assertEqual(aad.prefix_padding_ms, 300)
        self.assertEqual(base.speech_config.language_code,
                         deep.speech_config.language_code)
        self.assertEqual(
            base.speech_config.voice_config.prebuilt_voice_config.voice_name,
            deep.speech_config.voice_config.prebuilt_voice_config.voice_name)
        self.assertEqual(base.system_instruction, deep.system_instruction)


class VoiceThinkingLevelWireFormatTests(unittest.TestCase):
    """送出去的封包長相：thinkingConfig 必須落在 setup.generationConfig 底下。

    這條鎖的是「SDK 版本換掉之後還送得對」——欄位被搬家或改名時，這裡會先紅，
    而不是等長輩打電話進來才發現那通根本沒吃到設定。

    2026-07-27 對真的 Gemini Live 打過探針驗證過這個長相：故意送 SUPER_DEEP，伺服器
    逐字回「Invalid value at 'setup.generation_config.thinking_config.thinking_level'」
    ——證明它真的在讀這個欄位（不是收下來丟掉）；送 LOW 則正常建線。
    """

    def _wire_setup(self):
        from google.genai import _common
        from google.genai import _live_converters as conv

        class _FakeClient:      # 只為了走完 SDK 內部的模型名稱轉換
            vertexai = False

        cfg = voice.live_config(char="寧寧", name="寧寧")
        request = _common.convert_to_dict(conv._LiveConnectParameters_to_mldev(
            api_client=_FakeClient(),
            from_object=types.LiveConnectParameters(
                model=voice.MODEL, config=cfg).model_dump(exclude_none=True)))
        return request["setup"]

    def tearDown(self):
        os.environ.pop(ENV, None)

    def test_thinking_level_lands_in_setup_generation_config(self):
        os.environ[ENV] = "low"
        generation_config = self._wire_setup()["generationConfig"]
        self.assertEqual(
            generation_config["thinkingConfig"], {"thinking_level": "LOW"})

    def test_default_call_sends_no_thinking_key_at_all(self):
        os.environ.pop(ENV, None)
        generation_config = self._wire_setup()["generationConfig"]
        self.assertNotIn("thinkingConfig", generation_config)


if __name__ == "__main__":
    unittest.main(verbosity=2)
