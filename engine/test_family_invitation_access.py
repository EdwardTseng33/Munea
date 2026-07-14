#!/usr/bin/env python3
"""Authorization and entitlement checks for family-circle invitation flows."""
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "family-invite-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server


OWNER_AUTH = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
APPLICANT_AUTH = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OWNER_PERSON = "11111111-1111-4111-8111-111111111111"
APPLICANT_PERSON = "22222222-2222-4222-8222-222222222222"
FAMILY_ID = "33333333-3333-4333-8333-333333333333"


def paid_billing(plan="plus"):
    return {
        "activePlan": plan,
        "subscription": {"status": "active"},
        "serverVerificationRequired": False,
    }


class FakeFamilyBackend:
    enabled = lambda self: True
    request_scoped = True

    def __init__(self, auth_user_id=OWNER_AUTH, billing=None, owner=True):
        self.auth_user_id = auth_user_id
        self.person_id = OWNER_PERSON if auth_user_id == OWNER_AUTH else APPLICANT_PERSON
        self.family_group_id = FAMILY_ID
        self._billing = billing or paid_billing()
        self._owner = owner

    def is_account_owner(self):
        return self._owner

    def load_billing_store(self):
        return self._billing


def pending_invitation():
    return {
        "id": "fam_inv_1",
        "familyGroupId": FAMILY_ID,
        "shortCode": "123456",
        "status": "pending",
        "expiresAt": "2099-01-01T00:00:00+00:00",
        "metadata": {"maxMembers": 4, "plan": "plus", "ownerAuthUserId": OWNER_AUTH},
    }


class FamilyInvitationAccessTests(unittest.TestCase):
    def response(self, backend, data, actor=None):
        actor = {"authUserId": backend.auth_user_id} if actor is None else actor
        with patch.object(server, "data_backend", return_value=backend):
            return server.family_invitations_response(data, client_ip="127.0.0.1", actor=actor)

    def test_guest_cannot_create_or_join(self):
        backend = FakeFamilyBackend()
        self.assertEqual(self.response(backend, {"action": "create"}, actor={})["error"], "auth_required")
        self.assertEqual(self.response(backend, {"action": "accept", "shortCode": "123456"}, actor={})["error"], "auth_required")

    def test_free_member_cannot_create_or_join(self):
        backend = FakeFamilyBackend(billing={"activePlan": "free", "subscription": {"status": "inactive"}})
        self.assertEqual(self.response(backend, {"action": "create"})["error"], "family_plan_required")
        with patch.object(server, "find_pending_family_invitation_by_code", return_value=(pending_invitation(), "supabase")):
            joined = self.response(backend, {"action": "accept", "shortCode": "123456"})
        self.assertEqual(joined["error"], "family_plan_required")

    def test_create_uses_server_owned_identity_and_limit(self):
        backend = FakeFamilyBackend(billing=paid_billing("pro"))
        captured = {}

        def create(payload):
            captured.update(payload)
            return {"shortCode": "123456", **payload}, "supabase"

        with patch.object(server, "create_family_invitation", side_effect=create):
            result = self.response(backend, {
                "action": "create",
                "familyGroupId": "forged-family",
                "inviterPersonId": "forged-person",
                "metadata": {"maxMembers": 9999},
            })

        self.assertTrue(result["ok"])
        self.assertEqual(captured["familyGroupId"], FAMILY_ID)
        self.assertEqual(captured["inviterPersonId"], OWNER_PERSON)
        self.assertEqual(captured["metadata"]["maxMembers"], 12)
        self.assertEqual(captured["metadata"]["ownerAuthUserId"], OWNER_AUTH)

    def test_join_uses_authenticated_person_not_client_person_id(self):
        backend = FakeFamilyBackend(APPLICANT_AUTH)
        captured = {}

        def update(_invitation_id, patch):
            captured.update(patch)
            return {"id": "fam_inv_1", "familyGroupId": FAMILY_ID, **patch}, "supabase"

        with patch.object(server, "find_pending_family_invitation_by_code", return_value=(pending_invitation(), "supabase")), \
             patch.object(server, "family_circle_member_count", return_value=1), \
             patch.object(server, "add_family_member_after_invitation", return_value=({"id": APPLICANT_PERSON}, None)), \
             patch.object(server, "update_family_invitation_after_code_exchange", side_effect=update):
            result = self.response(backend, {
                "action": "accept",
                "shortCode": "123456",
                "inviteePersonId": "forged-person",
                "inviteeName": "小美",
            })

        self.assertTrue(result["ok"])
        self.assertEqual(captured["inviteePersonId"], APPLICANT_PERSON)
        self.assertEqual(captured["metadata"]["inviteeAuthUserId"], APPLICANT_AUTH)

    def test_application_uses_authenticated_identity_not_client_fields(self):
        backend = FakeFamilyBackend(APPLICANT_AUTH)
        captured = {}

        def update(_invitation_id, patch):
            captured.update(patch)
            return {"id": "fam_inv_1", "familyGroupId": FAMILY_ID, **patch}, "supabase"

        with patch.object(server, "find_pending_family_invitation_by_code", return_value=(pending_invitation(), "supabase")), \
             patch.object(server, "update_family_invitation_after_code_exchange", side_effect=update):
            result = self.response(backend, {
                "action": "apply",
                "shortCode": "123456",
                "inviteePersonId": "forged-person",
                "authUserId": "forged-auth-user",
                "inviteeName": "Applicant",
            })

        self.assertTrue(result["ok"])
        self.assertEqual(captured["inviteePersonId"], APPLICANT_PERSON)
        self.assertEqual(captured["metadata"]["applicantPersonId"], APPLICANT_PERSON)
        self.assertEqual(captured["metadata"]["applicantAuthUserId"], APPLICANT_AUTH)

    def test_full_circle_cannot_be_bypassed(self):
        backend = FakeFamilyBackend(APPLICANT_AUTH)
        with patch.object(server, "find_pending_family_invitation_by_code", return_value=(pending_invitation(), "supabase")), \
             patch.object(server, "family_circle_member_count", return_value=4), \
             patch.object(server, "update_family_invitation_after_code_exchange", side_effect=AssertionError("must not accept")):
            result = self.response(backend, {"action": "accept", "shortCode": "123456"})
        self.assertEqual(result["error"], "circle_full")


if __name__ == "__main__":
    unittest.main()
