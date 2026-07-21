#!/usr/bin/env python3
"""測試帳號隔離（A 案：名冊預設隱藏 + 數據自動排除 + 人工標記）驗證。"""
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "test-account-isolation-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


ACCOUNT_ID = "11111111-1111-4111-8111-111111111111"
TEST_ACCOUNT_ID = "22222222-2222-4222-8222-222222222222"
PERSON_ID = "33333333-3333-4333-8333-333333333333"


def fake_target(account_name="測試家庭"):
    return {"accountName": account_name, "identity": {"accountId": ACCOUNT_ID, "personId": PERSON_ID}}


class FakeBackend:
    """假的 data_backend()，模擬 SupabaseAdapter 對外可見的介面，不碰真網路。"""

    def __init__(self, accounts=None, signals=None, enabled=True, set_flag_error=None):
        self._accounts = accounts if accounts is not None else []
        self._signals = signals if signals is not None else {"domainTestIds": set(), "manualTestIds": set()}
        self._enabled = enabled
        self._set_flag_error = set_flag_error
        self.set_flag_calls = []

    def enabled(self):
        return self._enabled

    def load_admin_accounts(self, query=None, limit=50):
        return self._accounts

    def resolve_test_account_signals(self, account_ids=None, limit=200):
        return self._signals

    def set_account_test_flag(self, account_id, is_test):
        self.set_flag_calls.append((account_id, is_test))
        if self._set_flag_error:
            raise self._set_flag_error
        return {"id": account_id, "is_test_account": is_test}

    def status(self):
        return {"provider": "fake", "configured": True}


def make_account(account_id, name, is_test):
    return {
        "accountId": account_id,
        "accountName": name,
        "familyGroup": {"id": "fg-" + account_id, "name": name + " 家"},
        "primaryPerson": {"id": "p-" + account_id, "displayName": name},
        "companion": {"templateId": "nening-real-female", "displayName": "Munea"},
        "familyMembers": {"count": 1, "byRole": {}},
        "isTestAccount": is_test,
    }


class AdminAccountsSummaryTestVisibilityTests(unittest.TestCase):
    def test_test_accounts_hidden_by_default(self):
        accounts = [
            make_account(ACCOUNT_ID, "真實家庭", False),
            make_account(TEST_ACCOUNT_ID, "Munea QA Review", True),
        ]
        with patch.object(server, "data_backend", return_value=FakeBackend(accounts=accounts)), \
             patch.object(server, "_enrich_accounts_with_activity", side_effect=lambda accts, days=30: accts):
            result = server.admin_accounts_summary({})
        ids = [a["accountId"] for a in result["accounts"]]
        self.assertIn(ACCOUNT_ID, ids)
        self.assertNotIn(TEST_ACCOUNT_ID, ids)
        self.assertEqual(result["hiddenTestAccountCount"], 1)
        self.assertFalse(result["filters"]["includeTest"])

    def test_include_test_shows_everyone(self):
        accounts = [
            make_account(ACCOUNT_ID, "真實家庭", False),
            make_account(TEST_ACCOUNT_ID, "Munea QA Review", True),
        ]
        with patch.object(server, "data_backend", return_value=FakeBackend(accounts=accounts)), \
             patch.object(server, "_enrich_accounts_with_activity", side_effect=lambda accts, days=30: accts):
            result = server.admin_accounts_summary({"includeTest": True})
        ids = [a["accountId"] for a in result["accounts"]]
        self.assertIn(ACCOUNT_ID, ids)
        self.assertIn(TEST_ACCOUNT_ID, ids)
        self.assertEqual(result["hiddenTestAccountCount"], 0)

    def test_explicit_account_id_lookup_bypasses_hiding(self):
        accounts = [make_account(TEST_ACCOUNT_ID, "Munea QA Review", True)]
        with patch.object(server, "data_backend", return_value=FakeBackend(accounts=accounts)), \
             patch.object(server, "_enrich_accounts_with_activity", side_effect=lambda accts, days=30: accts):
            result = server.admin_accounts_summary({"accountId": TEST_ACCOUNT_ID})
        ids = [a["accountId"] for a in result["accounts"]]
        self.assertIn(TEST_ACCOUNT_ID, ids)

    def test_resolve_admin_target_identity_finds_test_account(self):
        accounts = [make_account(TEST_ACCOUNT_ID, "Munea QA Review", True)]
        with patch.object(server, "data_backend", return_value=FakeBackend(accounts=accounts)), \
             patch.object(server, "_enrich_accounts_with_activity", side_effect=lambda accts, days=30: accts):
            target = server._resolve_admin_target_identity(TEST_ACCOUNT_ID)
        self.assertIsNotNone(target)
        self.assertEqual(target["identity"]["accountId"], TEST_ACCOUNT_ID)


