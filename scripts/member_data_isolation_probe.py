#!/usr/bin/env python3
"""Read-only two-tenant staging probe for RLS and Brain account isolation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PRODUCTION_PROJECT_REFS = {
    "fespbkdwafueyonppzwq",
    "uhmpmystjjdqqxlpsthc",
}
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
PROJECT_REF_RE = re.compile(r"^[a-z0-9]{20}$")
SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
DEFAULT_BRAIN_URL = "https://munea-brain-staging-491603544409.asia-east1.run.app"


@dataclass(frozen=True)
class ProbeConfig:
    brain_url: str
    supabase_url: str
    staging_project_ref: str
    publishable_key: str
    app_key: str
    tenant_a_token: str
    tenant_b_token: str
    removed_member_token: str
    tenant_a_account_id: str
    tenant_b_account_id: str
    tenant_a_person_id: str
    tenant_b_person_id: str
    tenant_a_family_id: str
    tenant_b_family_id: str
    exact_commit: str
    evidence_reference: str
    fixture_lifecycle_reference: str
    timeout_seconds: float = 20.0


Transport = Callable[
    [str, str, dict[str, str], dict[str, Any] | None, float],
    tuple[int, Any],
]


def _clean_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("target URL must be a credential-free HTTPS origin")
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
    )


def validate_targets(
    brain_url: str,
    supabase_url: str,
    staging_project_ref: str,
) -> tuple[str, str]:
    brain = _clean_base_url(brain_url)
    brain_host = (urllib.parse.urlsplit(brain).hostname or "").lower()
    if "munea-brain-staging" not in brain_host or not brain_host.endswith(".run.app"):
        raise ValueError("Brain target must be the Munea staging Cloud Run service")

    project_ref = str(staging_project_ref or "").strip().lower()
    if not PROJECT_REF_RE.fullmatch(project_ref):
        raise ValueError("staging Supabase project ref must be 20 lowercase characters")
    if project_ref in PRODUCTION_PROJECT_REFS:
        raise ValueError("production or rollback Supabase project is forbidden")

    supabase = _clean_base_url(supabase_url)
    supabase_host = (urllib.parse.urlsplit(supabase).hostname or "").lower()
    if supabase_host != f"{project_ref}.supabase.co":
        raise ValueError("Supabase URL must exactly match the declared staging project ref")
    return brain, supabase


def validate_config(config: ProbeConfig) -> ProbeConfig:
    brain, supabase = validate_targets(
        config.brain_url,
        config.supabase_url,
        config.staging_project_ref,
    )
    required_secrets = {
        "publishable key": config.publishable_key,
        "App key": config.app_key,
        "tenant A token": config.tenant_a_token,
        "tenant B token": config.tenant_b_token,
        "removed-member token": config.removed_member_token,
    }
    missing = [name for name, value in required_secrets.items() if not str(value or "").strip()]
    if missing:
        raise ValueError("missing credential inputs: " + ", ".join(missing))
    identifiers = {
        "tenant A account": config.tenant_a_account_id,
        "tenant B account": config.tenant_b_account_id,
        "tenant A person": config.tenant_a_person_id,
        "tenant B person": config.tenant_b_person_id,
        "tenant A family": config.tenant_a_family_id,
        "tenant B family": config.tenant_b_family_id,
    }
    invalid = [name for name, value in identifiers.items() if not UUID_RE.fullmatch(value or "")]
    if invalid:
        raise ValueError("fixture identifiers must be UUIDs: " + ", ".join(invalid))
    if len(set(identifiers.values())) != len(identifiers):
        raise ValueError("tenant fixture identifiers must all be distinct")
    if not COMMIT_RE.fullmatch(config.exact_commit or ""):
        raise ValueError("exact commit must be a 40-character Git SHA")
    if not config.evidence_reference.strip() or not config.fixture_lifecycle_reference.strip():
        raise ValueError("evidence and fixture lifecycle references are required")
    if config.timeout_seconds <= 0 or config.timeout_seconds > 60:
        raise ValueError("timeout must be between 0 and 60 seconds")
    return ProbeConfig(
        **{
            **config.__dict__,
            "brain_url": brain,
            "supabase_url": supabase,
            "staging_project_ref": config.staging_project_ref.lower(),
            "exact_commit": config.exact_commit.lower(),
        }
    )


def request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeError, json.JSONDecodeError):
            parsed = None
        return exc.code, parsed


def _supabase_person_url(base_url: str, person_id: str) -> str:
    query = urllib.parse.urlencode(
        {"select": "id,account_id", "id": f"eq.{person_id}"}
    )
    return f"{base_url}/rest/v1/persons?{query}"


def _safe_check(name: str, passed: bool, status_code: int, **metrics: Any) -> dict[str, Any]:
    return {
        "name": name,
        "result": "pass" if passed else "fail",
        "statusCode": status_code,
        **metrics,
    }


def run_probe(
    config: ProbeConfig,
    *,
    transport: Transport = request_json,
    tested_at: str | None = None,
) -> dict[str, Any]:
    config = validate_config(config)
    checks: list[dict[str, Any]] = []

    publishable_headers = {
        "apikey": config.publishable_key,
        "accept": "application/json",
    }

    def direct_person(token: str, person_id: str, expected_rows: int, name: str) -> bool:
        status, payload = transport(
            "GET",
            _supabase_person_url(config.supabase_url, person_id),
            {**publishable_headers, "authorization": f"Bearer {token}"},
            None,
            config.timeout_seconds,
        )
        row_count = len(payload) if isinstance(payload, list) else -1
        passed = status == 200 and row_count == expected_rows
        checks.append(_safe_check(name, passed, status, rowCount=max(row_count, 0)))
        return passed

    def brain_post(
        token: str,
        path: str,
        payload: dict[str, Any],
        expected_status: int,
        name: str,
        require_ok: bool = False,
    ) -> bool:
        status, response = transport(
            "POST",
            f"{config.brain_url}{path}",
            {
                "authorization": f"Bearer {token}",
                "x-munea-key": config.app_key,
                "content-type": "application/json",
            },
            payload,
            config.timeout_seconds,
        )
        passed = status == expected_status and (
            not require_ok or isinstance(response, dict) and response.get("ok") is True
        )
        checks.append(_safe_check(name, passed, status))
        return passed

    version_status, version_payload = transport(
        "GET",
        f"{config.brain_url}/version",
        {"accept": "application/json"},
        None,
        config.timeout_seconds,
    )
    staging_commit = ""
    staging_revision = ""
    if isinstance(version_payload, dict):
        staging_commit = str(version_payload.get("commit") or "").lower()
        staging_revision = str(
            version_payload.get("revision")
            or version_payload.get("serviceRevision")
            or ""
        )
    release_identity_passed = (
        version_status == 200
        and isinstance(version_payload, dict)
        and version_payload.get("schema") == "munea.service-release.v1"
        and version_payload.get("service") == "brain"
        and version_payload.get("environment") == "staging"
        and COMMIT_RE.fullmatch(staging_commit) is not None
        and staging_commit == config.exact_commit.lower()
        and SAFE_LABEL_RE.fullmatch(staging_revision) is not None
        and staging_revision.lower() != "unknown"
    )
    checks.append(
        _safe_check(
            "staging_release_identity",
            release_identity_passed,
            version_status,
            commitMatched=staging_commit == config.exact_commit.lower(),
        )
    )

    own_direct = all(
        (
            direct_person(
                config.tenant_a_token,
                config.tenant_a_person_id,
                1,
                "tenant_a_reads_own_person_via_rls",
            ),
            direct_person(
                config.tenant_b_token,
                config.tenant_b_person_id,
                1,
                "tenant_b_reads_own_person_via_rls",
            ),
        )
    )
    cross_direct = all(
        (
            direct_person(
                config.tenant_a_token,
                config.tenant_b_person_id,
                0,
                "tenant_a_cannot_read_tenant_b_person_via_rls",
            ),
            direct_person(
                config.tenant_b_token,
                config.tenant_a_person_id,
                0,
                "tenant_b_cannot_read_tenant_a_person_via_rls",
            ),
        )
    )
    own_brain = all(
        (
            brain_post(
                config.tenant_a_token,
                "/person-profile",
                {"action": "load", "personId": config.tenant_a_person_id},
                200,
                "tenant_a_reads_own_person_via_brain",
                require_ok=True,
            ),
            brain_post(
                config.tenant_b_token,
                "/person-profile",
                {"action": "load", "personId": config.tenant_b_person_id},
                200,
                "tenant_b_reads_own_person_via_brain",
                require_ok=True,
            ),
        )
    )
    cross_person_brain = all(
        (
            brain_post(
                config.tenant_a_token,
                "/person-profile",
                {"action": "load", "personId": config.tenant_b_person_id},
                403,
                "tenant_a_cannot_read_tenant_b_person_via_brain",
            ),
            brain_post(
                config.tenant_b_token,
                "/person-profile",
                {"action": "load", "personId": config.tenant_a_person_id},
                403,
                "tenant_b_cannot_read_tenant_a_person_via_brain",
            ),
        )
    )
    cross_family_brain = all(
        (
            brain_post(
                config.tenant_a_token,
                "/family-members",
                {"action": "list", "familyGroupId": config.tenant_b_family_id},
                403,
                "tenant_a_cannot_read_tenant_b_family_via_brain",
            ),
            brain_post(
                config.tenant_b_token,
                "/family-members",
                {"action": "list", "familyGroupId": config.tenant_a_family_id},
                403,
                "tenant_b_cannot_read_tenant_a_family_via_brain",
            ),
        )
    )
    override_denied = brain_post(
        config.tenant_a_token,
        "/app-profile",
        {"action": "load", "accountId": config.tenant_b_account_id},
        403,
        "client_tenant_override_denied",
    )
    removed_denied = brain_post(
        config.removed_member_token,
        "/person-profile",
        {"action": "load"},
        403,
        "removed_member_denied",
    )
    unknown_status, unknown_response = transport(
        "POST",
        f"{config.brain_url}/auth-status",
        {
            "authorization": "Bearer invalid-i18n-isolation-probe-token",
            "x-munea-key": config.app_key,
            "content-type": "application/json",
        },
        {},
        config.timeout_seconds,
    )
    unknown_denied = unknown_status in (200, 401, 403) and not (
        isinstance(unknown_response, dict) and unknown_response.get("ok") is True
    )
    checks.append(_safe_check("unknown_user_denied", unknown_denied, unknown_status))

    scenarios = {
        "ownAccountReadable": release_identity_passed and own_direct and own_brain,
        "otherAccountPersonDeniedByRls": cross_direct,
        "otherAccountPersonDeniedByBrain": cross_person_brain,
        "otherAccountFamilyDeniedByBrain": cross_family_brain,
        "clientTenantOverrideDenied": override_denied,
        "removedMemberDenied": removed_denied,
        "unknownUserDenied": unknown_denied,
        "fixtureLifecycleReviewed": bool(config.fixture_lifecycle_reference.strip()),
    }
    passed = all(scenarios.values()) and all(
        check["result"] == "pass" for check in checks
    )
    return {
        "schema": "munea.member-data-isolation-e2e.v1",
        "result": "pass" if passed else "fail",
        "exactCommit": config.exact_commit,
        "testedAt": tested_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": "staging",
        "captureMode": "read-only-preprovisioned-two-tenant",
        "realMemberDataUsed": False,
        "productionWritesPerformed": False,
        "fixtureAccounts": 2,
        "fixtureLifecycleReviewed": True,
        "containsSecrets": False,
        "containsPersonalData": False,
        "stagingIdentitySchema": (
            version_payload.get("schema") if isinstance(version_payload, dict) else ""
        ),
        "stagingService": (
            version_payload.get("service") if isinstance(version_payload, dict) else ""
        ),
        "stagingEnvironment": (
            version_payload.get("environment") if isinstance(version_payload, dict) else ""
        ),
        "stagingCommit": staging_commit,
        "stagingRevision": staging_revision,
        "stagingProjectRef": config.staging_project_ref,
        "evidenceReference": config.evidence_reference,
        "fixtureLifecycleReference": config.fixture_lifecycle_reference,
        "scenarios": scenarios,
        "checks": checks,
        "scope": {
            "directSupabaseRls": True,
            "brainServiceRoleAuthorization": True,
            "writesAttempted": False,
            "productionTargetsForbidden": True,
            "responsePayloadsStored": False,
        },
    }


def _env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def config_from_environment(args: argparse.Namespace) -> ProbeConfig:
    return ProbeConfig(
        brain_url=args.brain_url or _env("MUNEA_I18N_STAGING_BRAIN_URL") or DEFAULT_BRAIN_URL,
        supabase_url=_env("MUNEA_I18N_STAGING_SUPABASE_URL"),
        staging_project_ref=_env("MUNEA_I18N_STAGING_SUPABASE_PROJECT_REF"),
        publishable_key=_env("MUNEA_I18N_STAGING_SUPABASE_PUBLISHABLE_KEY"),
        app_key=_env("MUNEA_APP_KEY"),
        tenant_a_token=_env("MUNEA_I18N_TENANT_A_TOKEN"),
        tenant_b_token=_env("MUNEA_I18N_TENANT_B_TOKEN"),
        removed_member_token=_env("MUNEA_I18N_REMOVED_MEMBER_TOKEN"),
        tenant_a_account_id=_env("MUNEA_I18N_TENANT_A_ACCOUNT_ID"),
        tenant_b_account_id=_env("MUNEA_I18N_TENANT_B_ACCOUNT_ID"),
        tenant_a_person_id=_env("MUNEA_I18N_TENANT_A_PERSON_ID"),
        tenant_b_person_id=_env("MUNEA_I18N_TENANT_B_PERSON_ID"),
        tenant_a_family_id=_env("MUNEA_I18N_TENANT_A_FAMILY_ID"),
        tenant_b_family_id=_env("MUNEA_I18N_TENANT_B_FAMILY_ID"),
        exact_commit=args.exact_commit,
        evidence_reference=args.evidence_reference,
        fixture_lifecycle_reference=args.fixture_lifecycle_reference,
        timeout_seconds=args.timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brain-url", default="")
    parser.add_argument("--exact-commit", required=True)
    parser.add_argument("--evidence-reference", required=True)
    parser.add_argument("--fixture-lifecycle-reference", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_probe(config_from_environment(args))
    except ValueError as exc:
        print(f"Member data isolation probe refused to run: {exc}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
