# -*- coding: utf-8 -*-
"""Durable Call Control contracts without requiring live Supabase or a GPU."""
import importlib
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "deploy" / "gateway"
sys.path.insert(0, str(GATEWAY))

from call_control_store import (  # noqa: E402
    AuthenticatedUser,
    CallControlError,
    SupabaseCallStore,
    issue_call_token,
    verify_call_token,
)


def test_short_lived_call_token():
    secret = "unit-test-secret-with-enough-entropy"
    token = issue_call_token({
        "call_id": "call-1", "worker_id": "worker-a", "slot_id": 2, "lease_version": 7,
    }, secret, ttl_seconds=60)
    payload = verify_call_token(token, secret, worker_id="worker-a", slot_id=2)
    assert payload["call_id"] == "call-1" and payload["lease_version"] == 7
    try:
        verify_call_token(token, secret, worker_id="worker-b")
        raise AssertionError("worker mismatch must fail")
    except CallControlError:
        pass
    try:
        verify_call_token(token + "broken", secret)
        raise AssertionError("tampered token must fail")
    except CallControlError:
        pass


def test_supabase_service_key_headers():
    modern = SupabaseCallStore("https://example.supabase.co", "sb_secret_modern")
    modern_headers = modern._service_headers()
    assert modern_headers["apikey"] == "sb_secret_modern"
    assert "Authorization" not in modern_headers

    legacy = SupabaseCallStore("https://example.supabase.co", "legacy.jwt.service-role")
    legacy_headers = legacy._service_headers()
    assert legacy_headers["Authorization"] == "Bearer legacy.jwt.service-role"


class FakeDurable:
    def __init__(self):
        self.requests = []
        self.heartbeats = []
        self.releases = []
        self.ready_events = []

    def authenticate(self, bearer):
        assert bearer == "valid-user-token"
        return AuthenticatedUser("00000000-0000-0000-0000-000000000001")

    def request_call(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs["idempotency_key"] == "queued":
            return {"status": "queued", "call_id": "q1", "queue": {"position": 1, "depth": 1, "eta_s": 120}}
        return {
            "status": "connect", "call_id": "11111111-1111-1111-1111-111111111111",
            "lease_version": 1, "slot_id": 2, "state": "reserved",
            "worker": {"worker_id": "glows-primary", "url": "https://avatar.example"},
            "voice": {"shard_id": "voice-1", "url": "wss://voice.example"},
        }

    def heartbeat(self, **kwargs):
        self.heartbeats.append(kwargs)
        return {"ok": True, "state": "active", "should_end": False}

    def release(self, **kwargs):
        self.releases.append(kwargs)
        return {"ok": True, "state": "ended", "idempotent": False}

    def ready(self, **kwargs):
        self.ready_events.append(kwargs)
        return {"ok": True, "state": "connecting"}

    def snapshot(self):
        return {"active_calls": 1, "queue_depth": 0}

    def reap(self):
        return 2

    def upsert_worker(self, row):
        return row

    def upsert_voice_shard(self, row):
        return row


def test_http_v2_contract():
    os.environ.setdefault("MUNEA_CALL_TOKEN_SECRET", "unit-test-call-token-secret")
    os.environ.setdefault("MUNEA_GATEWAY_ADMIN_KEY", "unit-admin")
    import gateway_server as gs  # noqa: E402
    from fastapi.testclient import TestClient

    gs.DURABLE = FakeDurable()
    gs._CALL_TOKEN_SECRET = "unit-test-call-token-secret"
    gs._ADMIN_GATE = "unit-admin"
    client = TestClient(gs.app)
    auth = {"Authorization": "Bearer valid-user-token"}

    response = client.post("/v1/calls", headers=auth, json={
        "character_id": "a05", "idempotency_key": "same-request",
    })
    body = response.json()
    assert response.status_code == 200 and body["status"] == "connect"
    assert body["worker"]["url"] == "https://avatar.example"
    assert body["voice"]["url"] == "wss://voice.example"
    token_payload = verify_call_token(
        body["call_token"], gs._CALL_TOKEN_SECRET, worker_id="glows-primary", slot_id=2
    )
    assert token_payload["call_id"] == body["call_id"]

    queued = client.post("/v1/calls", headers=auth, json={
        "character_id": "a05", "idempotency_key": "queued",
    }).json()
    assert queued["status"] == "queued" and queued["queue"]["position"] == 1

    call_id = body["call_id"]
    heartbeat = client.post(f"/v1/calls/{call_id}/heartbeat", headers=auth, json={
        "lease_version": 1, "event_id": "app-heartbeat-1",
    }).json()
    assert heartbeat["ok"] is True and gs.DURABLE.heartbeats[-1]["user_id"]

    released = client.post(f"/v1/calls/{call_id}/release", headers=auth, json={
        "lease_version": 1, "event_id": "app-release-1", "reason": "user_hangup",
    }).json()
    assert released["state"] == "ended" and gs.DURABLE.releases[-1]["user_id"]

    ready = client.post("/v1/internal/calls/ready", headers={"Authorization": "Bearer unit-admin"}, json={
        "call_id": call_id, "lease_version": 1, "event_id": "avatar-ready-1", "component": "avatar",
    }).json()
    assert ready["ok"] is True
    denied = client.post("/v1/internal/reap", headers={"Authorization": "Bearer wrong"})
    assert denied.status_code == 403
    assert client.get("/metrics").status_code == 403
    metrics = client.get("/metrics", headers={"Authorization": "Bearer unit-admin"})
    assert metrics.status_code == 200 and "munea_calls_active 1" in metrics.text


def test_sql_contract():
    sql = (ROOT / "supabase" / "sql" / "010_realtime_call_control.sql").read_text(encoding="utf-8")
    required = [
        "call_leases", "call_queue", "gpu_workers", "voice_shards", "provider_operations",
        "pg_advisory_xact_lock", "for update skip locked", "munea_call_request",
        "munea_call_ready", "munea_call_heartbeat", "munea_call_release",
        "call_credit_holds", "lease_version", "idempotency_key",
    ]
    missing = [item for item in required if item.lower() not in sql.lower()]
    assert not missing, "SQL call-control contract missing: " + ", ".join(missing)
    server = (GATEWAY / "gateway_server.py").read_text(encoding="utf-8")
    assert 'allow_origins=["*"]' not in server
    assert "MUNEA_GATEWAY_REQUIRE_DURABLE" in server
    assert "def metrics(authorization:" in server
    assert "_admin_bearer(authorization, x_munea_admin_token)" in server


def main():
    test_short_lived_call_token()
    test_supabase_service_key_headers()
    test_http_v2_contract()
    test_sql_contract()
    print("Durable Call Control contract: ALL PASS")


if __name__ == "__main__":
    main()
