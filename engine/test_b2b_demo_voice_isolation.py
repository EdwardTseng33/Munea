# -*- coding: utf-8 -*-
"""Contract tests for the anonymous B2B voice demo boundary."""

import os
import unittest
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "test-b2b-demo-key")

import live_voice_server as voice


class B2BDemoVoiceIsolationTests(unittest.TestCase):
    def test_demo_instruction_never_reads_user_context_or_recap(self):
        with (
            mock.patch.object(voice.server, "build_reply_context", side_effect=AssertionError("context read")),
            mock.patch.object(voice.server, "recent_call_recap_line", side_effect=AssertionError("recap read")),
            mock.patch.object(voice, "_brain_health_context", side_effect=AssertionError("health read")),
        ):
            instruction = voice.system_instruction(demo_mode=True)

        self.assertIn("匿名訪客體驗", instruction)
        self.assertIn("沒有任何使用者記憶", instruction)
        self.assertIn("不得宣稱記得對方", instruction)

    def test_demo_config_exposes_no_tools_even_if_capabilities_are_requested(self):
        with mock.patch.object(voice, "live_lookup_enabled", return_value=True):
            config = voice.live_config(
                allow_reminders=True,
                allow_events=True,
                demo_mode=True,
            )

        self.assertEqual(config.tools, [])


if __name__ == "__main__":
    unittest.main()
