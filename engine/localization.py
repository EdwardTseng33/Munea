"""Locale policy shared by Munea's API, model prompts, and speech synthesis."""

import re
from collections.abc import Mapping

from opencc import OpenCC

SUPPORTED_LOCALES = ("zh-TW", "en", "ja", "es")
DEFAULT_LOCALE = "zh-TW"
LOCALE_CONTEXT_VERSION = 1
APP_MUTABLE_LOCALE_FIELDS = (
    "uiLocale",
    "conversationLocale",
    "preferredLanguages",
    "timeZone",
)
SERVER_POLICY_LOCALE_FIELDS = (
    "countryCode",
    "units",
    "currency",
    "safetyRegion",
    "legalRegion",
    "dataRegion",
)
DEFAULT_LOCALE_CONTEXT = {
    "version": LOCALE_CONTEXT_VERSION,
    "uiLocale": DEFAULT_LOCALE,
    "conversationLocale": DEFAULT_LOCALE,
    "preferredLanguages": [DEFAULT_LOCALE],
    "countryCode": "TW",
    "timeZone": "Asia/Taipei",
    "units": "metric",
    "currency": "TWD",
    "safetyRegion": "TW",
    "legalRegion": "TW",
    "dataRegion": "tw-primary",
}
_VALID_UNITS = ("metric", "us")
_REGION_CODE_RE = re.compile(r"^[A-Z]{2}$")
_CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")
_TIME_ZONE_RE = re.compile(r"^(?:UTC|[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)+)$")
_DATA_REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
_SPEECH_CODES = {"zh-TW": "cmn-TW", "en": "en-US", "ja": "ja-JP", "es": "es-ES"}
_ASR_LANGUAGE_HINTS = {
    "zh-TW": ["cmn-Hant-TW"],
    "en": ["en-US"],
    "ja": ["ja-JP"],
    "es": ["es-ES"],
}
_REPLY_INSTRUCTIONS = {
    "zh-TW": "請一律使用自然的繁體台灣中文回覆，絕不使用簡體字。",
    "en": "**Every single word of your reply must be in English.** **And never address the person as \"Munea\" — that is the product's name, not theirs. Use their own name, or no name at all.** Even one Chinese sentence is a failure — the person cannot read it. Reply in warm, plain English. Keep voice responses short and easy to follow.",
    "ja": "**返答は一字残らず日本語で書いてください。****また、相手を「Munea」と呼んではいけません——それは製品の名前で、その人の名前ではありません。ご本人の名前で呼ぶか、呼びかけなしで話してください。**中国語の文が一つでも混ざれば失敗です——相手には読めません。自然でやさしい日本語で答えてください。音声で聞き取りやすい短い文を優先してください。",
    "es": "**Toda la respuesta debe estar en español, sin excepción.** **Y nunca llame a la persona «Munea»: ese es el nombre del producto, no el suyo. Use su nombre, o ninguno.** Una sola frase en chino ya es un fallo: la persona no puede leerla. Responde en español claro y cálido. Para voz, usa frases cortas y fáciles de entender.",
}
_OPENING_MESSAGES = {
    "zh-TW": "嗨，我在這裡。想從哪件事聊起都可以。",
    "en": "Hi, I am here with you. How has your day been? We can talk about anything.",
    "ja": "こんにちは。ここにいますよ。今日はどんな一日でしたか？何でも話してくださいね。",
    "es": "Hola, estoy aquí contigo. ¿Cómo ha ido tu día? Podemos hablar de lo que quieras.",
}
_RETRY_MESSAGES = {
    "zh-TW": "不好意思，我這邊連線有點不順，等一下再陪你好不好？",
    "en": "I am having a little trouble connecting. Could we try again in a moment?",
    "ja": "少し接続が不安定です。少し待ってから、もう一度話しかけてもらえますか？",
    "es": "Estoy teniendo un pequeño problema de conexión. ¿Podemos intentarlo de nuevo en un momento?",
}
_GENERIC_EMERGENCY_GUIDANCE = {
    "zh-TW": "如果有人有立即危險，請立刻聯絡所在地的緊急服務，並請附近可信任的人到場協助。",
    "en": "If anyone is in immediate danger, contact the local emergency service and ask a trusted person nearby to help.",
    "ja": "差し迫った危険がある場合は、現地の緊急通報先に連絡し、近くの信頼できる人にも助けを求めてください。",
    "es": "Si alguien está en peligro inmediato, contacta con el servicio local de emergencias y pide ayuda a una persona de confianza cercana.",
}
_TAIWAN_EMERGENCY_GUIDANCE = {
    "zh-TW": "如果有人有立即危險，請立刻撥打台灣 119；需要心理支持時可撥 1925，並請附近可信任的人到場協助。",
    "en": "If anyone is in immediate danger in Taiwan, call 119. For mental-health support, call 1925 and ask a trusted person nearby to help.",
    "ja": "台湾で差し迫った危険がある場合は119へ、心の相談は1925へ連絡し、近くの信頼できる人にも助けを求めてください。",
    "es": "Si alguien está en peligro inmediato en Taiwán, llama al 119. Para apoyo de salud mental, llama al 1925 y pide ayuda a una persona cercana de confianza.",
}
_SPAIN_EMERGENCY_GUIDANCE = {
    "zh-TW": "如果有人在西班牙有立即危險，請立刻撥打 112，並請附近可信任的人到場協助。",
    "en": "If anyone is in immediate danger in Spain, call 112 and ask a trusted person nearby to help.",
    "ja": "スペインで差し迫った危険がある場合は112へ連絡し、近くの信頼できる人にも助けを求めてください。",
    "es": "Si alguien está en peligro inmediato en España, llama al 112 y pide ayuda a una persona de confianza cercana.",
}
_MEXICO_EMERGENCY_GUIDANCE = {
    "zh-TW": "如果有人在墨西哥有立即危險，請立刻撥打 911，並請附近可信任的人到場協助。",
    "en": "If anyone is in immediate danger in Mexico, call 911 and ask a trusted person nearby to help.",
    "ja": "メキシコで差し迫った危険がある場合は911へ連絡し、近くの信頼できる人にも助けを求めてください。",
    "es": "Si alguien está en peligro inmediato en México, llama al 911 y pide ayuda a una persona de confianza cercana.",
}
_JAPAN_EMERGENCY_GUIDANCE = {
    "zh-TW": "如果有人在日本有立即危險，請立刻撥打 119（消防／救護）；報警是 110。要不要叫救護車拿不定主意時可撥 #7119（部分地區未開通）。心理支持可撥 0120-279-338，並請附近可信任的人到場協助。",
    "en": "If anyone is in immediate danger in Japan, call 119 for fire and ambulance (110 for police). If unsure whether to call an ambulance, #7119 offers guidance in many areas. For mental-health support, call 0120-279-338, and ask a trusted person nearby to help.",
    "ja": "日本で差し迫った危険がある場合は、119番（消防・救急）へ。警察は110番です。救急車を呼ぶか迷うときは#7119（地域により未対応）。こころの相談はよりそいホットライン0120-279-338（24時間・無料）へ連絡し、近くの信頼できる人にも助けを求めてください。",
    "es": "Si alguien está en peligro inmediato en Japón, llama al 119 (bomberos y ambulancia); el 110 es para la policía. Si dudas si llamar a una ambulancia, el #7119 orienta en muchas zonas. Para apoyo psicológico, llama al 0120-279-338 y pide ayuda a una persona de confianza cercana.",
}

