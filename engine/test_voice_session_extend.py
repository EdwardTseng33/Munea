#!/usr/bin/env python3
"""通話延長契約（2026-07-25 · GoAway 預警接續＋context window 壓縮）。

Edward 拍板方向：Gemini Live 對每條底層連線有時間上限，快到的時候會先送 GoAway
預警（time_left）才真的斷線；不接住這個訊號，通話滿 10 分鐘左右就會被硬切斷
（長輩通話常超過）。修法：收到預警＋在天然的輪替空檔（turn_complete）就主動換一條
新的底層連線、帶著 session resumption handle 接續同一通邏輯電話；沒有天然空檔時
用保底 watchdog 逼換線。context window 壓縮讓長通話不會撞上下文長度上限。

跑法：python engine/test_voice_session_extend.py（純函式＋假物件，不需要網路或鑰匙）
"""
import asyncio
import os
import types as pytypes
import unittest

os.environ.setdefault("GEMINI_API_KEY", "test")

import live_voice_server as voice
from google.genai import types


# ── 純函式測試 ──────────────────────────────────────────────────────────

class ParseDurationSecondsTests(unittest.TestCase):
    def test_typical_go_away_duration_string(self):
        self.assertEqual(voice._parse_duration_seconds("9.5s"), 9.5)
        self.assertEqual(voice._parse_duration_seconds("10s"), 10.0)

    def test_missing_or_empty_falls_back_to_default(self):
        self.assertEqual(voice._parse_duration_seconds(None, default=5.0), 5.0)
        self.assertEqual(voice._parse_duration_seconds("", default=5.0), 5.0)

    def test_garbage_falls_back_to_default_without_raising(self):
        self.assertEqual(voice._parse_duration_seconds("not-a-duration", default=7.0), 7.0)

    def test_never_negative(self):
        self.assertEqual(voice._parse_duration_seconds("-5s", default=3.0), 0.0)


class VoiceSessionExtendToggleTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("MUNEA_VOICE_SESSION_EXTEND", None)

    def tearDown(self):
        os.environ.pop("MUNEA_VOICE_SESSION_EXTEND", None)

    def test_default_enabled(self):
        self.assertTrue(voice._voice_session_extend_enabled())

    def test_explicit_zero_disables(self):
        os.environ["MUNEA_VOICE_SESSION_EXTEND"] = "0"
        self.assertFalse(voice._voice_session_extend_enabled())

    def test_any_other_value_stays_enabled(self):
        os.environ["MUNEA_VOICE_SESSION_EXTEND"] = "1"
        self.assertTrue(voice._voice_session_extend_enabled())


class LiveConfigSessionExtendWiringTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("MUNEA_VOICE_SESSION_EXTEND", None)

    def tearDown(self):
        os.environ.pop("MUNEA_VOICE_SESSION_EXTEND", None)

    def test_default_enables_resumption_and_compression(self):
        cfg = voice.live_config(char="寧寧", name="寧寧")
        self.assertIsNotNone(cfg.session_resumption)
        self.assertIsNotNone(cfg.context_window_compression)
        self.assertIsNone(cfg.session_resumption.handle)

    def test_resumption_handle_passthrough_on_reconnect(self):
        cfg = voice.live_config(char="寧寧", name="寧寧", resumption_handle="handle-abc")
        self.assertEqual(cfg.session_resumption.handle, "handle-abc")

    def test_escape_hatch_disables_both(self):
        os.environ["MUNEA_VOICE_SESSION_EXTEND"] = "0"
        cfg = voice.live_config(char="寧寧", name="寧寧")
        self.assertIsNone(cfg.session_resumption)
        self.assertIsNone(cfg.context_window_compression)


# ── 假物件：跑一次 _run_voice_session，驗證真的控制流程（不是只讀原始碼字面）──

class _FakeWs:
    """假的瀏覽器端 WebSocket：send 只記錄；沒有訊息可讀，等到被取消為止
    （模擬使用者在這條底層連線換線期間沒有新動作——真正的重點是 from_live 那邊）。"""

    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()  # 永遠不會有下一則訊息，直到工作被取消
        raise StopAsyncIteration


def _msg(**kwargs):
    return pytypes.SimpleNamespace(**kwargs)


class _FakeSession:
    """假的 Gemini Live session：receive() 依序吐出「批次」訊息，每批對應真實 SDK
    的一次 receive() 呼叫（真正的 session.receive() 吐到 turn_complete 就停、下一輪
    再呼叫一次繼續讀）。批次用完之後再呼叫 receive() 一律吐空——對應「這條底層連線
    真的沒東西了」，讓 from_live 的 `if not got: break` 正確觸發。"""

    def __init__(self, batches):
        self.batches = batches
        self._call_index = 0
        self.tool_responses = []

    async def receive(self):
        if self._call_index >= len(self.batches):
            return
        batch = self.batches[self._call_index]
        self._call_index += 1
        for m in batch:
            yield m

    async def send_client_content(self, **kwargs):
        pass

    async def send_tool_response(self, **kwargs):
        self.tool_responses.append(kwargs)


class RunVoiceSessionGoAwayReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_goaway_then_turn_complete_returns_reconnect_with_handle(self):
        go_away = _msg(go_away=_msg(time_left="5s"))
        resumption = _msg(session_resumption_update=_msg(new_handle="handle-xyz", resumable=True))
        turn_complete = _msg(
            server_content=_msg(
                input_transcription=None, output_transcription=None,
                interrupted=False, turn_complete=True,
            ),
            data=None, tool_call=None,
        )
        session = _FakeSession([[go_away, resumption, turn_complete]])
        ws = _FakeWs()
        st = voice._new_call_state()

        call_ended, handle = await voice._run_voice_session(
            session, cli=None, ws=ws, cid=1, t0=0.0, st=st, char="寧寧",
            location=None, topics=None, fam=0, day_call=None,
            call_payload=None, gate_key="", call_token="",
            asr_context_terms=["寧寧"], first_connect=False, resumption_handle=None,
        )

        self.assertFalse(call_ended)   # 這通電話沒結束——只是該換一條底層連線了
        self.assertEqual(handle, "handle-xyz")
        self.assertTrue(st["goaway_pending"])  # 由呼叫端（handle()）在下一輪重連前重置

    async def test_no_goaway_natural_end_reports_call_ended(self):
        """對照組：完全沒有 GoAway，正常聊完一輪之後 receive() 直接沒東西了——
        這是「底層連線真的結束」，不該被誤判成需要重連。"""
        turn_complete = _msg(
            server_content=_msg(
                input_transcription=None, output_transcription=None,
                interrupted=False, turn_complete=True,
            ),
            data=None, tool_call=None,
        )
        session = _FakeSession([[turn_complete]])
        ws = _FakeWs()
        st = voice._new_call_state()

        call_ended, handle = await voice._run_voice_session(
            session, cli=None, ws=ws, cid=2, t0=0.0, st=st, char="寧寧",
            location=None, topics=None, fam=0, day_call=None,
            call_payload=None, gate_key="", call_token="",
            asr_context_terms=["寧寧"], first_connect=False, resumption_handle="old-handle",
        )

        self.assertTrue(call_ended)
        # 沒有新的 session_resumption_update → 沿用呼叫端傳進來的舊 handle
        self.assertEqual(handle, "old-handle")


if __name__ == "__main__":
    unittest.main(verbosity=2)
