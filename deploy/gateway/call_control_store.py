# -*- coding: utf-8 -*-
"""Durable Supabase-backed control-plane client and short-lived call tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class CallControlError(RuntimeError):
    pass


class CallControlAuthError(CallControlError):
    """A caller credential was rejected; safe to report as HTTP 401."""

    def __init__(self, reason: str = "invalid_token"):
        self.reason = reason
        super().__init__(reason)


class SupabaseHTTPError(CallControlError):
    """Supabase returned an HTTP error without leaking its response to clients."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = int(status_code)
        self.detail = detail
        super().__init__(f"Supabase HTTP {self.status_code}: {detail}")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_call_token(payload: dict[str, Any], secret: str, ttl_seconds: int = 90) -> str:
    if not secret:
        raise CallControlError("MUNEA_CALL_TOKEN_SECRET is required")
    body = dict(payload)
    now = int(time.time())
    body.update({"iat": now, "exp": now + max(30, min(ttl_seconds, 300))})
    encoded = _b64url(json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64url(hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
    return encoded + "." + signature


def verify_call_token(token: str, secret: str, *, worker_id: str = "", slot_id: int | None = None) -> dict[str, Any]:
    try:
        encoded, supplied = token.split(".", 1)
        expected = _b64url(hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            raise CallControlError("invalid call token signature")
        payload = json.loads(_b64url_decode(encoded))
        if int(payload.get("exp") or 0) < int(time.time()):
            raise CallControlError("call token expired")
        if worker_id and payload.get("worker_id") != worker_id:
            raise CallControlError("call token worker mismatch")
        if slot_id is not None and int(payload.get("slot_id") or 0) != int(slot_id):
            raise CallControlError("call token slot mismatch")
        return payload
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CallControlError("malformed call token") from exc


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str = ""


class SupabaseCallStore:
    def __init__(self, url: str, service_role_key: str, anon_key: str = ""):
        self.url = url.rstrip("/")
        self.service_role_key = service_role_key.strip()
        self.anon_key = (anon_key or service_role_key).strip()
        if not self.url or not self.service_role_key:
            raise CallControlError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    @classmethod
    def from_env(cls) -> "SupabaseCallStore | None":
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not (url and key):
            return None
        anon = os.environ.get("SUPABASE_ANON_KEY", "").strip()
        return cls(url, key, anon)

    def _json(self, method: str, url: str, *, body: Any = None, headers: dict[str, str] | None = None,
              timeout: int = 15) -> Any:
        request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        request_headers.update(headers or {})
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise SupabaseHTTPError(exc.code, detail) from exc
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise CallControlError(f"Supabase request failed: {exc}") from exc

    def authenticate(self, bearer: str) -> AuthenticatedUser:
        if not bearer:
            raise CallControlAuthError("bearer_token_required")
        try:
            data = self._json("GET", self.url + "/auth/v1/user", headers={
                "apikey": self.anon_key,
                "Authorization": "Bearer " + bearer,
            })
        except SupabaseHTTPError as exc:
            if exc.status_code in (401, 403):
                detail = exc.detail.lower()
                reason = "token_expired" if "expired" in detail else "invalid_token"
                raise CallControlAuthError(reason) from exc
            raise
        user_id = str((data or {}).get("id") or "")
        if not user_id:
            raise CallControlAuthError("invalid_token")
        return AuthenticatedUser(user_id=user_id, email=str((data or {}).get("email") or ""))

    def _service_headers(self, prefer: str = "") -> dict[str, str]:
        headers = {"apikey": self.service_role_key}
        # Supabase's new sb_secret_* keys are API keys, not JWTs. Sending one
        # as a bearer token makes PostgREST reject an otherwise valid request.
        if not self.service_role_key.startswith("sb_secret_"):
            headers["Authorization"] = "Bearer " + self.service_role_key
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def rpc(self, name: str, body: dict[str, Any] | None = None) -> Any:
        return self._json(
            "POST", self.url + "/rest/v1/rpc/" + urllib.parse.quote(name),
            body=body or {}, headers=self._service_headers(),
        )

    def request_call(self, *, user_id: str, person_id: str | None, character_id: str,
                     idempotency_key: str, queue_max: int = 30) -> dict[str, Any]:
        return self.rpc("munea_call_request", {
            "p_user_id": user_id,
            "p_person_id": person_id or None,
            "p_character_id": character_id,
            "p_idempotency_key": idempotency_key,
            "p_queue_max": queue_max,
        })

    def ready(self, *, call_id: str, lease_version: int, component: str, event_id: str) -> dict[str, Any]:
        return self.rpc("munea_call_ready", {
            "p_call_id": call_id, "p_lease_version": lease_version,
            "p_component": component, "p_event_id": event_id,
        })

    def cancel(self, *, call_id: str, user_id: str) -> dict[str, Any]:
        return self.rpc("munea_call_cancel", {
            "p_call_id": call_id, "p_user_id": user_id,
        })

    def claim(self, *, call_id: str, lease_version: int, user_id: str) -> dict[str, Any]:
        return self.rpc("munea_call_claim", {
            "p_call_id": call_id, "p_lease_version": lease_version, "p_user_id": user_id,
        })

    def heartbeat(self, *, call_id: str, lease_version: int, component: str, event_id: str,
                  user_id: str | None = None) -> dict[str, Any]:
        return self.rpc("munea_call_heartbeat", {
            "p_call_id": call_id, "p_lease_version": lease_version,
            "p_component": component, "p_event_id": event_id, "p_user_id": user_id,
        })

    def release(self, *, call_id: str, lease_version: int, event_id: str, reason: str,
                user_id: str | None = None) -> dict[str, Any]:
        return self.rpc("munea_call_release", {
            "p_call_id": call_id, "p_lease_version": lease_version,
            "p_event_id": event_id, "p_reason": reason, "p_user_id": user_id,
        })

    def reap(self) -> int:
        result = self.rpc("munea_call_reap_expired")
        return int(result or 0)

    def snapshot(self) -> dict[str, Any]:
        return self.rpc("munea_call_snapshot")

    def upsert_worker(self, row: dict[str, Any]) -> dict[str, Any]:
        url = self.url + "/rest/v1/gpu_workers?on_conflict=worker_id"
        result = self._json("POST", url, body=row, headers=self._service_headers(
            "resolution=merge-duplicates,return=representation"
        ))
        return (result or [{}])[0]

    def update_worker(self, worker_id: str, values: dict[str, Any]) -> dict[str, Any]:
        url = self.url + "/rest/v1/gpu_workers?worker_id=eq." + urllib.parse.quote(worker_id)
        result = self._json("PATCH", url, body=values, headers=self._service_headers("return=representation"))
        return (result or [{}])[0]

    def upsert_voice_shard(self, row: dict[str, Any]) -> dict[str, Any]:
        url = self.url + "/rest/v1/voice_shards?on_conflict=shard_id"
        result = self._json("POST", url, body=row, headers=self._service_headers(
            "resolution=merge-duplicates,return=representation"
        ))
        return (result or [{}])[0]