_UNITED_STATES_EMERGENCY_GUIDANCE = {
    "zh-TW": "如果有人在美國有立即危險，請立刻撥打 911（醫療、消防、警察共用）；想不開時可撥打或傳簡訊到 988，並請附近可信任的人到場協助。",
    "en": "If anyone is in immediate danger in the United States, call 911 (medical, fire and police). For thoughts of suicide, call or text 988, and ask a trusted person nearby to help.",
    "ja": "アメリカで差し迫った危険がある場合は911番（救急・消防・警察）へ。死にたい気持ちのときは988に電話またはテキストで連絡し、近くの信頼できる人にも助けを求めてください。",
    "es": "Si alguien está en peligro inmediato en Estados Unidos, llama al 911 (sanitario, bomberos y policía). Ante ideas de suicidio, llama o envía un mensaje al 988, y pide ayuda a una persona de confianza cercana.",
}

_REGIONAL_EMERGENCY_GUIDANCE = {
    "TW": _TAIWAN_EMERGENCY_GUIDANCE,
    "ES": _SPAIN_EMERGENCY_GUIDANCE,
    "MX": _MEXICO_EMERGENCY_GUIDANCE,
    "JP": _JAPAN_EMERGENCY_GUIDANCE,
    "US": _UNITED_STATES_EMERGENCY_GUIDANCE,
}
REGIONAL_SAFETY_POLICY_SOURCES = {
    "ES": "https://www.interior.gob.es/opencms/en/contacta-con-nosotros/contacto-prueba-3-hide/index.html",
    "MX": "https://www.gob.mx/911/articulos/que-es-el-911emergencias?idiom=es",
    "JP": "https://www.fdma.go.jp/mission/enrichment/appropriate/appropriate003.html",
    "US": "https://988lifeline.org/",
}

# Launch gate: `cmn-TW` is Taiwan Mandarin, not Taiwanese Hokkien. The current
# Live provider does not list Taiwanese Hokkien as a supported language, so a
# pronunciation example must never be mistaken for end-to-end language support.
# Raise this score only after a representative human-listening ASR/TTS benchmark
# reaches the product threshold below.
TAIWANESE_HOKKIEN_MIN_RELEASE_SCORE = 0.80
TAIWANESE_HOKKIEN_VALIDATED_SCORE = 0.0
TAIWANESE_HOKKIEN_FALLBACK = "我目前只用國語陪你聊，可以用國語再說一次嗎？"
TAIWANESE_HOKKIEN_OUTPUT_FALLBACK = "我改用國語再說一次。剛才那句沒有說清楚。"

_TAIWANESE_HOKKIEN_REQUEST_RE = re.compile(
    r"(?:用|說|講|改用|請用).{0,8}(?:台語|臺語|閩南語|河洛話|Hokkien)"
    r"|(?:台語|臺語|閩南語|河洛話|Hokkien).{0,10}(?:說|講|回答|介紹|聊天|對話)",
    re.IGNORECASE,
)
_TAIWANESE_HOKKIEN_STRONG_PHRASES = (
    "食飽未", "呷飽未", "拍謝", "歹勢", "按怎", "按呢", "啥物", "毋知",
    "毋通", "袂使", "無要緊", "無代誌", "有影", "足感心",
)
_TAIWANESE_HOKKIEN_EXCLUSIVE_MARKERS = (
    "阮", "恁", "佮", "攏", "毋", "袂", "咧", "𪜶", "媠", "遐",
)
_TAIWANESE_HOKKIEN_CONTEXT_RE = re.compile(
    r"(?:伊.{0,3}(?:欲|咧|有|講|食|去|來)|(?:欲|閣).{0,3}(?:去|來|食|睏|講|買|做)|"
    r"予.{0,3}(?:你|伊|我)|甲你|敢有|真好食|足(?:好|濟))"
)

# Keep product copy canonical while giving speech synthesis an explicit,
# user-verified pronunciation. Add entries conservatively: an incorrect
# phonetic hint is worse than falling back to natural Taiwan Mandarin.
_TAIWANESE_SPEECH_FORMS = (
    ("卡早捆", "咖紮綑"),
)
_TAIWANESE_TRANSCRIPTION_ALIASES = (
    ("較早睏", "卡早捆"),
)
_TAIWANESE_MANDARIN_FALLBACKS = (
    ("卡早捆", "早點睡"),
    ("咖紮綑", "早點睡"),
    ("較早睏", "早點睡"),
    ("食飽未", "吃飽了嗎"),
    ("呷飽未", "吃飽了嗎"),
    ("拍謝", "不好意思"),
    ("歹勢", "不好意思"),
    ("按怎", "怎麼辦"),
    ("按呢", "這樣"),
    ("啥物", "什麼"),
    ("毋知", "不知道"),
    ("毋通", "不要"),
    ("袂使", "不可以"),
    ("無要緊", "沒關係"),
    ("無代誌", "沒事"),
    ("有影", "真的嗎"),
    ("足感心", "很感動"),
)

