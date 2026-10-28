# -*- coding: utf-8 -*-
"""C1 · P0-5 企業窗口專區的守門測試。

盯死三件事（需求單第三節「資料界線」）：窗口只看得到自己那一家、憑證會過期也不能改、
彙總裡不准有任何個別長輩的資料。
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import org_portal


SECRET = {"MUNEA_ORG_PORTAL_SECRET": "test-secret-do-not-use-in-prod"}


class TokenTests(unittest.TestCase):
    @patch.dict(os.environ, SECRET, clear=False)
    def test_issue_then_verify_returns_same_client(self):
        token = org_portal.issue_portal_token("client-abc")
        result = org_portal.verify_portal_token(token)
        self.assertEqual(result["clientId"], "client-abc")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_tampered_client_id_is_rejected(self):
        """改組織代號＝想偷看別家。簽章必須擋下來。"""
        token = org_portal.issue_portal_token("client-abc")
        payload_b64, signature = token.split(".", 1)
        forged_payload = org_portal._b64e(
            b'{"cid":"client-victim","exp":9999999999,"iat":1,"v":"v1"}'
        )
        with self.assertRaises(org_portal.PortalTokenError) as ctx:
            org_portal.verify_portal_token(f"{forged_payload}.{signature}")
        self.assertEqual(ctx.exception.code, "invalid_token")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_expired_token_is_rejected(self):
        long_ago = datetime.now(timezone.utc) - timedelta(days=40)
        token = org_portal.issue_portal_token("client-abc", ttl_days=30, issued_at=long_ago)
        with self.assertRaises(org_portal.PortalTokenError) as ctx:
            org_portal.verify_portal_token(token)
        self.assertEqual(ctx.exception.code, "token_expired")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_token_signed_by_another_secret_is_rejected(self):
        token = org_portal.issue_portal_token("client-abc")
        with patch.dict(os.environ, {"MUNEA_ORG_PORTAL_SECRET": "another-secret"}, clear=False):
            with self.assertRaises(org_portal.PortalTokenError):
                org_portal.verify_portal_token(token)

    @patch.dict(os.environ, {"MUNEA_ORG_PORTAL_SECRET": ""}, clear=False)
    def test_missing_secret_says_not_configured(self):
        """沒設鑰匙要明講，不可以自己編一把預設的。"""
        with self.assertRaises(org_portal.PortalTokenError) as ctx:
            org_portal.issue_portal_token("client-abc")
        self.assertEqual(ctx.exception.code, "portal_secret_not_configured")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_ttl_out_of_range_is_rejected(self):
        for bad in (0, -1, org_portal.MAX_TTL_DAYS + 1):
            with self.assertRaises(org_portal.PortalTokenError):
                org_portal.issue_portal_token("client-abc", ttl_days=bad)

    @patch.dict(os.environ, SECRET, clear=False)
    def test_garbage_tokens_are_rejected(self):
        for bad in ("", "   ", "no-dot", "a.b.c", "....", None):
            with self.assertRaises(org_portal.PortalTokenError):
                org_portal.verify_portal_token(bad)


CLIENT = {
    "id": "client-abc",
    "name": "青松健康護理之家",
    "planTier": "plus",
    "seatQuota": 10,
    "contractStart": "2026-10-01",
    "contractEnd": "2027-09-30",
    "contactEmail": "director@example.org",
    "notes": "內部備註不該外流",
}

SEATS = [
    {"id": "s1", "status": "active", "accountId": "acc-1", "inviteEmail": "a@example.org"},
    {"id": "s2", "status": "active", "accountId": "acc-2", "inviteEmail": "b@example.org"},
    {"id": "s3", "status": "pending", "inviteEmail": "c@example.org"},
    {"id": "s4", "status": "released", "accountId": "acc-4"},
]


class SummaryTests(unittest.TestCase):
    def test_counts_are_correct(self):
        summary = org_portal.build_portal_summary("client-abc", seats=SEATS, client=CLIENT)
        self.assertEqual(summary["seats"]["quota"], 10)
        self.assertEqual(summary["seats"]["active"], 2)
        self.assertEqual(summary["seats"]["pending"], 1)
        self.assertEqual(summary["seats"]["released"], 1)
        self.assertEqual(summary["seats"]["unusedQuota"], 8)
        self.assertEqual(summary["seats"]["utilization"], 0.2)
        self.assertEqual(summary["org"]["name"], "青松健康護理之家")

    def test_summary_has_no_personal_data(self):
        """整份彙總裡不准出現任何一位長輩的信箱或帳號代號。"""
        summary = org_portal.build_portal_summary("client-abc", seats=SEATS, client=CLIENT)
        blob = repr(summary)
        for leaked in ("a@example.org", "b@example.org", "acc-1", "acc-2", "director@example.org"):
            self.assertNotIn(leaked, blob)
        self.assertFalse(summary["privacy"]["personalDataIncluded"])

    def test_internal_notes_do_not_leak(self):
        summary = org_portal.build_portal_summary("client-abc", seats=SEATS, client=CLIENT)
        self.assertNotIn("內部備註不該外流", repr(summary))

    def test_privacy_guard_blows_up_on_personal_field(self):
        """把關本身要真的會擋——不是擺著好看。"""
        with self.assertRaises(org_portal.PortalPrivacyError):
            org_portal.assert_no_personal_data({"seats": {"active": 1}, "extra": {"email": "x@y.z"}})
        with self.assertRaises(org_portal.PortalPrivacyError):
            org_portal.assert_no_personal_data({"rows": [{"accountId": "acc-1"}]})

    def test_zero_quota_does_not_divide_by_zero(self):
        summary = org_portal.build_portal_summary(
            "client-abc", seats=[], client=dict(CLIENT, seatQuota=0)
        )
        self.assertIsNone(summary["seats"]["utilization"])
        self.assertEqual(summary["seats"]["unusedQuota"], 0)

    def test_unknown_client_is_rejected(self):
        with patch.object(org_portal.enterprise_seats, "get_client", return_value=None):
            with self.assertRaises(org_portal.PortalTokenError) as ctx:
                org_portal.build_portal_summary("nobody")
            self.assertEqual(ctx.exception.code, "client_not_found")

    def test_summary_only_reads_own_client_seats(self):
        """窗口拿到的席次只能是自己那家的——list_seats 一定要帶 client_id 過濾。"""
        captured = {}

        def fake_list_seats(client_id=None, **kwargs):
            captured["client_id"] = client_id
            return SEATS

        with patch.object(org_portal.enterprise_seats, "get_client", return_value=CLIENT), \
             patch.object(org_portal.enterprise_seats, "list_seats", side_effect=fake_list_seats):
            org_portal.build_portal_summary("client-abc")
        self.assertEqual(captured["client_id"], "client-abc")


class NoWriteSurfaceTests(unittest.TestCase):
    def test_module_exposes_no_write_functions(self):
        """這支模組只准讀。哪天有人加了寫入函式，這條會先響。"""
        banned = {"save", "create", "update", "delete", "grant", "revoke", "transition", "commit"}
        for name in dir(org_portal):
            if name.startswith("_"):
                continue
            lowered = name.lower()
            for word in banned:
                self.assertNotIn(
                    word, lowered,
                    f"org_portal 不應該有會寫資料的函式，發現 {name}",
                )


if __name__ == "__main__":
    unittest.main()
