#!/usr/bin/env python3
"""Static launch gate for production membership and signup-credit hardening."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "supabase" / "sql" / "012_production_security_hardening.sql").read_text(encoding="utf-8")
ADAPTER = (ROOT / "engine" / "supabase_adapter.py").read_text(encoding="utf-8")
SERVER = (ROOT / "engine" / "server.py").read_text(encoding="utf-8")
BUNDLE = (ROOT / "scripts" / "build_supabase_production_bundle.py").read_text(encoding="utf-8")
LAUNCH_UPGRADE = (ROOT / "scripts" / "build_supabase_launch_upgrade.py").read_text(encoding="utf-8")


required_sql = (
    "drop policy if exists account_members_insert_self_owner",
    "revoke insert, update, delete on public.account_members from authenticated",
    "pg_advisory_xact_lock",
    "munea_grant_free_signup_trial",
    "idempotency_key = v_key",
    "grant execute on function public.munea_grant_free_signup_trial(uuid, uuid) to service_role",
)
missing = [token for token in required_sql if token not in SQL]
assert not missing, "Missing production SQL hardening: " + ", ".join(missing)
assert '"rpc/munea_grant_free_signup_trial"' in ADAPTER
assert "backend.grant_free_signup_trial()" in SERVER
assert '"012_production_security_hardening.sql"' in BUNDLE
assert '"012_production_security_hardening.sql"' in LAUNCH_UPGRADE
assert '"010_realtime_call_control.sql"' in LAUNCH_UPGRADE
assert "001_initial_munea_schema.sql" not in LAUNCH_UPGRADE
print("production security SQL contract: PASS")
