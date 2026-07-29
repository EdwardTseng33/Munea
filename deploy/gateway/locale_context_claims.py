"""Build signed-call locale claims from trusted account and person records.

This module intentionally has no request-body override parameter. The Gateway
must resolve LocaleContext only after authentication and after loading the
caller's account/person records. Language is never used to infer geography,
safety policy, legal policy, currency, units, time zone, or data residency.
"""

import re
from collections.abc import Mapping


SUPPORTED_LOCALES = ("zh-TW", "en", "ja", "es")
LOCALE_CONTEXT_VERSION = 1
LEGACY_DEFAULT_CONTEXT = {
    "version": LOCALE_CONTEXT_VERSION,
    "uiLocale": "zh-TW",
    "conversationLocale": "zh-TW",
    "preferredLanguages": ["zh-TW"],
    "countryCode": "TW",
    "timeZone": "Asia/Taipei",
    "units": "metric",
    "currency": "TWD",
    "safetyRegion": "TW",
    "legalRegion": "TW",
    "dataRegion": "tw-primary",
}

_CONTEXT_FIELDS = tuple(LEGACY_DEFAULT_CONTEXT)
_REQUIRED_POLICY_FIELDS = tuple(
    field for field in _CONTEXT_FIELDS if field != "version"
)
_REGION_CODE_RE = re.compile(r"^[A-Z]{2}$")
_CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")
_TIME_ZONE_RE = re.compile(r"^(?:UTC|[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+)$")
_DATA_REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
_VALID_UNITS = ("metric", "us")


def build_verified_locale_context(account=None, person=None, *, allow_legacy=True):
    """Return LocaleContext v1 from already verified storage records.

    ``allow_legacy`` preserves today's Taiwan behavior while existing records
    are backfilled. Release must switch it off only after every required field
    is stored and exact-build App E2E has passed.
    """
    account = _trusted_record(account, "account")
    person = _trusted_record(person, "person")
    attributes = _trusted_record(person.get("attributes"), "person.attributes")

    values = {}
    for candidate in (
        account.get("localeContext"),
        account.get("locale_context"),
        attributes.get("localeContext"),
        attributes.get("locale_context"),
    ):
        if candidate is None:
            continue
        if not isinstance(candidate, Mapping):
            raise TypeError("Stored locale context must be a mapping")
        values.update(candidate)

    dedicated_values = {
        "uiLocale": account.get("locale"),
        "conversationLocale": person.get("locale"),
        "preferredLanguages": (
            account.get("preferredLanguages")
            if account.get("preferredLanguages") is not None
            else account.get("preferred_languages")
        ),
        "countryCode": (
            person.get("regionCode")
            if person.get("regionCode") is not None
            else person.get("region_code")
        ),
        "timeZone": (
            person.get("timeZone")
            if person.get("timeZone") is not None
            else person.get("timezone")
        ),
    }
    values.update(
        {field: value for field, value in dedicated_values.items() if value is not None}
    )

    if not allow_legacy:
        missing = [field for field in _REQUIRED_POLICY_FIELDS if values.get(field) is None]
        if missing:
            raise ValueError(
                "Trusted LocaleContext is incomplete: " + ", ".join(missing)
            )

    return _normalize_context(values, use_legacy_defaults=allow_legacy)


def locale_context_call_claims(context):
    """Return the only locale shape allowed in a signed Gateway call token."""
    return {
        "locale_context": _normalize_context(
            context,
            use_legacy_defaults=False,
        )
    }


def _trusted_record(value, label):
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"Trusted {label} record must be a mapping")
    return value


