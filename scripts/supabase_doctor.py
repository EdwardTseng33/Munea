#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.join(ROOT, "engine")
sys.path.insert(0, ENGINE_DIR)

from env_loader import load_engine_env
import supabase_adapter


SCHEMA_TABLES = {
    "supabase/sql/001_initial_munea_schema.sql": {
        "accounts",
        "account_members",
        "persons",
        "family_groups",
        "family_memberships",
        "companion_profiles",
        "routine_reminders",
        "voice_sessions",
        "conversation_summaries",
        "safety_events",
        "subscription_ledger",
        "usage_ledger",
        "privacy_requests",
        "audit_events",
    },
    "supabase/sql/003_analytics_admin_foundation.sql": {
        "product_events",
        "daily_user_metrics",
        "voice_session_metrics",
        "reminder_events",
        "family_interaction_events",
        "cost_ledger",
        "admin_notes",
    },
    "supabase/sql/004_ai_memory_service_foundation.sql": {
        "memory_items",
        "perception_snapshots",
        "ai_brain_runs",
    },
    "supabase/sql/005_companion_persona_layer.sql": {
        "companion_persona_templates",
        "companion_relationship_states",
    },
    "supabase/sql/006_billing_credits_foundation.sql": {
        "entitlement_policy_versions",
        "credit_wallets",
        "credit_transactions",
        "credit_ledger",
    },
    "supabase/sql/007_family_cloud_state_foundation.sql": {
        "family_invitations",
        "consent_records",
        "wellbeing_signals",
        "family_state_entries",
        "family_activities",
        "family_activity_participants",
    },
    "supabase/sql/014_medication_dose_events.sql": {
        "medication_dose_events",
    },
    "supabase/sql/015_family_relay_messages.sql": {
        "family_relay_messages",
    },
    "supabase/sql/016_notification_platform.sql": {
        "push_devices",
        "notification_events",
        "notification_deliveries",
    },
    "supabase/sql/017_notification_settings.sql": {
        "notification_settings",
    },
}


def schema_files_for_tables(tables):
    missing = set(tables)
    return [path for path, table_names in SCHEMA_TABLES.items() if missing.intersection(table_names)]


def safe_url(url):
    parsed = urllib.parse.urlparse(url or "")
    if not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def classify_table_error(exc):
    """Classify live failures so only an actual missing table recommends SQL."""
    kind = getattr(exc, "error_kind", None)
    message = str(exc)
    if kind == "missing_table" or "PGRST205" in message:
        return "missing"
    if kind == "permission" or "42501" in message or "permission denied" in message.lower():
        return "permission"
    if kind == "configuration" or "not fully configured" in message.lower():
        return "configuration"
    if kind == "unreachable" or "unreachable" in message.lower() or "circuit open" in message.lower():
        return "unreachable"
    return "error"


def failed_table_check(table, exc):
    item = {
        "table": table,
        "ok": False,
        "status": classify_table_error(exc),
        "error": str(exc)[:180],
    }
    error_code = getattr(exc, "error_code", None)
    status_code = getattr(exc, "status_code", None)
    if error_code:
        item["errorCode"] = error_code
    if status_code:
        item["httpStatus"] = status_code
    return item


def doctor(live=False):
    loaded = load_engine_env()
    adapter = supabase_adapter.make_adapter()
    status = adapter.status()
    result = {
        "ok": adapter.enabled(),
        "provider": status["provider"],
        "enabled": status["enabled"],
        "loadedEnvKeys": sorted([key for key in loaded if key != "SUPABASE_SERVICE_ROLE_KEY"]),
        "hasServiceRoleKey": bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
        "supabaseUrl": safe_url(os.environ.get("SUPABASE_URL")),
        "accountId": os.environ.get("MUNEA_SUPABASE_ACCOUNT_ID") or "",
        "personId": os.environ.get("MUNEA_SUPABASE_PERSON_ID") or "",
        "familyGroupId": os.environ.get("MUNEA_SUPABASE_FAMILY_GROUP_ID") or "",
        "missing": status["missing"],
        "tables": status["tables"],
        "tableChecks": [],
        "liveChecks": [],
        "recommendedSqlFiles": [],
    }

    if live and adapter.enabled():
        for table in status["tables"]:
            try:
                adapter.check_table(table)
                result["tableChecks"].append({"table": table, "ok": True, "status": "ok"})
            except Exception as exc:
                result["tableChecks"].append(failed_table_check(table, exc))

        checks = [
            ("appProfile", adapter.load_app_profile_store),
            ("companionProfile", adapter.load_companion_profile),
            ("billing", adapter.load_billing_store),
            ("privacyRequests", adapter.load_privacy_requests_store),
        ]
        for name, fn in checks:
            try:
                value = fn()
                result["liveChecks"].append({"name": name, "ok": value is not None})
            except Exception as exc:
                result["liveChecks"].append({"name": name, "ok": False, "error": str(exc)[:180]})
        result["ok"] = (
            all(check["ok"] for check in result["tableChecks"])
            and all(check["ok"] for check in result["liveChecks"])
        )
        missing_tables = [
            check["table"]
            for check in result["tableChecks"]
            if check.get("status") == "missing"
        ]
        result["recommendedSqlFiles"] = schema_files_for_tables(missing_tables)

    return result


def print_text(result):
    print("Munea Supabase Doctor")
    print(f"- provider: {result['provider']}")
    print(f"- enabled: {result['enabled']}")
    print(f"- url: {result['supabaseUrl'] or '(missing)'}")
    print(f"- service role key: {'present' if result['hasServiceRoleKey'] else 'missing'}")
    if result["missing"]:
        print("- missing:")
        for item in result["missing"]:
            print(f"  - {item}")
    else:
        print("- missing: none")
    if result["liveChecks"]:
        if result["tableChecks"]:
            failed_tables = [check for check in result["tableChecks"] if not check["ok"]]
            print(f"- table checks: {len(result['tableChecks']) - len(failed_tables)}/{len(result['tableChecks'])} ok")
            for check in failed_tables:
                print(
                    f"  - {check['table']}: {check.get('status', 'failed')} "
                    f"({check.get('error', 'failed')})"
                )
            if result.get("recommendedSqlFiles"):
                print("- recommended SQL apply order:")
                for path in result["recommendedSqlFiles"]:
                    print(f"  - {path}")
                print("  After applying, rerun: npm run supabase:doctor:live")
        print("- live checks:")
        for check in result["liveChecks"]:
            suffix = "" if check["ok"] else f" ({check.get('error', 'failed')})"
            print(f"  - {check['name']}: {'ok' if check['ok'] else 'failed'}{suffix}")


def main():
    parser = argparse.ArgumentParser(description="Validate Munea Supabase backend environment without printing secrets.")
    parser.add_argument("--live", action="store_true", help="Run read-only live REST checks when Supabase env is complete.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--allow-missing", action="store_true", help="Exit 0 even when Supabase env is incomplete.")
    args = parser.parse_args()

    result = doctor(live=args.live)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result)

    if result["ok"] or args.allow_missing:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
