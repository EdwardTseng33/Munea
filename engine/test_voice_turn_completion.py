import unittest

from voice_turn_completion import provider_turn_stalled


class ProviderTurnStallTests(unittest.TestCase):
    def test_requires_a_real_active_spoken_turn(self):
        self.assertFalse(provider_turn_stalled(10.0, active=False, last_audio_at=7.0, out_bytes=96000))
        self.assertFalse(provider_turn_stalled(10.0, active=True, last_audio_at=0.0, out_bytes=96000))
        self.assertFalse(provider_turn_stalled(10.0, active=True, last_audio_at=7.0, out_bytes=4800))

    def test_waits_through_normal_sentence_pauses(self):
        self.assertFalse(provider_turn_stalled(10.0, active=True, last_audio_at=8.0, out_bytes=96000))
        self.assertTrue(provider_turn_stalled(10.0, active=True, last_audio_at=7.5, out_bytes=96000))

    def test_tool_or_language_work_suppresses_the_guard(self):
        self.assertFalse(
            provider_turn_stalled(
                10.0,
                active=True,
                last_audio_at=7.0,
                out_bytes=96000,
                blocked=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
