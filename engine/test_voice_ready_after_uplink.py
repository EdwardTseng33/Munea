#!/usr/bin/env python3
"""聲音就緒要等手機上行證明活著才回報總機（2026-11-05 正式線：收音管死掉的通話被扣點）。"""
import asyncio
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "voice-ready-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import live_voice_server as lvs  # noqa: E402

CALL = {"call_id": "11111111-1111-4111-8111-111111111111", "lease_version": 1}


class FakeWs:
    def __init__(self):
        self.closed = None

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


def run(coro):
    return asyncio.run(coro)


class VoiceReadyAfterUplinkTest(unittest.TestCase):
    def test_dead_microphone_never_reports_ready(self):
        posts = []
        with patch.object(lvs, "post_internal", lambda *a: posts.append(a) or {"ok": True}):
            ok = run(lvs._report_voice_ready_after_uplink(
                FakeWs(), "t", 0.0, {"first_mic": False}, CALL, wait_s=0.15, poll_s=0.01))
        self.assertFalse(ok)
        self.assertEqual(posts, [], "沒有上行就不能回報就緒＝不能轉接通、不能扣點")

    def test_ready_reported_once_first_packet_arrives(self):
        posts = []
        st = {"first_mic": False}

        async def scenario():
            async def mic_arrives():
                await asyncio.sleep(0.05)
                st["first_mic"] = True
            asyncio.get_running_loop().create_task(mic_arrives())
            return await lvs._report_voice_ready_after_uplink(
                FakeWs(), "t", 0.0, st, CALL, wait_s=2, poll_s=0.01)

        with patch.object(lvs, "post_internal", lambda *a: posts.append(a) or {"ok": True}):
            ok = run(scenario())
        self.assertTrue(ok)
        self.assertEqual(len(posts), 1)
        path, body = posts[0][2], posts[0][3]
        self.assertEqual(path, "/v1/internal/calls/ready")
        self.assertEqual(body["component"], "voice")
        self.assertEqual(body["call_id"], CALL["call_id"])

    def test_rejected_reservation_closes_the_socket(self):
        ws = FakeWs()
        with patch.object(lvs, "post_internal", lambda *a: {"ok": False, "reason": "stale_lease"}):
            ok = run(lvs._report_voice_ready_after_uplink(
                ws, "t", 0.0, {"first_mic": True}, CALL, wait_s=1, poll_s=0.01))
        self.assertFalse(ok)
        self.assertEqual(ws.closed[0], 1011)


if __name__ == "__main__":
    unittest.main()
