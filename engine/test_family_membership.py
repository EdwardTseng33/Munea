#!/usr/bin/env python3
"""家人圈「退出」「移除」要在伺服器上真的撤銷看得到（2026-11-18，補助案 B4 查核）。

以前 App 的「移除」只改自己畫面上的名單、「退出」連請求都沒送；伺服器決定誰看得到誰的
family_memberships 沒動，被移除或退出的人照樣讀得到全家的健康數字與心情。
POST /family/membership 的規矩：
  - 一定要驗證過的登入身分；
  - 要動的圈＝登入身分推出來的「目前所在的圈」，不收 App 送來的圈代號；
  - leave：只能退出別人建立的圈、刪的是自己那一筆；圈主不能退自己的圈；
  - remove：只有圈主能移除別人；不能移除自己；目標要是合法的人員代號。
"""
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "family-membership-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402

OWNER_AUTH = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
MEMBER_AUTH = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OWNER_ACCOUNT = "44444444-4444-4444-8444-444444444444"
MEMBER_ACCOUNT = "55555555-5555-4555-8555-555555555555"
OWNER_PERSON = "11111111-1111-4111-8111-111111111111"
MEMBER_PERSON = "22222222-2222-4222-8222-222222222222"
OWNER_GROUP = "33333333-3333-4333-8333-333333333333"
MEMBER_OWN_GROUP = "66666666-6666-4666-8666-666666666666"


class FakeMembershipBackend:
    request_scoped = True

    def __init__(self, who="owner", memberships=None):
        self.auth_user_id = OWNER_AUTH if who == "owner" else MEMBER_AUTH
        self.account_id = OWNER_ACCOUNT if who == "owner" else MEMBER_ACCOUNT
        self.person_id = OWNER_PERSON if who == "owner" else MEMBER_PERSON
        # 兩個人目前所在的圈都是圈主建立的那個（成員是接受邀請進來的）
        self.family_group_id = OWNER_GROUP
        self.memberships = set(memberships if memberships is not None else {
            (OWNER_GROUP, OWNER_PERSON), (OWNER_GROUP, MEMBER_PERSON), (MEMBER_OWN_GROUP, MEMBER_PERSON),
        })
        self.deleted = []

    def enabled(self):
        return True

    def family_group_owner_account_unscoped(self, group_id):
        return {OWNER_GROUP: OWNER_ACCOUNT, MEMBER_OWN_GROUP: MEMBER_ACCOUNT}.get(group_id)

    def delete_family_membership_unscoped(self, group_id, person_id):
        key = (group_id, person_id)
        if key in self.memberships:
            self.memberships.discard(key)
            self.deleted.append(key)
            return 1
        return 0

    def own_family_group_id_unscoped(self):
        return {OWNER_ACCOUNT: OWNER_GROUP, MEMBER_ACCOUNT: MEMBER_OWN_GROUP}[self.account_id]


class FamilyMembershipTests(unittest.TestCase):
    def call(self, backend, data, actor=None):
        actor = {"authUserId": backend.auth_user_id} if actor is None else actor
        with patch.object(server, "data_backend", return_value=backend):
            return server.family_membership_response(data, actor=actor)

    def test_guest_cannot_leave_or_remove(self):
        backend = FakeMembershipBackend("member")
        self.assertEqual(self.call(backend, {"action": "leave"}, actor={})["error"], "auth_required")
        self.assertEqual(self.call(backend, {"action": "remove", "targetPersonId": OWNER_PERSON}, actor={})["error"], "auth_required")
        self.assertEqual(backend.deleted, [])

    def test_member_leaving_really_drops_their_membership(self):
        backend = FakeMembershipBackend("member")
        result = self.call(backend, {"action": "leave"})
        self.assertTrue(result["ok"])
        self.assertEqual(backend.deleted, [(OWNER_GROUP, MEMBER_PERSON)])
        self.assertNotIn((OWNER_GROUP, MEMBER_PERSON), backend.memberships)
        # 回到自己的圈；自己那個圈的關係不會被動到
        self.assertEqual(result["familyGroupId"], MEMBER_OWN_GROUP)
        self.assertIn((MEMBER_OWN_GROUP, MEMBER_PERSON), backend.memberships)

    def test_leave_ignores_any_group_id_sent_by_the_app(self):
        backend = FakeMembershipBackend("member")
        result = self.call(backend, {"action": "leave", "familyGroupId": MEMBER_OWN_GROUP})
        self.assertTrue(result["ok"])
        self.assertEqual(backend.deleted, [(OWNER_GROUP, MEMBER_PERSON)])

    def test_owner_cannot_leave_own_circle(self):
        backend = FakeMembershipBackend("owner")
        self.assertEqual(self.call(backend, {"action": "leave"})["error"], "owner_cannot_leave")
        self.assertEqual(backend.deleted, [])

    def test_owner_removes_member_for_real(self):
        backend = FakeMembershipBackend("owner")
        result = self.call(backend, {"action": "remove", "targetPersonId": MEMBER_PERSON})
        self.assertTrue(result["ok"])
        self.assertEqual(backend.deleted, [(OWNER_GROUP, MEMBER_PERSON)])
        # 被移除的人自己的圈不受影響
        self.assertIn((MEMBER_OWN_GROUP, MEMBER_PERSON), backend.memberships)

    def test_member_cannot_remove_anyone(self):
        backend = FakeMembershipBackend("member")
        self.assertEqual(self.call(backend, {"action": "remove", "targetPersonId": OWNER_PERSON})["error"], "family_owner_required")
        self.assertEqual(backend.deleted, [])

    def test_owner_cannot_remove_self_or_garbage(self):
        backend = FakeMembershipBackend("owner")
        self.assertEqual(self.call(backend, {"action": "remove", "targetPersonId": OWNER_PERSON})["error"], "cannot_remove_self")
        self.assertEqual(self.call(backend, {"action": "remove", "targetPersonId": "王奶奶"})["error"], "target_required")
        self.assertEqual(self.call(backend, {"action": "remove"})["error"], "target_required")
        self.assertEqual(backend.deleted, [])

    def test_removing_someone_not_in_circle_is_reported_not_faked(self):
        backend = FakeMembershipBackend("owner", memberships={(OWNER_GROUP, OWNER_PERSON)})
        result = self.call(backend, {"action": "remove", "targetPersonId": MEMBER_PERSON})
        self.assertEqual(result, {"ok": False, "error": "membership_not_found"})

    def test_unknown_action(self):
        backend = FakeMembershipBackend("owner")
        self.assertEqual(self.call(backend, {"action": "dissolve"})["error"], "unsupported_action")

    def test_route_requires_verified_login_and_is_scope_exempt(self):
        self.assertIn("/family/membership", server.SCOPE_EXEMPT_PATHS)
        self.assertNotIn("/family/membership", server.PUBLIC_POST_PATHS)
        with open(server.__file__, encoding="utf-8") as fh:
            source = fh.read()
        gate_line = next(line for line in source.splitlines() if '"/family/invitations", "/family-relays", "/push/devices"' in line)
        self.assertIn('"/family/membership"', gate_line)
        self.assertIn('elif self.path == "/family/membership":', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
