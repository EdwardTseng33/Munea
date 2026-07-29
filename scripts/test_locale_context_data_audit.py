#!/usr/bin/env python3
"""Tests for the zero-write, identifier-free LocaleContext data audit."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from locale_context_data_audit import AUDIT_SCHEMA, audit_export


EXACT_COMMIT = "a" * 40
AUDITED_AT = "2026-07-28T12:00:00Z"


def record(
    ref: str,
    *,
    ui_locale: str,
    conversation_locale: str,
    preferred_languages: list[str],
    country: str,
    timezone: str,
    units: str,
    currency: str,
    safety_region: str,
    legal_region: str,
    data_region: str,
) -> dict:
    return {
        "active": True,
        "account": {
            "ref": f"account-{ref}",
            "locale": ui_locale,
            "preferred_languages": preferred_languages,
        },
        "person": {
            "ref": f"person-{ref}",
            "accountRef": f"account-{ref}",
            "locale": conversation_locale,
            "timezone": timezone,
            "region_code": country,
            "attributes": {
                "localeContext": {
                    "version": 1,
                    "units": units,
                    "currency": currency,
                    "safetyRegion": safety_region,
                    "legalRegion": legal_region,
                    "dataRegion": data_region,
                }
            },
        },
    }


def complete_export() -> dict:
    return {
        "schema": "munea.locale-context-data-export.v1",
        "sourceCommit": EXACT_COMMIT,
        "generatedAt": "2026-07-28T11:00:00Z",
        "environment": "production",
        "captureMode": "read-only-redacted-export",
        "writesPerformed": False,
        "records": [
            record(
                "tw",
                ui_locale="zh-TW",
                conversation_locale="zh-TW",
                preferred_languages=["zh-TW", "en"],
                country="TW",
                timezone="Asia/Taipei",
                units="metric",
                currency="TWD",
                safety_region="TW",
                legal_region="TW",
                data_region="tw-primary",
            ),
            record(
                "us",
                ui_locale="en-US",
                conversation_locale="en",
                preferred_languages=["en", "es-MX"],
                country="US",
                timezone="America/Los_Angeles",
                units="us",
                currency="USD",
                safety_region="US",
                legal_region="US",
                data_region="us-primary",
            ),
            record(
                "jp",
                ui_locale="ja-JP",
                conversation_locale="ja",
                preferred_languages=["ja", "en"],
                country="JP",
                timezone="Asia/Tokyo",
                units="metric",
                currency="JPY",
                safety_region="JP",
                legal_region="JP",
                data_region="jp-primary",
            ),
            record(
                "mx",
                ui_locale="es-MX",
                conversation_locale="es",
                preferred_languages=["es-MX", "en"],
                country="MX",
                timezone="America/Mexico_City",
                units="metric",
                currency="MXN",
                safety_region="MX",
                legal_region="MX",
                data_region="mx-primary",
            ),
        ],
    }


class LocaleContextDataAuditTests(unittest.TestCase):
    def audit(self, payload: dict) -> dict:
        return audit_export(
            payload,
            source_commit=EXACT_COMMIT,
            audited_at=AUDITED_AT,
        )

    def test_complete_four_market_export_passes_without_identifiers(self) -> None:
        report = self.audit(complete_export())
        self.assertEqual(report["schema"], AUDIT_SCHEMA)
        self.assertEqual(report["result"], "pass")
        self.assertEqual(report["summary"]["activeRecordCount"], 4)
        self.assertEqual(report["summary"]["explicitCoverage"], 1.0)
        self.assertEqual(report["summary"]["accountIsolationFailures"], 0)
        self.assertFalse(report["outputPrivacy"]["containsDirectIdentifiers"])
        serialized = str(report)
        self.assertNotIn("account-tw", serialized)
        self.assertNotIn("person-tw", serialized)

    def test_language_and_country_are_independent(self) -> None:
        payload = complete_export()
        mixed = payload["records"][1]
        mixed["account"]["locale"] = "zh-TW"
        mixed["person"]["locale"] = "es"
        mixed["person"]["region_code"] = "JP"
        mixed["person"]["attributes"]["localeContext"].update(
            {
                "currency": "EUR",
                "safetyRegion": "ES",
                "legalRegion": "MX",
                "dataRegion": "eu-primary",
            }
        )
        report = self.audit(payload)
        self.assertEqual(report["result"], "pass")

    def test_missing_policy_blocks_release(self) -> None:
        payload = complete_export()
        del payload["records"][2]["person"]["attributes"]["localeContext"]
        report = self.audit(payload)
        self.assertEqual(report["result"], "fail")
        self.assertEqual(report["summary"]["invalidActiveRecords"], 1)
        self.assertIn("locale_policy_missing", report["records"][2]["issues"])

    def test_cross_account_person_link_blocks_release(self) -> None:
        payload = complete_export()
        payload["records"][3]["person"]["accountRef"] = "account-tw"
        report = self.audit(payload)
        self.assertEqual(report["result"], "fail")
        self.assertEqual(report["summary"]["accountIsolationFailures"], 1)
        self.assertIn("account_isolation_mismatch", report["records"][3]["issues"])

    def test_same_person_reference_cannot_appear_under_two_accounts(self) -> None:
        payload = complete_export()
        duplicate = copy.deepcopy(payload["records"][0])
        duplicate["account"]["ref"] = "account-other"
        duplicate["person"]["accountRef"] = "account-other"
        payload["records"].append(duplicate)
        report = self.audit(payload)
        self.assertEqual(report["result"], "fail")
        self.assertIn(
            "duplicate_person_ref_cross_account",
            report["records"][4]["issues"],
        )

    def test_duplicate_person_reference_cannot_inflate_coverage(self) -> None:
        payload = complete_export()
        payload["records"].append(copy.deepcopy(payload["records"][0]))
        report = self.audit(payload)
        self.assertEqual(report["result"], "fail")
        self.assertIn("duplicate_person_ref", report["records"][4]["issues"])

    def test_direct_identifiers_are_rejected_by_allowlist(self) -> None:
        payload = complete_export()
        payload["records"][0]["account"]["email"] = "not-allowed@example.test"
        report = self.audit(payload)
        self.assertEqual(report["result"], "fail")
        self.assertIn(
            "unexpected_field:account.email",
            report["records"][0]["issues"],
        )
        self.assertNotIn("not-allowed@example.test", str(report))

    def test_invalid_locale_and_policy_values_fail_closed(self) -> None:
        payload = complete_export()
        payload["records"][0]["account"]["locale"] = "fr-FR"
        payload["records"][0]["person"]["attributes"]["localeContext"]["currency"] = "12"
        report = self.audit(payload)
        self.assertEqual(report["result"], "fail")
        self.assertIn("ui_locale_invalid", report["records"][0]["issues"])
        self.assertIn("currency_invalid", report["records"][0]["issues"])

    def test_export_must_confirm_read_only_capture(self) -> None:
        payload = complete_export()
        payload["writesPerformed"] = True
        report = self.audit(payload)
        self.assertEqual(report["result"], "fail")
        self.assertIn("export_must_confirm_zero_writes", report["exportIssues"])

    def test_export_commit_must_match_audit_commit(self) -> None:
        payload = complete_export()
        payload["sourceCommit"] = "b" * 40
        report = self.audit(payload)
        self.assertEqual(report["result"], "fail")
        self.assertIn("export_source_commit_mismatch", report["exportIssues"])

    def test_commit_identity_is_normalized_to_lowercase(self) -> None:
        payload = complete_export()
        payload["sourceCommit"] = EXACT_COMMIT.upper()
        report = audit_export(
            payload,
            source_commit=EXACT_COMMIT.upper(),
            audited_at=AUDITED_AT,
        )
        self.assertEqual(report["result"], "pass")
        self.assertEqual(report["sourceCommit"], EXACT_COMMIT)
        self.assertEqual(report["sourceExport"]["sourceCommit"], EXACT_COMMIT)


if __name__ == "__main__":
    unittest.main()