def _normalize_context(values, *, use_legacy_defaults):
    if not isinstance(values, Mapping):
        raise TypeError("LocaleContext must be a mapping")
    unknown_fields = sorted(set(values) - set(_CONTEXT_FIELDS))
    if unknown_fields:
        raise ValueError(
            "Unsupported LocaleContext fields: " + ", ".join(unknown_fields)
        )

    if use_legacy_defaults:
        context = {
            field: list(value) if isinstance(value, list) else value
            for field, value in LEGACY_DEFAULT_CONTEXT.items()
        }
    else:
        missing = [field for field in _CONTEXT_FIELDS if values.get(field) is None]
        if missing:
            raise ValueError("LocaleContext is incomplete: " + ", ".join(missing))
        context = {}

    version = values.get("version", context.get("version"))
    if isinstance(version, bool):
        raise ValueError(f"Unsupported LocaleContext version: {version!r}")
    try:
        version = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid LocaleContext version: {version!r}") from exc
    if version != LOCALE_CONTEXT_VERSION:
        raise ValueError(f"Unsupported LocaleContext version: {version!r}")
    context["version"] = version

    context["uiLocale"] = _normalize_locale(
        values.get("uiLocale", context.get("uiLocale")),
        "uiLocale",
    )
    context["conversationLocale"] = _normalize_locale(
        values.get("conversationLocale", context.get("conversationLocale")),
        "conversationLocale",
    )
    context["preferredLanguages"] = _normalize_preferred_languages(
        values.get("preferredLanguages", context.get("preferredLanguages")),
        context["conversationLocale"],
    )
    context["countryCode"] = _normalize_code(
        values.get("countryCode", context.get("countryCode")),
        _REGION_CODE_RE,
        "countryCode",
    )
    context["timeZone"] = _normalize_text(
        values.get("timeZone", context.get("timeZone")),
        _TIME_ZONE_RE,
        "timeZone",
    )
    context["units"] = _normalize_choice(
        values.get("units", context.get("units")),
        _VALID_UNITS,
        "units",
    )
    context["currency"] = _normalize_code(
        values.get("currency", context.get("currency")),
        _CURRENCY_CODE_RE,
        "currency",
    )
    context["safetyRegion"] = _normalize_code(
        values.get("safetyRegion", context.get("safetyRegion")),
        _REGION_CODE_RE,
        "safetyRegion",
    )
    context["legalRegion"] = _normalize_code(
        values.get("legalRegion", context.get("legalRegion")),
        _REGION_CODE_RE,
        "legalRegion",
    )
    context["dataRegion"] = _normalize_text(
        values.get("dataRegion", context.get("dataRegion")),
        _DATA_REGION_RE,
        "dataRegion",
        lowercase=True,
    )
    return context


def _normalize_locale(value, field):
    raw = str(value or "").strip().replace("_", "-")
    lowered = raw.lower()
    if raw in SUPPORTED_LOCALES:
        return raw
    if lowered.startswith("zh"):
        return "zh-TW"
    if lowered.startswith("en"):
        return "en"
    if lowered.startswith("ja"):
        return "ja"
    if lowered.startswith("es"):
        return "es"
    raise ValueError(f"Unsupported LocaleContext {field}: {value!r}")


def _normalize_preferred_languages(values, conversation_locale):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        raise TypeError("LocaleContext preferredLanguages must be a list")
    normalized = [conversation_locale]
    for value in values:
        locale = _normalize_locale(value, "preferredLanguages")
        if locale not in normalized:
            normalized.append(locale)
    return normalized


def _normalize_code(value, pattern, field):
    normalized = str(value or "").strip().upper()
    if not pattern.fullmatch(normalized):
        raise ValueError(f"Invalid LocaleContext {field}: {value!r}")
    return normalized


def _normalize_text(value, pattern, field, *, lowercase=False):
    normalized = str(value or "").strip()
    if lowercase:
        normalized = normalized.lower()
    if not pattern.fullmatch(normalized):
        raise ValueError(f"Invalid LocaleContext {field}: {value!r}")
    return normalized


def _normalize_choice(value, choices, field):
    if value not in choices:
        raise ValueError(f"Invalid LocaleContext {field}: {value!r}")
    return value
