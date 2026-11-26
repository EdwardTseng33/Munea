#!/usr/bin/env python3
"""035 分鐘改回各帳號各扣的 SQL 靜態守門（不連任何資料庫）。

實際呼叫驗證在 scripts/sql_sandbox/check_035_per_account_minutes.mjs（PGlite）。
跑法：python scripts/test_per_account_minutes_sql.py
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase" / "sql" / "035_per_account_minutes.sql").read_text(encoding="utf-8")
FLAT = re.sub(r"\s+", " ", SQL.lower())


def function_body(name):
    match = re.search(
        rf"create\s+or\s+replace\s+function\s+public\.{name}\s*\(.*?\)\s+returns\s+.*?\bas\s+\$\$(.*?)\$\$;",
        SQL, flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing function body: {name}"
    return re.sub(r"\s+", " ", match.group(1).lower()).strip()


class PerAccountMinutesSqlTests(unittest.TestCase):
    def test_header_and_transaction(self):
        head = SQL.split("begin;", 1)[0]
        self.assertIn("Run after 034_family_shared_minutes_daily_free.sql", head)
        self.assertIn("回退", head)
        self.assertTrue(SQL.rstrip().endswith("commit;"))

    def test_share_owner_always_null(self):
        self.assertEqual(function_body("munea_family_share_owner"), "select null::jsonb;")

    def test_status_never_returns_family_share(self):
        body = function_body("munea_credit_share_status")
        self.assertIn("'familyshare', null", body)
        self.assertIn("'sharedspendable', 0", body)
        self.assertNotIn("munea_family_share_owner", body)
        self.assertNotIn("v_owner", body)
        self.assertIn("munea_ensure_free_allowance(p_account_id)", body, "免費額度照舊補建")

    def test_spend_functions_and_free_rules_untouched(self):
        for name in ("munea_call_consume_credit", "munea_call_request", "munea_ensure_free_allowance",
                     "munea_free_allowance_window", "account_in_family_group"):
            self.assertNotIn(f"function public.{name}", FLAT, f"{name} 不該在 035 改")

    def test_policy_v6_not_shared(self):
        self.assertIn("'munea_app_store_v1', 6, true", FLAT)
        self.assertEqual(FLAT.count('"familysharedminutes": false'), 2)
        self.assertNotIn('"familysharedminutes": true', FLAT)

    def test_permissions(self):
        self.assertIn("revoke all on function public.munea_family_share_owner(uuid, uuid) from public, anon, authenticated", FLAT)
        self.assertIn("revoke all on function public.munea_credit_share_status(uuid, uuid) from public, anon, authenticated", FLAT)
        self.assertIn("grant execute on function public.munea_credit_share_status(uuid, uuid) to service_role", FLAT)


if __name__ == "__main__":
    unittest.main()
