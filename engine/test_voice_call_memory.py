#!/usr/bin/env python3
"""通話記憶回寫測試（Edward 2026-07-15：20 分鐘後再打還被重問吃飯沒）。

驗三件事：
1. 語音線每輪字幕會收進整通紀錄（_capture_call_turns），防爆上限有效。
2. 收線回寫 persist_voice_call_turns：正規化 history、交給聊後管線；
   對方整通沒說話就跳過；管線炸掉不外拋（收線路徑不能炸）。
3. 上一通重點 recent_call_recap_line：視窗內回接續指令、過期/沒紀錄回空字串。
"""
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "voice-memory-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
_TMP = tempfile.mkdtemp(prefix="munea-voice-memory-")
for _env, _name in (
    ("MUNEA_MEMORY_ITEMS_PATH", "memory_items.json"),
    ("MUNEA_CONVERSATION_SUMMARIES_PATH", "conversation_summaries.json"),
    ("MUNEA_PRODUCT_EVENTS_PATH", "product_events.json"),
    ("MUNEA_RELATIONSHIP_STATES_PATH", "companion_relationship_states.json"),
    ("MUNEA_WELLBEING_PATH", "wellbeing_signals.json"),
):
    os.environ[_env] = os.path.join(_TMP, _name)
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
import live_voice_server  # noqa: E402


def _reset_summaries():
    server.save_conversation_summaries([])


class CaptureCallTurnsTest(unittest.TestCase):
    def test_capture_appends_both_sides_in_order(self):
        st = {"user_buf": "我還沒吃晚餐", "ai_buf": "那等等要記得吃喔", "call_turns": []}
        live_voice_server._capture_call_turns(st)
        self.assertEqual(st["call_turns"], [
            {"role": "user", "content": "我還沒吃晚餐"},
            {"role": "assistant", "content": "那等等要記得吃喔"},
        ])

    def test_capture_skips_empty_and_caps_turns(self):
        st = {"user_buf": "  ", "ai_buf": "", "call_turns": []}
        live_voice_server._capture_call_turns(st)
        self.assertEqual(st["call_turns"], [])
        st = {"user_buf": "好", "ai_buf": "",
              "call_turns": [{"role": "user", "content": str(i)} for i in range(130)]}
        live_voice_server._capture_call_turns(st, max_turns=120)
        self.assertEqual(len(st["call_turns"]), 120)
        self.assertEqual(st["call_turns"][-1], {"role": "user", "content": "好"})

    def test_capture_truncates_long_text(self):
        st = {"user_buf": "很" * 700, "ai_buf": "", "call_turns": []}
        live_voice_server._capture_call_turns(st, max_chars=600)
        self.assertEqual(len(st["call_turns"][0]["content"]), 600)


