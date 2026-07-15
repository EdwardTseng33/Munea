#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "free-trial-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


class DisabledDataBackend:
    """Keep the grant on the JSON path even when engine/.env.local points at Supabase."""

    def enabled(self):
        return False


class FreeSignupTrialTests(unittest.TestCase):
    def test_grant_is_five_credits_and_account_idempotent(self):
        store = server.default_credits_store()

        def load():
            return server.normalize_credits_store(store)

        def save(updated):
            store.clear()
            store.update(server.normalize_credits_store(updated))
            return server.normalize_credits_store(store)

        with patch.object(server, "data_backend", return_value=DisabledDataBackend()), \
             patch.object(server, "load_credits_store", side_effect=load), \
             patch.object(server, "save_credits_store", side_effect=save):
            first = server.ensure_free_signup_trial("account-a")
            replay = server.ensure_free_signup_trial("account-a")

        self.assertTrue(first["ok"])
        self.assertFalse(first["idempotentReplay"])
        self.assertEqual(first["walletSummary"]["total"], 5)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["walletSummary"]["total"], 5)
        grants = [tx for tx in store["transactions"] if tx["reason"] == "free_signup_voice_avatar_trial"]
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["idempotencyKey"], "free-signup-trial:account-a")

    def test_default_free_plan_bundles_voice_and_avatar(self):
        entitlements = server.default_billing_store()["entitlements"]
        self.assertTrue(entitlements["voiceCompanion"])
        self.assertTrue(entitlements["realtimeAvatar"])
        self.assertEqual(entitlements["signupTrialCredits"], 5)
        self.assertEqual(entitlements["creditMinutes"], 1)
        self.assertEqual(entitlements["familyMembersMax"], 1)


if __name__ == "__main__":
    unittest.main()
