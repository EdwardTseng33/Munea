#!/usr/bin/env python3
import os
import unittest

from supabase_adapter import SupabaseAdapter, make_adapter


USER_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ACCOUNT_A = "11111111-1111-4111-8111-111111111111"
ACCOUNT_B = "22222222-2222-4222-8222-222222222222"
PERSON_A = "33333333-3333-4333-8333-333333333333"
PERSON_B = "44444444-4444-4444-8444-444444444444"
FAMILY_A = "55555555-5555-4555-8555-555555555555"
FAMILY_B = "66666666-6666-4666-8666-666666666666"


class FakeSupabaseAdapter(SupabaseAdapter):
    identities = {
        USER_A: (ACCOUNT_A, PERSON_A, FAMILY_A),
        USER_B: (ACCOUNT_B, PERSON_B, FAMILY_B),
    }

    def _first(self, table, query):
        if table == "account_members":
            user_id = query["user_id"].removeprefix("eq.")
            identity = self.identities.get(user_id)
            return {"account_id": identity[0]} if identity else None
        if table == "persons":
            account_id = query["account_id"].removeprefix("eq.")
            for user_id, identity in self.identities.items():
                if identity[0] != account_id:
                    continue
                requested_user = query.get("auth_user_id", "").removeprefix("eq.")
                if not requested_user or requested_user == user_id:
                    return {"id": identity[1]}
            return None
        if table == "family_memberships":
            account_id = query["account_id"].removeprefix("eq.")
            person_id = query["person_id"].removeprefix("eq.")
            for identity in self.identities.values():
                if identity[:2] == (account_id, person_id):
                    return {"family_group_id": identity[2]}
        return None


class FakeDeletionAdapter(SupabaseAdapter):
    def __init__(self, env, identity, role="owner", auth_delete_fails=False):
        super().__init__(env=env, identity=identity)
        self.role = role
        self.auth_delete_fails = auth_delete_fails
        self.calls = []

    def _first(self, table, query):
        if table == "account_members" and self.role == "owner":
            return {"id": "88888888-8888-4888-8888-888888888888"}
        return None

    def _request(self, method, table, query=None, payload=None, prefer=None):
        self.calls.append((method, table, payload))
        if method == "DELETE" and table == "accounts":
            return [{"id": self.account_id}]
        return []

    def _delete_auth_user(self, auth_user_id):
        self.calls.append(("DELETE", "auth.users", {"id": auth_user_id}))
        if self.auth_delete_fails:
            raise RuntimeError("simulated auth cleanup failure")


class AccountScopeTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "MUNEA_DATABASE_PROVIDER": "supabase",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
            "MUNEA_SUPABASE_ACCOUNT_ID": ACCOUNT_A,
            "MUNEA_SUPABASE_PERSON_ID": PERSON_A,
            "MUNEA_SUPABASE_FAMILY_GROUP_ID": FAMILY_A,
        }

    def test_two_users_resolve_to_separate_scopes(self):
        adapter = FakeSupabaseAdapter(env=self.env)
        scope_a = adapter.resolve_auth_identity(USER_A)
        scope_b = adapter.resolve_auth_identity(USER_B)

        self.assertNotEqual(scope_a["accountId"], scope_b["accountId"])
        self.assertNotEqual(scope_a["personId"], scope_b["personId"])
        self.assertNotEqual(scope_a["familyGroupId"], scope_b["familyGroupId"])

        scoped_b = make_adapter(env=self.env, identity=scope_b)
        self.assertEqual(scoped_b.account_id, ACCOUNT_B)
        self.assertEqual(scoped_b.person_id, PERSON_B)
        self.assertEqual(scoped_b.family_group_id, FAMILY_B)

    def test_unknown_user_fails_closed(self):
        adapter = FakeSupabaseAdapter(env=self.env)
        unknown = "77777777-7777-4777-8777-777777777777"
        self.assertIsNone(adapter.resolve_auth_identity(unknown))

    def test_scoped_adapter_ignores_client_tenant_override(self):
        scope_b = FakeSupabaseAdapter(env=self.env).resolve_auth_identity(USER_B)
        scoped_b = make_adapter(env=self.env, identity=scope_b)
        self.assertEqual(scoped_b.payload_account_id(ACCOUNT_A), ACCOUNT_B)

        admin_adapter = make_adapter(env=self.env)
        self.assertEqual(admin_adapter.payload_account_id(ACCOUNT_B), ACCOUNT_B)

    def test_owner_account_deletion_removes_data_then_auth_user(self):
        identity = {
            "accountId": ACCOUNT_A,
            "personId": PERSON_A,
            "familyGroupId": FAMILY_A,
            "authUserId": USER_A,
        }
        adapter = FakeDeletionAdapter(self.env, identity)
        result = adapter.delete_scoped_account(USER_A)

        self.assertTrue(result["accountDeleted"])
        self.assertTrue(result["authUserDeleted"])
        self.assertFalse(result["cleanupRequired"])
        self.assertEqual([call[:2] for call in adapter.calls], [
            ("POST", "audit_events"),
            ("DELETE", "accounts"),
            ("DELETE", "auth.users"),
        ])

    def test_non_owner_cannot_delete_family_account(self):
        identity = {
            "accountId": ACCOUNT_A,
            "personId": PERSON_A,
            "familyGroupId": FAMILY_A,
            "authUserId": USER_A,
        }
        adapter = FakeDeletionAdapter(self.env, identity, role="member")
        with self.assertRaisesRegex(PermissionError, "account_deletion_owner_required"):
            adapter.delete_scoped_account(USER_A)
        self.assertEqual(adapter.calls, [])

    def test_auth_cleanup_failure_is_reported_after_personal_data_deletion(self):
        identity = {
            "accountId": ACCOUNT_A,
            "personId": PERSON_A,
            "familyGroupId": FAMILY_A,
            "authUserId": USER_A,
        }
        adapter = FakeDeletionAdapter(self.env, identity, auth_delete_fails=True)
        result = adapter.delete_scoped_account(USER_A)
        self.assertTrue(result["accountDeleted"])
        self.assertFalse(result["authUserDeleted"])
        self.assertTrue(result["cleanupRequired"])


if __name__ == "__main__":
    unittest.main()
