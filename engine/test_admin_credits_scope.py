#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "admin-credits-scope-test-key")
os.environ["MUNEA_DATABASE_PROVIDER"] = "json"
sys.path.insert(0, os.path.dirname(__file__))

import server  # noqa: E402


class AdminCreditsSummaryScopeTests(unittest.TestCase):
    """2026-07-24 稽核補：這支讀的是單一示範帳號、不是跨帳號聚合——response 要老實標 scope，
    讓前端未來能顯示提醒（本次不動 web/admin.js）。"""

    def test_response_declares_single_demo_account_scope(self):
        with patch.object(server, "load_billing_store", return_value={}), \
             patch.object(server, "load_credits_store", return_value={"wallets": [], "transactions": [], "ledger": []}):
            response = server.admin_credits_summary({})
        self.assertTrue(response["ok"])
        self.assertEqual(response["scope"], "single_demo_account")


if __name__ == "__main__":
    unittest.main()
