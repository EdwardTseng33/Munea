#!/usr/bin/env python3
"""稽核紀錄帳號欄只能寫 uuid（2026-11-21）。

事故：正式機與測試機每次上線後的檢查都會丟一封假的「蘋果伺服器通知」，被拒時寫稽核紀錄
apple_server_notification_rejected——這種系統事件沒有帳號，server.normalize_audit_event
把帳號欄補成 "local-demo-account"，資料庫帳號欄是 uuid → 400 22P02，整筆退到本機暫存檔，雲端沒存到。
後台補點數（credits_granted）等不綁登入身分的事件同一條路。

這支只打樁 _request，不碰真網路。
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "audit-event-account-uuid-test-key")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import supabase_adapter  # noqa: E402
import server  # noqa: E402

SERVICE_ACCOUNT = "11111111-1111-4111-8111-111111111111"
FAMILY_ACCOUNT = "44444444-4444-4444-8444-444444444444"
OTHER_ACCOUNT = "66666666-6666-4666-8666-666666666666"
AUTH_USER = "55555555-5555-4555-8555-555555555555"


def make_env(account_id=SERVICE_ACCOUNT):
    return {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
        "MUNEA_DATABASE_PROVIDER": "supabase",
        "MUNEA_SUPABASE_ACCOUNT_ID": account_id,
        "MUNEA_SUPABASE_PERSON_ID": "22222222-2222-4222-8222-222222222222",
    }


class AuditRowAccountTests(unittest.TestCase):
    def test_placeholder_account_falls_back_to_service_account(self):
        adapter = supabase_adapter.SupabaseAdapter(env=make_env())
        row = adapter.audit_event_to_row({"accountId": "local-demo-account", "eventType": "x"})
        self.assertEqual(row["account_id"], SERVICE_ACCOUNT)

    def test_empty_and_odd_values_never_reach_the_uuid_column(self):
        adapter = supabase_adapter.SupabaseAdapter(env=make_env())
        for bad in ("", "  ", "test-identity", "+886912345678", 12345, {"id": 1}, None):
            row = adapter.audit_event_to_row({"accountId": bad, "actorUserId": bad, "targetId": bad})
            self.assertEqual(row["account_id"], SERVICE_ACCOUNT, bad)
            self.assertIsNone(row["actor_user_id"], bad)
            self.assertIsNone(row["target_id"], bad)

    def test_no_valid_default_writes_null_instead_of_bad_text(self):
        adapter = supabase_adapter.SupabaseAdapter(env=make_env(account_id="local-demo-account"))
        row = adapter.audit_event_to_row({"accountId": "local-demo-account"})
        self.assertIsNone(row["account_id"])

    def test_real_uuid_account_is_kept_on_unscoped_writes(self):
        adapter = supabase_adapter.SupabaseAdapter(env=make_env())
        row = adapter.audit_event_to_row({"accountId": FAMILY_ACCOUNT})
        self.assertEqual(row["account_id"], FAMILY_ACCOUNT)

    def test_signed_in_request_still_ignores_client_supplied_account(self):
        adapter = supabase_adapter.SupabaseAdapter(
            env=make_env(), identity={"accountId": FAMILY_ACCOUNT, "authUserId": AUTH_USER}
        )
        for supplied in ("local-demo-account", OTHER_ACCOUNT, None):
            row = adapter.audit_event_to_row({"accountId": supplied})
            self.assertEqual(row["account_id"], FAMILY_ACCOUNT, supplied)


class AppendAuditEventReachesCloudTests(unittest.TestCase):
    """走真的 server.append_audit_event：雲端寫得進去就不准退本機暫存檔。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store_path = os.path.join(self.tmp.name, "audit_events_store.json")
        self.adapter = supabase_adapter.SupabaseAdapter(env=make_env())
        self.posted = []

        def fake_request(method, table, query=None, payload=None, prefer=None, **_):
            self.posted.append((method, table, payload))
            if any(isinstance(payload.get(k), str) and not supabase_adapter.SupabaseAdapter._is_uuid(payload.get(k))
                   for k in ("account_id", "actor_user_id", "target_id")):
                raise supabase_adapter.SupabaseRequestError(
                    'Supabase POST audit_events failed: 400 {"code":"22P02"}', error_kind="write_failed"
                )
            return [{**payload, "id": "77777777-7777-4777-8777-777777777777", "created_at": "2026-11-21T00:00:00Z"}]

        self.patches = [
            patch.object(self.adapter, "_request", side_effect=fake_request),
            patch.object(server, "data_backend", return_value=self.adapter),
            patch.object(server, "AUDIT_EVENTS_STORE_PATH", self.store_path),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_rejected_apple_notification_is_saved_to_cloud(self):
        server.apple_notification_response({"signedPayload": "not-a-real-jws"})
        self.assertEqual(len(self.posted), 1)
        method, table, payload = self.posted[0]
        self.assertEqual((method, table), ("POST", "audit_events"))
        self.assertEqual(payload["event_type"], "apple_server_notification_rejected")
        self.assertEqual(payload["account_id"], SERVICE_ACCOUNT)
        self.assertFalse(os.path.exists(self.store_path), "雲端寫得進去，就不該退本機暫存檔")

    def test_event_without_account_is_saved_to_cloud(self):
        result = server.append_audit_event({"eventType": "credits_granted", "targetTable": "credit_transactions"})
        self.assertEqual(result["id"], "77777777-7777-4777-8777-777777777777")
        self.assertFalse(os.path.exists(self.store_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
