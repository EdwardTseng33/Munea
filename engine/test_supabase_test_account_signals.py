#!/usr/bin/env python3
"""SupabaseAdapter 測試帳號判準（resolve_test_account_signals / set_account_test_flag）驗證。
只打樁 _select／_request／_fetch_auth_user_email，不碰真網路。"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

import supabase_adapter


def make_adapter():
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
        "MUNEA_DATABASE_PROVIDER": "supabase",
        "MUNEA_SUPABASE_ACCOUNT_ID": "11111111-1111-4111-8111-111111111111",
        "MUNEA_SUPABASE_PERSON_ID": "22222222-2222-4222-8222-222222222222",
    }
    return supabase_adapter.SupabaseAdapter(env=env)


class ResolveTestAccountSignalsTests(unittest.TestCase):
    def test_not_enabled_returns_empty(self):
        adapter = supabase_adapter.SupabaseAdapter(env={})
        result = adapter.resolve_test_account_signals(account_ids=["a"])
        self.assertEqual(result["domainTestIds"], set())
        self.assertEqual(result["manualTestIds"], set())

    def test_domain_and_manual_ids_combined(self):
        adapter = make_adapter()

        def fake_select(table, query):
            if table == "accounts":
                return [{"id": "acct-b"}]
            if table == "account_members":
                return [
                    {"account_id": "acct-a", "user_id": "user-a"},
                    {"account_id": "acct-b", "user_id": "user-b"},
                ]
            raise AssertionError("unexpected table " + table)

        def fake_email(user_id):
            return {"user-a": "qa-review@munea.net", "user-b": "someone@gmail.com"}.get(user_id)

        with patch.object(adapter, "_select", side_effect=fake_select), \
             patch.object(adapter, "_fetch_auth_user_email", side_effect=fake_email):
            result = adapter.resolve_test_account_signals(account_ids=["acct-a", "acct-b"])
        self.assertEqual(result["domainTestIds"], {"acct-a"})
        self.assertEqual(result["manualTestIds"], {"acct-b"})

    def test_manual_flag_query_failure_is_fail_open(self):
        adapter = make_adapter()

        def fake_select(table, query):
            if table == "accounts":
                raise supabase_adapter.SupabaseRequestError("column is_test_account does not exist")
            if table == "account_members":
                return [{"account_id": "acct-a", "user_id": "user-a"}]
            raise AssertionError("unexpected table " + table)

        with patch.object(adapter, "_select", side_effect=fake_select), \
             patch.object(adapter, "_fetch_auth_user_email", return_value="qa-review@munea.net"):
            result = adapter.resolve_test_account_signals(account_ids=["acct-a"])
        self.assertEqual(result["manualTestIds"], set())
        self.assertEqual(result["domainTestIds"], {"acct-a"})

    def test_membership_query_failure_is_fail_open(self):
        adapter = make_adapter()

        def fake_select(table, query):
            if table == "accounts":
                return []
            if table == "account_members":
                raise supabase_adapter.SupabaseRequestError("unreachable")
            raise AssertionError("unexpected table " + table)

        with patch.object(adapter, "_select", side_effect=fake_select):
            result = adapter.resolve_test_account_signals(account_ids=["acct-a"])
        self.assertEqual(result["domainTestIds"], set())
        self.assertEqual(result["manualTestIds"], set())

    def test_no_account_ids_returns_empty_without_querying(self):
        adapter = make_adapter()
        with patch.object(adapter, "_select") as mock_select:
            result = adapter.resolve_test_account_signals(account_ids=[])
        mock_select.assert_not_called()
        self.assertEqual(result["domainTestIds"], set())

    def test_self_scan_mode_queries_accounts_first(self):
        adapter = make_adapter()
        calls = []

        def fake_select(table, query):
            calls.append((table, dict(query)))
            if table == "accounts" and "order" in query:
                return [{"id": "acct-a"}, {"id": "acct-b"}]
            if table == "accounts" and "is_test_account" in query:
                return []
            if table == "account_members":
                return []
            raise AssertionError("unexpected call " + str((table, query)))

        with patch.object(adapter, "_select", side_effect=fake_select):
            result = adapter.resolve_test_account_signals(account_ids=None, limit=50)
        self.assertEqual(result["domainTestIds"], set())
        self.assertTrue(any(t == "accounts" and "order" in q for t, q in calls))


class FetchAuthUserEmailTests(unittest.TestCase):
    def test_not_configured_returns_none(self):
        adapter = supabase_adapter.SupabaseAdapter(env={})
        self.assertIsNone(adapter._fetch_auth_user_email("11111111-1111-4111-8111-111111111111"))

    def test_invalid_uuid_returns_none(self):
        adapter = make_adapter()
        self.assertIsNone(adapter._fetch_auth_user_email("not-a-uuid"))

    def test_network_failure_returns_none(self):
        adapter = make_adapter()
        with patch("supabase_adapter.urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertIsNone(adapter._fetch_auth_user_email("11111111-1111-4111-8111-111111111111"))

    def test_parses_wrapped_and_flat_user_shapes(self):
        adapter = make_adapter()
        import json as _json

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return _json.dumps(self._payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with patch("supabase_adapter.urllib.request.urlopen", return_value=FakeResp({"user": {"email": "a@munea.net"}})):
            self.assertEqual(adapter._fetch_auth_user_email("11111111-1111-4111-8111-111111111111"), "a@munea.net")
        with patch("supabase_adapter.urllib.request.urlopen", return_value=FakeResp({"email": "b@munea.net"})):
            self.assertEqual(adapter._fetch_auth_user_email("11111111-1111-4111-8111-111111111111"), "b@munea.net")


class SetAccountTestFlagTests(unittest.TestCase):
    def test_not_enabled_raises(self):
        adapter = supabase_adapter.SupabaseAdapter(env={})
        with self.assertRaises(RuntimeError):
            adapter.set_account_test_flag("11111111-1111-4111-8111-111111111111", True)

    def test_invalid_account_id_raises(self):
        adapter = make_adapter()
        with self.assertRaises(RuntimeError):
            adapter.set_account_test_flag("not-a-uuid", True)

    def test_happy_path_patches_accounts_table(self):
        adapter = make_adapter()
        with patch.object(adapter, "_request", return_value=[{"id": "acct-a", "is_test_account": True}]) as mock_request:
            result = adapter.set_account_test_flag("11111111-1111-4111-8111-111111111111", True)
        self.assertEqual(result, {"id": "acct-a", "is_test_account": True})
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "PATCH")
        self.assertEqual(args[1], "accounts")
        self.assertEqual(kwargs["payload"], {"is_test_account": True})

    def test_column_missing_propagates_error(self):
        adapter = make_adapter()
        with patch.object(adapter, "_request", side_effect=supabase_adapter.SupabaseRequestError("column is_test_account does not exist")):
            with self.assertRaises(supabase_adapter.SupabaseRequestError):
                adapter.set_account_test_flag("11111111-1111-4111-8111-111111111111", True)


if __name__ == "__main__":
    unittest.main()