class TestAccountIdSetTests(unittest.TestCase):
    def setUp(self):
        server._TEST_ACCOUNT_ID_CACHE["ids"] = set()
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0

    def tearDown(self):
        server._TEST_ACCOUNT_ID_CACHE["ids"] = set()
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0

    def test_unions_domain_and_manual_ids(self):
        backend = FakeBackend(signals={"domainTestIds": {"acct-a"}, "manualTestIds": {"acct-b"}})
        with patch.object(server, "data_backend", return_value=backend):
            ids = server.test_account_id_set(force_refresh=True)
        self.assertEqual(ids, {"acct-a", "acct-b"})

    def test_fail_open_keeps_previous_cache_on_error(self):
        server._TEST_ACCOUNT_ID_CACHE["ids"] = {"acct-old"}
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0

        class BoomBackend(FakeBackend):
            def resolve_test_account_signals(self, account_ids=None, limit=200):
                raise RuntimeError("supabase unreachable")

        with patch.object(server, "data_backend", return_value=BoomBackend()):
            ids = server.test_account_id_set(force_refresh=True)
        self.assertIn("acct-old", ids)

    def test_cache_ttl_avoids_recompute(self):
        backend = FakeBackend(signals={"domainTestIds": {"acct-a"}, "manualTestIds": set()})
        with patch.object(server, "data_backend", return_value=backend) as mock_backend:
            server.test_account_id_set(force_refresh=True)
            server.test_account_id_set()
            server.test_account_id_set()
        self.assertEqual(mock_backend.call_count, 1)

    def test_env_excluded_ids_still_included(self):
        backend = FakeBackend(signals={"domainTestIds": set(), "manualTestIds": set()})
        with patch.object(server, "data_backend", return_value=backend), \
             patch.dict(os.environ, {"MUNEA_ANALYTICS_EXCLUDED_ACCOUNT_IDS": "acct-env"}):
            ids = server.test_account_id_set(force_refresh=True)
        self.assertIn("acct-env", ids)


class IsAnalyticsExcludedEventTests(unittest.TestCase):
    def setUp(self):
        server._TEST_ACCOUNT_ID_CACHE["ids"] = {"test-acct-1"}
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = server.time.time() + 999

    def tearDown(self):
        server._TEST_ACCOUNT_ID_CACHE["ids"] = set()
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0

    def test_event_from_test_account_is_excluded(self):
        event = {"accountId": "test-acct-1", "properties": {}}
        self.assertTrue(server.is_analytics_excluded_event(event))

    def test_event_from_real_account_is_not_excluded(self):
        event = {"accountId": "real-acct-1", "properties": {}}
        self.assertFalse(server.is_analytics_excluded_event(event))


class AdminSetTestAccountFlagTests(unittest.TestCase):
    def test_missing_account_id_rejected(self):
        result = server.admin_set_test_account_flag_response({"isTestAccount": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "account_id_required")

    def test_unknown_account_rejected(self):
        with patch.object(server, "_resolve_admin_target_identity", return_value=None):
            result = server.admin_set_test_account_flag_response({"accountId": "nope", "isTestAccount": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "account_not_found")

    def test_backend_not_configured_rejected(self):
        backend = FakeBackend(enabled=False)
        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "data_backend", return_value=backend):
            result = server.admin_set_test_account_flag_response({"accountId": ACCOUNT_ID, "isTestAccount": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "test_flag_not_configured")

    def test_missing_column_reports_clear_error(self):
        backend = FakeBackend(set_flag_error=RuntimeError("column is_test_account does not exist"))
        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "data_backend", return_value=backend):
            result = server.admin_set_test_account_flag_response({"accountId": ACCOUNT_ID, "isTestAccount": True})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "test_account_column_missing")

    def test_happy_path_marks_and_writes_audit_and_refreshes_cache(self):
        backend = FakeBackend()
        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target("陳先生家")), \
             patch.object(server, "data_backend", return_value=backend), \
             patch.object(server, "append_audit_event") as audit:
            result = server.admin_set_test_account_flag_response(
                {"accountId": ACCOUNT_ID, "isTestAccount": True}, headers={"X-Munea-Admin-Token": "t"}
            )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["accountId"], ACCOUNT_ID)
        self.assertTrue(result["isTestAccount"])
        self.assertEqual(backend.set_flag_calls, [(ACCOUNT_ID, True)])
        audit.assert_called_once()
        event = audit.call_args.args[0]
        self.assertEqual(event["eventType"], "admin_test_account_flag_changed")
        self.assertEqual(event["accountId"], ACCOUNT_ID)
        self.assertTrue(event["details"]["isTestAccount"])

    def test_unmark_sends_false(self):
        backend = FakeBackend()
        with patch.object(server, "_resolve_admin_target_identity", return_value=fake_target()), \
             patch.object(server, "data_backend", return_value=backend), \
             patch.object(server, "append_audit_event"):
            result = server.admin_set_test_account_flag_response({"accountId": ACCOUNT_ID, "isTestAccount": False})
        self.assertTrue(result["ok"])
        self.assertFalse(result["isTestAccount"])
        self.assertEqual(backend.set_flag_calls, [(ACCOUNT_ID, False)])


class RouteRegistrationTests(unittest.TestCase):
    def test_route_is_scope_exempt_and_does_not_require_user_auth(self):
        self.assertIn("/admin/accounts/set-test-flag", server.ADMIN_POST_PATHS)
        self.assertIn("/admin/accounts/set-test-flag", server.SCOPE_EXEMPT_PATHS)
        self.assertFalse(server.auth_required_for_request("/admin/accounts/set-test-flag", {}))


if __name__ == "__main__":
    unittest.main()
