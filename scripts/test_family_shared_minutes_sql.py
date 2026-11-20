#!/usr/bin/env python3
"""034 家人圈共用分鐘＋每日／每週免費額度的 SQL 靜態守門（不連任何資料庫）。

跑法：python scripts/test_family_shared_minutes_sql.py
有裝 pglast（libpg_query）時順便做一次真正的 PostgreSQL／PL/pgSQL 語法解析。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "supabase" / "sql" / "034_family_shared_minutes_daily_free.sql"
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()
FLAT = re.sub(r"\s+", " ", LOWER)


def function_body(name):
    match = re.search(
        rf"create\s+or\s+replace\s+function\s+public\.{name}\s*\(.*?\)\s+returns\s+.*?\bas\s+\$\$(.*?)\$\$;",
        SQL, flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing function body: {name}"
    return re.sub(r"\s+", " ", match.group(1).lower()).strip()


class FamilySharedMinutesSqlTests(unittest.TestCase):
    def test_header_states_order_and_rollback(self):
        head = SQL.split("begin;", 1)[0]
        self.assertIn("Run after 033_enterprise_seat_redeem_codes.sql", head)
        self.assertIn("回退", head)
        self.assertIn("010_realtime_call_control.sql", head)
        self.assertTrue(LOWER.strip().startswith("--"))
        self.assertIn("\nbegin;", SQL)
        self.assertTrue(SQL.rstrip().endswith("commit;"))

    def test_rerunnable(self):
        self.assertIn("drop constraint if exists credit_wallets_wallet_type_check", FLAT)
        self.assertIn("create table if not exists public.free_allowance_settings", FLAT)
        self.assertIn("create unique index if not exists credit_wallets_free_allowance_period_uidx", FLAT)
        self.assertIn("insert into public.free_allowance_settings (id) values (1) on conflict (id) do nothing", FLAT)
        for statement in re.findall(r"^\s*create\s+(?!or replace|table if not exists|unique index if not exists|index if not exists)\w+", LOWER, re.M):
            self.fail(f"non-idempotent create: {statement}")

    def test_wallet_type_and_settings_defaults(self):
        self.assertIn("check (wallet_type in ('included_monthly', 'purchased', 'free_allowance'))", FLAT)
        for fragment in (
            "trial_days integer not null default 7",
            "trial_daily_minutes numeric not null default 10",
            "reduced_daily_minutes numeric not null default 5",
            "weekly_minutes numeric not null default 10",
            "monthly_cap_minutes numeric not null default 1360",
        ):
            self.assertIn(fragment, FLAT)
        self.assertIn("alter table public.free_allowance_settings enable row level security", FLAT)
        self.assertIn("revoke all on public.free_allowance_settings from anon, authenticated", FLAT)

    def test_window_uses_taipei_days_and_monday_weeks(self):
        body = function_body("munea_free_allowance_window")
        self.assertIn("v_today := (p_at at time zone 'asia/taipei')::date", body)
        self.assertIn("v_today - (v_created at time zone 'asia/taipei')::date + 1", body)
        self.assertIn("extract(isodow from v_today)", body)
        self.assertIn("v_cap_reached := v_used >= v_cap", body)
        self.assertIn("case when v_cap_reached then v_reduced else v_daily end", body)
        self.assertIn("'free-daily:'", body)
        self.assertIn("'free-weekly:'", body)
        used = function_body("munea_free_allowance_month_used")
        self.assertIn("w.wallet_type = 'free_allowance'", used)
        self.assertIn("date_trunc('month', p_at at time zone 'asia/taipei') at time zone 'asia/taipei'", used)

    def test_ensure_is_idempotent_and_skips_paid_accounts(self):
        body = function_body("munea_ensure_free_allowance")
        self.assertLess(body.index("munea_account_paid_plan(p_account_id)"), body.index("insert into public.credit_wallets"))
        self.assertIn("pg_advisory_xact_lock(pg_catalog.hashtextextended(v_key, 0))", body)
        self.assertIn("on conflict (account_id, period) where wallet_type = 'free_allowance' do nothing", body)
        self.assertIn("on conflict (idempotency_key) do nothing", body)
        self.assertIn("'free-allowance:' || p_account_id::text || ':' || v_period", body)

    def test_owner_is_the_group_account_and_must_be_paid(self):
        body = function_body("munea_family_share_owner")
        self.assertIn("join public.family_groups g on g.id = m.family_group_id and g.deleted_at is null", body)
        self.assertIn("p.account_id = p_account_id", body)
        self.assertIn("where g.account_id <> p_account_id", body)
        self.assertIn("order by m.created_at desc", body)
        self.assertLess(body.index("munea_account_paid_plan(p_account_id) is not null"), body.index("from public.family_memberships"))
        self.assertIn("v_plan := public.munea_account_paid_plan(v_owner)", body)
        paid = function_body("munea_account_paid_plan")
        self.assertIn("s.status in ('active', 'trial', 'grace_period')", paid)
        self.assertIn("order by s.updated_at desc", paid)

    def test_free_grant_failure_does_not_block_paid_minutes(self):
        for name in ("munea_call_consume_credit", "munea_call_request"):
            body = function_body(name)
            self.assertRegex(body, r"begin perform public\.munea_ensure_free_allowance\([a-z_]+\); exception when others then raise warning")

    def test_status_hides_other_people_from_members(self):
        body = function_body("munea_credit_share_status")
        self.assertIn("where v_role = 'owner' or u.person_id = v_viewer", body)
        self.assertNotIn("email", body)
        self.assertIn("'sharedspendable', v_spendable", body)

    def test_signatures_unchanged_and_permissions(self):
        for signature in (
            "function public.munea_call_consume_credit( p_call_id uuid, p_account_id uuid, p_person_id uuid, p_minute integer ) returns boolean",
            "function public.munea_call_request( p_user_id uuid, p_person_id uuid, p_character_id text, p_idempotency_key text, p_queue_max integer default 30 ) returns jsonb",
            "function public.munea_grant_free_signup_trial( p_account_id uuid, p_person_id uuid default null ) returns jsonb",
        ):
            self.assertIn(signature, FLAT)
        for fn in (
            "munea_free_allowance_month_used(timestamptz)",
            "munea_account_paid_plan(uuid)",
            "munea_free_allowance_window(uuid, timestamptz)",
            "munea_ensure_free_allowance(uuid)",
            "munea_family_share_owner(uuid, uuid)",
            "munea_credit_share_status(uuid, uuid)",
            "munea_call_consume_credit(uuid,uuid,uuid,integer)",
            "munea_call_request(uuid,uuid,text,text,integer)",
        ):
            self.assertIn(f"revoke all on function public.{fn} from public, anon, authenticated", FLAT)
        granted = set(re.findall(r"grant execute on function public\.([a-z_]+)\(", FLAT))
        self.assertEqual(granted, {"munea_ensure_free_allowance", "munea_credit_share_status",
                                   "munea_call_request", "munea_grant_free_signup_trial"})
        self.assertNotRegex(FLAT, r"grant execute on function [^;]* to (anon|authenticated|public)")

    def test_pglast_parses_sql_and_plpgsql(self):
        try:
            import pglast
        except ImportError:
            self.skipTest("pglast not installed")
        self.assertGreater(len(pglast.parse_sql(SQL)), 20)
        self.assertEqual(len(pglast.parse_plpgsql(SQL)), 9)


if __name__ == "__main__":
    unittest.main()
