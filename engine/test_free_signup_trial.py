#!/usr/bin/env python3
"""免費額度（2026-11-26 起）：註冊送一次 5 分鐘，用完就訂閱或加買；不會每天／每週再給。"""
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

    def test_new_account_gets_five_once_and_bootstrap_is_idempotent(self):
        store = server.default_credits_store()
        first, replay = self.run_with(
            json_store_patches(store, created_at=server.utc_now()),
            lambda: (server.ensure_free_signup_trial("account-a"), server.ensure_free_signup_trial("account-a")),
        )
        self.assertTrue(first["ok"])
        self.assertFalse(first["idempotentReplay"])
        self.assertEqual((first["mode"], first["period"], first["credits"]), ("free_once", "free-once", 5))
        self.assertEqual(first["walletSummary"]["freeAllowance"], 5)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["walletSummary"]["total"], 5)
        grants = [tx for tx in store["transactions"] if tx["type"] == "grant"]
        self.assertEqual([g["idempotencyKey"] for g in grants], ["free-signup-trial:account-a"])
        wallet = next(w for w in store["wallets"] if w["type"] == "free_allowance")
        self.assertIsNone(wallet.get("expiresAt"), "一次性 5 分鐘不會到期")

    def test_used_up_is_not_refilled_on_a_later_day(self):
        store = server.default_credits_store()
        self.run_with(json_store_patches(store, created_at=server.utc_now()),
                      lambda: server.ensure_free_signup_trial("account-a"))
        for wallet in store["wallets"]:
            if wallet["type"] == "free_allowance":
                wallet["balance"] = 0
        later = self.run_with(json_store_patches(store, created_at="2026-07-01T00:00:00Z"),
                              lambda: server.ensure_free_signup_trial("account-a"))
        self.assertTrue(later["idempotentReplay"])
        self.assertEqual(later["walletSummary"]["total"], 0, "用掉的不回補、也不會每天／每週再給")
        self.assertEqual(sum(1 for tx in store["transactions"] if tx["type"] == "grant"), 1)

    def test_old_account_that_got_legacy_five_points_gets_nothing_more(self):
        store = server.default_credits_store()
        store["wallets"] = [
            {"id": "wallet_purchased", "type": "purchased", "period": None, "balance": 3, "status": "active"},
        ]
        store["transactions"] = [
            {"id": "tx-old", "type": "grant", "walletId": "wallet_purchased", "amount": 5,
             "reason": "free_signup_voice_avatar_trial", "idempotencyKey": "free-signup-trial:account-a"},
        ]
        result = self.run_with(
            json_store_patches(store, created_at="2026-07-01T00:00:00Z"),
            lambda: server.ensure_free_signup_trial("account-a"),
        )
        self.assertTrue(result["idempotentReplay"])
        self.assertEqual(result["walletSummary"]["purchased"], 3, "舊的一次性 5 點剩下的要保留")
        self.assertEqual(result["walletSummary"]["total"], 3)
        self.assertFalse(any(w["type"] == "free_allowance" for w in store["wallets"]))

    def test_account_that_only_had_daily_allowance_gets_five_once_and_daily_wallet_closes(self):
        store = server.default_credits_store()
        store["wallets"] = [
            {"id": "wallet_free-daily_2099-01-01", "type": "free_allowance", "period": "free-daily:2099-01-01",
             "balance": 7, "expiresAt": "2099-01-01T16:00:00Z", "status": "active"},
        ]
        store["transactions"] = [
            {"id": "tx-daily", "type": "grant", "walletId": "wallet_free-daily_2099-01-01", "amount": 10,
             "reason": "free_allowance_free_daily", "idempotencyKey": "free-allowance:account-a:free-daily:2099-01-01"},
        ]
        result = self.run_with(json_store_patches(store, created_at=server.utc_now()),
                               lambda: server.ensure_free_signup_trial("account-a"))
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(result["walletSummary"]["total"], 5, "每日錢包收掉、補一次 5 分鐘")
        daily = next(w for w in store["wallets"] if w["period"] == "free-daily:2099-01-01")
        self.assertEqual(daily["metadata"]["closedBy"], "035_free_once")

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

    def test_supabase_falls_back_to_old_rpc_when_new_one_is_missing(self):
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
        self.assertEqual((result["mode"], result["credits"]), ("free_once", 5))

    def test_supabase_uses_new_rpc(self):
        class Backend:
            def enabled(self):
                return True

            def ensure_free_allowance(self):
                return {"ok": True, "mode": "free_once", "period": "free-once", "credits": 5,
                        "balance": 5, "idempotentReplay": False}

            def grant_free_signup_trial(self):
                raise AssertionError("新的資料庫函式在的時候不該走舊的註冊送點")

        with patch.object(server, "data_backend", return_value=Backend()):
            result = server.ensure_free_signup_trial("11111111-1111-4111-8111-111111111111")
        self.assertEqual((result["mode"], result["credits"], result["walletSummary"]["total"]), ("free_once", 5, 5))

    def test_default_free_plan_bundles_voice_and_avatar(self):
        entitlements = server.default_billing_store()["entitlements"]
        self.assertTrue(entitlements["voiceCompanion"])
        self.assertTrue(entitlements["realtimeAvatar"])
        self.assertEqual(entitlements["signupTrialCredits"], 5, "2026-11-26：註冊送一次 5 分鐘")
        self.assertEqual(entitlements["freeOnceMinutes"], 5)
        for gone in ("freeTrialDays", "freeTrialDailyMinutes", "freeWeeklyMinutes"):
            self.assertNotIn(gone, entitlements, "沒有天數概念")
        self.assertEqual(entitlements["creditMinutes"], 1)
        # 2026-07-31 #458：免費版開放 1 位家人（本人＋1＝2）。
        # 程式改對了、守門沒跟上，main 的出貨閘門紅著——今天第七次同一個病。
        self.assertEqual(entitlements["familyMembersMax"], 2,
                         "免費版現在是本人＋1 位家人＝2；改這個數字要連動邀請與加入的開關")


if __name__ == "__main__":
    unittest.main()
