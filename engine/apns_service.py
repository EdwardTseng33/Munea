"""APNs HTTP/2 sender and durable outbox drain for Munea notifications."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass


APNS_PRODUCTION_HOST = "https://api.push.apple.com"
APNS_SANDBOX_HOST = "https://api.sandbox.push.apple.com"
INVALID_TOKEN_REASONS = {"BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"}
RETRYABLE_STATUS_CODES = {429, 500, 503}


def _b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class APNSConfig:
    key_id: str
    team_id: str
    private_key: str

    @classmethod
    def from_env(cls, env=None):
        env = env or os.environ
        private_key = (env.get("MUNEA_APNS_PRIVATE_KEY") or "").replace("\\n", "\n").strip()
        private_key_path = (env.get("MUNEA_APNS_PRIVATE_KEY_PATH") or "").strip()
        if not private_key and private_key_path:
            with open(private_key_path, encoding="utf-8") as source:
                private_key = source.read().strip()
        return cls(
            key_id=(env.get("MUNEA_APNS_KEY_ID") or "").strip(),
            team_id=(env.get("MUNEA_APNS_TEAM_ID") or "").strip(),
            private_key=private_key,
        )

    def configured(self):
        return bool(self.key_id and self.team_id and self.private_key)

    def status(self):
        missing = []
        if not self.key_id:
            missing.append("MUNEA_APNS_KEY_ID")
        if not self.team_id:
            missing.append("MUNEA_APNS_TEAM_ID")
        if not self.private_key:
            missing.append("MUNEA_APNS_PRIVATE_KEY or MUNEA_APNS_PRIVATE_KEY_PATH")
        return {"enabled": not missing, "missing": missing}


class APNSTokenProvider:
    def __init__(self, config, clock=time.time):
        self.config = config
        self.clock = clock
        self._lock = threading.Lock()
        self._token = None
        self._issued_at = 0

    def token(self):
        now = int(self.clock())
        with self._lock:
            if self._token and now - self._issued_at < 45 * 60:
                return self._token
            self._token = self._sign(now)
            self._issued_at = now
            return self._token

    def _sign(self, issued_at):
        if not self.config.configured():
            raise RuntimeError("apns_not_configured")
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        except ImportError as error:
            raise RuntimeError("apns_crypto_dependency_missing") from error
        header = _b64url(_json_bytes({"alg": "ES256", "kid": self.config.key_id}))
        claims = _b64url(_json_bytes({"iss": self.config.team_id, "iat": issued_at}))
        signing_input = f"{header}.{claims}".encode("ascii")
        key = serialization.load_pem_private_key(self.config.private_key.encode("utf-8"), password=None)
        der_signature = key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_signature)
        raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return f"{header}.{claims}.{_b64url(raw_signature)}"


def build_payload(delivery):
    delivery = delivery or {}
    show_sensitive = bool(delivery.get("show_sensitive_content") or delivery.get("showSensitiveContent"))
    sensitivity = delivery.get("sensitivity") or "private"
    if sensitivity == "public" or show_sensitive:
        title = delivery.get("title") or "沐寧提醒"
        body = delivery.get("body") or "你有一則新提醒。"
    else:
        title = delivery.get("public_title") or delivery.get("publicTitle") or "沐寧提醒"
        body = delivery.get("public_body") or delivery.get("publicBody") or "你的健康提醒到了，解鎖後查看。"
    event_type = delivery.get("event_type") or delivery.get("eventType") or "notification"
    event_id = str(delivery.get("event_id") or delivery.get("eventId") or "")
    payload = {
        "aps": {
            "alert": {"title": str(title)[:160], "body": str(body)[:500]},
            "sound": "default",
            "thread-id": str(event_type)[:64],
        },
        "eventId": event_id,
        "eventType": event_type,
        "resourceId": delivery.get("resource_id") or delivery.get("resourceId"),
        "deepLink": delivery.get("deep_link") or delivery.get("deepLink") or "munea://notifications",
    }
    raw = _json_bytes(payload)
    if len(raw) > 4096:
        payload["aps"]["alert"]["body"] = payload["aps"]["alert"]["body"][:180]
        raw = _json_bytes(payload)
    if len(raw) > 4096:
        raise ValueError("apns_payload_too_large")
    return payload


def classify_response(status_code, response_body=None, headers=None):
    response_body = response_body or {}
    headers = headers or {}
    reason = response_body.get("reason") if isinstance(response_body, dict) else None
    apns_id = headers.get("apns-id") or headers.get("Apns-Id")
    if status_code == 200:
        return {"status": "accepted", "apnsId": apns_id}
    if reason in INVALID_TOKEN_REASONS or status_code == 410:
        return {"status": "invalid_token", "apnsId": apns_id, "errorCode": reason or "Unregistered"}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    try:
        retry_after = int(retry_after) if retry_after else None
    except (TypeError, ValueError):
        retry_after = None
    if status_code in RETRYABLE_STATUS_CODES:
        return {
            "status": "failed", "apnsId": apns_id,
            "errorCode": reason or f"HTTP_{status_code}",
            "retryAfterSeconds": retry_after or (300 if status_code == 429 else 60),
        }
    return {
        "status": "suppressed", "apnsId": apns_id,
        "errorCode": reason or f"HTTP_{status_code}",
    }


class APNSSender:
    def __init__(self, config=None, client=None):
        self.config = config or APNSConfig.from_env()
        self.tokens = APNSTokenProvider(self.config)
        self.client = client

    def send(self, delivery):
        if not self.config.configured():
            return {"status": "failed", "errorCode": "apns_not_configured", "retryAfterSeconds": 3600}
        try:
            import httpx
        except ImportError as error:
            raise RuntimeError("apns_http2_dependency_missing") from error
        environment = delivery.get("environment") or "production"
        host = APNS_SANDBOX_HOST if environment == "sandbox" else APNS_PRODUCTION_HOST
        token = str(delivery.get("token") or "").strip()
        bundle_id = str(delivery.get("bundle_id") or delivery.get("bundleId") or "").strip()
        if not token or not bundle_id:
            return {"status": "invalid_token", "errorCode": "push_device_incomplete"}
        event_id = str(delivery.get("event_id") or delivery.get("eventId") or "")
        headers = {
            "authorization": f"bearer {self.tokens.token()}",
            "apns-topic": bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10",
            "apns-collapse-id": event_id[:64],
        }
        owns_client = self.client is None
        client = self.client or httpx.Client(http2=True, timeout=10.0)
        try:
            response = client.post(
                f"{host}/3/device/{token}", headers=headers, content=_json_bytes(build_payload(delivery))
            )
            try:
                body = response.json() if response.content else {}
            except (ValueError, json.JSONDecodeError):
                body = {}
            result = classify_response(response.status_code, body, response.headers)
            if result.get("errorCode"):
                result["errorDetail"] = str(body)[:500]
            return result
        finally:
            if owns_client:
                client.close()


def drain_outbox(adapter, sender=None, limit=50):
    sender = sender or APNSSender()
    deliveries = adapter.claim_notification_deliveries(limit=limit) or []
    summary = {"claimed": len(deliveries), "accepted": 0, "failed": 0, "invalidToken": 0, "suppressed": 0}
    results = []
    for delivery in deliveries:
        try:
            result = sender.send(delivery)
        except Exception as error:
            result = {
                "status": "failed", "errorCode": type(error).__name__,
                "errorDetail": str(error)[:500], "retryAfterSeconds": 300,
            }
        adapter.complete_notification_delivery(
            delivery.get("delivery_id") or delivery.get("deliveryId"),
            result.get("status") or "failed",
            apns_id=result.get("apnsId"),
            error_code=result.get("errorCode"),
            error_detail=result.get("errorDetail"),
            retry_after_seconds=result.get("retryAfterSeconds"),
        )
        key = {
            "accepted": "accepted", "failed": "failed",
            "invalid_token": "invalidToken", "suppressed": "suppressed",
        }.get(result.get("status"), "failed")
        summary[key] += 1
        results.append({
            "deliveryId": delivery.get("delivery_id") or delivery.get("deliveryId"),
            "status": result.get("status"),
            "errorCode": result.get("errorCode"),
        })
    return {"ok": True, "summary": summary, "results": results}
