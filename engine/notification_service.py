"""Shared notification contracts for the Munea inbox and APNs transport."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone


EVENT_TYPES = {
    "family_relay",
    "invitation_applied",
    "invitation_decided",
    "medication_due",
    "medication_missed",
    "clinic_upcoming",
    "family_activity",
    "health_alert",
}
SENSITIVITY_LEVELS = {"public", "private", "health_sensitive"}
PERMISSION_STATUSES = {"not_determined", "denied", "authorized", "provisional", "ephemeral"}
DELIVERY_ACTIONS = {"opened", "actioned"}
HEX_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{32,256}$")

GENERIC_TITLE = "沐寧提醒"
GENERIC_BODY = "你的健康提醒到了，解鎖後查看。"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value, maximum, default=""):
    value = str(value or default).strip()
    return value[:maximum]


def token_hash(token):
    normalized = _text(token, 512).replace(" ", "").replace("<", "").replace(">", "")
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_device(item, identity=None):
    item = item or {}
    identity = identity or {}
    token = _text(item.get("token"), 512).replace(" ", "").replace("<", "").replace(">", "")
    environment = _text(item.get("environment"), 16, "production").lower()
    permission = _text(
        item.get("permissionStatus") or item.get("permission_status"), 32, "not_determined"
    ).lower()
    if environment not in {"sandbox", "production"}:
        environment = "production"
    if permission not in PERMISSION_STATUSES:
        permission = "not_determined"
    notifications_enabled = bool(
        item.get("notificationsEnabled")
        if "notificationsEnabled" in item
        else item.get("notifications_enabled", permission in {"authorized", "provisional"})
    )
    return {
        "id": _text(item.get("id"), 80),
        "accountId": identity.get("accountId") or item.get("accountId") or item.get("account_id"),
        "personId": identity.get("personId") or item.get("personId") or item.get("person_id"),
        "authUserId": identity.get("authUserId") or item.get("authUserId") or item.get("auth_user_id"),
        "platform": "ios",
        "environment": environment,
        "bundleId": _text(item.get("bundleId") or item.get("bundle_id"), 160, "net.munea.app"),
        "token": token,
        "tokenHash": token_hash(token) or _text(item.get("tokenHash") or item.get("token_hash"), 64),
        "appVersion": _text(item.get("appVersion") or item.get("app_version"), 40),
        "locale": _text(item.get("locale"), 40, "zh-TW"),
        "timezone": _text(item.get("timezone"), 80, "Asia/Taipei"),
        "permissionStatus": permission,
        "notificationsEnabled": notifications_enabled,
        "showSensitiveContent": bool(item.get("showSensitiveContent") or item.get("show_sensitive_content")),
        "invalidatedAt": item.get("invalidatedAt") or item.get("invalidated_at"),
        "lastSeenAt": item.get("lastSeenAt") or item.get("last_seen_at") or utc_now(),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        "createdAt": item.get("createdAt") or item.get("created_at"),
        "updatedAt": item.get("updatedAt") or item.get("updated_at"),
    }


def validate_device(device):
    if not device.get("token") or not HEX_TOKEN_RE.match(device["token"]):
        return "push_token_invalid"
    if not device.get("accountId") or not device.get("personId") or not device.get("authUserId"):
        return "push_identity_required"
    if not device.get("bundleId"):
        return "push_bundle_id_required"
    return None


def public_device(device):
    device = normalize_device(device)
    return {
        "id": device.get("id"),
        "platform": device.get("platform"),
        "environment": device.get("environment"),
        "bundleId": device.get("bundleId"),
        "appVersion": device.get("appVersion"),
        "locale": device.get("locale"),
        "timezone": device.get("timezone"),
        "permissionStatus": device.get("permissionStatus"),
        "notificationsEnabled": device.get("notificationsEnabled"),
        "showSensitiveContent": device.get("showSensitiveContent"),
        "invalidatedAt": device.get("invalidatedAt"),
        "lastSeenAt": device.get("lastSeenAt"),
        "createdAt": device.get("createdAt"),
        "updatedAt": device.get("updatedAt"),
    }


def normalize_event(item, recipient_person_id=None, actor_person_id=None):
    item = item or {}
    event_type = _text(item.get("eventType") or item.get("event_type"), 64)
    sensitivity = _text(item.get("sensitivity"), 32, "private")
    if event_type not in EVENT_TYPES:
        event_type = "family_activity"
    if sensitivity not in SENSITIVITY_LEVELS:
        sensitivity = "private"
    return {
        "id": _text(item.get("id"), 80) or str(uuid.uuid4()),
        "accountId": item.get("accountId") or item.get("account_id"),
        "recipientPersonId": recipient_person_id or item.get("recipientPersonId") or item.get("recipient_person_id"),
        "actorPersonId": actor_person_id or item.get("actorPersonId") or item.get("actor_person_id"),
        "familyGroupId": item.get("familyGroupId") or item.get("family_group_id"),
        "eventType": event_type,
        "resourceType": _text(item.get("resourceType") or item.get("resource_type"), 80),
        "resourceId": _text(item.get("resourceId") or item.get("resource_id"), 160),
        "title": _text(item.get("title"), 160, GENERIC_TITLE),
        "body": _text(item.get("body"), 500, GENERIC_BODY),
        "publicTitle": _text(item.get("publicTitle") or item.get("public_title"), 160, GENERIC_TITLE),
        "publicBody": _text(item.get("publicBody") or item.get("public_body"), 500, GENERIC_BODY),
        "sensitivity": sensitivity,
        "deepLink": _text(item.get("deepLink") or item.get("deep_link"), 500, "munea://notifications"),
        "dedupeKey": _text(item.get("dedupeKey") or item.get("dedupe_key"), 240),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
        "expiresAt": item.get("expiresAt") or item.get("expires_at"),
        "readAt": item.get("readAt") or item.get("read_at"),
        "archivedAt": item.get("archivedAt") or item.get("archived_at"),
        "actedAt": item.get("actedAt") or item.get("acted_at"),
        "createdAt": item.get("createdAt") or item.get("created_at") or utc_now(),
        "updatedAt": item.get("updatedAt") or item.get("updated_at") or utc_now(),
    }


def validate_event(event):
    if event.get("eventType") not in EVENT_TYPES:
        return "notification_event_type_invalid"
    if not event.get("recipientPersonId"):
        return "notification_recipient_required"
    if not event.get("deepLink", "").startswith("munea://"):
        return "notification_deep_link_invalid"
    return None


def lock_screen_content(event, show_sensitive_content=False):
    event = normalize_event(event)
    if event["sensitivity"] == "public" or show_sensitive_content:
        return event["title"], event["body"]
    return event["publicTitle"], event["publicBody"]


def mark_event(event, action):
    event = normalize_event(event)
    now = utc_now()
    if action == "read":
        event["readAt"] = event.get("readAt") or now
    elif action == "archive":
        event["archivedAt"] = event.get("archivedAt") or now
    elif action == "opened":
        event["readAt"] = event.get("readAt") or now
    elif action == "actioned":
        event["readAt"] = event.get("readAt") or now
        event["actedAt"] = event.get("actedAt") or now
    else:
        raise ValueError("notification_action_invalid")
    event["updatedAt"] = now
    return event
