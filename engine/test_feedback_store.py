#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "feedback-store-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402
from supabase_adapter import SupabaseAdapter  # noqa: E402


ACCOUNT = "11111111-1111-4111-8111-111111111111"
PERSON = "22222222-2222-4222-8222-222222222222"


def _tmp_json(initial):
    handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    handle.write(initial.encode("utf-8"))
    handle.close()
    return handle.name


class FakeFeedbackBackend:
    """假的 data_backend()，只模擬 feedback 相關介面，不碰真網路。"""

    def __init__(self, enabled=True, save_result=None, save_error=None, load_result=None, load_error=None):
        self._enabled = enabled
        self._save_result = save_result
        self._save_error = save_error
        self._load_result = load_result
        self._load_error = load_error
        self.saved_items = []

    def enabled(self):
        return self._enabled

    def save_feedback_item(self, item):
        if self._save_error:
            raise self._save_error
        self.saved_items.append(item)
        return self._save_result

    def load_admin_feedback_items(self, limit=2000):
        if self._load_error:
            raise self._load_error
        return self._load_result


class FeedbackResponseTests(unittest.TestCase):
    def setUp(self):
        self.path = _tmp_json("[]")
        self.path_patch = patch.object(server, "FEEDBACK_PATH", self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_bad_type_rejected(self):
        result = server.feedback_response({"type": "not-a-real-type"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "bad_type")

    def test_falls_back_to_local_json_when_backend_disabled(self):
        backend = FakeFeedbackBackend(enabled=False)
        with patch.object(server, "data_backend", return_value=backend):
            result = server.feedback_response({"type": "idea", "text": "多一點提醒", "category": "提醒"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "json")
        items = server.read_json_file(self.path, [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "多一點提醒")

    def test_writes_to_supabase_when_available_and_skips_local_json(self):
        backend = FakeFeedbackBackend(enabled=True, save_result={"id": "fb_remote_1"})
        with patch.object(server, "data_backend", return_value=backend):
            result = server.feedback_response({"type": "bug", "text": "登入卡住"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "supabase")
        self.assertEqual(len(backend.saved_items), 1)
        items = server.read_json_file(self.path, [])
        self.assertEqual(items, [])

    def test_missing_table_falls_back_to_local_json(self):
        backend = FakeFeedbackBackend(enabled=True, save_error=RuntimeError("Could not find the table 'feedback_items'"))
        with patch.object(server, "data_backend", return_value=backend):
            result = server.feedback_response({"type": "praise", "text": "很喜歡"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["backend"], "json")
        items = server.read_json_file(self.path, [])
        self.assertEqual(len(items), 1)

    def test_unexpected_error_propagates_when_backend_enabled(self):
        backend = FakeFeedbackBackend(enabled=True, save_error=RuntimeError("boom, not a missing-table error"))
        with patch.object(server, "data_backend", return_value=backend):
            with self.assertRaises(RuntimeError):
                server.feedback_response({"type": "bug", "text": "x"})


class AdminFeedbackSummaryTests(unittest.TestCase):
    def setUp(self):
        self.path = _tmp_json("[]")
        self.path_patch = patch.object(server, "FEEDBACK_PATH", self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_reads_supabase_items_when_available(self):
        remote_items = [
            {"id": "fb_1", "type": "bug", "category": "聊聊", "text": "斷線", "score": None, "appVersion": "1.0.1", "plan": "free", "createdAt": server.utc_now()},
        ]
        backend = FakeFeedbackBackend(enabled=True, load_result=remote_items)
        with patch.object(server, "data_backend", return_value=backend):
            response = server.admin_feedback_summary({})
        self.assertTrue(response["ok"])
        self.assertEqual(response["totals"], {"bug": 1})
        self.assertEqual(len(response["latest"]), 1)

    def test_falls_back_to_local_json_when_supabase_unavailable(self):
        server.write_json_file(self.path, [
            {"id": "fb_local", "type": "idea", "category": "", "text": "本機備援", "score": None, "appVersion": "", "plan": "", "createdAt": server.utc_now()},
        ])
        backend = FakeFeedbackBackend(enabled=False)
        with patch.object(server, "data_backend", return_value=backend):
            response = server.admin_feedback_summary({})
        self.assertTrue(response["ok"])
        self.assertEqual(response["totals"], {"idea": 1})

    def test_missing_table_falls_back_to_local_json(self):
        server.write_json_file(self.path, [
            {"id": "fb_local2", "type": "praise", "category": "", "text": "讚", "score": None, "appVersion": "", "plan": "", "createdAt": server.utc_now()},
        ])
        backend = FakeFeedbackBackend(enabled=True, load_error=RuntimeError("Could not find the table 'feedback_items'"))
        with patch.object(server, "data_backend", return_value=backend):
            response = server.admin_feedback_summary({})
        self.assertTrue(response["ok"])
        self.assertEqual(response["totals"], {"praise": 1})


class SupabaseAdminFeedbackCrossAccountTests(unittest.TestCase):
    """Adapter 層：feedback_items 寫入帶目前帳號身分；後台跨帳號讀取不能被單一 account_id 過濾掉。"""

    def _adapter(self):
        return SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )

    def test_feedback_item_to_row_uses_request_scoped_account_id(self):
        adapter = self._adapter()
        row = adapter.feedback_item_to_row({
            "id": "fb_1", "type": "bug", "category": "聊聊", "text": "斷線了",
            "score": None, "appVersion": "1.0.1", "plan": "free", "createdAt": "2026-07-24T00:00:00Z",
            "accountId": "someone-elses-account",
        })
        self.assertEqual(row["account_id"], ACCOUNT)
        self.assertEqual(row["person_id"], PERSON)
        self.assertEqual(row["content"], "斷線了")

    def test_save_feedback_item_posts_and_maps_row_back(self):
        adapter = self._adapter()
        captured = {}

        def fake_request(method, table, query=None, payload=None, prefer=None):
            captured["method"] = method
            captured["table"] = table
            captured["payload"] = payload
            return [{
                "id": "fb_1", "account_id": ACCOUNT, "person_id": PERSON, "type": "bug",
                "category": "聊聊", "content": "斷線了", "score": None,
                "app_version": "1.0.1", "plan": "free", "created_at": "2026-07-24T00:00:00Z",
            }]

        with patch.object(adapter, "_request", side_effect=fake_request):
            item = adapter.save_feedback_item({"id": "fb_1", "type": "bug", "text": "斷線了"})

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["table"], "feedback_items")
        self.assertEqual(item["text"], "斷線了")
        self.assertEqual(item["type"], "bug")

    def test_load_admin_feedback_items_has_no_account_scope_filter(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{
                "id": "fb_2", "account_id": "other-account-not-in-identity", "person_id": "other-person",
                "type": "idea", "category": "", "content": "多加個功能", "score": None,
                "app_version": "", "plan": "", "created_at": "2026-07-24T00:00:00Z",
            }]

        with patch.object(adapter, "_select", side_effect=fake_select):
            rows = adapter.load_admin_feedback_items(limit=100)

        self.assertEqual(captured["table"], "feedback_items")
        self.assertNotIn("account_id", captured["query"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "多加個功能")


if __name__ == "__main__":
    unittest.main()
