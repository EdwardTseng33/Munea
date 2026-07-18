#!/usr/bin/env python3
"""Deterministic tests for operations-console provenance and freshness metadata."""

import os
from pathlib import Path
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "admin-data-quality-test-key")
os.environ.setdefault("MUNEA_SKIP_ENV_LOCAL", "1")

from admin_data_quality import (
    SCHEMA,
    admin_contract_response,
    build_admin_data_meta,
    latest_record_timestamp,
    record_admin_data_source,
)


class FakeProductEventsBackend:
    def __init__(self, events=None, error=None):
        self.events = events
        self.error = error

    def enabled(self):
        return True

    def status(self):
        return {"provider": "supabase", "enabled": True}

    def load_app_profile_store(self):
        return {
            "account": {"id": "acct_1", "name": "Test", "locale": "zh-TW"},
            "familyGroup": {"id": "family_1", "name": "Test", "members": []},
            "primaryCareRecipientId": "person_1",
            "companionProfiles": {},
            "updatedAt": "2026-07-18T00:00:00Z",
        }

    def load_product_events(self, since_iso=None, limit=500):
        if self.error:
            raise self.error
        return list(self.events or [])[:limit]


def test_latest_record_timestamp_ignores_invalid_values():
    assert latest_record_timestamp([
        {"eventTime": "invalid"},
        {"eventTime": "2026-07-18T01:00:00Z"},
        {"createdAt": "2026-07-18T03:00:00+00:00"},
    ]) == "2026-07-18T03:00:00Z"


def test_missing_source_metadata_fails_closed():
    meta = build_admin_data_meta("munea.admin.test.v1", [])
    assert meta["schema"] == SCHEMA
    assert meta["status"] == "unverified"
    assert meta["degraded"] is True
    assert meta["degradationReasons"] == ["source_metadata_missing"]
    assert meta["freshness"] == {"status": "unknown", "reason": "source_metadata_missing"}


def test_fallback_source_is_explicitly_degraded():
    meta = build_admin_data_meta("munea.admin.test.v1", [{
        "dataset": "product_events",
        "provider": "json",
        "authority": "fallback",
        "recordCount": 4,
        "dataAsOf": "2026-07-18T02:00:00Z",
        "freshness": {"status": "unknown", "reason": "source_watermark_unavailable"},
        "degraded": True,
        "degradationReason": "primary_unavailable",
    }])
    assert meta["status"] == "degraded"
    assert meta["dataAsOf"] == "2026-07-18T02:00:00Z"
    assert meta["degradationReasons"] == ["primary_unavailable"]


def test_request_scope_deduplicates_repeated_reads():
    def produce():
        for count, data_as_of in ((2, "2026-07-18T01:00:00Z"), (5, "2026-07-18T04:00:00Z")):
            record_admin_data_source(
                "product_events",
                "supabase",
                record_count=count,
                data_as_of=data_as_of,
            )
        return {"ok": True, "value": 5}

    payload = admin_contract_response("munea.admin.usage.v1", produce)
    assert payload["ok"] is True
    assert payload["meta"]["metricVersion"] == "munea.admin.usage.v1"
    assert payload["meta"]["status"] == "unverified"
    assert payload["meta"]["degraded"] is False
    assert len(payload["meta"]["sources"]) == 1
    assert payload["meta"]["sources"][0]["recordCount"] == 5
    assert payload["meta"]["dataAsOf"] == "2026-07-18T04:00:00Z"


def test_server_primary_and_fallback_reads_are_distinguishable():
    import server

    event = {
        "id": "evt_1",
        "accountId": "acct_1",
        "personId": "person_1",
        "eventName": "voice_session_completed",
        "eventTime": "2026-07-18T05:00:00Z",
        "properties": {"durationMs": 120000, "turnCount": 4},
    }
    primary = FakeProductEventsBackend(events=[event])
    with mock.patch.object(server, "data_backend", return_value=primary):
        payload = admin_contract_response(
            "munea.admin.north-star.v1",
            lambda: server.north_star_summary({"days": 7}),
        )
    source = payload["meta"]["sources"][0]
    assert source["provider"] == "supabase"
    assert source["authority"] == "primary"
    assert source["recordCount"] == 1
    assert payload["meta"]["degraded"] is False

    fallback_store = {"schemaVersion": 1, "events": [event], "updatedAt": "2026-07-18T05:01:00Z"}
    unavailable = FakeProductEventsBackend(error=RuntimeError("database unavailable"))
    with mock.patch.object(server, "data_backend", return_value=unavailable), \
            mock.patch.object(server, "read_json_file", return_value=fallback_store):
        payload = admin_contract_response(
            "munea.admin.north-star.v1",
            lambda: server.north_star_summary({"days": 7}),
        )
    source = payload["meta"]["sources"][0]
    assert source["provider"] == "json"
    assert source["authority"] == "fallback"
    assert payload["meta"]["status"] == "degraded"
    assert payload["meta"]["degradationReasons"] == ["primary_unavailable"]


def test_admin_read_handlers_are_wrapped_by_the_contract():
    source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
    for metric_version in (
        "munea.admin.accounts.v1",
        "munea.admin.north-star.v1",
        "munea.admin.usage.v1",
        "munea.admin.credits.v1",
        "munea.admin.subscription-metrics.v1",
        "munea.admin.conversation-summaries.v1",
        "munea.admin.privacy-requests.v1",
        "munea.admin.feedback.v1",
        "munea.admin.safety-events.v1",
        "munea.admin.audit-events.v1",
        "munea.admin.voice-diagnostics.v1",
    ):
        assert f'admin_contract_response("{metric_version}"' in source


def main():
    tests = [
        test_latest_record_timestamp_ignores_invalid_values,
        test_missing_source_metadata_fails_closed,
        test_fallback_source_is_explicitly_degraded,
        test_request_scope_deduplicates_repeated_reads,
        test_server_primary_and_fallback_reads_are_distinguishable,
        test_admin_read_handlers_are_wrapped_by_the_contract,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("Admin data quality contract: ALL PASS")


if __name__ == "__main__":
    main()
