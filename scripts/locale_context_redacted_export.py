#!/usr/bin/env python3
"""Capture a GET-only, identifier-free LocaleContext export from production."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


EXPORT_SCHEMA = "munea.locale-context-data-export.v1"
CAPTURE_MODE = "read-only-redacted-export"
PRODUCTION_PROJECT_REFS = {
    "fespbkdwafueyonppzwq",
    "uhmpmystjjdqqxlpsthc",
}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_PROJECT_REF_RE = re.compile(r"^[a-z0-9]{20}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8}){0,3}$")
_TIME_ZONE_RE = re.compile(r"^(?:UTC|[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+)$")
_REGION_RE = re.compile(r"^[A-Za-z]{2}$")
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")
_DATA_REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
_MAX_ROWS = 1_000_000


class ExportRefused(RuntimeError):
    """Raised when the exporter cannot preserve its read-only privacy contract."""


@dataclass(frozen=True)
class ExportConfig:
    supabase_url: str
    expected_project_ref: str
    service_role_key: str = field(repr=False)
    source_commit: str
    page_size: int = 500
    timeout_seconds: float = 20.0


Transport = Callable[
    [str, str, dict[str, str], float],
    tuple[int, Any],
]


def _clean_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Supabase target must be a credential-free HTTPS origin")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def validate_config(config: ExportConfig) -> ExportConfig:
    project_ref = str(config.expected_project_ref or "").strip().lower()
    if not _PROJECT_REF_RE.fullmatch(project_ref):
        raise ValueError("expected production project ref must be 20 lowercase characters")
    if project_ref not in PRODUCTION_PROJECT_REFS:
        raise ValueError("target is not an approved Munea production project")

    supabase_url = _clean_origin(config.supabase_url)
    host = (urllib.parse.urlsplit(supabase_url).hostname or "").lower()
    if host != f"{project_ref}.supabase.co":
        raise ValueError("Supabase URL does not match the expected production project")
    service_role_key = str(config.service_role_key or "").strip()
    if not service_role_key:
        raise ValueError("missing dedicated read-only audit credential")
    source_commit = str(config.source_commit or "").strip().lower()
    if not _COMMIT_RE.fullmatch(source_commit):
        raise ValueError("source commit must be a 40-character Git SHA")
    if config.page_size < 1 or config.page_size > 1000:
        raise ValueError("page size must be between 1 and 1000")
    if config.timeout_seconds <= 0 or config.timeout_seconds > 60:
        raise ValueError("timeout must be between 0 and 60 seconds")
    return ExportConfig(
        supabase_url=supabase_url,
        expected_project_ref=project_ref,
        service_role_key=service_role_key,
        source_commit=source_commit,
        page_size=config.page_size,
        timeout_seconds=config.timeout_seconds,
    )


def request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, Any]:
    if method != "GET":
        raise ExportRefused("export transport permits GET requests only")
    request = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else None
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ExportRefused("production export returned invalid JSON") from exc
            return response.status, payload
    except urllib.error.HTTPError as exc:
        raise ExportRefused(
            f"production export request failed with HTTP {exc.code}"
        ) from None
    except urllib.error.URLError as exc:
        raise ExportRefused("production export request failed at the transport layer") from exc


def _table_url(
    base_url: str,
    table: str,
    select: str,
    *,
    limit: int,
    offset: int,
) -> str:
    query = urllib.parse.urlencode(
        {
            "select": select,
            "deleted_at": "is.null",
            "order": "id.asc",
            "limit": str(limit),
            "offset": str(offset),
        }
    )
    return f"{base_url}/rest/v1/{table}?{query}"


def _fetch_rows(
    config: ExportConfig,
    table: str,
    select: str,
    *,
    transport: Transport,
) -> list[dict[str, Any]]:
    headers = {
        "accept": "application/json",
        "apikey": config.service_role_key,
        "authorization": f"Bearer {config.service_role_key}",
    }
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        status, payload = transport(
            "GET",
            _table_url(
                config.supabase_url,
                table,
                select,
                limit=config.page_size,
                offset=offset,
            ),
            headers,
            config.timeout_seconds,
        )
        if status != 200:
            raise ExportRefused(
                f"production export request failed with HTTP {status}"
            )
        if not isinstance(payload, list) or not all(
            isinstance(row, dict) for row in payload
        ):
            raise ExportRefused("production export returned an invalid row collection")
        rows.extend(payload)
        if len(rows) > _MAX_ROWS:
            raise ExportRefused("production export exceeded the bounded row limit")
        if len(payload) < config.page_size:
            break
        offset += len(payload)
    return rows


def _active_rows(
    rows: list[dict[str, Any]],
    *,
    label: str,
) -> list[dict[str, Any]]:
    if not all("deleted_at" in row for row in rows):
        raise ExportRefused(f"{label} response omitted the deletion marker")
    return [row for row in rows if row.get("deleted_at") in (None, "")]


def _validated_ids(rows: list[dict[str, Any]], label: str) -> list[str]:
    identifiers = [row.get("id") for row in rows]
    if not all(isinstance(value, str) and _UUID_RE.fullmatch(value) for value in identifiers):
        raise ExportRefused(f"{label} response contained an invalid identifier")
    normalized = [value.lower() for value in identifiers]
    if len(set(normalized)) != len(normalized):
        raise ExportRefused(f"{label} response contained a duplicate identifier")
    return normalized


def _safe_text(value: Any, pattern: re.Pattern[str]) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if pattern.fullmatch(stripped) else None


def _safe_locales(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        locale = _safe_text(item, _LOCALE_RE)
        if locale is None:
            return []
        result.append(locale)
    return result


def _safe_policy(attributes: Any) -> dict[str, Any]:
    if not isinstance(attributes, dict):
        return {}
    raw = attributes.get("localeContext")
    if not isinstance(raw, dict):
        return {}
    version = raw.get("version")
    return {
        "version": version if isinstance(version, int) and not isinstance(version, bool) else None,
        "units": raw.get("units") if raw.get("units") in ("metric", "us") else None,
        "currency": _safe_text(raw.get("currency"), _CURRENCY_RE),
        "safetyRegion": _safe_text(raw.get("safetyRegion"), _REGION_RE),
        "legalRegion": _safe_text(raw.get("legalRegion"), _REGION_RE),
        "dataRegion": _safe_text(raw.get("dataRegion"), _DATA_REGION_RE),
    }


def _redacted_account(row: dict[str, Any] | None, ref: str) -> dict[str, Any]:
    row = row or {}
    return {
        "ref": ref,
        "locale": _safe_text(row.get("locale"), _LOCALE_RE),
        "preferred_languages": _safe_locales(row.get("preferred_languages")),
    }


def _redacted_person(
    row: dict[str, Any] | None,
    *,
    ref: str,
    account_ref: str,
) -> dict[str, Any]:
    row = row or {}
    return {
        "ref": ref,
        "accountRef": account_ref,
        "locale": _safe_text(row.get("locale"), _LOCALE_RE),
        "timezone": _safe_text(row.get("timezone"), _TIME_ZONE_RE),
        "region_code": _safe_text(row.get("region_code"), _REGION_RE),
        "attributes": {
            "localeContext": _safe_policy(row.get("attributes")),
        },
    }


def build_export(
    config: ExportConfig,
    *,
    transport: Transport = request_json,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Read production through GET requests and return only ordinal references."""
    config = validate_config(config)
    account_rows = _active_rows(
        _fetch_rows(
            config,
            "accounts",
            "id,locale,preferred_languages,deleted_at",
            transport=transport,
        ),
        label="accounts",
    )
    person_rows = _active_rows(
        _fetch_rows(
            config,
            "persons",
            "id,account_id,locale,timezone,region_code,attributes,deleted_at",
            transport=transport,
        ),
        label="persons",
    )

    account_ids = _validated_ids(account_rows, "accounts")
    person_ids = _validated_ids(person_rows, "persons")
    account_pairs = sorted(zip(account_ids, account_rows), key=lambda item: item[0])
    person_pairs = sorted(zip(person_ids, person_rows), key=lambda item: item[0])
    account_refs = {
        identifier: f"account-{index:04d}"
        for index, (identifier, _) in enumerate(account_pairs, start=1)
    }
    account_by_id = {identifier: row for identifier, row in account_pairs}
    people_by_account: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    orphan_index = 0

    for person_index, (_, person) in enumerate(person_pairs, start=1):
        raw_account_id = person.get("account_id")
        normalized_account_id = (
            raw_account_id.lower()
            if isinstance(raw_account_id, str) and _UUID_RE.fullmatch(raw_account_id)
            else ""
        )
        account = account_by_id.get(normalized_account_id)
        account_ref = account_refs.get(normalized_account_id)
        if account_ref is None:
            orphan_index += 1
            account_ref = f"account-orphan-{orphan_index:04d}"
        else:
            people_by_account[normalized_account_id] = (
                people_by_account.get(normalized_account_id, 0) + 1
            )
        records.append(
            {
                "active": True,
                "account": _redacted_account(account, account_ref),
                "person": _redacted_person(
                    person,
                    ref=f"person-{person_index:04d}",
                    account_ref=account_ref,
                ),
            }
        )

    missing_person_index = 0
    for account_id, account in account_pairs:
        if people_by_account.get(account_id, 0):
            continue
        missing_person_index += 1
        account_ref = account_refs[account_id]
        records.append(
            {
                "active": True,
                "account": _redacted_account(account, account_ref),
                "person": _redacted_person(
                    None,
                    ref=f"person-missing-{missing_person_index:04d}",
                    account_ref=account_ref,
                ),
            }
        )

    return {
        "schema": EXPORT_SCHEMA,
        "sourceCommit": config.source_commit,
        "generatedAt": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": "production",
        "captureMode": CAPTURE_MODE,
        "writesPerformed": False,
        "records": records,
    }


def _env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def config_from_environment(args: argparse.Namespace) -> ExportConfig:
    return ExportConfig(
        supabase_url=_env("MUNEA_LOCALE_AUDIT_SUPABASE_URL"),
        expected_project_ref=args.expected_project_ref,
        service_role_key=_env("MUNEA_LOCALE_AUDIT_SUPABASE_SERVICE_ROLE_KEY"),
        source_commit=args.source_commit,
        page_size=args.page_size,
        timeout_seconds=args.timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-project-ref", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    try:
        payload = build_export(config_from_environment(args))
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, ExportRefused) as exc:
        print(f"LocaleContext production export refused to run: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
