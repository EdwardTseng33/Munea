#!/usr/bin/env python3
"""Contract tests for the two-phase voice barge-in acceptance probe."""

import asyncio
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))

from voice_barge_probe import FRAME_BYTES, _barge_frames, _stream_two_phase_barge


def _pcm_frame(amplitude):
    samples = FRAME_BYTES // 2
    return struct.pack("<" + "h" * samples, *([amplitude] * samples))


class _FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


async def _test_two_phase_order():
    quiet = [_pcm_frame(100)] * 5
    voice = [_pcm_frame(4000)] * 14
    trailing = [_pcm_frame(2500)] * 3
    websocket = _FakeWebSocket()

    payload = await _stream_two_phase_barge(
        websocket,
        b"".join(quiet + voice + trailing),
        threshold=0.04,
        sustain_ms=150,
        pre_roll_ms=400,
        frame_sleep=0,
        tail_seconds=0,
    )

    first = json.loads(websocket.messages[0])
    commit_index = next(
        index for index, message in enumerate(websocket.messages)
        if isinstance(message, str) and json.loads(message).get("type") == "barge_in"
    )
    commit = json.loads(websocket.messages[commit_index])

    assert first["type"] == "barge_in_start"
    assert commit_index == payload["evidence_frames"] + 1
    assert all(isinstance(message, bytes) for message in websocket.messages[1:commit_index])
    assert commit == {"type": "barge_in", **payload}
    assert payload["evidence_frames"] >= 8
    assert payload["sustain_ms"] == 150
    assert payload["candidate_threshold"] == 0.04
    assert websocket.messages[1] == quiet[0], "retained evidence must preserve speech onset margin"
    assert any(isinstance(message, bytes) for message in websocket.messages[commit_index + 1:])


def _test_rejects_missing_sustained_voice():
    choppy = b"".join(
        [_pcm_frame(4000), _pcm_frame(100)] * 6
    )
    try:
        _barge_frames(choppy, threshold=0.04, sustain_ms=150, pre_roll_ms=400)
    except RuntimeError as exc:
        assert "never crosses its own sustain gate" in str(exc)
    else:
        raise AssertionError("choppy non-sustained input should be rejected")


def main():
    asyncio.run(_test_two_phase_order())
    _test_rejects_missing_sustained_voice()
    print("PASS voice barge probe contract")


if __name__ == "__main__":
    main()
