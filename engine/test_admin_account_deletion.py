#!/usr/bin/env python3
"""後台永久刪除測試帳號（admin_delete_test_account）守門驗證。

這支的重點只有一個：**沒標記為測試的帳號，後台一律刪不掉**。
上線後名冊裡會混著真客戶跟演習／審查留下的假帳號，維運端清場時手滑點錯的成本是刪掉付費用戶——
所以刪除永遠要先勾「標記為測試帳號」，兩個動作分開。只打樁 _first／_select／_request，不碰真網路。
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

import supabase_adapter

ACCOUNT_ID = "44444444-4444-4444-8444-444444444444"
OWNER_ID = "55555555-5555-4555-8555-555555555555"


def make_adapter():
    env = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
        "MUNEA_DATABASE_PROVIDER": "supabase",
        "MUNEA_SUPABASE_ACCOUNT_ID": "11111111-1111-4111-8111-111111111111",
        "MUNEA_SUPABASE_PERSON_ID": "22222222-2222-4222-8222-222222222222",
    }
    return supabase_adapter.SupabaseAdapter(env=env)


class AdminDeleteTestAccountTests(unittest.TestCase):
    def test_real_account_cannot_be_deleted(self):
        """沒有測試標記＝真客戶，後台刪不掉，而且一列資料都不准動。"""
        adapter = make_adapter()
        account = {"id": ACCOUNT_ID, "name": "阿宏", "is_test_account": False}
        with patch.object(adapter, "_first", return_value=account), \
             patch.object(adapter, "_request") as request:
            with self.assertRaises(PermissionError):
                adapter.admin_delete_test_account(ACCOUNT_ID)
        request.assert_not_called()

    def test_missing_account_raises_lookup_error(self):
        adapter = make_adapter()
        with patch.object(adapter, "_first", return_value=None), \
             patch.object(adapter, "_request") as request:
            with self.assertRaises(LookupError):
                adapter.admin_delete_test_account(ACCOUNT_ID)
        request.assert_not_called()

    def test_test_account_is_deleted_with_auth_identity(self):
        """標記過的測試帳號：刪帳號列、刪登入身分、留下稽核紀錄。"""
        adapter = make_adapter()
        account = {"id": ACCOUNT_ID, "name": "Queue burst drill", "is_test_account": True}
        calls = []

        def fake_request(method, table, query=None, payload=None, prefer=None):
            calls.append((method, table))
            if method == "DELETE" and table == "accounts":
                return [{"id": ACCOUNT_ID}]
            return []

        with patch.object(adapter, "_first", return_value=account), \
             patch.object(adapter, "_select", return_value=[{"user_id": OWNER_ID}]), \
             patch.object(adapter, "_request", side_effect=fake_request), \
             patch.object(adapter, "_delete_auth_user") as delete_auth:
            result = adapter.admin_delete_test_account(ACCOUNT_ID, actor="admin@munea.net")

        self.assertTrue(result["ok"])
        self.assertFalse(result["cleanupRequired"])
        self.assertEqual(result["authCleanup"]["deleted"], 1)
        delete_auth.assert_called_once_with(OWNER_ID)
        self.assertIn(("POST", "audit_events"), calls)
        self.assertIn(("DELETE", "accounts"), calls)

    def test_auth_cleanup_failure_is_reported_not_hidden(self):
        """帳號刪掉了但登入身分沒清乾淨——老實回報 cleanupRequired，不假裝完全成功。"""
        adapter = make_adapter()
        account = {"id": ACCOUNT_ID, "name": "Queue burst drill", "is_test_account": True}

        def fake_request(method, table, query=None, payload=None, prefer=None):
            if method == "DELETE" and table == "accounts":
                return [{"id": ACCOUNT_ID}]
            return []

        with patch.object(adapter, "_first", return_value=account), \
             patch.object(adapter, "_select", return_value=[{"user_id": OWNER_ID}]), \
             patch.object(adapter, "_request", side_effect=fake_request), \
             patch.object(adapter, "_delete_auth_user", side_effect=RuntimeError("gotrue down")):
            result = adapter.admin_delete_test_account(ACCOUNT_ID)

        self.assertTrue(result["ok"])
        self.assertTrue(result["cleanupRequired"])
        self.assertEqual(result["authCleanup"]["failed"][0]["authUserId"], OWNER_ID)

    def test_orphan_account_without_owner_still_deletes(self):
        """演習腳本留下的孤兒帳號（登入身分早就被刪掉）也要清得掉，不能卡在找不到 owner。"""
        adapter = make_adapter()
        account = {"id": ACCOUNT_ID, "name": "Queue burst drill", "is_test_account": True}

        def fake_request(method, table, query=None, payload=None, prefer=None):
            if method == "DELETE" and table == "accounts":
                return [{"id": ACCOUNT_ID}]
            return []

        with patch.object(adapter, "_first", return_value=account), \
             patch.object(adapter, "_select", return_value=[]), \
             patch.object(adapter, "_request", side_effect=fake_request), \
             patch.object(adapter, "_delete_auth_user") as delete_auth:
            result = adapter.admin_delete_test_account(ACCOUNT_ID)

        self.assertTrue(result["ok"])
        self.assertEqual(result["authCleanup"]["attempted"], 0)
        delete_auth.assert_not_called()

    def test_invalid_account_id_rejected(self):
        adapter = make_adapter()
        with self.assertRaises(RuntimeError):
            adapter.admin_delete_test_account("not-a-uuid")


class OwnerSummaryTests(unittest.TestCase):
    def test_apple_private_relay_is_flagged_not_shown_as_real_email(self):
        owner = supabase_adapter.SupabaseAdapter.auth_user_to_owner({
            "id": OWNER_ID,
            "email": "abc123@privaterelay.appleid.com",
            "app_metadata": {"provider": "apple"},
            "user_metadata": {"name": "John Apple"},
            "created_at": "2026-07-22T12:34:15Z",
            "last_sign_in_at": "2026-07-22T12:34:15Z",
        })
        self.assertTrue(owner["emailIsPrivateRelay"])
        self.assertEqual(owner["signInMethod"], "apple")
        self.assertEqual(owner["signInName"], "John Apple")

    def test_google_owner_keeps_real_email(self):
        owner = supabase_adapter.SupabaseAdapter.auth_user_to_owner({
            "id": OWNER_ID,
            "email": "someone@gmail.com",
            "app_metadata": {"provider": "google"},
        })
        self.assertFalse(owner["emailIsPrivateRelay"])
        self.assertEqual(owner["email"], "someone@gmail.com")




class AdminAccountSummaryFieldTests(unittest.TestCase):
    """名冊回應的最後一層格式整理不准把「這一戶是誰」的欄位濾掉。

    真踩過（2026-07-29）：supabase_adapter 已經把 owner／profileName 組好了，
    但 server.normalize_admin_account_summary 只逐欄重建它認識的欄位，新欄位默默消失——
    測試機部署後名冊還是空的，程式碼看起來卻完全正確，非常難查。
    """

    def setUp(self):
        os.environ.setdefault("GEMINI_API_KEY", "admin-account-summary-test-key")
        import server
        self.server = server

    def test_owner_and_real_name_survive_normalization(self):
        raw = {
            "accountId": ACCOUNT_ID,
            "accountName": "Munea account",
            "primaryPerson": {"id": "p1", "displayName": "寧寧", "profileName": "林建國", "nickname": "阿國"},
            "owner": {
                "authUserId": OWNER_ID, "email": "someone@gmail.com", "emailIsPrivateRelay": False,
                "signInMethod": "google", "signInName": "陳美玲",
                "signedUpAt": "2026-07-29T12:45:11Z", "lastSignInAt": "2026-07-29T12:45:13Z",
            },
        }
        out = self.server.normalize_admin_account_summary(raw)
        self.assertEqual(out["owner"]["email"], "someone@gmail.com")
        self.assertEqual(out["owner"]["signInMethod"], "google")
        self.assertEqual(out["owner"]["signInName"], "陳美玲")
        self.assertEqual(out["owner"]["lastSignInAt"], "2026-07-29T12:45:13Z")
        # 使用者本人的名字（profileName／nickname）跟 AI 陪伴角色名（displayName）都要留著
        self.assertEqual(out["primaryPerson"]["profileName"], "林建國")
        self.assertEqual(out["primaryPerson"]["nickname"], "阿國")
        self.assertEqual(out["primaryPerson"]["displayName"], "寧寧")

    def test_missing_owner_becomes_empty_shell_not_missing_key(self):
        out = self.server.normalize_admin_account_summary({"accountId": ACCOUNT_ID})
        self.assertIn("owner", out)
        self.assertEqual(out["owner"]["email"], "")
        self.assertEqual(out["owner"]["signInMethod"], "")

    def test_apple_relay_email_is_flagged_even_if_upstream_forgot(self):
        out = self.server.normalize_admin_account_summary(
            {"accountId": ACCOUNT_ID, "owner": {"email": "abc@privaterelay.appleid.com"}}
        )
        self.assertTrue(out["owner"]["emailIsPrivateRelay"])


if __name__ == "__main__":
    unittest.main()
