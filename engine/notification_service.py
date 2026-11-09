"""Shared notification contracts for the Munea inbox and APNs transport."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

import localization


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

# 通知中心（2026-07-15 Edward 定稿）：總開關＋分類開關。
# 分類：medication=用藥提醒、clinic=看診提醒、family=家人消息、safety=安全通知。
NOTIFICATION_CATEGORIES = ("medication", "clinic", "family", "safety")
CATEGORY_BY_EVENT_TYPE = {
    "medication_due": "medication",
    "medication_missed": "medication",
    "clinic_upcoming": "clinic",
    "family_relay": "family",
    "family_activity": "family",
    "invitation_applied": "family",
    "invitation_decided": "family",
    "health_alert": "safety",
}


def normalize_notification_settings(item=None):
    item = item or {}
    cats = item.get("categories") or {}
    if "pushEnabled" in item:
        push_enabled = item.get("pushEnabled")
    elif "push_enabled" in item:
        push_enabled = item.get("push_enabled")
    else:
        # 設定層是「覆蓋層」：沒存過設定＝不阻擋（預設放行）。
        # 「預設關」的 UX 由 App 實現——總開關沒開就不註冊裝置、iOS 也沒授權，
        # 本來就推不到；伺服器端若再預設擋，會出現「用戶開了開關卻收不到」的雙重門。
        push_enabled = True
    return {
        "personId": item.get("personId") or item.get("person_id"),
        "pushEnabled": bool(push_enabled),
        "categories": {c: bool(cats.get(c, True)) for c in NOTIFICATION_CATEGORIES},
        "updatedAt": item.get("updatedAt") or item.get("updated_at") or utc_now(),
    }


def push_allowed(settings, event_type):
    """這則事件可不可以推到「本人手機」。只管本人裝置——家人告警是發給
    家人那個收件人、走家人自己的設定，所以長輩關掉安全通知不會關掉家人端的守護告警。"""
    settings = normalize_notification_settings(settings)
    if not settings["pushEnabled"]:
        return False
    category = CATEGORY_BY_EVENT_TYPE.get(str(event_type or ""), "family")
    return settings["categories"].get(category, True)
PERMISSION_STATUSES = {"not_determined", "denied", "authorized", "provisional", "ephemeral"}
DELIVERY_ACTIONS = {"opened", "actioned"}
HEX_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{32,256}$")

GENERIC_COPY = {
    "zh-TW": {
        "title": "沐寧提醒",
        "body": "你的健康提醒到了，解鎖後查看。",
        "familyRelayPublicBody": "家人捎來一則訊息，解鎖後收聽。",
    },
    "en": {
        "title": "Munea Reminder",
        "body": "Your health reminder is ready. Unlock to view it.",
        "familyRelayPublicBody": "A family member sent you a message. Unlock to listen.",
    },
    "ja": {
        "title": "Muneaからのお知らせ",
        "body": "健康に関するお知らせがあります。ロックを解除して確認してください。",
        "familyRelayPublicBody": "ご家族からメッセージが届きました。ロックを解除して再生できます。",
    },
    "es": {
        "title": "Recordatorio de Munea",
        "body": "Tienes un recordatorio de salud. Desbloquea para verlo.",
        "familyRelayPublicBody": "Un familiar te envió un mensaje. Desbloquea para escucharlo.",
    },
}
FAMILY_SENDER_FALLBACK = {
    "zh-TW": "家人",
    "en": "A family member",
    "ja": "ご家族",
    "es": "Un familiar",
}
GENERIC_TITLE = GENERIC_COPY["zh-TW"]["title"]
GENERIC_BODY = GENERIC_COPY["zh-TW"]["body"]


# health_alert（2026-11-09 緊急聯絡人通知）：鎖定畫面一律用 HEALTH_ALERT_PUBLIC_BODY（完全通用，
# 不帶任何健康數值／逐字稿／長輩姓名），解鎖後在通知中心看到的 title/body 才用這兩張表（帶長輩稱呼，
# 但同樣不帶數值或逐字稿——category 只分「通話中讓人擔心」vs「健康數據異常」兩種，不細分到底是什麼症狀，
# 避免被滑過手機的人看到會引發恐慌或曝露隱私的內容）。
HEALTH_ALERT_PUBLIC_BODY = {
    "zh-TW": "家人的健康有提醒，解鎖後查看。",
    "en": "There's a health check-in alert from your family. Unlock to view.",
    "ja": "ご家族の健康に関するお知らせです。ロックを解除して確認してください。",
    "es": "Hay un aviso de salud de un familiar. Desbloquea para verlo.",
}

HEALTH_ALERT_TITLES = {
    "guardian": {
        "zh-TW": "沐寧提醒：{name}可能需要關心",
        "en": "Munea alert: {name} may need a check-in",
        "ja": "Muneaからのお知らせ：{name}さんが心配な様子です",
        "es": "Aviso de Munea: {name} puede necesitar que lo contactes",
    },
    "vitals": {
        "zh-TW": "沐寧提醒：{name}的健康數據有異常",
        "en": "Munea alert: {name}'s health numbers look unusual",
        "ja": "Muneaからのお知らせ：{name}さんの健康データに変化があります",
        "es": "Aviso de Munea: los datos de salud de {name} se ven distintos a lo habitual",
    },
}

HEALTH_ALERT_BODIES = {
    "guardian": {
        "zh-TW": "剛剛通話中，有些話讓人有點擔心。方便的話，打個電話關心一下，或到App裡看看近況。真的危急的話，請直接聯絡當地的緊急服務。",
        "en": "During a recent call, something {name} said sounded concerning. When you can, give them a call or check the app for more. If this looks like a real emergency, contact local emergency services right away.",
        "ja": "さきほどの通話で、{name}さんの話に少し心配な内容がありました。都合がよければ電話で様子を聞いてみてください。アプリでも近況が見られます。本当に危険な状況だと思われる場合は、すぐに地域の緊急窓口に連絡してください。",
        "es": "Durante una llamada reciente, algo que dijo {name} pareció preocupante. Cuando puedas, llámalo o revisa la app para más detalles. Si parece una emergencia real, contacta de inmediato con los servicios de emergencia locales.",
    },
    "vitals": {
        "zh-TW": "最近一次健康數據超出平常留意的範圍。方便的話，打個電話關心一下，或到App裡看看近況。數據可能有延遲，有狀況還是打電話問他本人最準。",
        "en": "A recent health reading from {name} was outside their usual range. When you can, give them a call or check the app for details. Readings can be delayed, so calling them directly is the most reliable way to check in.",
        "ja": "最近の健康データが、いつもと違う値になっています。都合がよければ電話で様子を聞いてみてください。アプリでも近況が見られます。データには遅れが出ることがあるので、本人に直接聞くのが一番確実です。",
        "es": "Una lectura reciente de salud de {name} estuvo fuera de su rango habitual. Cuando puedas, llámalo o revisa la app para más detalles. Las lecturas pueden tener retraso, así que llamarlo directamente es la forma más segura de saber cómo está.",
    },
}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value, maximum, default=""):
    value = str(value or default).strip()
    return value[:maximum]


def notification_locale(value=None):
    return localization.normalize_locale(value)


def generic_copy(locale=None):
    return dict(GENERIC_COPY[notification_locale(locale)])


def family_relay_copy(sender_label=None, locale=None):
    locale = notification_locale(locale)
    copy = generic_copy(locale)
    sender = _text(sender_label, 80, FAMILY_SENDER_FALLBACK[locale])
    titles = {
        "zh-TW": f"{sender}捎來一則話",
        "en": f"{sender} sent you a message",
        "ja": f"{sender}さんからメッセージが届きました",
        "es": f"{sender} te envió un mensaje",
    }
    return {
        "title": titles[locale],
        "publicTitle": copy["title"],
        "publicBody": copy["familyRelayPublicBody"],
    }


def health_alert_copy(category=None, elder_label=None, locale=None):
    """緊急聯絡人通知文案——category 只收 'guardian'（通話守護腦 high/critical）或
    'vitals'（健康數據超出留意範圍），帶不進來的值一律退回 'guardian'。
    title/body 不放健康數值、不放通話逐字稿；public_* 進一步收斂成完全通用的句子（鎖定畫面用）。"""
    locale = notification_locale(locale)
    category = category if category in HEALTH_ALERT_TITLES else "guardian"
    copy = generic_copy(locale)
    name = _text(elder_label, 40, FAMILY_SENDER_FALLBACK[locale])
    title = HEALTH_ALERT_TITLES[category][locale].format(name=name)
    body = HEALTH_ALERT_BODIES[category][locale].format(name=name)
    return {
        "title": title,
        "body": body,
        "publicTitle": copy["title"],
        "publicBody": HEALTH_ALERT_PUBLIC_BODY[locale],
    }


def preferred_device_locale(devices=None, person_id=None, requested_locale=None):
    if requested_locale:
        return notification_locale(requested_locale)
    candidates = []
    for item in devices or []:
        device = normalize_device(item)
        if person_id and device.get("personId") != person_id:
            continue
        if device.get("invalidatedAt") or not device.get("notificationsEnabled"):
            continue
        candidates.append(device)
    candidates.sort(key=lambda item: item.get("lastSeenAt") or "", reverse=True)
    return notification_locale(candidates[0].get("locale") if candidates else None)


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
    metadata = dict(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {}
    locale = notification_locale(item.get("locale") or metadata.get("locale"))
    metadata["locale"] = locale
    copy = generic_copy(locale)
    event_copy = {}
    if event_type == "family_relay":
        event_copy = family_relay_copy(metadata.get("senderLabel"), locale)
    return {
        "id": _text(item.get("id"), 80) or str(uuid.uuid4()),
        "accountId": item.get("accountId") or item.get("account_id"),
        "recipientPersonId": recipient_person_id or item.get("recipientPersonId") or item.get("recipient_person_id"),
        "actorPersonId": actor_person_id or item.get("actorPersonId") or item.get("actor_person_id"),
        "familyGroupId": item.get("familyGroupId") or item.get("family_group_id"),
        "eventType": event_type,
        "resourceType": _text(item.get("resourceType") or item.get("resource_type"), 80),
        "resourceId": _text(item.get("resourceId") or item.get("resource_id"), 160),
        "title": _text(item.get("title"), 160, event_copy.get("title") or copy["title"]),
        "body": _text(item.get("body"), 500, copy["body"]),
        "publicTitle": _text(
            item.get("publicTitle") or item.get("public_title"),
            160,
            event_copy.get("publicTitle") or copy["title"],
        ),
        "publicBody": _text(
            item.get("publicBody") or item.get("public_body"),
            500,
            event_copy.get("publicBody") or copy["body"],
        ),
        "sensitivity": sensitivity,
        "deepLink": _text(item.get("deepLink") or item.get("deep_link"), 500, "munea://notifications"),
        "dedupeKey": _text(item.get("dedupeKey") or item.get("dedupe_key"), 240),
        "metadata": metadata,
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
