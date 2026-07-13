# -*- coding: utf-8 -*-
"""Small, dependency-free client used by the realtime Voice service."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any


class CallControlError(RuntimeError):
    pass


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_call_token(token: str, secret: str, *, voice_shard_id: str = "") -> dict[str, Any]:
    if not secret:
        raise CallControlError("call token signer is not configured")
    try:
        encoded, supplied = token.split(".", 1)
        expected = _b64url(hmac.new(secret.encode(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            raise CallControlError("invalid call token signature")
        payload = json.loads(_b64url_decode(encoded))
        if int(payload.get("exp") or 0) < int(time.time()):
            raise CallControlError("call token expired")
        if voice_shard_id and payload.get("voice_shard_id") != voice_shard_id:
            raise CallControlError("call token voice shard mismatch")
        if not payload.get("call_id") or not payload.get("lease_version"):
            raise CallControlError("call token is missing lease identity")
        return payload
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CallControlError("malformed call token") from exc


def post_internal(base_url: str, admin_key: str, path: str, body: dict[str, Any], timeout: int = 8) -> dict[str, Any]:
    if not base_url or not admin_key:
        raise CallControlError("call control callback is not configured")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + admin_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise CallControlError(f"call control HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise CallControlError(f"call control callback failed: {exc}") from exc
