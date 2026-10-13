# -*- coding: utf-8 -*-
"""C1 · P0-5 機構窗口專區的兩支接口。

驗收標準（需求單）：「組織窗口看不到管理功能」——所以這裡最重要的一條是
test_link_for_one_org_cannot_read_another：拿 A 機構的連結，絕對翻不到 B 機構的數字。
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "org-portal-endpoints-test-key")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import org_portal
import server

SECRET = {"MUNEA_ORG_PORTAL_SECRET": "test-secret-do-not-use-in-prod"}

CLIENT_A = {"id": "cli-a", "name": "青松健康護理之家", "planTier": "plus", "seatQuota": 10}
CLIENT_B = {"id": "cli-b", "name": "清福養老院", "planTier": "pro", "seatQuota": 50}

SEATS = {
    "cli-a": [
        {"id": "a1", "status": "active", "accountId": "acc-a1", "inviteEmail": "a1@example.org"},
        {"id": "a2", "status": "pending", "inviteEmail": "a2@example.org"},
    ],
    "cli-b": [{"id": "b1", "status": "active", "accountId": "acc-b1"}] * 7,
}

CLIENTS = {"cli-a": CLIENT_A, "cli-b": CLIENT_B}


def fake_get_client(client_id):
    return CLIENTS.get(client_id)


def fake_list_seats(client_id=None, **kwargs):
    return SEATS.get(client_id, [])


class IssueLinkTests(unittest.TestCase):
    @patch.dict(os.environ, SECRET, clear=False)
    def test_admin_can_issue_link(self):
        with patch.object(server.enterprise_seats, "get_client", side_effect=fake_get_client):
            result = server.admin_enterprise_portal_issue_link_response({"clientId": "cli-a"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["clientName"], "青松健康護理之家")
        self.assertIn("/org-portal.html?t=", result["url"])
        self.assertGreater(result["expiresAt"], int(datetime.now(timezone.utc).timestamp()))

    @patch.dict(os.environ, SECRET, clear=False)
    def test_missing_client_id_is_rejected(self):
        result = server.admin_enterprise_portal_issue_link_response({})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "client_id_required")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_unknown_client_is_rejected(self):
        with patch.object(server.enterprise_seats, "get_client", side_effect=fake_get_client):
            result = server.admin_enterprise_portal_issue_link_response({"clientId": "nobody"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "client_not_found")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_ttl_zero_is_rejected_not_silently_defaulted(self):
        """0 天要被擋，不可以悄悄變成預設的 30 天。"""
        with patch.object(server.enterprise_seats, "get_client", side_effect=fake_get_client):
            result = server.admin_enterprise_portal_issue_link_response({"clientId": "cli-a", "ttlDays": 0})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_ttl")

    @patch.dict(os.environ, {"MUNEA_ORG_PORTAL_SECRET": ""}, clear=False)
    def test_missing_secret_reports_not_configured(self):
        with patch.object(server.enterprise_seats, "get_client", side_effect=fake_get_client):
            result = server.admin_enterprise_portal_issue_link_response({"clientId": "cli-a"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "portal_secret_not_configured")


class SummaryEndpointTests(unittest.TestCase):
    @patch.dict(os.environ, SECRET, clear=False)
    def test_valid_link_returns_own_summary(self):
        token = org_portal.issue_portal_token("cli-a")
        with patch.object(server.org_portal.enterprise_seats, "get_client", side_effect=fake_get_client), \
             patch.object(server.org_portal.enterprise_seats, "list_seats", side_effect=fake_list_seats):
            result = server.org_portal_summary_response({"token": token})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["org"]["name"], "青松健康護理之家")
        self.assertEqual(result["seats"]["active"], 1)
        self.assertEqual(result["seats"]["pending"], 1)

    @patch.dict(os.environ, SECRET, clear=False)
    def test_link_for_one_org_cannot_read_another(self):
        """最重要的一條：A 的連結只看得到 A。"""
        token_a = org_portal.issue_portal_token("cli-a")
        with patch.object(server.org_portal.enterprise_seats, "get_client", side_effect=fake_get_client), \
             patch.object(server.org_portal.enterprise_seats, "list_seats", side_effect=fake_list_seats):
            result = server.org_portal_summary_response({"token": token_a})
        self.assertEqual(result["org"]["name"], "青松健康護理之家")
        self.assertNotIn("清福養老院", repr(result))
        self.assertNotEqual(result["seats"]["quota"], CLIENT_B["seatQuota"])

    @patch.dict(os.environ, SECRET, clear=False)
    def test_summary_never_leaks_individual_data(self):
        token = org_portal.issue_portal_token("cli-a")
        with patch.object(server.org_portal.enterprise_seats, "get_client", side_effect=fake_get_client), \
             patch.object(server.org_portal.enterprise_seats, "list_seats", side_effect=fake_list_seats):
            result = server.org_portal_summary_response({"token": token})
        blob = repr(result)
        for leaked in ("acc-a1", "a1@example.org", "a2@example.org"):
            self.assertNotIn(leaked, blob)

    @patch.dict(os.environ, SECRET, clear=False)
    def test_garbage_token_says_only_invalid(self):
        """錯誤訊息不能透露是哪一關沒過，否則變成試探組織代號的工具。"""
        result = server.org_portal_summary_response({"token": "not-a-real-token"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_token")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_unknown_client_also_says_only_invalid(self):
        token = org_portal.issue_portal_token("cli-ghost")
        with patch.object(server.org_portal.enterprise_seats, "get_client", side_effect=fake_get_client):
            result = server.org_portal_summary_response({"token": token})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_token")

    @patch.dict(os.environ, SECRET, clear=False)
    def test_expired_link_tells_user_to_ask_for_a_new_one(self):
        long_ago = datetime.now(timezone.utc) - timedelta(days=40)
        token = org_portal.issue_portal_token("cli-a", ttl_days=30, issued_at=long_ago)
        result = server.org_portal_summary_response({"token": token})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "token_expired")


class RouteRegistrationTests(unittest.TestCase):
    def test_portal_paths_are_exempt_from_member_login(self):
        """窗口不是 App 會員、沒有登入證，漏列就會被會員門擋死。"""
        self.assertIn("/enterprise/portal/summary", server.PUBLIC_POST_PATHS)
        self.assertIn("/admin/enterprise/portal/issue-link", server.ADMIN_POST_PATHS)

    def test_issue_link_is_not_a_public_path(self):
        """發連結是管理動作，絕不能落進免驗清單。"""
        self.assertNotIn("/admin/enterprise/portal/issue-link", server.PUBLIC_POST_PATHS)


if __name__ == "__main__":
    unittest.main()
