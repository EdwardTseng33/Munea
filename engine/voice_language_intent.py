"""Conservative spoken-language switch intent parsing for Live Voice.

This parser only recognizes explicit commands. Merely mentioning a language or
mixing languages in one utterance must not change the conversation session.
Country, safety, legal, currency, unit, and data-region policy are deliberately
outside this module.
"""

import re


_LANGUAGE_ALIASES = {
    "zh-TW": (
        "繁體中文",
        "traditional chinese",
        "mandarin chinese",
        "mandarin",
        "chinese",
        "中文",
        "國語",
        "国语",
        "華語",
        "华语",
        "chino",
    ),
    "en": (
        "english",
        "inglés",
        "ingles",
        "英文",
        "英語",
        "英语",
        "英語で",
    ),
    "ja": (
        "japanese",
        "日本語",
        "日文",
        "日語",
        "日语",
        "japonés",
        "japones",
    ),
    "es": (
        "spanish",
        "español",
        "espanol",
        "西班牙文",
        "西班牙語",
        "西班牙语",
        "西文",
        "西語",
        "西语",
        "スペイン語",
    ),
}

_FALSE_POSITIVE_PATTERNS = (
    r"怎麼說",
    r"怎么说",
    r"\bhow\s+(?:do|would)\s+you\s+say\b",
    r"\bwhat(?:'s|\s+is)\b.{0,30}\bin\b",
    r"なんて(?:言|い)う",
    r"どう(?:言|い)います",
    r"\bc[oó]mo\s+se\s+dice\b",
)

_PERMANENT_PATTERNS = (
    r"以後",
    r"以后",
    r"從現在開始",
    r"从现在开始",
    r"預設",
    r"预设",
    r"記住",
    r"记住",
    r"\balways\b",
    r"\bfrom\s+now\s+on\b",
    r"\bdefault\b",
    r"\bremember\b",
    r"これから",
    r"今後",
    r"いつも",
    r"デフォルト",
    r"覚えて",
    r"\bsiempre\b",
    r"\ba\s+partir\s+de\s+ahora\b",
    r"\bpredeterminad[oa]\b",
    r"\brecuerda\b",
)

_CONFIRM_PHRASES = {
    "確認",
    "确认",
    "是",
    "好",
    "好的",
    "確定",
    "确定",
    "yes",
    "yes confirm",
    "confirm",
    "okay",
    "ok",
    "はい",
    "確認します",
    "確定します",
    "sí",
    "si",
    "confirmar",
    "sí confirmar",
    "si confirmar",
}

_CANCEL_PHRASES = {
    "取消",
    "不要",
    "否",
    "不用",
    "算了",
    "no",
    "no cancel",
    "cancel",
    "いいえ",
    "やめて",
    "キャンセル",
    "cancelar",
    "no cancelar",
}


def _alias_pattern(alias):
    escaped = re.escape(alias)
    if re.fullmatch(r"[a-záéíóúüñ\s]+", alias, re.IGNORECASE):
        return rf"(?<!\w){escaped}(?!\w)"
    return escaped


def _target_pattern(locale):
    aliases = sorted(_LANGUAGE_ALIASES[locale], key=len, reverse=True)
    return "(?:" + "|".join(_alias_pattern(alias) for alias in aliases) + ")"


def _normalize_confirmation_text(text):
    value = str(text or "").casefold().strip()
    value = re.sub(r"[\s,，、。.!！?？;；:：]+", " ", value)
    return value.strip()


