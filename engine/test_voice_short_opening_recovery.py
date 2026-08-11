#!/usr/bin/env python3
"""Regression gate for a short first utterance that Vertex never commits."""

import asyncio
import json
import os
import types as pytypes
import unittest
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "test")

import live_voice_server as voice
from voice_locale_session import VoiceLocaleSession


class ShortOpeningPredicateTests(unittest.TestCase):
    def test_audible_two_second_first_turn_is_eligible(self):
        previous_engine = voice.VOICE_ENGINE
        voice.VOICE_ENGINE = "vertex25"
        try:
            self.assertTrue(voice.should_recover_short_opening(
                input_bytes=64000,
                non_silent=True,
                asr_turns=0,
                assistant_output_bytes=0,
                recoveries=0,
            ))
        finally:
            voice.VOICE_ENGINE = previous_engine

    def test_gemini31_never_injects_a_second_opening_turn(self):
        previous_engine = voice.VOICE_ENGINE
        voice.VOICE_ENGINE = "31"
        try:
            self.assertFalse(voice.should_recover_short_opening(
                input_bytes=64000,
                non_silent=True,
                asr_turns=0,
                assistant_output_bytes=0,
                recoveries=0,
            ))
        finally:
            voice.VOICE_ENGINE = previous_engine

    def test_silence_long_audio_and_existing_activity_are_ineligible(self):
        previous_engine = voice.VOICE_ENGINE
        voice.VOICE_ENGINE = "vertex25"
        base = dict(input_bytes=64000, non_silent=True, asr_turns=0,
                    assistant_output_bytes=0, recoveries=0)
        try:
            for override in (
                {"non_silent": False},
                {"input_bytes": voice.SHORT_OPENING_MAX_PCM_BYTES + 2},
                {"asr_turns": 1},
                {"assistant_output_bytes": 2},
                {"recoveries": 1},
            ):
                case = dict(base)
                case.update(override)
                self.assertFalse(voice.should_recover_short_opening(**case))
        finally:
            voice.VOICE_ENGINE = previous_engine


class SameVoiceCueTests(unittest.TestCase):
    def test_lookup_cues_never_fall_back_to_generic_tts(self):
        char = "same-voice-regression"
        wait_text = "我還在幫你確認。"
        cue_text = "我幫你看看。"
        wait_key = (char, "zh-TW", wait_text)
        cue_key = (char, "zh-TW", cue_text)
        voice._LOOKUP_WAIT_PCM.pop(wait_key, None)
        voice._LOOKUP_CUE_PCM.pop(cue_key, None)
        with mock.patch.object(voice, "_gemini_tts_pcm", return_value=b""), \
                mock.patch.object(voice.server, "tts_b64") as generic_tts:
            self.assertEqual(voice._lookup_wait_pcm(char, wait_text), b"")
            self.assertEqual(voice._lookup_cue_pcm(char, cue_text), b"")
        generic_tts.assert_not_called()
        voice._LOOKUP_WAIT_PCM.pop(wait_key, None)
        voice._LOOKUP_CUE_PCM.pop(cue_key, None)


class ProviderSessionRecoveryTests(unittest.TestCase):
    class ProviderError(Exception):
        code = 1008

    def test_exact_resumable_provider_abort_rotates_the_underlying_session(self):
        error = self.ProviderError("1008 None. The operation was aborted.")
        self.assertTrue(voice._recoverable_provider_session_abort(error, "resume-handle"))

    def test_abort_without_handle_and_other_1008_errors_remain_fatal(self):
        aborted = self.ProviderError("1008 None. The operation was aborted.")
        policy = self.ProviderError("1008 policy violation")
        self.assertFalse(voice._recoverable_provider_session_abort(aborted, ""))
        self.assertFalse(voice._recoverable_provider_session_abort(policy, "resume-handle"))

class _ShortOpeningWs:
    def __init__(self):
        self.messages = [b"\xa0\x0f" * 32000, json.dumps({"type": "audio_end"})]
        self.sent = []
        self.recovered = asyncio.Event()

    async def send(self, data):
        self.sent.append(data)
        if isinstance(data, str):
            event = json.loads(data)
            if event.get("type") == "short_turn_recovery":
                self.recovered.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.messages:
            return self.messages.pop(0)
        await self.recovered.wait()
        raise StopAsyncIteration


