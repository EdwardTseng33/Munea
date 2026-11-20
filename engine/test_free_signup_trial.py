#!/usr/bin/env python3
"""免費額度（2026-11-20 起）：前 7 天每天 10 分鐘、之後每週 10 分鐘，取代註冊一次送 5 點。"""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "free-trial-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


class DisabledDataBackend:
    """Keep the grant on the JSON path even when engine/.env.local points at Supabase."""

    def enabled(self):
        return False


def json_store_patches(store, *, created_at, account_id="account-a", billing=None):
    def load():
        return server.normalize_credits_store(store)

    def save(updated):
        store.clear()
        store.update(server.normalize_credits_store(updated))
        return server.normalize_credits_store(store)

    profile = {"account": {"id": account_id, "createdAt": created_at}, "primaryCareRecipientId": "person-a",
               "familyGroup": {"id": "fg-a"}}
    return [
        patch.object(server, "data_backend", return_value=DisabledDataBackend()),
        patch.object(server, "load_credits_store", side_effect=load),
        patch.object(server, "save_credits_store", side_effect=save),
        patch.object(server, "load_billing_store", return_value=server.normalize_billing_store(billing or {})),
        patch.object(server, "load_app_profile_store", return_value=profile),
        patch.object(server, "json_credit_share_state", return_value={"accounts": {}, "memberships": []}),
    ]


class FreeSignupTrialTests(unittest.TestCase):
    def run_with(self, patches, fn):
        for p in patches:
            p.start()
        try:
            return fn()
        finally:
            for p in reversed(patches):
                p.stop()

    def test_new_account_gets_ten_today_and_bootstrap_is_idempotent(self):
        store = server.default_credits_store()
        now_iso = server.utc_now()
        first, replay = self.run_with(
            json_store_patches(store, created_at=now_iso),
            lambda: (server.ensure_free_signup_trial("account-a"), server.ensure_free_signup_trial("account-a")),
        )
        self.assertTrue(first["ok"])
        self.assertFalse(first["idempotentReplay"])
        self.assertEqual(first["mode"], "free_daily")
        self.assertEqual(first["credits"], 10)
        self.assertEqual(first["walletSummary"]["total"], 10)
        self.assertEqual(first["walletSummary"]["freeAllowance"], 10)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["walletSummary"]["total"], 10)
        grants = [tx for tx in store["transactions"] if tx["type"] == "grant"]
        self.assertEqual(len(grants), 1)
        self.assertTrue(grants[0]["idempotencyKey"].startswith("free-allowance:account-a:free-daily:"))
        self.assertFalse(any(tx["reason"] == "free_signup_voice_avatar_trial" for tx in store["transactions"]),
                         "不再發一次性 5 點")

    def test_old_account_goes_straight_to_weekly_and_keeps_legacy_five_points(self):
        store = server.default_credits_store()
        store["wallets"] = [
            {"id": "wallet_purchased", "type": "purchased", "period": None, "balance": 3, "status": "active"},
        ]
        result = self.run_with(
            json_store_patches(store, created_at="2026-07-01T00:00:00Z"),
            lambda: server.ensure_free_signup_trial("account-a"),
        )
        self.assertEqual(result["mode"], "free_weekly")
        self.assertTrue(result["period"].startswith("free-weekly:"))
        self.assertEqual(result["walletSummary"]["purchased"], 3, "舊的一次性 5 點剩下的要保留")
        self.assertEqual(result["walletSummary"]["total"], 13)

    def test_paid_account_gets_no_free_allowance(self):
        store = server.default_credits_store()
        billing = {"activePlan": "plus", "subscription": {"status": "active", "expiresAt": "2099-01-01T00:00:00Z"}}
        result = self.run_with(
            json_store_patches(store, created_at=server.utc_now(), billing=billing),
            lambda: server.ensure_free_signup_trial("account-a"),
        )
        self.assertEqual(result["mode"], "plan")
        self.assertEqual(result["credits"], 0)
        self.assertFalse(any(w["type"] == "free_allowance" for w in store["wallets"]))

    def test_supabase_falls_back_to_old_rpc_until_034_is_applied(self):
        class Backend:
            def enabled(self):
                return True

            def ensure_free_allowance(self):
                raise RuntimeError("function munea_ensure_free_allowance does not exist")

            def grant_free_signup_trial(self):
                return {"ok": True, "credits": 5, "balance": 5, "idempotentReplay": False}

        with patch.object(server, "data_backend", return_value=Backend()):
            result = server.ensure_free_signup_trial("11111111-1111-4111-8111-111111111111")
        self.assertTrue(result["ok"])
        self.assertEqual(result["credits"], 5)
        self.assertEqual(result["mode"], "free_signup_trial")

    def test_supabase_uses_new_rpc(self):
        class Backend:
            def enabled(self):
                return True

            def ensure_free_allowance(self):
                return {"ok": True, "mode": "free_daily", "period": "free-daily:2026-11-20", "credits": 10,
                        "balance": 10, "idempotentReplay": False}

            def grant_free_signup_trial(self):
                raise AssertionError("034 套用後不該再走舊的註冊送點")

        with patch.object(server, "data_backend", return_value=Backend()):
            result = server.ensure_free_signup_trial("11111111-1111-4111-8111-111111111111")
        self.assertEqual((result["mode"], result["credits"], result["walletSummary"]["total"]), ("free_daily", 10, 10))

    def test_default_free_plan_bundles_voice_and_avatar(self):
        entitlements = server.default_billing_store()["entitlements"]
        self.assertTrue(entitlements["voiceCompanion"])
        self.assertTrue(entitlements["realtimeAvatar"])
        self.assertEqual(entitlements["signupTrialCredits"], 0, "一次性 5 點已改成每日／每週免費額度")
        self.assertEqual(entitlements["freeTrialDays"], 7)
        self.assertEqual(entitlements["freeTrialDailyMinutes"], 10)
        self.assertEqual(entitlements["freeWeeklyMinutes"], 10)
        self.assertEqual(entitlements["creditMinutes"], 1)
        # 2026-07-31 #458：免費版開放 1 位家人（本人＋1＝2）。
        # 程式改對了、守門沒跟上，main 的出貨閘門紅著——今天第七次同一個病。
        self.assertEqual(entitlements["familyMembersMax"], 2,
                         "免費版現在是本人＋1 位家人＝2；改這個數字要連動邀請與加入的開關")


if __name__ == "__main__":
    unittest.main()
