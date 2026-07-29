#!/usr/bin/env python3
"""Audit a redacted LocaleContext export without network or database writes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

import localization


EXPORT_SCHEMA = "munea.locale-context-data-export.v1"
AUDIT_SCHEMA = "munea.locale-context-data-audit.v1"
CAPTURE_MODE = "read-only-redacted-export"
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_REGION_RE = re.compile(r"^[A-Za-z]{2}$")
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")
_TIME_ZONE_RE = re.compile(r"^(?:UTC|[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+)$")
_DATA_REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
_SUPPORTED_PREFIXES = ("zh", "en", "ja", "es")

_ROOT_FIELDS = {
    "schema",
    "sourceCommit",
    "generatedAt",
    "environment",
    "captureMode",
    "writesPerformed",
    "records",
}
_RECORD_FIELDS = {"active", "account", "person"}
_ACCOUNT_FIELDS = {"ref", "locale", "preferred_languages"}
_PERSON_FIELDS = {
    "ref",
    "accountRef",
    "locale",
    "timezone",
    "region_code",
    "attributes",
}
_ATTRIBUTE_FIELDS = {"localeContext"}
_POLICY_FIELDS = {
    "version",
    "units",
    "currency",
    "safetyRegion",
    "legalRegion",
    "dataRegion",
}


def _iso_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _locale_supported(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.strip().replace("_", "-").lower()
    return normalized.split("-", 1)[0] in _SUPPORTED_PREFIXES


def _unexpected_fields(value: Any, allowed: set[str], path: str) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [
        f"unexpected_field:{path}.{key}"
        for key in sorted(set(value) - allowed)
    ]


def _require_string(
    value: Any,
    missing_code: str,
    invalid_code: str,
    pattern: re.Pattern[str] | None = None,
) -> list[str]:
    if value is None or value == "":
        return [missing_code]
    if not isinstance(value, str) or not value.strip():
        return [invalid_code]
    if pattern is not None and pattern.fullmatch(value.strip()) is None:
        return [invalid_code]
    return []


def _record_issues(record: Any) -> tuple[list[str], bool, str | None, str | None]:
    if not isinstance(record, dict):
        return ["record_shape_invalid"], False, None, None

    issues = _unexpected_fields(record, _RECORD_FIELDS, "record")
    active = record.get("active")
    if not isinstance(active, bool):
        issues.append("active_flag_invalid")
        active = True

    account = record.get("account")
    person = record.get("person")
    if not isinstance(account, dict):
        issues.append("account_shape_invalid")
        account = {}
    if not isinstance(person, dict):
        issues.append("person_shape_invalid")
        person = {}

    issues.extend(_unexpected_fields(account, _ACCOUNT_FIELDS, "account"))
    issues.extend(_unexpected_fields(person, _PERSON_FIELDS, "person"))

    account_ref = account.get("ref")
    person_ref = person.get("ref")
    person_account_ref = person.get("accountRef")
    issues.extend(_require_string(account_ref, "account_ref_missing", "account_ref_invalid"))
    issues.extend(_require_string(person_ref, "person_ref_missing", "person_ref_invalid"))
    issues.extend(
        _require_string(
            person_account_ref,
            "person_account_ref_missing",
            "person_account_ref_invalid",
        )
    )
    if (
        isinstance(account_ref, str)
        and isinstance(person_account_ref, str)
        and account_ref != person_account_ref
    ):
        issues.append("account_isolation_mismatch")

    ui_locale = account.get("locale")
    if ui_locale is None or ui_locale == "":
        issues.append("ui_locale_missing")
    elif not _locale_supported(ui_locale):
        issues.append("ui_locale_invalid")

    preferred_languages = account.get("preferred_languages")
    if not isinstance(preferred_languages, list) or not preferred_languages:
        issues.append("preferred_languages_missing")
    elif not all(_locale_supported(value) for value in preferred_languages):
        issues.append("preferred_languages_invalid")

    conversation_locale = person.get("locale")
    if conversation_locale is None or conversation_locale == "":
        issues.append("conversation_locale_missing")
    elif not _locale_supported(conversation_locale):
        issues.append("conversation_locale_invalid")

    issues.extend(
        _require_string(
            person.get("region_code"),
            "country_code_missing",
            "country_code_invalid",
            _REGION_RE,
        )
    )
    issues.extend(
        _require_string(
            person.get("timezone"),
            "time_zone_missing",
            "time_zone_invalid",
            _TIME_ZONE_RE,
        )
    )

    attributes = person.get("attributes")
    if not isinstance(attributes, dict):
        issues.append("person_attributes_missing")
        attributes = {}
    else:
        issues.extend(_unexpected_fields(attributes, _ATTRIBUTE_FIELDS, "person.attributes"))

    policy = attributes.get("localeContext")
    if not isinstance(policy, dict):
        issues.append("locale_policy_missing")
        policy = {}
    else:
        issues.extend(
            _unexpected_fields(
                policy,
                _POLICY_FIELDS,
                "person.attributes.localeContext",
            )
        )

    version = policy.get("version")
    if version is None:
        issues.append("locale_policy_version_missing")
    elif isinstance(version, bool) or version != localization.LOCALE_CONTEXT_VERSION:
        issues.append("locale_policy_version_invalid")

    units = policy.get("units")
    if units is None or units == "":
        issues.append("units_missing")
    elif units not in ("metric", "us"):
        issues.append("units_invalid")

    issues.extend(
        _require_string(
            policy.get("currency"),
            "currency_missing",
            "currency_invalid",
            _CURRENCY_RE,
        )
    )
    issues.extend(
        _require_string(
            policy.get("safetyRegion"),
            "safety_region_missing",
            "safety_region_invalid",
            _REGION_RE,
        )
    )
    issues.extend(
        _require_string(
            policy.get("legalRegion"),
            "legal_region_missing",
            "legal_region_invalid",
            _REGION_RE,
        )
    )
    issues.extend(
        _require_string(
            policy.get("dataRegion"),
            "data_region_missing",
            "data_region_invalid",
            _DATA_REGION_RE,
        )
    )

    if not issues:
        try:
            localization.locale_context_from_account(account, person)
        except (TypeError, ValueError):
            issues.append("locale_context_normalization_failed")

    return (
        sorted(set(issues)),
        active,
        person_ref if isinstance(person_ref, str) else None,
        account_ref if isinstance(account_ref, str) else None,
    )


def audit_export(
    payload: Any,
    *,
    source_commit: str,
    audited_at: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic, identifier-free audit report."""
    normalized_source_commit = str(source_commit or "").lower()
    export_issues: list[str] = []
    if not isinstance(payload, dict):
        payload = {}
        export_issues.append("export_root_invalid")
    else:
        export_issues.extend(_unexpected_fields(payload, _ROOT_FIELDS, "export"))

    if payload.get("schema") != EXPORT_SCHEMA:
        export_issues.append("export_schema_invalid")
    export_source_commit = str(payload.get("sourceCommit") or "")
    if not _COMMIT_RE.fullmatch(export_source_commit):
        export_issues.append("export_source_commit_invalid")
    elif export_source_commit.lower() != normalized_source_commit:
        export_issues.append("export_source_commit_mismatch")
    if not _iso_timestamp(payload.get("generatedAt")):
        export_issues.append("export_generated_at_invalid")
    if payload.get("environment") not in ("staging", "production"):
        export_issues.append("export_environment_invalid")
    if payload.get("captureMode") != CAPTURE_MODE:
        export_issues.append("export_capture_mode_invalid")
    if payload.get("writesPerformed") is not False:
        export_issues.append("export_must_confirm_zero_writes")
    if not _COMMIT_RE.fullmatch(normalized_source_commit):
        export_issues.append("source_commit_invalid")

    records = payload.get("records")
    if not isinstance(records, list):
        records = []
        export_issues.append("records_invalid")
    if not records:
        export_issues.append("records_empty")

    record_results = []
    active_count = 0
    complete_active = 0
    invalid_active = 0
    invalid_inactive = 0
    isolation_failures = 0
    seen_person_accounts: dict[str, str] = {}

    for index, record in enumerate(records, start=1):
        issues, active, person_ref, account_ref = _record_issues(record)
        if person_ref and account_ref:
            previous_account = seen_person_accounts.get(person_ref)
            if previous_account is not None:
                issues.append(
                    "duplicate_person_ref_cross_account"
                    if previous_account != account_ref
                    else "duplicate_person_ref"
                )
            seen_person_accounts[person_ref] = account_ref
        issues = sorted(set(issues))
        isolation_failures += sum(
            issue in ("account_isolation_mismatch", "duplicate_person_ref_cross_account")
            for issue in issues
        )
        if active:
            active_count += 1
            if issues:
                invalid_active += 1
            else:
                complete_active += 1
        elif issues:
            invalid_inactive += 1
        record_results.append(
            {
                "record": f"record-{index:04d}",
                "active": active,
                "status": "complete" if not issues else "invalid",
                "issues": issues,
            }
        )

    coverage = complete_active / active_count if active_count else 0.0
    passed = (
        not export_issues
        and active_count > 0
        and invalid_active == 0
        and invalid_inactive == 0
        and isolation_failures == 0
        and coverage == 1.0
    )
    return {
        "schema": AUDIT_SCHEMA,
        "result": "pass" if passed else "fail",
        "sourceCommit": normalized_source_commit,
        "generatedAt": audited_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sourceExport": {
            "schema": payload.get("schema"),
            "sourceCommit": (
                export_source_commit.lower()
                if _COMMIT_RE.fullmatch(export_source_commit)
                else payload.get("sourceCommit")
            ),
            "generatedAt": payload.get("generatedAt"),
            "environment": payload.get("environment"),
            "captureMode": payload.get("captureMode"),
            "writesPerformed": payload.get("writesPerformed"),
        },
        "summary": {
            "recordCount": len(records),
            "activeRecordCount": active_count,
            "completeActiveRecords": complete_active,
            "invalidActiveRecords": invalid_active,
            "invalidInactiveRecords": invalid_inactive,
            "accountIsolationFailures": isolation_failures,
            "explicitCoverage": coverage,
            "exportIssueCount": len(set(export_issues)),
        },
        "outputPrivacy": {
            "containsDirectIdentifiers": False,
            "containsNames": False,
            "containsContactDetails": False,
            "recordReferencesAreOrdinalOnly": True,
        },
        "exportIssues": sorted(set(export_issues)),
        "records": record_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        payload = json.loads(args.export.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"LocaleContext data audit could not read export: {exc}", file=sys.stderr)
        return 2

    report = audit_export(payload, source_commit=args.source_commit)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
