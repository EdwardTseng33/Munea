#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "mood-trend-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
from supabase_adapter import SupabaseAdapter  # noqa: E402


ACCOUNT = "11111111-1111-4111-8111-111111111111"
PERSON = "22222222-2222-4222-8222-222222222222"


class AdminMoodTrendTests(unittest.TestCase):
    """後台「心情趨勢」：跨帳號心情訊號趨勢＋需要關心名單（JSON 備援路徑）。
    資料源只用 wellbeing_signals；不得出現醫療判讀措辭、也不得外洩聊天內容。"""

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        handle.write(b"[]")
        handle.close()
        self.path = handle.name
        self.path_patch = patch.object(server, "WELLBEING_PATH", self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    @staticmethod
    def _day(offset):
        return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%d")

    def _seed(self, items):
        server.write_json_file(self.path, items)

    def test_empty_window_reports_null_rate_not_zero(self):
        response = server.admin_mood_trend({"days": 30, "limit": 50})
        self.assertTrue(response["ok"])
        self.assertIsNone(response["averageLevel"])
        self.assertIsNone(response["positiveRate"])
        self.assertIsNone(response["lowRate"])
        self.assertEqual(response["daily"], [])
        self.assertEqual(response["watchlist"], [])
        self.assertEqual(response["totals"], {"signals": 0, "positive": 0, "steady": 0, "low": 0, "other": 0})

    def test_totals_daily_and_rates_cross_account(self):
        self._seed([
            {"personId": "person-a", "accountId": "account-a", "date": self._day(0), "mood": "happy", "level": 5, "observedAt": self._day(0) + "T09:00:00Z"},
            {"personId": "person-a", "accountId": "account-a", "date": self._day(1), "mood": "steady", "level": 3, "observedAt": self._day(1) + "T09:00:00Z"},
            {"personId": "person-b", "accountId": "account-b", "date": self._day(0), "mood": "low", "level": 2, "observedAt": self._day(0) + "T10:00:00Z"},
            {"personId": "person-b", "accountId": "account-b", "date": self._day(1), "mood": "mixed", "level": 3, "observedAt": self._day(1) + "T10:00:00Z"},
        ])
        response = server.admin_mood_trend({"days": 30, "limit": 50})
        self.assertTrue(response["ok"])
        self.assertEqual(response["totals"], {"signals": 4, "positive": 1, "steady": 1, "low": 1, "other": 1})
        self.assertAlmostEqual(response["averageLevel"], 3.25, places=2)
        self.assertAlmostEqual(response["positiveRate"], 1 / 3, places=4)
        self.assertAlmostEqual(response["lowRate"], 1 / 3, places=4)
        self.assertEqual(len(response["daily"]), 2)
        self.assertEqual([d["date"] for d in response["daily"]], sorted(d["date"] for d in response["daily"]))

    def test_watchlist_flags_three_or_more_low_signals_in_7_days_even_without_streak(self):
        self._seed([
            {"personId": "person-c", "accountId": "account-c", "date": self._day(1), "mood": "low", "level": 2, "observedAt": self._day(1) + "T08:00:00Z"},
            {"personId": "person-c", "accountId": "account-c", "date": self._day(1), "mood": "irritated", "level": 2, "observedAt": self._day(1) + "T12:00:00Z"},
            {"personId": "person-c", "accountId": "account-c", "date": self._day(1), "mood": "tired", "level": 2, "observedAt": self._day(1) + "T18:00:00Z"},
        ])
        response = server.admin_mood_trend({"days": 30, "limit": 50})
        self.assertEqual(len(response["watchlist"]), 1)
        entry = response["watchlist"][0]
        self.assertEqual(entry["personId"], "person-c")
        self.assertEqual(entry["lowCount"], 3)
        self.assertEqual(entry["lowStreak"], 1)

    def test_watchlist_flags_three_consecutive_calendar_days_low(self):
        self._seed([
            {"personId": "person-d", "accountId": "account-d", "date": self._day(2), "mood": "low", "level": 2, "observedAt": self._day(2) + "T09:00:00Z"},
            {"personId": "person-d", "accountId": "account-d", "date": self._day(1), "mood": "tired", "level": 2, "observedAt": self._day(1) + "T09:00:00Z"},
            {"personId": "person-d", "accountId": "account-d", "date": self._day(0), "mood": "irritated", "level": 2, "observedAt": self._day(0) + "T09:00:00Z"},
        ])
        response = server.admin_mood_trend({"days": 30, "limit": 50})
        self.assertEqual(len(response["watchlist"]), 1)
        entry = response["watchlist"][0]
        self.assertEqual(entry["personId"], "person-d")
        self.assertEqual(entry["lowStreak"], 3)
        self.assertEqual(entry["lowCount"], 3)

    def test_non_consecutive_low_days_do_not_count_as_streak(self):
        self._seed([
            {"personId": "person-e", "accountId": "account-e", "date": self._day(6), "mood": "low", "level": 2, "observedAt": self._day(6) + "T09:00:00Z"},
            {"personId": "person-e", "accountId": "account-e", "date": self._day(4), "mood": "steady", "level": 3, "observedAt": self._day(4) + "T09:00:00Z"},
            {"personId": "person-e", "accountId": "account-e", "date": self._day(2), "mood": "low", "level": 2, "observedAt": self._day(2) + "T09:00:00Z"},
        ])
        response = server.admin_mood_trend({"days": 30, "limit": 50})
        self.assertEqual(response["watchlist"], [])

    def test_needs_attention_person_sorted_before_others_and_display_name_optional(self):
        self._seed([
            {"personId": "person-f", "accountId": "account-f", "date": self._day(2), "mood": "low", "level": 2, "observedAt": self._day(2) + "T09:00:00Z"},
            {"personId": "person-f", "accountId": "account-f", "date": self._day(1), "mood": "low", "level": 2, "observedAt": self._day(1) + "T09:00:00Z"},
            {"personId": "person-f", "accountId": "account-f", "date": self._day(0), "mood": "low", "level": 1, "observedAt": self._day(0) + "T09:00:00Z"},
            {"personId": "person-g", "accountId": "account-g", "date": self._day(0), "mood": "low", "level": 2, "observedAt": self._day(0) + "T09:00:00Z"},
            {"personId": "person-g", "accountId": "account-g", "date": self._day(1), "mood": "low", "level": 2, "observedAt": self._day(1) + "T09:00:00Z"},
            {"personId": "person-g", "accountId": "account-g", "date": self._day(2), "mood": "low", "level": 2, "observedAt": self._day(2) + "T09:00:00Z"},
            {"personId": "person-g", "accountId": "account-g", "date": self._day(3), "mood": "low", "level": 2, "observedAt": self._day(3) + "T09:00:00Z"},
        ])
        response = server.admin_mood_trend({"days": 30, "limit": 50})
        watch = response["watchlist"]
        self.assertEqual(len(watch), 2)
        self.assertEqual(watch[0]["personId"], "person-g")
        self.assertEqual(watch[0]["lowStreak"], 4)
        self.assertEqual(watch[1]["personId"], "person-f")
        self.assertEqual(watch[1]["lowStreak"], 3)
        for entry in watch:
            self.assertNotIn("displayName", entry)

    def test_no_medical_claims_in_principle_text(self):
        response = server.admin_mood_trend({})
        for banned in ("療效", "確診", "病情", "憂鬱症", "焦慮症"):
            self.assertNotIn(banned, response["principle"])
        self.assertIn("不是醫療診斷", response["principle"])
        self.assertIn("不是健康建議", response["principle"])
        self.assertIn("AI 依對話內容推測", response["principle"])

    def test_response_never_leaks_conversation_content(self):
        secret_phrase = "提到膝蓋很痛想念女兒"
        self._seed([{
            "personId": "person-h", "accountId": "account-h", "date": self._day(0),
            "mood": "low", "level": 2, "observedAt": self._day(0) + "T09:00:00Z",
            "voiceObs": secret_phrase, "chatObs": secret_phrase, "wordObs": secret_phrase,
            "topics": [secret_phrase], "concerns": [secret_phrase], "positives": [secret_phrase],
        }])
        response = server.admin_mood_trend({"days": 30, "limit": 50})
        import json
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn(secret_phrase, serialized)
        self.assertNotIn("voiceObs", serialized)
        self.assertNotIn("chatObs", serialized)
        self.assertNotIn("wordObs", serialized)
        self.assertNotIn("concerns", serialized)

    def test_test_account_signals_are_excluded_from_totals_and_watchlist(self):
        """2026-07-24 稽核補：這頁原本沒接測試帳號排除，示範／QA 帳號的心情訊號會混進真實數字。"""
        server._TEST_ACCOUNT_ID_CACHE["ids"] = {"test-account-x"}
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = server.time.time() + 999
        try:
            self._seed([
                {"personId": "person-real", "accountId": "account-real", "date": self._day(0), "mood": "happy", "level": 5, "observedAt": self._day(0) + "T09:00:00Z"},
                {"personId": "person-test", "accountId": "test-account-x", "date": self._day(1), "mood": "low", "level": 1, "observedAt": self._day(1) + "T09:00:00Z"},
                {"personId": "person-test", "accountId": "test-account-x", "date": self._day(2), "mood": "low", "level": 1, "observedAt": self._day(2) + "T09:00:00Z"},
                {"personId": "person-test", "accountId": "test-account-x", "date": self._day(3), "mood": "low", "level": 1, "observedAt": self._day(3) + "T09:00:00Z"},
            ])
            response = server.admin_mood_trend({"days": 30, "limit": 50})
        finally:
            server._TEST_ACCOUNT_ID_CACHE["ids"] = set()
            server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0
        self.assertEqual(response["totals"], {"signals": 1, "positive": 1, "steady": 0, "low": 0, "other": 0})
        self.assertEqual(response["watchlist"], [])


class SupabaseAdminMoodTrendCrossAccountTests(unittest.TestCase):
    """Adapter 層：後台跨帳號心情訊號查詢不能被單一 account_id 過濾掉。"""

    def test_load_admin_wellbeing_signals_has_no_account_scope_filter(self):
        adapter = SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{
                "id": "wb-1",
                "account_id": "other-account-not-in-identity",
                "person_id": "other-person-not-in-identity",
                "mood": "low",
                "level": 2,
                "signal_date": "2026-07-18",
                "observed_at": "2026-07-18T09:00:00Z",
                "facts": {},
            }]

        with patch.object(adapter, "_select", side_effect=fake_select):
            rows = adapter.load_admin_wellbeing_signals(since_iso="2026-06-19T00:00:00Z", limit=100)

        self.assertEqual(captured["table"], "wellbeing_signals")
        self.assertNotIn("account_id", captured["query"])
        self.assertNotIn("person_id", captured["query"])
        self.assertEqual(captured["query"]["observed_at"], "gte.2026-06-19T00:00:00Z")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accountId"], "other-account-not-in-identity")
        self.assertEqual(rows[0]["mood"], "low")


if __name__ == "__main__":
    unittest.main()
