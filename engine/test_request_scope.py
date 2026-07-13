#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "request-scope-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


ACCOUNT_A = "11111111-1111-4111-8111-111111111111"
ACCOUNT_B = "22222222-2222-4222-8222-222222222222"
PERSON_A = "33333333-3333-4333-8333-333333333333"
PERSON_B = "44444444-4444-4444-8444-444444444444"
FAMILY_A = "55555555-5555-4555-8555-555555555555"
FAMILY_B = "66666666-6666-4666-8666-666666666666"


class FakeScopedBackend:
    def enabled(self):
        return True

    def owns_account_id(self, value):
        return value == ACCOUNT_A

    def owns_person_id(self, value):
        return value == PERSON_A

    def owns_family_group_id(self, value):
        return value == FAMILY_A


AUTH_GATE = {
    "ok": True,
    "required": True,
    "auth": {"authUserId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
}


class RequestScopeTests(unittest.TestCase):
    def authorize(self, path, data):
        with patch.object(server, "data_backend", return_value=FakeScopedBackend()):
            server.authorize_request_data_scope(path, data, AUTH_GATE)

    def test_owned_nested_scope_is_allowed(self):
        self.authorize("/memory/retrieve", {
            "accountId": ACCOUNT_A,
            "query": {
                "person_id": PERSON_A,
                "familyGroupId": FAMILY_A,
            },
        })

    def test_cross_account_id_is_rejected(self):
        with self.assertRaisesRegex(PermissionError, "request_scope_forbidden"):
            self.authorize("/wellbeing/recent", {"accountId": ACCOUNT_B})

    def test_cross_person_id_is_rejected(self):
        with self.assertRaisesRegex(PermissionError, "request_scope_forbidden"):
            self.authorize("/memory/retrieve", {"personId": PERSON_B})

    def test_cross_family_id_is_rejected(self):
        with self.assertRaisesRegex(PermissionError, "request_scope_forbidden"):
            self.authorize("/family/state", {"family_group_id": FAMILY_B})

    def test_non_uuid_local_person_is_rejected_on_private_data_api(self):
        with self.assertRaisesRegex(PermissionError, "request_scope_forbidden"):
            self.authorize("/routine-reminders", {"personId": "local-device-person"})

    def test_family_invitation_flow_remains_owned_by_claude_scope(self):
        self.authorize("/family/invitations", {
            "action": "apply",
            "inviteePersonId": "local-device-person",
            "familyGroupId": FAMILY_B,
        })

    def test_public_or_unrequired_request_is_not_scoped(self):
        with patch.object(server, "data_backend", side_effect=AssertionError("backend should not be called")):
            server.authorize_request_data_scope("/account-bootstrap", {"accountId": ACCOUNT_B}, {
                "ok": True,
                "required": False,
            })

    def test_verified_new_user_can_reach_account_bootstrap(self):
        class MissingIdentityBackend:
            def configured(self):
                return True

            def resolve_auth_identity(self, _auth_user_id):
                return None

        with patch.object(server.supabase_adapter, "make_adapter", return_value=MissingIdentityBackend()):
            self.assertIsNone(server.bind_request_data_identity(AUTH_GATE, allow_missing=True))

    def test_missing_identity_stays_blocked_outside_bootstrap(self):
        class MissingIdentityBackend:
            def configured(self):
                return True

            def resolve_auth_identity(self, _auth_user_id):
                return None

        with patch.object(server.supabase_adapter, "make_adapter", return_value=MissingIdentityBackend()):
            with self.assertRaisesRegex(PermissionError, "account_scope_missing"):
                server.bind_request_data_identity(AUTH_GATE)


if __name__ == "__main__":
    unittest.main()
