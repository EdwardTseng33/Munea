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
os.environ["MUNEA_VOICE_CALL_MEMORY"] = "1"   # 功能總開關預設關；測試明確打開
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


class FeatureGateTest(unittest.TestCase):
    """總開關預設關：現行 Voice 部署沒有 Supabase env，落地是容器本機 JSON
    （全來電者共用、回收即失），沒明確開啟前收發都必須是 no-op。"""

    def test_disabled_flag_makes_persist_and_recap_noop(self):
        _reset_summaries()
        server.append_conversation_summary({"summary": "fresh call"})
        with patch.dict(os.environ, {"MUNEA_VOICE_CALL_MEMORY": ""}):
            with patch.object(server, "butler_post_turn_response") as post_turn:
                self.assertIsNone(server.persist_voice_call_turns(
                    [{"role": "user", "content": "喂"}]))
            post_turn.assert_not_called()
            self.assertEqual(server.recent_call_recap_line(), "")
        # 重新打開就恢復
        self.assertIn("上次聊天", server.recent_call_recap_line())


class PersonScopeTest(unittest.TestCase):
    """收線回寫與開場接續必須同 scope 隔離：A 的上次聊天不能講給 B 聽。"""

    def test_recap_only_sees_same_person_scope(self):
        _reset_summaries()
        server.persist_voice_call_turns(
            [{"role": "user", "content": "我今天去復健"},
             {"role": "assistant", "content": "辛苦了"}],
            voice_session_id="call-a", person_id="voice-user-a")
        line_a = server.recent_call_recap_line(person_id="voice-user-a")
        line_b = server.recent_call_recap_line(person_id="voice-user-b")
        self.assertIn("上次聊天", line_a)
        self.assertEqual(line_b, "")

    def test_persist_without_scope_falls_back_to_primary(self):
        _reset_summaries()
        server.persist_voice_call_turns(
            [{"role": "user", "content": "喂喂"},
             {"role": "assistant", "content": "我在"}],
            voice_session_id="call-dev")
        summaries = server.load_conversation_summaries(limit=5)
        self.assertEqual(
            summaries[-1].get("personId"), server.PRIMARY_CARE_RECIPIENT_ID)


class VoiceBrainBridgeTest(unittest.TestCase):
    """B 路線：Voice 掛斷交 Brain 代存、開場向 Brain 要重點。
    Brain 端點以內部密語為啟用條件（不受 MUNEA_VOICE_CALL_MEMORY 管）。"""

    def test_brain_endpoints_work_even_when_master_flag_off(self):
        _reset_summaries()
        with patch.dict(os.environ, {"MUNEA_VOICE_CALL_MEMORY": ""}):
            stored = server.voice_call_memory_response({
                "turns": [{"role": "user", "content": "我今天去看醫生"},
                          {"role": "assistant", "content": "檢查還順利嗎"}],
                "char": "寧寧", "voiceSessionId": "live-9",
            })
            self.assertTrue(stored["ok"] and stored["stored"])
            recap = server.voice_call_recap_response({})
            self.assertIn("上次聊天", recap["recapLine"])

    def test_brain_endpoint_unknown_identity_falls_back_to_default_person(self):
        _reset_summaries()
        # json 模式 resolve_auth_identity 回 None → identityResolved=False、走預設人
        result = server.voice_call_memory_response({
            "userId": "99999999-9999-4999-8999-999999999999",
            "turns": [{"role": "user", "content": "喂"}],
        })
        self.assertTrue(result["ok"])
        self.assertFalse(result["identityResolved"])

    def test_brain_channel_config_requires_both_url_and_secret(self):
        env = {"MUNEA_BRAIN_INTERNAL_URL": "http://brain", "MUNEA_VOICE_BRAIN_SECRET": "s3"}
        with patch.dict(os.environ, env):
            self.assertEqual(live_voice_server._brain_memory_config(), ("http://brain", "s3"))
        with patch.dict(os.environ, {"MUNEA_BRAIN_INTERNAL_URL": "http://brain",
                                     "MUNEA_VOICE_BRAIN_SECRET": ""}):
            self.assertEqual(live_voice_server._brain_memory_config(), (None, None))
        with patch.dict(os.environ, {"MUNEA_BRAIN_INTERNAL_URL": "",
                                     "MUNEA_VOICE_BRAIN_SECRET": "s3"}):
            self.assertEqual(live_voice_server._brain_memory_config(), (None, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
