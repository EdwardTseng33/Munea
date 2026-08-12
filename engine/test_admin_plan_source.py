#!/usr/bin/env python3
"""名冊的「方案」欄必須讀真正的訂閱帳，不准從購買事件推算。

真踩過（2026-07-30）：Edward 在後台把測試帳號改成 Pro——訂閱帳寫進 pro/active、200 點也發了，
但名冊那一欄還是「免費」。因為它是從 product_events 的 subscription_purchased 推算的，
而**後台改方案不會產生那種事件**，永遠讀不到。

這是同一種病的第三次（點數欄假 0、聊聊分鐘拿近 30 天推算值冒充累積量）：
**顯示的來源必須跟執行的來源同一個。**
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("GEMINI_API_KEY", "admin-plan-source-test-key")

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


class LoadAccountPlansTests(unittest.TestCase):
    def test_latest_active_row_wins(self):
        """訂閱帳是流水，要取每戶最新一筆——舊的 free 不能蓋掉新的 pro。"""
        adapter = make_adapter()
        rows = [
            {"account_id": A1, "active_plan": "pro", "status": "active", "created_at": "2026-07-30T10:04:59Z", "updated_at": "2026-07-30T10:04:59Z"},
            {"account_id": A1, "active_plan": "free", "status": "inactive", "created_at": "2026-07-15T00:00:00Z", "updated_at": "2026-07-15T00:00:00Z"},
            {"account_id": A2, "active_plan": "plus", "status": "active", "created_at": "2026-07-20T00:00:00Z", "updated_at": "2026-07-20T00:00:00Z"},
        ]
        with patch.object(adapter, "_select", return_value=rows):
            plans = adapter.load_account_plans([A1, A2, A3])
        self.assertEqual(plans[A1], "pro")
        self.assertEqual(plans[A2], "plus")
        self.assertNotIn(A3, plans, "沒有訂閱紀錄的帳號不要硬塞方案，讓呼叫端退回原本判斷")

    def test_expired_or_downgraded_counts_as_free(self):
        """過期／降級的 pro 不該還掛著 Pro。"""
        adapter = make_adapter()
        rows = [
            {"account_id": A1, "active_plan": "pro", "status": "expired", "created_at": "2026-07-30T00:00:00Z", "updated_at": "2026-07-30T00:00:00Z"},
            {"account_id": A2, "active_plan": "plus", "status": "inactive", "created_at": "2026-07-30T00:00:00Z", "updated_at": "2026-07-30T00:00:00Z"},
        ]
        with patch.object(adapter, "_select", return_value=rows):
            plans = adapter.load_account_plans([A1, A2])
        self.assertEqual(plans[A1], "free")
        self.assertEqual(plans[A2], "free")

    def test_unknown_plan_value_falls_back_to_free(self):
        adapter = make_adapter()
        with patch.object(adapter, "_select",
                          return_value=[{"account_id": A1, "active_plan": "enterprise-x",
                                         "status": "active", "created_at": "2026-07-30T00:00:00Z"}]):
            self.assertEqual(adapter.load_account_plans([A1])[A1], "free")

    def test_reads_the_ledger_once_not_per_account(self):
        adapter = make_adapter()
        calls = []

        def fake_select(table, query=None):
            calls.append((table, (query or {}).get("order")))
            return []

        with patch.object(adapter, "_select", side_effect=fake_select):
            adapter.load_account_plans([A1, A2, A3])
        self.assertEqual(len(calls), 1, "只准打一次，不要逐戶查")
        self.assertEqual(calls[0][0], "subscription_ledger")
        self.assertEqual(calls[0][1], "updated_at.desc", "排序要跟 App 讀訂閱帳那條路一致")

    def test_no_ids_skips_the_query(self):
        adapter = make_adapter()
        with patch.object(adapter, "_select") as select:
            self.assertEqual(adapter.load_account_plans([]), {})
        select.assert_not_called()


class RosterUsesLedgerPlanTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server

    def test_ledger_plan_beats_event_guess(self):
        """後台改方案只會寫訂閱帳、不會產生購買事件——名冊必須以訂閱帳為準。"""
        accounts = [{"accountId": A1}]
        with patch.object(self.server, "_account_activity_index",
                          return_value=({A1: {"voiceMinutes": 0.0, "avatarMinutes": 0.0, "eventCount": 1,
                                              "lastActiveAt": None, "plan": None, "planAt": None}},
                                        {"voiceMinutes": 0.0, "avatarMinutes": 0.0, "eventCount": 0,
                                         "lastActiveAt": None, "plan": None, "planAt": None})), \
             patch.object(self.server, "_account_points_map", return_value={A1: 200}), \
             patch.object(self.server, "_account_usage_minutes_map", return_value={}), \
             patch.object(self.server, "_account_plan_map", return_value={A1: "pro"}):
            out = self.server._enrich_accounts_with_activity(accounts)
        self.assertEqual(out[0]["plan"], "pro", "訂閱帳說 pro，名冊就該是 pro")

    def test_falls_back_to_event_guess_when_ledger_silent(self):
        """訂閱帳查不到時保留舊行為（Apple 購買事件推算），不要一律變免費。"""
        accounts = [{"accountId": A1}]
        with patch.object(self.server, "_account_activity_index",
                          return_value=({A1: {"voiceMinutes": 0.0, "avatarMinutes": 0.0, "eventCount": 1,
                                              "lastActiveAt": None, "plan": "munea.plus.monthly", "planAt": "x"}},
                                        {"voiceMinutes": 0.0, "avatarMinutes": 0.0, "eventCount": 0,
                                         "lastActiveAt": None, "plan": None, "planAt": None})), \
             patch.object(self.server, "_account_points_map", return_value={}), \
             patch.object(self.server, "_account_usage_minutes_map", return_value={}), \
             patch.object(self.server, "_account_plan_map", return_value={}):
            out = self.server._enrich_accounts_with_activity(accounts)
        self.assertEqual(out[0]["plan"], "plus")


if __name__ == "__main__":
    unittest.main()