# Gemini Live currently exposes a language code and voice choice, but no
# per-word pronunciation lexicon. Avoid user-verified unstable terms in spoken
# output instead of hoping a prompt-only phonetic hint will always be obeyed.
# 供應商唸不穩的詞 → 換成穩定說法。
#
# 2026-07-28 拿掉 ("興趣", "喜好")：這條原本是為了修「興趣」走音，但 Edward 真機聽到
# 換上去的「喜好」也走音（聽成「信號」——後面的「ㄏㄠˋ」一樣、錯在前一個字），
# 等於拿一個唸錯換另一個唸錯，而且新的錯法意思差更遠。
# 兩個補強：①這張表只驗「原詞」有沒有漏出來，從來沒驗過「換上去的詞唸得對不對」——
# 底下 unstable_replacement_targets() 就是補這個缺口，讓考卷能一起盯替換後的詞；
# ②「興趣／喜好」都是書面詞，跟長輩講話本來就不該用——改成句型層級的指示
# （見 taiwan_mandarin_pronunciation_guard_instruction），直接叫她問「你平常喜歡做什麼」，
# 比在兩個都會走音的書面詞之間換來換去更根本。
_TAIWAN_MANDARIN_SPEECH_REPLACEMENTS = (
    ("濃醇", "厚實"),
)

# 已知會走音、但沒有安全替換詞的書面語：直接叫她別用，改用口語句型。
_TAIWAN_MANDARIN_AVOID_TERMS = ("興趣", "喜好")

_TAIWAN_TRADITIONAL_CONVERTER = OpenCC("s2twp")
_CJK_PUNCTUATION_RE = re.compile(r"\s*([，。！？；：、])\s*")
_CONTEXT_ASR_ALIASES = {
    "寧寧": ("凝凝", "甯甯"),
    "阿宏": ("阿紅", "阿洪"),
    "小昀": ("小雲", "小芸"),
    "阿原": ("阿源", "阿元"),
    "咪咪": ("米米",),
    "旺財": ("旺才",),
}


def normalize_locale(locale):
    raw = str(locale or "").strip().replace("_", "-")
    if raw in SUPPORTED_LOCALES: return raw
    lowered = raw.lower()
    if lowered.startswith("zh"): return "zh-TW"
    if lowered.startswith("ja"): return "ja"
    if lowered.startswith("es"): return "es"
    if lowered.startswith("en"): return "en"
    return DEFAULT_LOCALE


