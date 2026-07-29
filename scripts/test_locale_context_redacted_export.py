#!/usr/bin/env python3
"""Tests for the production GET-only, identifier-free LocaleContext exporter."""

from __future__ import annotations

import json
import sys
import unittest
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from locale_context_data_audit import audit_export
from locale_context_redacted_export import (
    ExportConfig,
    ExportRefused,
    build_export,
    request_json,
    validate_config,
)


EXACT_COMMIT = "a" * 40
PROJECT_REF = "fespbkdwafueyonppzwq"
ACCOUNT_A = "11111111-1111-4111-8111-111111111111"
ACCOUNT_B = "22222222-2222-4222-8222-222222222222"
ACCOUNT_DELETED = "33333333-3333-4333-8333-333333333333"
PERSON_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PERSON_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PERSON_DELETED = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SECRET = "service-role-secret-must-never-be-serialized"


def config(**overrides) -> ExportConfig:
    values = {
        "supabase_url": f"https://{PROJECT_REF}.supabase.co",
        "expected_project_ref": PROJECT_REF,
        "service_role_key": SECRET,
        "source_commit": EXACT_COMMIT,
        "page_size": 1,
        "timeout_seconds": 10.0,
    }
    values.update(overrides)
    return ExportConfig(**values)


def policy(**overrides) -> dict:
    value = {
        "version": 1,
        "units": "metric",
        "currency": "TWD",
        "safetyRegion": "TW",
        "legalRegion": "TW",
        "dataRegion": "tw-primary",
    }
    value.update(overrides)
    return value


def accounts() -> list[dict]:
    return [
        {
            "id": ACCOUNT_A,
            "locale": "zh-TW",
            "preferred_languages": ["zh-TW", "en"],
            "deleted_at": None,
            "name": "Must not leave transport",
        },
        {
            "id": ACCOUNT_B,
            "locale": "ja-JP",
            "preferred_languages": ["ja", "en"],
            "deleted_at": None,
        },
        {
            "id": ACCOUNT_DELETED,
            "locale": "es-MX",
            "preferred_languages": ["es"],
            "deleted_at": "2026-07-01T00:00:00Z",
        },
    ]


def persons() -> list[dict]:
    return [
        {
            "id": PERSON_A,
            "account_id": ACCOUNT_A,
            "locale": "en-US",
            "timezone": "Asia/Taipei",
            "region_code": "TW",
            "locale_context": policy(),
            "attributes": {
                "localeContext": policy(),
                "email": "never@example.test",
                "phone": "+886900000000",
            },
            "deleted_at": None,
            "display_name": "Never Export Me",
        },
        {
            "id": PERSON_B,
            "account_id": ACCOUNT_B,
            "locale": "ja-JP",
            "timezone": "Asia/Tokyo",
            "region_code": "JP",
            "locale_context": policy(
                currency="JPY",
                safetyRegion="JP",
                legalRegion="JP",
                dataRegion="jp-primary",
            ),
            "attributes": {
                "localeContext": policy(
                    currency="JPY",
                    safetyRegion="JP",
                    legalRegion="JP",
                    dataRegion="jp-primary",
                ),
                "notes": "private",
            },
            "deleted_at": None,
        },
        {
            "id": PERSON_DELETED,
            "account_id": ACCOUNT_A,
            "locale": "es-MX",
            "timezone": "America/Mexico_City",
            "region_code": "MX",
            "locale_context": policy(),
            "attributes": {"localeContext": policy()},
            "deleted_at": "2026-07-01T00:00:00Z",
        },
    ]


class FakeTransport:
    def __init__(
        self,
        account_rows: list[dict] | None = None,
        person_rows: list[dict] | None = None,
    ) -> None:
        self.rows = {
            "accounts": account_rows if account_rows is not None else accounts(),
            "persons": person_rows if person_rows is not None else persons(),
        }
        self.calls: list[tuple[str, str, dict[str, str], float]] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        timeout: float,
    ) -> tuple[int, object]:
        self.calls.append((method, url, headers, timeout))
        parsed = urllib.parse.urlsplit(url)
        table = parsed.path.rsplit("/", 1)[-1]
        query = urllib.parse.parse_qs(parsed.query)
        offset = int(query["offset"][0])
        limit = int(query["limit"][0])
        return 200, self.rows[table][offset : offset + limit]


