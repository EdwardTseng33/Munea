#!/usr/bin/env python3
"""後台名冊「持有點數」欄要顯示每一戶的真餘額。

真踩過（2026-07-29 上線前巡後台）：名冊上 11 戶通通印「0 點」，但資料庫裡那些帳號
確實有 5 點、453 點——舊版 _account_points_map 只有「當前 scoped 那一戶」拿得到真餘額，
其餘一律填 0。後果不只是數字難看：「快用完名單」那一頁是拿這個欄位算的，等於整頁失去意義。

這支釘住兩件事：多戶時每一戶都要拿到自己的餘額；資料庫查不到時寧可退回舊行為也不編數字。
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("GEMINI_API_KEY", "admin-points-map-test-key")

import server
import supabase_adapter

A1 = "11111111-1111-4111-8111-111111111111"
A2 = "22222222-2222-4222-8222-222222222222"
A3 = "33333333-3333-4333-8333-333333333333"


class FakeBackend:
    def __init__(self, balances=None, enabled=True, raises=False):
        self._balances = balances or {}
        self._enabled = enabled
        self._raises = raises
        self.asked_for = None

    def enabled(self):
        return self._enabled

    def load_account_credit_balances(self, account_ids):
        if self._raises:
            raise RuntimeError("supabase down")
        self.asked_for = list(account_ids)
        return dict(self._balances)


class AccountPointsMapTests(unittest.TestCase):
    def accounts(self, *ids):
        return [{"accountId": aid} for aid in ids]

    def test_every_house_gets_its_own_balance(self):
        backend = FakeBackend({A1: 5, A2: 453, A3: 0})
        with patch.object(server, "data_backend", return_value=backend):
            points = server._account_points_map(self.accounts(A1, A2, A3))
        self.assertEqual(points, {A1: 5, A2: 453, A3: 0})
        self.assertEqual(backend.asked_for, [A1, A2, A3])

    def test_house_missing_from_result_is_zero_not_dropped(self):
        """資料庫沒回這一戶＝那戶沒有可用錢包，要顯示 0，不能整欄消失。"""
        backend = FakeBackend({A1: 5})
        with patch.object(server, "data_backend", return_value=backend):
            points = server._account_points_map(self.accounts(A1, A2))
        self.assertEqual(points[A1], 5)
        self.assertEqual(points[A2], 0)

    def test_backend_failure_falls_back_and_does_not_invent(self):
        """查詢炸掉時退回舊的 scoped 行為——寧可顯示 0，也不憑空給數字。"""
        backend = FakeBackend(raises=True)
        with patch.object(server, "data_backend", return_value=backend), \
             patch.object(server, "load_credits_store", return_value={"accountId": A1}), \
             patch.object(server, "credit_wallet_summary", return_value={"total": 7}):
            points = server._account_points_map(self.accounts(A1, A2))
        self.assertEqual(points[A1], 7)
        self.assertEqual(points[A2], 0)


class LoadAccountCreditBalancesTests(unittest.TestCase):
    def adapter(self):
        return supabase_adapter.SupabaseAdapter(env={
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
            "MUNEA_DATABASE_PROVIDER": "supabase",
            "MUNEA_SUPABASE_ACCOUNT_ID": A1,
            "MUNEA_SUPABASE_PERSON_ID": A2,
        })

    def test_sums_active_wallets_per_account_in_one_query(self):
        adapter = self.adapter()
        calls = []

        def fake_select(table, query=None):
            calls.append((table, (query or {}).get("status")))
            return [
                {"account_id": A1, "balance": 5},
                {"account_id": A1, "balance": 3},   # 同一戶多個錢包要加總
                {"account_id": A2, "balance": 453},
            ]

        with patch.object(adapter, "_select", side_effect=fake_select):
            balances = adapter.load_account_credit_balances([A1, A2, A3])

        self.assertEqual(balances[A1], 8)
        self.assertEqual(balances[A2], 453)
        self.assertNotIn(A3, balances)
        self.assertEqual(len(calls), 1, "只准打一次，不能逐戶查")
        self.assertEqual(calls[0][1], "eq.active", "只算還能用的錢包")

    def test_no_ids_skips_the_query(self):
        adapter = self.adapter()
        with patch.object(adapter, "_select") as select:
            self.assertEqual(adapter.load_account_credit_balances([]), {})
        select.assert_not_called()

    def test_bad_balance_value_is_skipped_not_crashing(self):
        adapter = self.adapter()
        with patch.object(adapter, "_select",
                          return_value=[{"account_id": A1, "balance": "壞掉的值"},
                                        {"account_id": A1, "balance": 5}]):
            balances = adapter.load_account_credit_balances([A1])
        self.assertEqual(balances[A1], 5)


if __name__ == "__main__":
    unittest.main()
