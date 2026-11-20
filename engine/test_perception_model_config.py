# -*- coding: utf-8 -*-
"""perception_engine 換代守門（2026-11-18）：gemini-2.5-flash 12/1 停用後，三處呼叫要能換模型、
3.x 不送 temperature（被忽略、下一代回 400）、守護腦第二層的 JSON 壞掉要重問一次、呼叫失敗要記帳。
不連網：用假的 client。跑法：python engine/test_perception_model_config.py"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import perception_engine as pe  # noqa: E402
from google.genai import types as gtypes  # noqa: E402

ENVS = ("MUNEA_GUARDIAN_MODEL", "MUNEA_PERCEPTION_MODEL", "MUNEA_GUARDIAN_THINKING")


class _Resp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate_content(self, model=None, contents=None, config=None):
        self.calls.append({"model": model, "config": config})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Resp(r)


class _FakeClient:
    def __init__(self, replies):
        self.models = _FakeModels(replies)


class PerceptionModelConfigTest(unittest.TestCase):
    def setUp(self):
        self._saved_env = {k: os.environ.pop(k, None) for k in ENVS}
        self._saved_client = pe._genai_client

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        pe._genai_client = self._saved_client

    def _use(self, replies):
        fake = _FakeClient(replies)
        pe._genai_client = lambda: fake
        return fake

    def test_default_models_are_not_the_retired_one(self):
        self.assertNotEqual(pe.guardian_model(), "gemini-2.5-flash")
        self.assertNotEqual(pe.perception_model(), "gemini-2.5-flash")
        with open(pe.__file__, encoding="utf-8") as f:
            self.assertNotIn('model="gemini-2.5-flash"', f.read(), "還有寫死停用模型的呼叫")

    def test_env_overrides(self):
        os.environ["MUNEA_GUARDIAN_MODEL"] = "gemini-x"
        os.environ["MUNEA_PERCEPTION_MODEL"] = "gemini-y"
        os.environ["MUNEA_GUARDIAN_THINKING"] = "LOW"
        self.assertEqual(pe.guardian_model(), "gemini-x")
        self.assertEqual(pe.perception_model(), "gemini-y")
        self.assertEqual(pe.guardian_thinking(), "low")

    def test_gen_config_drops_temperature_on_3x_keeps_on_2x(self):
        c3 = pe._gen_config(gtypes, "gemini-3.5-flash-lite", temperature=0.1, thinking="low", system_instruction="x")
        self.assertIsNone(c3.temperature)
        self.assertTrue(str(c3.thinking_config.thinking_level).upper().endswith("LOW"))
        c2 = pe._gen_config(gtypes, "gemini-2.5-flash", temperature=0.1, thinking="low", system_instruction="x")
        self.assertEqual(c2.temperature, 0.1)
        self.assertIsNone(c2.thinking_config)

    def test_guardian_review_sends_schema_and_retries_bad_json_once(self):
        good = json.dumps({"level": "critical", "category": "self_harm", "confidence": 0.9, "reason": "r"})
        fake = self._use(['{"level": "critical",, "x"', good])
        before = dict(pe.GUARDIAN_REVIEW_STATS)
        out = pe.guardian_semantic_review("我把藥都存起來了，今晚一次吃掉", None, True)
        self.assertEqual((out or {}).get("level"), "critical")
        self.assertEqual(len(fake.models.calls), 2)
        cfg = fake.models.calls[0]["config"]
        self.assertTrue(cfg.response_json_schema)
        self.assertIsNone(cfg.temperature)
        self.assertEqual(pe.GUARDIAN_REVIEW_STATS["retries"], before["retries"] + 1)
        self.assertEqual(pe.GUARDIAN_REVIEW_STATS["errors"], before["errors"])

    def test_guardian_review_counts_failures_and_never_raises(self):
        before = pe.GUARDIAN_REVIEW_STATS["errors"]
        self._use([RuntimeError("quota")])
        self.assertIsNone(pe.guardian_semantic_review("今天胸口很悶", None, False))
        self.assertEqual(pe.GUARDIAN_REVIEW_STATS["errors"], before + 1)
        self._use(["not json", "still not json"])
        self.assertIsNone(pe.guardian_semantic_review("今天胸口很悶", None, False))
        self.assertEqual(pe.GUARDIAN_REVIEW_STATS["errors"], before + 2)

    def test_mood_and_topics_use_configurable_model(self):
        os.environ["MUNEA_PERCEPTION_MODEL"] = "gemini-3.5-flash-lite"
        mood = json.dumps({"mood": "平穩", "level": 3, "confidence": 0.5})
        fake = self._use([mood, '{"topics": []}'])
        self.assertEqual(pe.analyze_conversation_mood([{"role": "user", "text": "今天還不錯"}])["mood"], "平穩")
        self.assertEqual(pe.fetch_weekly_topics(2), [])
        self.assertEqual([c["model"] for c in fake.models.calls], ["gemini-3.5-flash-lite"] * 2)
        self.assertTrue(all(c["config"].temperature is None for c in fake.models.calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
