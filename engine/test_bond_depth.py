#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "bond-depth-test-key")
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


class AdminBondDepthTests(unittest.TestCase):
    """後台「關係深度」：跨帳號四階關係分佈＋平均記憶筆數＋卡住名單（JSON 備援路徑）。
    資料源只用 companion_relationship_states（等級／時間）＋ memory_items（只算筆數）；
    記憶內容一律不得出現在回應裡。"""

    def setUp(self):
        self.states_path = _tmp_json('{"states": []}')
        self.memory_path = _tmp_json("[]")
        self.patches = [
            patch.object(server, "RELATIONSHIP_STATES_PATH", self.states_path),
            patch.object(server, "MEMORY_ITEMS_PATH", self.memory_path),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for path in (self.states_path, self.memory_path):
            try:
                os.unlink(path)
            except OSError:
                pass

    @staticmethod
    def _iso(days_ago):
        return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _seed_states(self, items):
        normalized = [server.normalize_relationship_state(item) for item in items]
        server.write_json_file(self.states_path, {"states": normalized})

    def _seed_memories(self, items):
        server.write_json_file(self.memory_path, items)

    def test_empty_state_reports_null_averages_not_zero(self):
        response = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 14})
        self.assertTrue(response["ok"])
        self.assertIsNone(response["avgMemories"])
        self.assertIsNone(response["upgradeDays"])
        self.assertEqual(response["totals"], {"people": 0, "newly": 0, "familiar": 0, "trusted": 0, "close": 0, "stuck": 0})
        self.assertEqual(response["stuckList"], [])

    def test_totals_distribution_and_avg_memories_cross_account_active_window(self):
        self._seed_states([
            {"personId": "person-a", "accountId": "account-a", "rapportLevel": "new", "createdAt": self._iso(0), "updatedAt": self._iso(0)},
            {"personId": "person-b", "accountId": "account-b", "rapportLevel": "familiar", "createdAt": self._iso(5), "updatedAt": self._iso(0)},
            {"personId": "person-c", "accountId": "account-c", "rapportLevel": "trusted", "createdAt": self._iso(10), "updatedAt": self._iso(1)},
            {"personId": "person-d", "accountId": "account-d", "rapportLevel": "close", "createdAt": self._iso(20), "updatedAt": self._iso(2)},
        ])
        self._seed_memories([
            {"personId": "person-a", "createdAt": self._iso(0)},
            {"personId": "person-a", "createdAt": self._iso(0)},
            {"personId": "person-b", "createdAt": self._iso(1)},
            {"personId": "person-b", "createdAt": self._iso(1)},
            {"personId": "person-b", "createdAt": self._iso(1)},
            {"personId": "person-b", "createdAt": self._iso(1)},
            {"personId": "person-c", "createdAt": self._iso(2)},
            {"personId": "person-c", "createdAt": self._iso(2)},
            {"personId": "person-c", "createdAt": self._iso(2)},
            {"personId": "person-c", "createdAt": self._iso(2)},
            {"personId": "person-c", "createdAt": self._iso(2)},
            {"personId": "person-c", "createdAt": self._iso(2)},
            {"personId": "person-d", "createdAt": self._iso(3)},
            {"personId": "person-d", "createdAt": self._iso(3)},
            {"personId": "person-d", "createdAt": self._iso(3)},
            {"personId": "person-d", "createdAt": self._iso(3)},
            {"personId": "person-d", "createdAt": self._iso(3)},
            {"personId": "person-d", "createdAt": self._iso(3)},
            {"personId": "person-d", "createdAt": self._iso(3)},
            {"personId": "person-d", "createdAt": self._iso(3)},
        ])
        response = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 14})
        self.assertTrue(response["ok"])
        self.assertEqual(response["totals"], {"people": 4, "newly": 1, "familiar": 1, "trusted": 1, "close": 1, "stuck": 0})
        self.assertAlmostEqual(response["avgMemories"], 5.0, places=2)

    def test_stale_relationship_excluded_from_totals_but_kept_in_stuck_list(self):
        self._seed_states([
            {"personId": "person-e", "accountId": "account-e", "rapportLevel": "new", "createdAt": self._iso(30), "updatedAt": self._iso(40)},
        ])
        self._seed_memories([
            {"personId": "person-e", "createdAt": self._iso(30)},
        ])
        response = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 14})
        self.assertEqual(response["totals"]["people"], 0)
        self.assertIsNone(response["avgMemories"])
        self.assertEqual(len(response["stuckList"]), 1)
        entry = response["stuckList"][0]
        self.assertEqual(entry["personId"], "person-e")
        self.assertGreaterEqual(entry["daysSinceJoin"], 29)
        self.assertEqual(entry["memories"], 1)
        self.assertEqual(entry["lastTalkAt"], self._iso(40))

    def test_stuck_list_excludes_upgraded_and_recently_joined_people(self):
        self._seed_states([
            {"personId": "person-f", "accountId": "account-f", "rapportLevel": "trusted", "createdAt": self._iso(60), "updatedAt": self._iso(0)},
            {"personId": "person-g", "accountId": "account-g", "rapportLevel": "new", "createdAt": self._iso(3), "updatedAt": self._iso(0)},
            {"personId": "person-h", "accountId": "account-h", "rapportLevel": "new", "createdAt": self._iso(20), "updatedAt": self._iso(1)},
        ])
        response = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 14})
        ids = [e["personId"] for e in response["stuckList"]]
        self.assertNotIn("person-f", ids)  # 已升級，不算卡住
        self.assertNotIn("person-g", ids)  # 才加入 3 天，還沒到卡住門檻
        self.assertIn("person-h", ids)     # 20 天還在新認識，卡住了

    def test_stuck_list_sorted_by_longest_stuck_first(self):
        self._seed_states([
            {"personId": "person-i", "accountId": "account-i", "rapportLevel": "new", "createdAt": self._iso(20), "updatedAt": self._iso(0)},
            {"personId": "person-j", "accountId": "account-j", "rapportLevel": "new", "createdAt": self._iso(40), "updatedAt": self._iso(0)},
        ])
        response = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 14})
        ids = [e["personId"] for e in response["stuckList"]]
        self.assertEqual(ids, ["person-j", "person-i"])

    def test_custom_stuck_days_threshold_applies(self):
        self._seed_states([
            {"personId": "person-k", "accountId": "account-k", "rapportLevel": "new", "createdAt": self._iso(10), "updatedAt": self._iso(0)},
        ])
        response_default = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 14})
        self.assertEqual(response_default["stuckList"], [])
        response_tight = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 5})
        self.assertEqual(len(response_tight["stuckList"]), 1)
        self.assertEqual(response_tight["stuckList"][0]["personId"], "person-k")

    def test_response_never_leaks_memory_content(self):
        secret_phrase = "提到膝蓋很痛想念女兒"
        self._seed_states([
            {"personId": "person-l", "accountId": "account-l", "rapportLevel": "new", "createdAt": self._iso(0), "updatedAt": self._iso(0)},
        ])
        self._seed_memories([
            {
                "personId": "person-l", "createdAt": self._iso(0),
                "content": secret_phrase, "type": "emotion", "source": "conversation",
                "metadata": {"topicDomains": [secret_phrase]},
            },
        ])
        response = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 14})
        import json
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn(secret_phrase, serialized)
        self.assertNotIn("topicDomains", serialized)

    def test_no_engineering_jargon_in_principle_text(self):
        response = server.admin_bond_depth({})
        for banned in ("person_id", "account_id", "SQL", "rapport_level"):
            self.assertNotIn(banned, response["principle"])
        self.assertIn("記憶", response["principle"])

    def test_test_account_signals_are_excluded_from_totals_and_stuck_list(self):
        """2026-07-24 稽核補：這頁原本沒接測試帳號排除，示範／QA 帳號的關係狀態會混進真實數字。"""
        server._TEST_ACCOUNT_ID_CACHE["ids"] = {"test-account-x"}
        server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = server.time.time() + 999
        try:
            self._seed_states([
                {"personId": "person-real", "accountId": "account-real", "rapportLevel": "familiar", "createdAt": self._iso(5), "updatedAt": self._iso(0)},
                {"personId": "person-test", "accountId": "test-account-x", "rapportLevel": "new", "createdAt": self._iso(30), "updatedAt": self._iso(0)},
            ])
            self._seed_memories([
                {"personId": "person-real", "createdAt": self._iso(0)},
                {"personId": "person-test", "createdAt": self._iso(0)},
            ])
            response = server.admin_bond_depth({"days": 30, "limit": 50, "stuckDays": 14})
        finally:
            server._TEST_ACCOUNT_ID_CACHE["ids"] = set()
            server._TEST_ACCOUNT_ID_CACHE["expiresAt"] = 0.0
        self.assertEqual(response["totals"], {"people": 1, "newly": 0, "familiar": 1, "trusted": 0, "close": 0, "stuck": 0})
        self.assertEqual(response["stuckList"], [])


