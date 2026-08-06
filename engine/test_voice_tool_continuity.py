import asyncio
import pathlib
import sys
import unittest


ENGINE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE_DIR))

import voice_tool_continuity as continuity


class VoiceToolContinuityTests(unittest.IsolatedAsyncioTestCase):
    def test_live_server_wires_sustained_activity_to_interruptible_lookup(self):
        source = (ENGINE_DIR / "live_voice_server.py").read_text(encoding="utf-8")
        self.assertIn('"node.tool_wait_user_resumed"', source)
        self.assertIn('"node.lookup_cancelled_user_resumed"', source)
        self.assertIn("voice_tool_continuity.run_interruptible(", source)
        self.assertIn("live_lookup.user_resumed_instruction(response_locale)", source)

    def test_sustained_voice_requires_consecutive_evidence(self):
        total, triggered = continuity.sustained_voice_ms(0, True, 80)
        self.assertFalse(triggered)
        total, triggered = continuity.sustained_voice_ms(total, True, 110)
        self.assertTrue(triggered)
        total, triggered = continuity.sustained_voice_ms(total, False, 40)
        self.assertEqual(0, total)
        self.assertFalse(triggered)

    async def test_tool_result_wins_when_user_stays_quiet(self):
        event = asyncio.Event()

        async def result():
            await asyncio.sleep(0)
            return {"status": "ok"}

        self.assertEqual(
            {"status": "ok"},
            await continuity.run_interruptible(result(), event, 0.2),
        )

    async def test_user_resume_cancels_stale_lookup(self):
        event = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow_result():
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()

        task = asyncio.create_task(
            continuity.run_interruptible(slow_result(), event, 1),
        )
        await asyncio.sleep(0)
        event.set()
        with self.assertRaises(continuity.ToolWaitInterrupted):
            await task
        self.assertTrue(cancelled.is_set())

    async def test_timeout_cancels_tool(self):
        event = asyncio.Event()
        with self.assertRaises(asyncio.TimeoutError):
            await continuity.run_interruptible(asyncio.sleep(1), event, 0.05)


if __name__ == "__main__":
    unittest.main()
