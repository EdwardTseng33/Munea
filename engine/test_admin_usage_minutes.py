#!/usr/bin/env python3
"""名冊「聊聊分鐘」欄：累積 ＋ 本月，用來看誰是大戶。

真實來源是 credit_ledger——通話每分鐘扣 1 點記一筆（event_type=credits_consumed）。
不用 voice_sessions（表是空的）也不用 usage_ledger（used 欄一直是 0、沒在累加），
更不能拿「近 30 天推算值」冒充累積量：那答不了「誰是大戶」。

這支釘住：一次撈完不逐戶查、只算消耗、本月要分得出來、撈到上限要老實標示、查不到不編數字。
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("GEMINI_API_KEY", "admin-usage-minutes-test-key")

import supabase_adapter

A1 = "11111111-1111-4111-8111-111111111111"
A2 = "22222222-2222-4222-8222-222222222222"
A3 = "33333333-3333-4333-8333-333333333333"


def make_adapter():
    return supabase_adapter.SupabaseAdapter(env={
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
        "MUNEA_DATABASE_PROVIDER": "supabase",
        "MUNEA_SUPABASE_ACCOUNT_ID": A1,
        "MUNEA_SUPABASE_PERSON_ID": A2,
    })


class UsageMinutesTests(unittest.TestCase):
    def test_splits_lifetime_and_this_month(self):
        adapter = make_adapter()
        rows = [
            {"account_id": A1, "amount": -1, "created_at": "2026-07-29T10:00:00Z"},
            {"account_id": A1, "amount": -1, "created_at": "2026-07-28T10:00:00Z"},
            {"account_id": A1, "amount": -1, "created_at": "2026-06-30T10:00:00Z"},
            {"account_id": A2, "amount": -5, "created_at": "2026-05-01T10:00:00Z"},
        ]
        with patch.object(adapter, "_select", return_value=rows):
            out = adapter.load_account_usage_minutes([A1, A2, A3], month_prefix="2026-07")
        self.assertEqual(out[A1]["totalMinutes"], 3)
        self.assertEqual(out[A1]["monthMinutes"], 2)
        self.assertEqual(out[A2]["totalMinutes"], 5)
        self.assertEqual(out[A2]["monthMinutes"], 0)
        # 沒有任何紀錄的帳號要是 0，不是整筆消失——前端才分得出「沒聊過」跟「查不到」
        self.assertEqual(out[A3], {"totalMinutes": 0, "monthMinutes": 0, "truncated": False})

    def test_only_one_query_and_only_consumption(self):
        adapter = make_adapter()
        calls = []

        def fake_select(table, query=None):
            calls.append((table, (query or {}).get("event_type")))
            return []

        with patch.object(adapter, "_select", side_effect=fake_select):
            adapter.load_account_usage_minutes([A1, A2])
        self.assertEqual(len(calls), 1, "不准逐戶查")
        self.assertEqual(calls[0][0], "credit_ledger")
        self.assertEqual(calls[0][1], "eq.credits_consumed", "只算消耗，不要把贈點也算成使用量")

    def test_hitting_the_row_cap_is_reported(self):
        """撈到上限代表數字可能不完整——要老實標，不能假裝是全部。"""
        adapter = make_adapter()
        rows = [{"account_id": A1, "amount": -1, "created_at": "2026-07-01T00:00:00Z"}] * 5
        with patch.object(adapter, "_select", return_value=rows):
            out = adapter.load_account_usage_minutes([A1], month_prefix="2026-07", limit=5)
        self.assertTrue(out[A1]["truncated"])

    def test_bad_rows_are_skipped_not_crashing(self):
        adapter = make_adapter()
        rows = [
            {"account_id": A1, "amount": "壞掉", "created_at": "2026-07-01T00:00:00Z"},
            {"account_id": A1, "amount": -2, "created_at": "2026-07-02T00:00:00Z"},
            {"account_id": None, "amount": -9, "created_at": "2026-07-02T00:00:00Z"},
        ]
        with patch.object(adapter, "_select", return_value=rows):
            out = adapter.load_account_usage_minutes([A1], month_prefix="2026-07")
        self.assertEqual(out[A1]["totalMinutes"], 2)

    def test_no_ids_skips_the_query(self):
        adapter = make_adapter()
        with patch.object(adapter, "_select") as select:
            self.assertEqual(adapter.load_account_usage_minutes([]), {})
        select.assert_not_called()


class ServerUsageMapTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server

    def test_backend_failure_returns_empty_so_ui_shows_dash(self):
        """查不到就回空——前端顯示「—」，不要拿 0 冒充「沒聊過」。"""
        class Boom:
            def enabled(self): return True
            def load_account_usage_minutes(self, ids): raise RuntimeError("down")
        with patch.object(self.server, "data_backend", return_value=Boom()):
            self.assertEqual(self.server._account_usage_minutes_map([{"accountId": A1}]), {})


if __name__ == "__main__":
    unittest.main()