def _is_explicit_switch(text, target_pattern):
    patterns = (
        # English commands, including polite assistant-directed variants.
        rf"^\s*(?:(?:from\s+now\s+on|always)\s*[,，]?\s*)?"
        rf"(?:(?:please|can\s+you|could\s+you|would\s+you)\s+)?"
        rf"(?:switch|change|speak|talk|reply|respond|continue)"
        rf"(?:\s+(?:to|in|using|with))?\s+{target_pattern}",
        rf"^\s*(?:(?:from\s+now\s+on|always)\s*[,，]?\s*)?"
        rf"(?:(?:please|can\s+you|could\s+you|would\s+you)\s+)?"
        rf"(?:switch|change)\s+from\b.{{1,40}}\bto\s+{target_pattern}",
        # Chinese commands require a request/switch verb, avoiding "我會說英文".
        rf"(?:請|请|麻煩|麻烦)(?:幫我|帮我)?\s*(?:用|講|说|說|改用|改成|"
        rf"切換(?:成|到)?|切换(?:成|到)?|換成|换成|回覆|回复|回答)\s*{target_pattern}",
        rf"^\s*(?:(?:以後|以后)(?:都)?|從現在開始|从现在开始|"
        rf"預設(?:都)?|预设(?:都)?|記住(?:以後)?(?:都)?|记住(?:以后)?(?:都)?)?\s*"
        rf"(?:改用|改成|切換(?:成|到)?|切换(?:成|到)?|換成|换成|用)\s*"
        rf"{target_pattern}\s*(?:回覆|回复|回答|聊天|對話|对话|繼續|继续)?",
        # Japanese normally puts the target language before the action.
        rf"^\s*(?:(?:これから|今後|いつも)\s*)?{target_pattern}\s*"
        rf"(?:に切り替えて|へ切り替えて|で(?:話して|話してください|"
        rf"答えて|返事して|続けて)|を使って)(?:ください|下さい)?",
        # Spanish request forms.
        rf"^\s*(?:por\s+favor\s+)?(?:habla|hable|responde|resp[oó]ndeme|"
        rf"cambia|cambiar|continuemos|sigamos)"
        rf"(?:\s+(?:siempre|a\s+partir\s+de\s+ahora))?"
        rf"(?:\s+(?:en|a))?\s+{target_pattern}",
        # Short, unambiguous polite commands such as "English, please".
        rf"^\s*{target_pattern}\s*(?:please|por\s+favor|拜託|拜托|謝謝|谢谢|"
        rf"お願いします)\s*[。.!！?？]*\s*$",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def parse_spoken_language_intent(transcript, pending_permanent=False):
    """Return a structured switch, confirm, cancel, or no-intent decision."""
    text = str(transcript or "").strip()
    normalized_confirmation = _normalize_confirmation_text(text)

    if pending_permanent:
        if normalized_confirmation in _CANCEL_PHRASES:
            return {
                "kind": "cancel",
                "switchLocale": None,
                "permanent": False,
                "confirmation": False,
                "cancelConfirmation": True,
            }
        if normalized_confirmation in _CONFIRM_PHRASES:
            return {
                "kind": "confirm",
                "switchLocale": None,
                "permanent": False,
                "confirmation": True,
                "cancelConfirmation": False,
            }

    if not text or any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in _FALSE_POSITIVE_PATTERNS
    ):
        return _no_intent()

    matches = []
    for locale in _LANGUAGE_ALIASES:
        target_pattern = _target_pattern(locale)
        if _is_explicit_switch(text, target_pattern):
            first_alias = min(
                (
                    match.start()
                    for alias in _LANGUAGE_ALIASES[locale]
                    for match in re.finditer(
                        _alias_pattern(alias),
                        text,
                        re.IGNORECASE,
                    )
                ),
                default=len(text),
            )
            matches.append((first_alias, locale))

    if not matches:
        return _no_intent()

    _, locale = min(matches)
    permanent = any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in _PERMANENT_PATTERNS
    )
    return {
        "kind": "switch",
        "switchLocale": locale,
        "permanent": permanent,
        "confirmation": False,
        "cancelConfirmation": False,
    }


def _no_intent():
    return {
        "kind": "none",
        "switchLocale": None,
        "permanent": False,
        "confirmation": False,
        "cancelConfirmation": False,
    }
