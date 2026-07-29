#!/usr/bin/env python3
"""名冊查「這一戶是誰登入的」要一次撈完，不能一戶問一次。

背景（2026-07-29）：登入資料在 GoTrue（不是一般資料表），沒辦法跟其他表一起 in.() 批次查。
舊法逐一問，6 戶實測就佔掉整支名冊約七成時間——把其他四張表改批次（#329）只解了一半，
戶數上去照樣會撞後台 15 秒逾時。

這支釘住：批次那支只准被問一次、拿到全部 owner；列表沒撈到的才准逐一補問（寧可慢一點，
也不能讓那幾戶的登入資訊整欄空掉）。只打樁內部方法，不碰真網路。
"""
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


class AuthUserBulkLookupTests(unittest.TestCase):
    def test_thirty_houses_ask_the_listing_once(self):
        adapter = make_adapter()
        asked = []

        def fake_select(table, query=None):
            if table == "account_members":
                return [{"account_id": f"acct-{i}", "user_id": f"user-{i}"} for i in range(30)]
            return []

        def fake_map(ids, **kwargs):
            asked.append(list(ids))
            return {i: {"id": i, "email": f"{i}@example.com", "app_metadata": {"provider": "google"}} for i in ids}

        with patch.object(adapter, "_select", side_effect=fake_select), \
             patch.object(adapter, "_fetch_auth_users_map", side_effect=fake_map), \
             patch.object(adapter, "_fetch_auth_user", side_effect=AssertionError("不該再逐一查")):
            signals = adapter.resolve_test_account_signals(account_ids=[f"acct-{i}" for i in range(30)])

        self.assertEqual(len(asked), 1, "30 戶只准問一次")
        self.assertEqual(len(asked[0]), 30)
        self.assertEqual(len(signals["ownersByAccount"]), 30)

    def test_ids_missing_from_listing_fall_back_to_single_lookup(self):
        """列表沒撈到的那幾戶要逐一補問——寧可慢一點，也不能整欄空掉。"""
        adapter = make_adapter()
        singles = []

        def fake_select(table, query=None):
            if table == "account_members":
                return [{"account_id": "acct-a", "user_id": "user-a"},
                        {"account_id": "acct-b", "user_id": "user-b"}]
            return []

        def fake_single(uid):
            singles.append(uid)
            return {"id": uid, "email": f"{uid}@example.com", "app_metadata": {"provider": "email"}}

        with patch.object(adapter, "_select", side_effect=fake_select), \
             patch.object(adapter, "_fetch_auth_users_map",
                          return_value={"user-a": {"id": "user-a", "email": "a@example.com",
                                                   "app_metadata": {"provider": "google"}}}), \
             patch.object(adapter, "_fetch_auth_user", side_effect=fake_single):
            signals = adapter.resolve_test_account_signals(account_ids=["acct-a", "acct-b"])

        owners = signals["ownersByAccount"]
        self.assertEqual(owners["acct-a"]["email"], "a@example.com")
        self.assertEqual(owners["acct-b"]["email"], "user-b@example.com")
        self.assertEqual(singles, ["user-b"], "只有列表沒撈到的那個才准逐一補問")

    def test_domain_test_account_rule_still_works_through_bulk_path(self):
        """走批次路徑後，@munea.net 自動判測試帳號那條規則不能失效。"""
        adapter = make_adapter()

        def fake_select(table, query=None):
            if table == "account_members":
                return [{"account_id": "acct-qa", "user_id": "user-qa"},
                        {"account_id": "acct-real", "user_id": "user-real"}]
            return []

        bulk = {
            "user-qa": {"id": "user-qa", "email": "qa-review@munea.net", "app_metadata": {"provider": "email"}},
            "user-real": {"id": "user-real", "email": "someone@gmail.com", "app_metadata": {"provider": "google"}},
        }
        with patch.object(adapter, "_select", side_effect=fake_select), \
             patch.object(adapter, "_fetch_auth_users_map", return_value=bulk), \
             patch.object(adapter, "_fetch_auth_user", side_effect=AssertionError("不該再逐一查")):
            signals = adapter.resolve_test_account_signals(account_ids=["acct-qa", "acct-real"])

        self.assertEqual(signals["domainTestIds"], {"acct-qa"})


class FetchAuthUsersMapTests(unittest.TestCase):
    """列表接口本身：分頁、提早停、失敗不炸。"""

    def _adapter_with_pages(self, pages):
        adapter = make_adapter()
        calls = []

        class FakeResponse:
            def __init__(self, body):
                self._body = body

            def read(self):
                import json
                return json.dumps(self._body).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            page = int(req.full_url.split("page=")[1].split("&")[0])
            if page > len(pages):
                return FakeResponse({"users": []})
            return FakeResponse({"users": pages[page - 1]})

        return adapter, calls, fake_urlopen

    def test_stops_early_once_every_wanted_id_is_found(self):
        pages = [[{"id": "a"}, {"id": "b"}], [{"id": "c"}]]
        adapter, calls, fake_urlopen = self._adapter_with_pages(pages)
        with patch.object(supabase_adapter.urllib.request, "urlopen", side_effect=fake_urlopen):
            found = adapter._fetch_auth_users_map(["a", "b"], per_page=2)
        self.assertEqual(set(found), {"a", "b"})
        self.assertEqual(len(calls), 1, "想找的都在第一頁就不該再翻下一頁")

    def test_walks_pages_until_found(self):
        pages = [[{"id": "a"}, {"id": "b"}], [{"id": "c"}, {"id": "d"}]]
        adapter, calls, fake_urlopen = self._adapter_with_pages(pages)
        with patch.object(supabase_adapter.urllib.request, "urlopen", side_effect=fake_urlopen):
            found = adapter._fetch_auth_users_map(["d"], per_page=2)
        self.assertEqual(set(found), {"d"})
        self.assertEqual(len(calls), 2)

    def test_network_failure_returns_empty_not_raise(self):
        adapter = make_adapter()
        with patch.object(supabase_adapter.urllib.request, "urlopen", side_effect=OSError("boom")):
            self.assertEqual(adapter._fetch_auth_users_map(["a"]), {})

    def test_no_ids_skips_the_call(self):
        adapter = make_adapter()
        with patch.object(supabase_adapter.urllib.request, "urlopen") as urlopen:
            self.assertEqual(adapter._fetch_auth_users_map([]), {})
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
