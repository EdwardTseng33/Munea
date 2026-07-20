#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "family-health-test-key")
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


class AdminFamilyHealthTests(unittest.TestCase):
    """後台「家庭圈健康度」：跨帳號有人顧比例、多人守護、沒人顧名單（JSON 備援路徑）。"""

    def setUp(self):
        self.relay_path = _tmp_json("[]")
        self.activities_path = _tmp_json("[]")
        self.invitations_path = _tmp_json("[]")
        self.events_path = _tmp_json("{}")
        self.profile_path = _tmp_json("{}")

        self.patches = [
            patch.object(server, "FAMILY_RELAYS_PATH", self.relay_path),
            patch.object(server, "FAMILY_ACTIVITIES_PATH", self.activities_path),
            patch.object(server, "FAMILY_INVITATIONS_PATH", self.invitations_path),
            patch.object(server, "PRODUCT_EVENTS_PATH", self.events_path),
            patch.object(server, "APP_PROFILE_STORE_PATH", self.profile_path),
        ]
        for p in self.patches:
            p.start()
        server._APP_PROFILE_CACHE["store"] = None
        server._APP_PROFILE_CACHE["ts"] = 0.0

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for path in (self.relay_path, self.activities_path, self.invitations_path, self.events_path, self.profile_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        server._APP_PROFILE_CACHE["store"] = None
        server._APP_PROFILE_CACHE["ts"] = 0.0

    def _seed_relays(self, items):
        server.write_json_file(self.relay_path, [server.normalize_family_relay(item) for item in items])

    def _seed_activities(self, items):
        server.write_json_file(self.activities_path, [server.normalize_family_activity(item) for item in items])

    def _seed_invitations(self, items):
        server.write_json_file(self.invitations_path, [server.normalize_family_invitation(item) for item in items])

    def _seed_events(self, items):
        store = server.default_product_events_store()
        store["events"] = [server.normalize_product_event(item) for item in items]
        server.write_json_file(self.events_path, store)

    @staticmethod
    def _iso(days_ago, hour=12):
        dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return dt.strftime("%Y-%m-%dT{:02d}:00:00Z".format(hour))

    def test_empty_state_reports_null_rate_not_zero(self):
        with patch.object(server, "load_admin_family_membership_rows", return_value=[]):
            response = server.admin_family_health({"days": 30, "limit": 50})
        self.assertTrue(response["ok"])
        self.assertIsNone(response["guardedRate"])
        self.assertIsNone(response["invites"]["acceptRate"])
        self.assertEqual(response["totals"], {
            "households": 0, "membersTotal": 0, "withActiveGuardian": 0,
            "multiGuardian": 0, "unwatched": 0,
        })
        self.assertEqual(response["unwatchedList"], [])
        self.assertEqual(response["daily"], [])

    def test_guarded_rate_multi_guardian_and_unwatched_list_cross_household(self):
        membership_rows = [
            {"familyGroupId": "fg-a", "accountId": "acct-a", "personId": "elder-a", "role": "primary_user"},
            {"familyGroupId": "fg-a", "accountId": "acct-a", "personId": "fam-a1", "role": "family_contact"},
            {"familyGroupId": "fg-b", "accountId": "acct-b", "personId": "elder-b", "role": "primary_user"},
            {"familyGroupId": "fg-b", "accountId": "acct-b", "personId": "fam-b1", "role": "family_contact"},
            {"familyGroupId": "fg-b", "accountId": "acct-b", "personId": "fam-b2", "role": "caregiver"},
            {"familyGroupId": "fg-c", "accountId": "acct-c", "personId": "elder-c", "role": "primary_user"},
            {"familyGroupId": "fg-c", "accountId": "acct-c", "personId": "fam-c1", "role": "family_contact"},
            {"familyGroupId": "fg-d", "accountId": "acct-d", "personId": "elder-d", "role": "primary_user"},
            {"familyGroupId": "fg-d", "accountId": "acct-d", "personId": "fam-d1", "role": "family_contact"},
        ]

        # 家 A：家人傳話給長輩 -> 1 位活躍家人
        self._seed_relays([
            {
                "id": "relay-a1", "familyGroupId": "fg-a", "accountId": "acct-a",
                "senderPersonId": "fam-a1", "recipientPersonId": "elder-a",
                "content": "今天狀況如何", "createdAt": self._iso(0),
            },
            {
                "id": "relay-b1", "familyGroupId": "fg-b", "accountId": "acct-b",
                "senderPersonId": "fam-b1", "recipientPersonId": "elder-b",
                "content": "記得吃藥", "createdAt": self._iso(1),
            },
        ])
        # 家 B：另一位家人看過家庭看板 -> fam-b2 也活躍，家 B 變多人守護
        self._seed_events([
            {
                "id": "ev-b2", "familyGroupId": "fg-b", "accountId": "acct-b", "personId": "fam-b2",
                "eventName": "family_dashboard_viewed", "eventTime": self._iso(2),
            },
        ])
        # 家 D：家人參與家庭活動（不是傳話也不是查看）-> fam-d1 活躍
        self._seed_activities([
            {
                "id": "act-1", "familyGroupId": "fg-d", "accountId": "acct-d",
                "ownerPersonId": "elder-d", "status": "completed", "updatedAt": self._iso(1),
                "participants": [
                    {"personId": "fam-d1", "status": "accepted"},
                ],
            },
        ])
        # 邀請：2 筆成功、1 筆待確認
        self._seed_invitations([
            {"id": "inv-1", "familyGroupId": "fg-a", "accountId": "acct-a", "status": "accepted", "createdAt": self._iso(3)},
            {"id": "inv-2", "familyGroupId": "fg-b", "accountId": "acct-b", "status": "accepted", "createdAt": self._iso(3)},
            {"id": "inv-3", "familyGroupId": "fg-c", "accountId": "acct-c", "status": "pending", "createdAt": self._iso(3)},
        ])
        # 家 C：完全沒有任何家人動作 -> 應該落在「沒人顧」名單

        with patch.object(server, "load_admin_family_membership_rows", return_value=membership_rows):
            response = server.admin_family_health({"days": 30, "limit": 50})

        self.assertTrue(response["ok"])
        totals = response["totals"]
        self.assertEqual(totals["households"], 4)
        self.assertEqual(totals["membersTotal"], 5)
        self.assertEqual(totals["withActiveGuardian"], 3)
        self.assertEqual(totals["multiGuardian"], 1)
        self.assertEqual(totals["unwatched"], 1)
        self.assertAlmostEqual(response["guardedRate"], 3 / 4, places=4)

        self.assertEqual(response["invites"], {"sent": 3, "accepted": 2, "pending": 1, "acceptRate": round(2 / 3, 4)})
        self.assertEqual(response["relay"]["messages"], 2)
        self.assertEqual(response["relay"]["viewers"], 1)

        unwatched = response["unwatchedList"]
        self.assertEqual(len(unwatched), 1)
        self.assertEqual(unwatched[0]["accountId"], "acct-c")
        self.assertEqual(unwatched[0]["memberCount"], 1)
        self.assertIsNone(unwatched[0]["lastFamilyActionAt"])

    def test_elder_own_action_does_not_count_as_guarded(self):
        membership_rows = [
            {"familyGroupId": "fg-e", "accountId": "acct-e", "personId": "elder-e", "role": "primary_user"},
            {"familyGroupId": "fg-e", "accountId": "acct-e", "personId": "fam-e1", "role": "family_contact"},
        ]
        self._seed_events([
            {
                "id": "ev-e1", "familyGroupId": "fg-e", "accountId": "acct-e", "personId": "elder-e",
                "eventName": "family_message_viewed", "eventTime": self._iso(0),
            },
        ])
        with patch.object(server, "load_admin_family_membership_rows", return_value=membership_rows):
            response = server.admin_family_health({"days": 30, "limit": 50})
        self.assertEqual(response["totals"]["withActiveGuardian"], 0)
        self.assertEqual(response["totals"]["unwatched"], 1)

    def test_membership_json_fallback_reads_single_local_household(self):
        server.write_json_file(self.profile_path, {
            "account": {"id": "local-demo-account"},
            "familyGroup": {"id": "local-demo-family", "members": [
                {"id": "local-elder", "role": "primary_user", "displayName": "長輩"},
                {"id": "local-family-1", "role": "family_contact", "displayName": "女兒"},
            ]},
            "primaryCareRecipientId": "local-elder",
        })
        rows = server.load_admin_family_membership_rows(limit=100)
        by_person = {r["personId"]: r for r in rows}
        self.assertEqual(by_person["local-elder"]["role"], "primary_user")
        self.assertEqual(by_person["local-family-1"]["role"], "family_contact")
        self.assertTrue(all(r["familyGroupId"] == "local-demo-family" for r in rows))

    def test_no_engineering_jargon_in_principle_text(self):
        with patch.object(server, "load_admin_family_membership_rows", return_value=[]):
            response = server.admin_family_health({})
        for banned in ("event_name", "family_group_id", "SQL", "API"):
            self.assertNotIn(banned, response["principle"])
        self.assertIn("有人顧", response["principle"])


class SupabaseAdminFamilyHealthCrossAccountTests(unittest.TestCase):
    """Adapter 層：後台跨帳號家庭圈查詢不能被單一 account_id 過濾掉。"""

    def _adapter(self):
        return SupabaseAdapter(
            env={
                "MUNEA_DATABASE_PROVIDER": "supabase",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            identity={"accountId": ACCOUNT, "personId": PERSON},
        )

    def test_load_admin_family_memberships_has_no_account_scope_filter(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{
                "id": "mem-1", "account_id": "other-account", "family_group_id": "fg-other",
                "person_id": "person-other", "role": "primary_user",
            }]

        with patch.object(adapter, "_select", side_effect=fake_select):
            rows = adapter.load_admin_family_memberships(limit=100)

        self.assertEqual(captured["table"], "family_memberships")
        self.assertNotIn("account_id", captured["query"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accountId"], "other-account")

    def test_load_admin_family_engagement_events_builds_event_name_in_filter(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return []

        with patch.object(adapter, "_select", side_effect=fake_select):
            adapter.load_admin_family_engagement_events(
                ("family_dashboard_viewed", "family_message_viewed"),
                since_iso="2026-06-19T00:00:00Z",
                limit=100,
            )

        self.assertEqual(captured["table"], "product_events")
        self.assertNotIn("account_id", captured["query"])
        self.assertEqual(captured["query"]["event_name"], "in.(family_dashboard_viewed,family_message_viewed)")
        self.assertEqual(captured["query"]["event_time"], "gte.2026-06-19T00:00:00Z")

    def test_load_admin_family_last_action_scopes_by_family_group_ids_only(self):
        adapter = self._adapter()
        calls = []

        def fake_select(table, query):
            calls.append((table, dict(query)))
            return []

        fg1 = "33333333-3333-4333-8333-333333333333"
        fg2 = "44444444-4444-4444-8444-444444444444"
        with patch.object(adapter, "_select", side_effect=fake_select):
            result = adapter.load_admin_family_last_action(
                [fg1, fg2], ("family_dashboard_viewed", "family_message_viewed"), limit=100,
            )

        self.assertEqual(result, {})
        tables = [c[0] for c in calls]
        self.assertIn("family_relay_messages", tables)
        self.assertIn("product_events", tables)
        for _, query in calls:
            self.assertNotIn("account_id", query)
            self.assertIn("family_group_id", query)
            self.assertIn(fg1, query["family_group_id"])
            self.assertIn(fg2, query["family_group_id"])

    def test_load_family_groups_by_ids_filters_out_non_uuid(self):
        adapter = self._adapter()
        captured = {}

        def fake_select(table, query):
            captured["table"] = table
            captured["query"] = dict(query)
            return [{"id": PERSON, "name": "陳家守護圈"}]

        with patch.object(adapter, "_select", side_effect=fake_select):
            names = adapter.load_family_groups_by_ids([PERSON, "not-a-uuid", None])

        self.assertEqual(captured["table"], "family_groups")
        self.assertIn(PERSON, captured["query"]["id"])
        self.assertNotIn("not-a-uuid", captured["query"]["id"])
        self.assertEqual(names, {PERSON: "陳家守護圈"})


if __name__ == "__main__":
    unittest.main()
