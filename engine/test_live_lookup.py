#!/usr/bin/env python3

import types
import unittest

import live_lookup


class LiveLookupTest(unittest.TestCase):
    def test_query_is_normalized_and_bounded(self):
        query = live_lookup.normalize_query("  南港   興南街  " + "好" * 400)
        self.assertTrue(query.startswith("南港 興南街"))
        self.assertLessEqual(len(query), live_lookup.MAX_QUERY_CHARS)

    def test_request_keeps_location_context_without_voice_preamble(self):
        request = live_lookup.build_request("有什麼好吃的", "台北市南港區")
        self.assertIn("台北市南港區", request)
        self.assertIn("有什麼好吃的", request)
        self.assertIn("使用 Google Search 查證", request)
        self.assertNotIn(live_lookup.CUE_TEXT, request)

    def test_request_asks_for_spoken_style_material(self):
        """2026-07-24：材料是給語音助理直接照著念的，不能是條列或書面體。"""
        request = live_lookup.build_request("附近牙醫推薦")
        self.assertIn("口語", request)
        self.assertIn("不要用條列符號", request)
        self.assertIn("不要用書面體", request)

    def test_result_removes_urls_and_citations_and_counts_sources(self):
        grounding = types.SimpleNamespace(grounding_chunks=[object(), object()])
        candidate = types.SimpleNamespace(grounding_metadata=grounding)
        response = types.SimpleNamespace(
            text="推薦 [甲店](https://example.com/a) [1]，另見 https://example.com/b",
            candidates=[candidate],
        )
        result = live_lookup.extract_result(response)
        self.assertEqual(result["sources"], 2)
        self.assertIn("甲店", result["text"])
        self.assertNotIn("http", result["text"])
        self.assertNotIn("[1]", result["text"])

    def test_empty_result_is_an_explicit_failure(self):
        with self.assertRaisesRegex(ValueError, "no answer material"):
            live_lookup.extract_result(types.SimpleNamespace(text="", candidates=[]))

    def test_ungrounded_result_is_not_treated_as_fresh_information(self):
        response = types.SimpleNamespace(text="我印象中可能有一家店", candidates=[])
        with self.assertRaisesRegex(ValueError, "no grounded sources"):
            live_lookup.extract_result(response)


if __name__ == "__main__":
    unittest.main(verbosity=2)