class _SilentProviderSession:
    def __init__(self):
        self.realtime_inputs = []
        self.client_turns = []

    async def send_realtime_input(self, **kwargs):
        self.realtime_inputs.append(kwargs)

    async def send_client_content(self, **kwargs):
        self.client_turns.append(kwargs)

    async def receive(self):
        await asyncio.Event().wait()
        if False:
            yield None


class _ProviderAudioSession(_SilentProviderSession):
    async def receive(self):
        await asyncio.sleep(0.01)
        yield pytypes.SimpleNamespace(
            go_away=None,
            session_resumption_update=None,
            server_content=None,
            data=b"\x01\x00" * 2400,
            tool_call=None,
        )
        await asyncio.Event().wait()


class _CloseSoonWs(_ShortOpeningWs):
    async def __anext__(self):
        if self.messages:
            return self.messages.pop(0)
        await asyncio.sleep(0.12)
        raise StopAsyncIteration


class ShortOpeningRecoveryFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_silent_provider_gets_exactly_one_safe_recovery_turn(self):
        previous_delay = voice.SHORT_OPENING_RECOVERY_MS
        previous_engine = voice.VOICE_ENGINE
        voice.VOICE_ENGINE = "vertex25"
        voice.SHORT_OPENING_RECOVERY_MS = 50
        try:
            ws = _ShortOpeningWs()
            session = _SilentProviderSession()
            st = voice._new_call_state()
            call_ended, _ = await voice._run_voice_session(
                session, cli=None, ws=ws, cid=91, t0=0.0, st=st, char="a05",
                location=None, topics=None, fam=0, day_call=None,
                call_payload=None, gate_key="", call_token="",
                asr_context_terms=["a05"], first_connect=False,
                resumption_handle="same-session",
                voice_locale_session=VoiceLocaleSession({}),
            )
        finally:
            voice.SHORT_OPENING_RECOVERY_MS = previous_delay
            voice.VOICE_ENGINE = previous_engine

        self.assertTrue(call_ended)
        self.assertEqual(st["short_opening_recoveries"], 1)
        self.assertEqual(len(session.client_turns), 1)
        self.assertTrue(session.client_turns[0]["turn_complete"])
        recovery_events = [
            json.loads(item) for item in ws.sent
            if isinstance(item, str) and json.loads(item).get("type") == "short_turn_recovery"
        ]
        self.assertEqual(len(recovery_events), 1)
        self.assertEqual(recovery_events[0]["reason"], "uncommitted_short_opening")
        self.assertTrue(any(item.get("audio_stream_end") for item in session.realtime_inputs))

    async def test_real_provider_audio_cancels_pending_recovery(self):
        previous_delay = voice.SHORT_OPENING_RECOVERY_MS
        previous_engine = voice.VOICE_ENGINE
        voice.VOICE_ENGINE = "vertex25"
        voice.SHORT_OPENING_RECOVERY_MS = 80
        try:
            ws = _CloseSoonWs()
            session = _ProviderAudioSession()
            st = voice._new_call_state()
            await voice._run_voice_session(
                session, cli=None, ws=ws, cid=92, t0=0.0, st=st, char="a05",
                location=None, topics=None, fam=0, day_call=None,
                call_payload=None, gate_key="", call_token="",
                asr_context_terms=["a05"], first_connect=False,
                resumption_handle="same-session",
                voice_locale_session=VoiceLocaleSession({}),
            )
        finally:
            voice.SHORT_OPENING_RECOVERY_MS = previous_delay
            voice.VOICE_ENGINE = previous_engine

        self.assertEqual(st["short_opening_recoveries"], 0)
        self.assertEqual(session.client_turns, [])
        self.assertFalse(any(
            isinstance(item, str)
            and json.loads(item).get("type") == "short_turn_recovery"
            for item in ws.sent
        ))


if __name__ == "__main__":
    unittest.main()