def build_locale_context(values=None):
    """Return a normalized, JSON-ready LocaleContext v1.

    This is an additive contract scaffold. It is intentionally not connected to
    the production Gateway or Live call path yet. Language never infers country,
    legal/safety policy, data residency, units, currency, or time zone.
    """
    if values is None:
        values = {}
    if not isinstance(values, Mapping):
        raise TypeError("LocaleContext input must be a mapping")
    if "version" in values:
        try:
            version = int(values["version"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid LocaleContext version: {values['version']!r}") from exc
        if isinstance(values["version"], bool) or version != LOCALE_CONTEXT_VERSION:
            raise ValueError(f"Unsupported LocaleContext version: {values['version']!r}")

    context = {
        key: list(value) if isinstance(value, list) else value
        for key, value in DEFAULT_LOCALE_CONTEXT.items()
    }
    context["uiLocale"] = normalize_locale(values.get("uiLocale"))
    context["conversationLocale"] = normalize_locale(
        values.get("conversationLocale") or context["uiLocale"]
    )
    context["preferredLanguages"] = _normalize_preferred_languages(
        values.get("preferredLanguages"),
        context["conversationLocale"],
    )
    context["countryCode"] = _normalize_code(
        values.get("countryCode"),
        context["countryCode"],
        _REGION_CODE_RE,
    )
    context["timeZone"] = _normalize_text(
        values.get("timeZone"),
        context["timeZone"],
        _TIME_ZONE_RE,
    )
    context["units"] = _normalize_choice(
        values.get("units"),
        context["units"],
        _VALID_UNITS,
        "units",
    )
    context["currency"] = _normalize_code(
        values.get("currency"),
        context["currency"],
        _CURRENCY_CODE_RE,
    )
    context["safetyRegion"] = _normalize_code(
        values.get("safetyRegion"),
        context["safetyRegion"],
        _REGION_CODE_RE,
    )
    context["legalRegion"] = _normalize_code(
        values.get("legalRegion"),
        context["legalRegion"],
        _REGION_CODE_RE,
    )
    context["dataRegion"] = _normalize_text(
        values.get("dataRegion"),
        context["dataRegion"],
        _DATA_REGION_RE,
        lowercase=True,
    )
    return context


def locale_context_from_account(account=None, person=None, overrides=None):
    """Build LocaleContext v1 from the existing account/person storage model.

    Language, geography, legal/safety policy, and data residency remain
    independent. Person attributes carry policy fields that do not have
    dedicated database columns yet; no value is inferred from a language tag.
    """
    account = account if isinstance(account, Mapping) else {}
    person = person if isinstance(person, Mapping) else {}
    attributes = person.get("attributes")
    attributes = attributes if isinstance(attributes, Mapping) else {}
    stored = {}
    for candidate in (
        account.get("localeContext"),
        account.get("locale_context"),
        attributes.get("localeContext"),
        attributes.get("locale_context"),
    ):
        if isinstance(candidate, Mapping):
            stored.update(candidate)

    values = dict(stored)
    storage_values = {
        "uiLocale": account.get("locale"),
        "conversationLocale": person.get("locale"),
        "preferredLanguages": (
            account.get("preferredLanguages")
            or account.get("preferred_languages")
        ),
        "countryCode": person.get("regionCode") or person.get("region_code"),
        "timeZone": person.get("timeZone") or person.get("timezone"),
    }
    values.update({key: value for key, value in storage_values.items() if value is not None})
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            raise TypeError("LocaleContext overrides must be a mapping")
        values.update(overrides)
    return build_locale_context(values)


def locale_context_from_request(data=None, account=None, person=None):
    """Normalize a trusted App/API request without coupling locale to country."""
    data = data if isinstance(data, Mapping) else {}
    requested = data.get("localeContext") or data.get("locale_context") or {}
    if not isinstance(requested, Mapping):
        raise TypeError("localeContext request value must be a mapping")
    requested = dict(requested)
    aliases = {
        "uiLocale": data.get("uiLocale") or data.get("ui_locale") or data.get("locale"),
        "conversationLocale": (
            data.get("conversationLocale")
            or data.get("conversation_locale")
        ),
        "preferredLanguages": (
            data.get("preferredLanguages")
            or data.get("preferred_languages")
        ),
        "countryCode": data.get("countryCode") or data.get("country_code"),
        "timeZone": data.get("timeZone") or data.get("time_zone") or data.get("timezone"),
        "units": data.get("units"),
        "currency": data.get("currency"),
        "safetyRegion": data.get("safetyRegion") or data.get("safety_region"),
        "legalRegion": data.get("legalRegion") or data.get("legal_region"),
        "dataRegion": data.get("dataRegion") or data.get("data_region"),
    }
    requested.update({key: value for key, value in aliases.items() if value is not None})
    return locale_context_from_account(account, person, requested)


def locale_context_from_app_preferences(data=None, account=None, person=None):
    """Apply untrusted App language preferences without changing policy regions.

    The App may report the iOS language list and device time zone. It may not
    decide country, currency, units, safety/legal policy, or data residency.
    Those fields must already come from verified account/person storage or a
    separate server-side market policy resolver.
    """
    data = data if isinstance(data, Mapping) else {}
    requested = data.get("localeContext") or data.get("locale_context") or {}
    if not isinstance(requested, Mapping):
        raise TypeError("localeContext App preference value must be a mapping")
    requested = dict(requested)

    aliases = {
        "uiLocale": data.get("uiLocale") or data.get("ui_locale") or data.get("locale"),
        "conversationLocale": (
            data.get("conversationLocale")
            or data.get("conversation_locale")
        ),
        "preferredLanguages": (
            data.get("preferredLanguages")
            or data.get("preferred_languages")
        ),
        "timeZone": data.get("timeZone") or data.get("time_zone") or data.get("timezone"),
    }
    requested.update({key: value for key, value in aliases.items() if value is not None})

    protected_aliases = {
        "countryCode": ("countryCode", "country_code"),
        "units": ("units",),
        "currency": ("currency",),
        "safetyRegion": ("safetyRegion", "safety_region"),
        "legalRegion": ("legalRegion", "legal_region"),
        "dataRegion": ("dataRegion", "data_region"),
    }
    protected = []
    for field, field_aliases in protected_aliases.items():
        if field in requested or any(
            alias in data or alias in requested
            for alias in field_aliases
        ):
            protected.append(field)
    if protected:
        raise ValueError(
            "App preferences cannot change server policy fields: "
            + ", ".join(sorted(protected))
        )

    unknown = sorted(set(requested) - set(APP_MUTABLE_LOCALE_FIELDS))
    if unknown:
        raise ValueError(
            "Unsupported App locale preference fields: " + ", ".join(unknown)
        )
    return locale_context_from_account(account, person, requested)


def locale_context_storage_fields(context, person_attributes=None):
    """Map LocaleContext v1 onto existing account/person database fields."""
    normalized = build_locale_context(context)
    attributes = dict(person_attributes) if isinstance(person_attributes, Mapping) else {}
    attributes["localeContext"] = {
        "version": normalized["version"],
        "units": normalized["units"],
        "currency": normalized["currency"],
        "safetyRegion": normalized["safetyRegion"],
        "legalRegion": normalized["legalRegion"],
        "dataRegion": normalized["dataRegion"],
    }
    return {
        "account": {
            "locale": normalized["uiLocale"],
            "preferred_languages": list(normalized["preferredLanguages"]),
        },
        "person": {
            "locale": normalized["conversationLocale"],
            "timezone": normalized["timeZone"],
            "region_code": normalized["countryCode"],
            "attributes": attributes,
        },
    }


def locale_context_call_claims(context):
    """Return the only locale claim shape allowed inside a signed call token.

    Gateway integration must use a LocaleContext resolved from trusted account
    policy. This helper deliberately emits one nested object instead of legacy
    top-level locale/country fields, which prevents downstream services from
    accidentally treating UI language as geography or safety policy.
    """
    return {"locale_context": build_locale_context(context)}


def locale_context_from_verified_call_payload(payload, allow_legacy=True):
    """Read LocaleContext only after the surrounding call token is verified.

    Existing production tokens carry no locale claim. During the additive
    rollout they retain the current Taiwan defaults. Once Gateway and installed
    App E2E are ready, callers can set ``allow_legacy=False`` to fail closed.
    Top-level locale, country, or region fields are never trusted as aliases.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("Verified call-token payload must be a mapping")
    raw = payload.get("locale_context")
    if raw is None:
        if allow_legacy:
            return build_locale_context()
        raise ValueError("Verified call token is missing locale_context")
    if not isinstance(raw, Mapping):
        raise TypeError("Verified call token locale_context must be a mapping")
    return build_locale_context(raw)


def _normalize_preferred_languages(values, conversation_locale):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        values = []
    normalized = [conversation_locale]
    for value in values:
        locale = _match_supported_locale(value)
        if locale and locale not in normalized:
            normalized.append(locale)
    return normalized


def _match_supported_locale(locale):
    raw = str(locale or "").strip().replace("_", "-")
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
    return None


def new_conversation_locale_state(locale_context=None):
    """Create session language state without copying geography or policy fields."""
    context = build_locale_context(locale_context)
    locale = context["conversationLocale"]
    return {
        "baseLocale": locale,
        "sessionLocale": locale,
        "pendingPermanentLocale": None,
    }


def resolve_conversation_turn_locale(
    state,
    detected_languages=None,
    switch_locale=None,
    permanent=False,
    confirmation=False,
):
    """Resolve one voice turn without treating code-switching as a saved preference.

    ASR or the model supplies ``detected_languages`` in dominant-first order.
    A separate structured intent parser supplies ``switch_locale`` and whether
    the request is permanent; this policy deliberately does not guess those
    intents from raw speech. A permanent change is returned only after an
    explicit confirmation turn.
    """
    if not isinstance(state, Mapping):
        raise TypeError("Conversation locale state must be a mapping")
    base_locale = _required_supported_locale(state.get("baseLocale"), "baseLocale")
    session_locale = _required_supported_locale(
        state.get("sessionLocale") or base_locale,
        "sessionLocale",
    )
    pending_locale = state.get("pendingPermanentLocale")
    if pending_locale is not None:
        pending_locale = _required_supported_locale(
            pending_locale,
            "pendingPermanentLocale",
        )

    detected = detected_languages
    if isinstance(detected, str):
        detected = [detected]
    if not isinstance(detected, (list, tuple)):
        detected = []
    detected_locales = []
    for value in detected:
        locale = _match_supported_locale(value)
        if locale and locale not in detected_locales:
            detected_locales.append(locale)

    requested_locale = None
    if switch_locale is not None:
        requested_locale = _required_supported_locale(switch_locale, "switchLocale")
    if permanent and requested_locale is None and not confirmation:
        raise ValueError("A permanent conversation locale change requires switchLocale")

    previous_session_locale = session_locale
    confirmation_required = False
    persisted_locale = None

    if requested_locale is not None:
        session_locale = requested_locale
        if permanent:
            if confirmation:
                base_locale = requested_locale
                pending_locale = None
                persisted_locale = requested_locale
            else:
                pending_locale = requested_locale
                confirmation_required = True
        else:
            pending_locale = None
    elif confirmation:
        if pending_locale is None:
            raise ValueError("No permanent conversation locale change is pending")
        base_locale = pending_locale
        session_locale = pending_locale
        persisted_locale = pending_locale
        pending_locale = None

    response_locale = requested_locale or (
        detected_locales[0] if detected_locales else session_locale
    )
    next_state = {
        "baseLocale": base_locale,
        "sessionLocale": session_locale,
        "pendingPermanentLocale": pending_locale,
    }
    return {
        "state": next_state,
        "responseLocale": response_locale,
        "detectedLocales": detected_locales,
        "codeSwitchDetected": len(detected_locales) > 1,
        "sessionChanged": previous_session_locale != session_locale,
        "confirmationRequired": confirmation_required,
        "persistedLocale": persisted_locale,
    }


def _required_supported_locale(value, field):
    locale = _match_supported_locale(value)
    if locale is None:
        raise ValueError(f"Unsupported conversation locale for {field}: {value!r}")
    return locale


def _normalize_code(value, fallback, pattern):
    if value is None:
        return fallback
    normalized = str(value or "").strip().upper()
    if not pattern.fullmatch(normalized):
        raise ValueError(f"Invalid LocaleContext value: {value!r}")
    return normalized


def _normalize_text(value, fallback, pattern, lowercase=False):
    if value is None:
        return fallback
    normalized = str(value or "").strip()
    if lowercase:
        normalized = normalized.lower()
    if not pattern.fullmatch(normalized):
        raise ValueError(f"Invalid LocaleContext value: {value!r}")
    return normalized


def _normalize_choice(value, fallback, choices, field):
    if value is None:
        return fallback
    if value not in choices:
        raise ValueError(f"Invalid LocaleContext {field}: {value!r}")
    return value


def speech_language_code(locale): return _SPEECH_CODES[normalize_locale(locale)]


def asr_language_hints(locale):
    return list(_ASR_LANGUAGE_HINTS[normalize_locale(locale)])


def detect_supported_languages(text):
    """Return conservative dominant-first locale hints for one ASR turn.

    This is intentionally a lightweight routing hint, not identity or region
    inference. It only helps Live Voice reply to a code-switched turn; safety,
    legal, currency, and data-region policy remain fixed in LocaleContext.
    """
    value = str(text or "")
    if not value.strip():
        return []

    scores = {locale: 0 for locale in SUPPORTED_LOCALES}
    first = {locale: len(value) + 1 for locale in SUPPORTED_LOCALES}

    kana = list(re.finditer(r"[\u3040-\u30ff]", value))
    if kana:
        scores["ja"] += len(kana) * 3
        first["ja"] = kana[0].start()

    han = list(re.finditer(r"[\u3400-\u4dbf\u4e00-\u9fff]", value))
    if han:
        if kana:
            scores["ja"] += len(han)
            first["ja"] = min(first["ja"], han[0].start())
        else:
            scores["zh-TW"] += len(han)
            first["zh-TW"] = han[0].start()

    words = list(re.finditer(r"[A-Za-zÀ-ÿ]+(?:'[A-Za-zÀ-ÿ]+)?", value))
    spanish_markers = {
        "el", "la", "los", "las", "un", "una", "que", "de", "por", "para",
        "con", "como", "hola", "gracias", "quiero", "puedo", "hablar",
        "español", "dime", "ahora", "sí", "también",
    }
    english_markers = {
        "the", "a", "an", "and", "or", "but", "to", "of", "in", "with",
        "hello", "thanks", "want", "can", "could", "please", "speak",
        "english", "tell", "now", "also",
    }
    normalized_words = [match.group(0).casefold() for match in words]
    has_spanish = any(
        word in spanish_markers or re.search(r"[áéíóúüñ¿¡]", word)
        for word in normalized_words
    )
    has_english = any(word in english_markers for word in normalized_words)
    for match, word in zip(words, normalized_words):
        if word in spanish_markers or re.search(r"[áéíóúüñ¿¡]", word):
            scores["es"] += 3
            first["es"] = min(first["es"], match.start())
        elif word in english_markers:
            scores["en"] += 3
            first["en"] = min(first["en"], match.start())
        elif has_spanish and not has_english:
            scores["es"] += 1
            first["es"] = min(first["es"], match.start())
        else:
            scores["en"] += 1
            first["en"] = min(first["en"], match.start())

    ranked = [
        locale for locale in SUPPORTED_LOCALES
        if scores[locale] > 0
    ]
    ranked.sort(key=lambda locale: (-scores[locale], first[locale]))
    return ranked


def live_voice_code_switch_instruction(locale):
    """Prompt contract for spoken language switching inside one call."""
    normalized = normalize_locale(locale)
    return (
        "\n[Live language switching]\n"
        f"The saved conversation language for this call is {normalized}. "
        "If the user clearly asks to switch to Traditional Chinese, English, "
        "Japanese, or Spanish, answer in the requested language and keep using "
        "it for later turns in this call. If a user naturally mixes supported "
        "languages without asking to switch, answer only this turn in the "
        "predominant language they just used, then keep the saved conversation "
        "language for later turns. A language switch never changes country, "
        "timezone, emergency, legal, currency, units, or data-region policy. "
        "If the user asks to save a new default language, ask for explicit "
        "confirmation before saying it was saved."
    )


def canonicalize_transcription(text, locale="zh-TW"):
    """Convert provider ASR copy to canonical Taiwan Traditional Chinese."""
    value = str(text or "")
    if normalize_locale(locale) != "zh-TW":
        return value.strip()
    value = _TAIWAN_TRADITIONAL_CONVERTER.convert(value)
    if re.search(r"[\u3400-\u9fff]", value):
        value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value)
        value = _CJK_PUNCTUATION_RE.sub(r"\1", value)
    return value.strip()


def reconcile_context_transcription(text, expected_terms=None, locale="zh-TW"):
    """Resolve verified product-name homophones only when active this call."""
    value = canonicalize_transcription(text, locale)
    if normalize_locale(locale) != "zh-TW":
        return value
    active = {canonicalize_transcription(term, locale) for term in (expected_terms or []) if term}
    for canonical, aliases in _CONTEXT_ASR_ALIASES.items():
        if canonical not in active or canonical in value:
            continue
        for alias in aliases:
            value = value.replace(alias, canonical)
    return value

def opening_message(locale): return _OPENING_MESSAGES[normalize_locale(locale)]

def retry_message(locale): return _RETRY_MESSAGES[normalize_locale(locale)]


def regional_safety_instruction(locale, safety_region):
    """Return localized emergency guidance from an explicit safety region.

    The response language never chooses a country, hotline, legal regime, or
    data region. Only a trusted ``safetyRegion`` may select regional numbers;
    unknown regions use generic local-emergency guidance until a separately
    reviewed regional policy is added.
    """
    normalized_locale = normalize_locale(locale)
    normalized_region = str(safety_region or "").strip().upper()
    copy = _REGIONAL_EMERGENCY_GUIDANCE.get(
        normalized_region,
        _GENERIC_EMERGENCY_GUIDANCE,
    )
    return "\n[Regional safety]\n" + copy[normalized_locale]


def voice_session_locale_profile(locale_context=None):
    """Build the complete locale bundle consumed by one Live voice session."""
    context = build_locale_context(locale_context)
    locale = context["conversationLocale"]
    return {
        "localeContext": context,
        "sessionLocale": locale,
        "responseLocale": locale,
        "captionLocale": locale,
        "speechLanguageCode": speech_language_code(locale),
        "openingMessage": opening_message(locale),
        "retryMessage": retry_message(locale),
        "replyLanguageInstruction": reply_language_instruction(locale),
        "regionalSafetyInstruction": regional_safety_instruction(
            locale,
            context["safetyRegion"],
        ),
    }


def voice_turn_locale_profile(
    locale_context,
    state,
    detected_languages=None,
    switch_locale=None,
    permanent=False,
    confirmation=False,
):
    """Resolve a mixed-language turn and return its prompt/speech locale bundle."""
    context = build_locale_context(locale_context)
    decision = resolve_conversation_turn_locale(
        state,
        detected_languages=detected_languages,
        switch_locale=switch_locale,
        permanent=permanent,
        confirmation=confirmation,
    )
    response_locale = decision["responseLocale"]
    profile = voice_session_locale_profile({
        **context,
        "conversationLocale": response_locale,
    })
    profile["localeContext"] = context
    profile["sessionLocale"] = decision["state"]["sessionLocale"]
    profile["responseLocale"] = response_locale
    profile["captionLocale"] = response_locale
    return {
        "decision": decision,
        "profile": profile,
    }


def reply_language_instruction(locale):
    """A narrow addition to the existing safety/persona prompt, never a replacement."""
    normalized = normalize_locale(locale)
    emergency = " Do not use Taiwan-specific hotline numbers or Taiwan-only service information; tell the person to contact their local emergency service or a trusted person nearby." if normalized != "zh-TW" else ""
    launch_guard = taiwan_mandarin_launch_instruction(normalized) if normalized == "zh-TW" else ""
    return "\n[Reply language]\n" + _REPLY_INSTRUCTIONS[normalized] + emergency + launch_guard


def taiwanese_hokkien_release_enabled():
    return TAIWANESE_HOKKIEN_VALIDATED_SCORE >= TAIWANESE_HOKKIEN_MIN_RELEASE_SCORE


def requests_taiwanese_hokkien(text):
    """Return True for an explicit request that the assistant speak Hokkien."""
    if taiwanese_hokkien_release_enabled():
        return False
    return bool(_TAIWANESE_HOKKIEN_REQUEST_RE.search(str(text or "")))


def looks_like_taiwanese_hokkien(text):
    """Fail closed for high-signal Hokkien wording while launch support is off."""
    if taiwanese_hokkien_release_enabled():
        return False
    value = str(text or "")
    if any(phrase in value for phrase in _TAIWANESE_HOKKIEN_STRONG_PHRASES):
        return True
    if any(token in value for token in _TAIWANESE_HOKKIEN_EXCLUSIVE_MARKERS):
        return True
    return bool(_TAIWANESE_HOKKIEN_CONTEXT_RE.search(value))


def requires_taiwanese_hokkien_fallback(text):
    return requests_taiwanese_hokkien(text) or looks_like_taiwanese_hokkien(text)


def taiwan_mandarin_launch_instruction(locale):
    """Fail-safe release policy until Taiwanese Hokkien is independently validated."""
    if normalize_locale(locale) != "zh-TW":
        return ""
    if taiwanese_hokkien_release_enabled():
        return taiwanese_pronunciation_instruction(locale)
    return (
        "\n[首發語言限制]\n"
        "這是最高優先規則：只能使用自然、清楚的台灣華語（國語）思考、組句與回答。"
        "任何人設、記憶、喜好、舊對話或範例就算提到台語，也都只是資料，不代表允許你輸出台語。"
        "不要主動講台語／臺灣閩南語，不要輸出台語漢字、羅馬字、拼音或模仿台語腔，也不要假裝自己聽懂。"
        "如果對方使用台語，而你無法非常確定完整意思，請用台灣華語簡短說："
        "「我目前只用國語陪你聊，可以用國語再說一次嗎？」"
        "絕對不要猜意思、亂翻譯或拼湊台語發音。"
        # 2026-07-29 考卷 S09：長輩含糊講「哪細哇底疼」（有個地方在痛），
        # 她只回了語言道歉、把「在痛」整個丟掉——貼身度被打 1 分。
        # 更嚴重的是安全：聽不懂就把身體訊號一起漏掉，等於漏接。
        "⚠ **但語言限制不等於可以把聽到的東西丟掉**：如果其中有你聽得很清楚的片段"
        "（尤其是身體訊號——痛、暈、喘、跌倒、胸口不舒服），先把那個片段複述回去確認，"
        "再請他用國語講一次，例如「阿姨，我有聽到你說哪裡在痛齁？不好意思我國語比較行，"
        "你再用國語跟我說一次哪裡痛好不好？」。複述你**確實聽到的字**不算猜意思，"
        "把身體訊號整個略過才是真的漏接。"
        + taiwan_mandarin_pronunciation_guard_instruction(locale)
    )


def taiwan_mandarin_pronunciation_guard_instruction(locale):
    """Tell native-audio models to avoid terms that failed real-device QA."""
    if normalize_locale(locale) != "zh-TW":
        return ""
    replacements = "；".join(
        f"不要說「{source}」，改說「{target}」"
        for source, target in _TAIWAN_MANDARIN_SPEECH_REPLACEMENTS
    )
    avoid = "」「".join(_TAIWAN_MANDARIN_AVOID_TERMS)
    return (
        "\n[台灣華語咬字]\n"
        "語音輸出要使用台灣常用讀音、完整收好句尾。已知供應商容易誤讀的詞直接換成穩定說法："
        + replacements
        + "。即使對方用了原詞，也不要原樣複誦。\n"
        # 2026-07-28：這兩個詞都會走音、又沒有同樣意思又唸得穩的替代詞，所以改成
        # 「別用這個詞、改用這種問法」——長輩對話本來也不會用書面語問「你的興趣是什麼」。
        "另外「" + avoid + "」這類書面詞一律不要說出口，改用口語問法"
        "（例如「你平常喜歡做什麼」「你喜歡的事是什麼」）。"
    )


def unstable_replacement_targets():
    """替換表「換上去」的那些詞——考卷要一起盯這些字的唸法。

    2026-07-28 立：舊版只驗原詞有沒有漏出來，沒人驗換上去的詞唸得對不對，
    結果「興趣→喜好」把一個走音換成另一個走音，兩個禮拜沒被抓到。
    """
    return tuple(target for _, target in _TAIWAN_MANDARIN_SPEECH_REPLACEMENTS)


def voice_opening_instruction(familiarity=0, topics=None, location=None, opening_index=None):
    """Rotate concrete opening directions instead of repeating mood check-ins."""
    try:
        familiarity = max(0, int(familiarity or 0))
    except (TypeError, ValueError):
        familiarity = 0
    try:
        route_index = familiarity if opening_index is None else max(0, int(opening_index or 0))
    except (TypeError, ValueError):
        route_index = familiarity
    liked = [str(topic).strip() for topic in (topics or []) if str(topic).strip()]
    place = str(location or "").strip()
    # 2026-08-01（Edward 7/31 深夜真機：她開場說「你看新聞了嗎？這次奧運台灣選手超有精神」，
    # 而當天備好的資料裡一個奧運的字都沒有）。病根就在這裡：舊版第 2、4 條路線叫她
    # 「挑一個具體的小切口」「直接分享一句輕巧的話」，卻沒說**材料從哪來**。開場又規定
    # 要短、要有內容、要立刻開口，她手上沒東西就自己生一個聽起來很合理的——而「新聞只能
    # 講備好的」那條規則躺在一萬七千多字說明書的另一端，搶不過眼前這句直接指令。
    # 改法：每條路線都綁死材料來源，並且給她一條「不必編也能過關」的路（短招呼永遠合格）。
    # 只寫「不准編」沒用，要同時給替代做法——7/29 誠實防線學到的同一件事。
    # 2026-08-01 Edward 拍板：「開頭只要打招呼就好，可以理解一下當下的時間該說早安／午安／
    # 晚安、給一些情緒價值或樂趣、與記憶。不需要用時事來開頭。」
    # 所以四條路線全部收斂成「招呼」這一件事，只是溫度來源不同：時段、心意、記憶、輕鬆。
    # 材料一律限定在她真的有的東西（現在幾點、上面寫著的記憶），沒有就退回純招呼。
    # 2026-08-01 Edward 定版：「就是暱稱、名稱加上時間的招呼，與記憶是否需要詢問什麼問題之類。」
    # 並明確拿掉「我在喔」「我在這裡」——那是機器人式的存在宣告，真人朋友接起電話不會那樣講。
    # 所以開場只有兩種長相，輪流用：①稱呼＋時段招呼，講完停 ②稱呼＋時段招呼＋一句從記憶來的問句。
    greet_core = "用他的稱呼開頭，接一句照現在時間的招呼（早上早安、下午午安、晚上晚安、太晚就順口提早點休息）"
    ask_route = (
        greet_core + "，然後接一句問句——問的內容只能來自**上面真的寫著**的他的事"
        "（他講過的、記著的，像上次說的不舒服、要去做的事）；"
        "**上面沒寫的一律不准問、也不准自己補細節**，想不到可問的就只招呼、講完停。"
    )
    # Edward 8/1 補：「有時輕鬆一點、有時有溫度一點」——四條輪流，語氣不要每通一樣。
    warm_route = (
        greet_core + "，再加一點溫度——只能是**此刻成立**的話"
        "（像「你來啦」「接到你真好」，或一句祝福「祝你今天順順的」），講完就停；"
        "**不准說「今天想到你」「等你好久」「這幾天都在想」這類**——"
        "你沒有兩通之間的日子，那是憑空生出來的心情。"
    )
    routes = (
        greet_core + "，講完就停下來把話權留給對方；這次不要問問題。",
        ask_route,
        greet_core + "，語氣輕鬆一點、可以有一點點俏皮，講完就停；不要問對方今天開不開心。",
        warm_route,
    )
    # 2026-08-01 Edward：「不要講什麼『我在喔』『我在這裡』」——那是機器人式的存在宣告，
    # 真人朋友接起電話不會先報告自己存在。
    forbidden = (
        "「今天開心嗎」「有開心嗎」「心情好嗎」「今天過得怎麼樣」「最近好嗎」"
        "「我在喔」「我在這裡」「我一直都在」"
    )
    # 興趣與所在地只當「他先聊到才接」的方向，不再當開場素材（Edward 8/1：開頭只要打招呼）。
    ctx_note = ""
    if liked:
        ctx_note = "（他喜歡的話題有「" + "、".join(liked[:3]) + "」——那是**他先聊到才接**的方向，不是開場素材。）"
    elif place:
        ctx_note = "（他住在「" + place + "」——那是他先聊到才接的方向，不是開場素材。）"
    return (
        "本通開場路線：" + routes[route_index % len(routes)]
        + " 禁止使用或改寫成這些制式問候：" + forbidden
        + "。不要每通都先查問情緒或近況；開場只能一句，講完就停。" + ctx_note
        # 開場專屬鐵律：釘在她真正會照做的那句指令旁邊，不放在說明書遠處。
        + "\n**開場這一句絕對不准提新聞、時事、比賽、活動、或誰誰誰最近怎樣**"
        "——不管你覺得多合理、多像真的。他自己先問，你才去查了再講；他沒問，"
        "就當作你今天沒有任何消息。**想不到內容就只講一句招呼**——"
        "短招呼永遠是合格的開場，編一句有內容的不是。"
    )


def contains_unstable_mandarin_speech(text):
    """這句話裡有沒有「已知會唸歪」的詞——有就攔下來讓她重講。

    2026-07-28 補上 _TAIWAN_MANDARIN_AVOID_TERMS：舊版只攔替換表的「原詞」，
    所以「興趣」會被攔、換上去的「喜好」不會——Edward 真機聽到「喜好」走音成「信號」
    整整兩個禮拜沒被攔過一次。現在原詞跟避用詞一起攔。
    """
    value = str(text or "")
    if any(source in value for source, _ in _TAIWAN_MANDARIN_SPEECH_REPLACEMENTS):
        return True
    return any(term in value for term in _TAIWAN_MANDARIN_AVOID_TERMS)


def assistant_output_text(text, locale):
    """Return display-safe assistant text and fail closed on residual Hokkien."""
    value = display_text(text, locale)
    if normalize_locale(locale) == "zh-TW" and looks_like_taiwanese_hokkien(value):
        return TAIWANESE_HOKKIEN_OUTPUT_FALLBACK
    return value

def speech_text(text, locale):
    """Return speech-only text without changing stored or displayed copy."""
    value = str(text or "")
    if normalize_locale(locale) != "zh-TW":
        return value
    if not taiwanese_hokkien_release_enabled():
        for source, mandarin in _TAIWANESE_MANDARIN_FALLBACKS:
            value = value.replace(source, mandarin)
        for source, replacement in _TAIWAN_MANDARIN_SPEECH_REPLACEMENTS:
            value = value.replace(source, replacement)
        return value
    for display, spoken in _TAIWANESE_SPEECH_FORMS:
        value = value.replace(display, spoken)
    return value

def display_text(text, locale):
    """Normalize speech transcriptions back to canonical product copy."""
    value = canonicalize_transcription(text, locale)
    if normalize_locale(locale) != "zh-TW":
        return value
    if not taiwanese_hokkien_release_enabled():
        value = speech_text(value, locale)
        if re.search(r"[\u3400-\u9fff]", value):
            value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value).strip()
        return value
    for display, spoken in _TAIWANESE_SPEECH_FORMS:
        # Live transcription may insert spaces between CJK syllables. Limit
        # whitespace cleanup to verified terms instead of changing all copy.
        for form in (spoken, display):
            pattern = r"\s*".join(re.escape(char) for char in form)
            value = re.sub(pattern, display, value)
    for alias, display in _TAIWANESE_TRANSCRIPTION_ALIASES:
        pattern = r"\s*".join(re.escape(char) for char in alias)
        value = re.sub(pattern, display, value)
    if re.search(r"[\u3400-\u9fff]", value):
        value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value).strip()
    return value

def taiwanese_pronunciation_instruction(locale):
    """Narrow speech policy for native-audio models such as Gemini Live."""
    if normalize_locale(locale) != "zh-TW":
        return ""
    examples = "；".join(f"「{display}」要唸成「{spoken}」" for display, spoken in _TAIWANESE_SPEECH_FORMS)
    return (
        "\n[台語發音]\n"
        "回覆可使用自然的台灣口語。遇到下列台語詞時，畫面文字仍保留原詞，但實際發音必須依照指定讀法："
        + examples
        + "。不要按國語逐字朗讀；若不確定其他台語詞的發音，就改用自然台灣華語表達，不要自行猜音。"
    )