class LocaleContextRedactedExportTests(unittest.TestCase):
    def test_export_is_get_only_paginated_and_identifier_free(self) -> None:
        transport = FakeTransport()
        payload = build_export(
            config(),
            transport=transport,
            generated_at="2026-07-29T12:00:00Z",
        )
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["schema"], "munea.locale-context-data-export.v1")
        self.assertEqual(payload["environment"], "production")
        self.assertEqual(payload["captureMode"], "read-only-redacted-export")
        self.assertIs(payload["writesPerformed"], False)
        self.assertEqual(len(payload["records"]), 2)
        self.assertTrue(all(call[0] == "GET" for call in transport.calls))
        self.assertGreaterEqual(len(transport.calls), 6)
        self.assertTrue(
            all("deleted_at=is.null" in call[1] for call in transport.calls)
        )
        self.assertTrue(
            all(call[2]["authorization"] == f"Bearer {SECRET}" for call in transport.calls)
        )
        account_select = urllib.parse.parse_qs(
            urllib.parse.urlsplit(transport.calls[0][1]).query
        )["select"][0]
        self.assertEqual(
            account_select,
            "id,locale,preferred_languages,deleted_at",
        )
        self.assertNotIn("name", account_select)
        person_select = urllib.parse.parse_qs(
            urllib.parse.urlsplit(
                next(call[1] for call in transport.calls if "/persons?" in call[1])
            ).query
        )["select"][0]
        self.assertIn(
            "locale_context:attributes->localeContext",
            person_select,
        )
        self.assertNotIn(",attributes,", person_select)
        self.assertNotIn("display_name", serialized)
        for private_value in (
            ACCOUNT_A,
            ACCOUNT_B,
            PERSON_A,
            PERSON_B,
            SECRET,
            "Must not leave transport",
            "Never Export Me",
            "never@example.test",
            "+886900000000",
            "private",
        ):
            self.assertNotIn(private_value, serialized)
        self.assertEqual(payload["records"][0]["account"]["ref"], "account-0001")
        self.assertEqual(payload["records"][0]["person"]["ref"], "person-0001")

        audit = audit_export(payload, source_commit=EXACT_COMMIT)
        self.assertEqual(audit["result"], "pass")

    def test_deleted_rows_are_excluded_even_if_transport_ignores_filter(self) -> None:
        payload = build_export(config(page_size=100), transport=FakeTransport())
        serialized = json.dumps(payload)
        self.assertEqual(len(payload["records"]), 2)
        self.assertNotIn(ACCOUNT_DELETED, serialized)
        self.assertNotIn(PERSON_DELETED, serialized)

    def test_orphan_person_fails_existing_audit_gate_without_raw_id(self) -> None:
        orphan_account = "44444444-4444-4444-8444-444444444444"
        rows = persons()[:1]
        rows[0] = {**rows[0], "account_id": orphan_account}
        payload = build_export(
            config(page_size=100),
            transport=FakeTransport(account_rows=accounts()[:1], person_rows=rows),
        )
        serialized = json.dumps(payload)
        self.assertNotIn(orphan_account, serialized)
        self.assertEqual(payload["records"][0]["account"]["ref"], "account-orphan-0001")
        self.assertEqual(
            audit_export(payload, source_commit=EXACT_COMMIT)["result"],
            "fail",
        )

    def test_account_without_person_fails_existing_audit_gate(self) -> None:
        payload = build_export(
            config(page_size=100),
            transport=FakeTransport(
                account_rows=accounts()[:2],
                person_rows=persons()[:1],
            ),
        )
        self.assertEqual(len(payload["records"]), 2)
        missing = payload["records"][1]
        self.assertEqual(missing["person"]["ref"], "person-missing-0001")
        self.assertEqual(
            audit_export(payload, source_commit=EXACT_COMMIT)["result"],
            "fail",
        )

    def test_invalid_sensitive_values_are_blank_instead_of_copied(self) -> None:
        unsafe_accounts = accounts()[:1]
        unsafe_accounts[0] = {
            **unsafe_accounts[0],
            "locale": "email@example.test",
            "preferred_languages": ["zh-TW", "email@example.test"],
        }
        unsafe_persons = persons()[:1]
        unsafe_persons[0] = {
            **unsafe_persons[0],
            "timezone": "private@example.test",
            "locale_context": policy(dataRegion="private@example.test"),
        }
        payload = build_export(
            config(page_size=100),
            transport=FakeTransport(unsafe_accounts, unsafe_persons),
        )
        serialized = json.dumps(payload)
        self.assertNotIn("email@example.test", serialized)
        self.assertNotIn("private@example.test", serialized)
        self.assertIsNone(payload["records"][0]["account"]["locale"])
        self.assertEqual(payload["records"][0]["account"]["preferred_languages"], [])
        self.assertEqual(
            audit_export(payload, source_commit=EXACT_COMMIT)["result"],
            "fail",
        )

    def test_config_rejects_non_production_and_mismatched_targets(self) -> None:
        with self.assertRaisesRegex(ValueError, "not an approved"):
            validate_config(
                config(
                    supabase_url="https://abcdefghijklmnopqrst.supabase.co",
                    expected_project_ref="abcdefghijklmnopqrst",
                )
            )
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_config(
                config(
                    supabase_url="https://uhmpmystjjdqqxlpsthc.supabase.co",
                )
            )

    def test_config_requires_dedicated_credential_without_echoing_secret(self) -> None:
        self.assertNotIn(SECRET, repr(config()))
        with self.assertRaisesRegex(ValueError, "missing dedicated"):
            validate_config(config(service_role_key=""))
        try:
            validate_config(config(supabase_url=f"https://{SECRET}.example.test"))
        except ValueError as exc:
            self.assertNotIn(SECRET, str(exc))
        else:
            self.fail("unsafe target must be rejected")

    def test_transport_rejects_any_write_method_before_network(self) -> None:
        with self.assertRaisesRegex(ExportRefused, "GET requests only"):
            request_json("POST", "https://example.test", {}, 1.0)

    def test_malformed_or_duplicate_source_ids_are_refused(self) -> None:
        invalid = accounts()[:1]
        invalid[0] = {**invalid[0], "id": "not-a-uuid"}
        with self.assertRaisesRegex(ExportRefused, "invalid identifier"):
            build_export(
                config(page_size=100),
                transport=FakeTransport(account_rows=invalid, person_rows=[]),
            )
        duplicate = accounts()[:1] * 2
        with self.assertRaisesRegex(ExportRefused, "duplicate identifier"):
            build_export(
                config(page_size=100),
                transport=FakeTransport(account_rows=duplicate, person_rows=[]),
            )

    def test_missing_deletion_marker_is_refused(self) -> None:
        missing_marker = accounts()[:1]
        del missing_marker[0]["deleted_at"]
        with self.assertRaisesRegex(ExportRefused, "omitted the deletion marker"):
            build_export(
                config(page_size=100),
                transport=FakeTransport(
                    account_rows=missing_marker,
                    person_rows=[],
                ),
            )


if __name__ == "__main__":
    unittest.main()