class SupabaseAdminBondDepthCrossAccountTests(unittest.TestCase):
    """Adapter 層：後台跨帳號關係深度查詢不能被單一 account_id 過濾掉，且記憶查詢絕不選 content。"""

    def _adapter(self):
        return SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )

    def test_load_admin_relationship_states_has_no_account_scope_filter(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{
                "person_id": "other-person-not-in-identity",
                "account_id": "other-account-not-in-identity",
                "rapport_level": "trusted",
                "created_at": "2026-06-01T00:00:00Z",
                "updated_at": "2026-07-18T00:00:00Z",
            }]

        with patch.object(adapter, "_select", side_effect=fake_select):
            rows = adapter.load_admin_relationship_states(limit=100)

        self.assertEqual(captured["table"], "companion_relationship_states")
        self.assertNotIn("account_id", captured["query"])
        self.assertNotIn("person_id", captured["query"])
        self.assertEqual(captured["query"]["deleted_at"], "is.null")
        self.assertNotIn("relationship_memory", captured["query"]["select"])
        self.assertNotIn("tone_overrides", captured["query"]["select"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accountId"], "other-account-not-in-identity")
        self.assertEqual(rows[0]["rapportLevel"], "trusted")

    def test_load_admin_memory_item_counts_excludes_content_and_account_scope(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{
                "person_id": "other-person-not-in-identity",
                "account_id": "other-account-not-in-identity",
                "created_at": "2026-07-18T00:00:00Z",
            }]

        with patch.object(adapter, "_select", side_effect=fake_select):
            rows = adapter.load_admin_memory_item_counts(limit=100)

        self.assertEqual(captured["table"], "memory_items")
        self.assertNotIn("account_id", captured["query"])
        self.assertNotIn("person_id", captured["query"])
        self.assertEqual(captured["query"]["select"], "person_id,account_id,created_at")
        self.assertEqual(captured["query"]["deleted_at"], "is.null")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["personId"], "other-person-not-in-identity")
        self.assertNotIn("content", rows[0])

    def test_load_family_groups_by_account_ids_filters_out_non_uuid(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{"account_id": ACCOUNT, "name": "陳家守護圈"}]

        with patch.object(adapter, "_select", side_effect=fake_select):
            names = adapter.load_family_groups_by_account_ids([ACCOUNT, "not-a-uuid", None])

        self.assertEqual(captured["table"], "family_groups")
        self.assertIn(ACCOUNT, captured["query"]["account_id"])
        self.assertNotIn("not-a-uuid", captured["query"]["account_id"])
        self.assertEqual(names, {ACCOUNT: "陳家守護圈"})


if __name__ == "__main__":
    unittest.main()