class PersistVoiceCallTurnsTest(unittest.TestCase):
    def test_persist_normalizes_and_forwards_to_post_turn(self):
        captured = {}

        def fake_post_turn(data):
            captured.update(data)
            return {"ok": True}

        with patch.object(server, "butler_post_turn_response", fake_post_turn):
            result = server.persist_voice_call_turns(
                [
                    {"role": "user", "content": " 我還沒吃 "},
                    {"role": "assistant", "content": "要記得吃喔"},
                    {"role": "user", "content": ""},
                    "not-a-dict",
                ],
                char="寧寧", voice_session_id="call-123",
            )
        self.assertEqual(result, {"ok": True})
        # text 與 content 都要有：memory_engine／心情分析讀 text、conversation_text 讀兩者皆可
        self.assertEqual(captured["history"], [
            {"role": "user", "text": "我還沒吃", "content": "我還沒吃"},
            {"role": "assistant", "text": "要記得吃喔", "content": "要記得吃喔"},
        ])
        self.assertEqual(captured["char"], "寧寧")
        self.assertEqual(captured["voiceSessionId"], "call-123")
        self.assertEqual(captured["source"], "live_voice")

    def test_persist_stringifies_voice_session_id(self):
        captured = {}
        with patch.object(server, "butler_post_turn_response",
                          lambda data: captured.update(data) or {"ok": True}):
            server.persist_voice_call_turns(
                [{"role": "user", "content": "喂"}], voice_session_id=7)
        # 整數流水號必須轉字串，否則 Supabase 端 UUID_RE.match(int) 會 TypeError
        self.assertEqual(captured["voiceSessionId"], "7")
        with patch.object(server, "butler_post_turn_response",
                          lambda data: captured.update(data) or {"ok": True}):
            server.persist_voice_call_turns([{"role": "user", "content": "喂"}])
        self.assertIsNone(captured["voiceSessionId"])

    def test_persist_accepts_text_key_input(self):
        captured = {}
        with patch.object(server, "butler_post_turn_response",
                          lambda data: captured.update(data) or {"ok": True}):
            server.persist_voice_call_turns([{"role": "user", "text": "app 端格式"}])
        self.assertEqual(captured["history"][0]["text"], "app 端格式")

    def test_persist_real_extractors_see_user_text(self):
        """memory_engine.extract 與 mood 分析只讀 text 欄位——確保真萃取看得到對話。"""
        import memory_engine
        history_seen = {}

        def fake_extract(history):
            history_seen["texts"] = [
                h.get("text") for h in history if h.get("role") == "user"]
            return []

        with patch.object(memory_engine, "extract", fake_extract):
            server.persist_voice_call_turns(
                [
                    {"role": "user", "content": "我孫子下個月要結婚了"},
                    {"role": "assistant", "content": "好棒喔"},
                ],
                voice_session_id="call-extract")
        self.assertEqual(history_seen["texts"], ["我孫子下個月要結婚了"])

    def test_persist_skips_when_user_never_spoke(self):
        with patch.object(server, "butler_post_turn_response") as post_turn:
            result = server.persist_voice_call_turns(
                [{"role": "assistant", "content": "阿公你好呀"}])
        self.assertIsNone(result)
        post_turn.assert_not_called()

    def test_persist_swallows_pipeline_errors(self):
        with patch.object(server, "butler_post_turn_response", side_effect=RuntimeError("boom")):
            result = server.persist_voice_call_turns(
                [{"role": "user", "content": "喂？"}])
        self.assertIsNone(result)

    def test_persist_end_to_end_stores_summary(self):
        _reset_summaries()
        result = server.persist_voice_call_turns(
            [
                {"role": "user", "content": "我今天去公園散步"},
                {"role": "assistant", "content": "聽起來很舒服耶"},
            ],
            char="寧寧", voice_session_id="call-e2e",
        )
        self.assertTrue(result and result.get("ok"))
        summaries = server.load_conversation_summaries(limit=10)
        self.assertTrue(summaries)
        self.assertEqual(summaries[-1].get("voiceSessionId"), "call-e2e")
        self.assertFalse(
            summaries[-1].get("privacy", {}).get("storesRawTranscriptByDefault", True))


class RecentCallRecapLineTest(unittest.TestCase):
    def test_recap_within_window(self):
        _reset_summaries()
        server.append_conversation_summary({
            "summary": "Post-turn companion review covered daily topics; user turns: 3.",
            "memoryTags": ["self_harm", "diet"],
        })
        line = server.recent_call_recap_line()
        self.assertIn("上次聊天", line)
        self.assertIn("分鐘", line)
        self.assertIn("不要當開場再問一次", line)
        # memoryTags 是內部英文 slug、可能含守護腦風險分類，絕不能進 prompt
        self.assertNotIn("self_harm", line)
        self.assertNotIn("diet", line)

    def test_recap_expired_returns_empty(self):
        _reset_summaries()
        server.append_conversation_summary({
            "summary": "old call",
            "createdAt": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time() - (server.VOICE_CALL_RECAP_WINDOW_HOURS + 1) * 3600)),
        })
        self.assertEqual(server.recent_call_recap_line(), "")

    def test_recap_empty_store_returns_empty(self):
        _reset_summaries()
        self.assertEqual(server.recent_call_recap_line(), "")

    def test_recap_hours_wording(self):
        _reset_summaries()
        server.append_conversation_summary({
            "summary": "call three hours ago",
            "createdAt": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3 * 3600)),
        })
        line = server.recent_call_recap_line()
        self.assertIn("3 小時", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
