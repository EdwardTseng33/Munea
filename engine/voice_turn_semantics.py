"""Privacy-safe shadow hints for possibly unfinished voice turns.

This module never controls Gemini Live turn taking.  It classifies only a
finished input transcription so production evidence can show whether provider
turn commits are often happening after a hesitation or an unfinished phrase.
No transcript is returned by the classifier.
"""

from dataclasses import dataclass
import os
import re


_FALSE_VALUES = {"0", "false", "off", "no"}
_SUPPORTED_LOCALES = {"zh", "zh-tw", "zh-hant", "zh-hant-tw"}
_TERMINAL_PUNCTUATION = ("。", "！", "？", "!", "?")
_OPEN_PUNCTUATION = ("…", "...", "，", ",", "、", "：", ":")
_EXPLICIT_HOLD = (
    "我想一下",
    "我再想一下",
    "讓我想一下",
    "先讓我想想",
    "等我一下",
    "先等一下",
    "先聽我說",
)
_SHORT_FILLERS = {"嗯", "恩", "呃", "痾", "那個", "就是", "然後"}
_TRAILING_CONNECTORS = (
    "因為",
    "然後",
    "可是",
    "但是",
    "所以",
    "如果",
    "只是",
    "我想",
    "還有",
    "再來",
)


@dataclass(frozen=True)
class TurnSemanticHint:
    decision: str
    reason: str
    supported: bool


def semantic_turn_shadow_enabled(value=None):
    """Return whether observation-only semantic turn logging is enabled."""
    raw = os.environ.get("MUNEA_VOICE_SEMANTIC_TURN_SHADOW", "1") if value is None else value
    return str(raw).strip().lower() not in _FALSE_VALUES


def _compact(text):
    return re.sub(r"\s+", "", str(text or "")).strip()


def classify_turn_end(text, locale="zh-TW"):
    """Return a low-cardinality hint without retaining or echoing ``text``."""
    normalized_locale = str(locale or "").strip().lower().replace("_", "-")
    if normalized_locale not in _SUPPORTED_LOCALES:
        return TurnSemanticHint("respond", "unsupported_locale", False)

    compact = _compact(text)
    if not compact:
        return TurnSemanticHint("respond", "empty", True)

    without_punctuation = compact.rstrip("….,，、:：。！？!?")
    if any(without_punctuation.endswith(phrase) for phrase in _EXPLICIT_HOLD):
        return TurnSemanticHint("hold", "explicit_hold", True)
    if without_punctuation in _SHORT_FILLERS:
        return TurnSemanticHint("hold", "short_filler", True)
    if compact.endswith(_OPEN_PUNCTUATION):
        return TurnSemanticHint("hold", "open_punctuation", True)
    if compact.endswith(_TERMINAL_PUNCTUATION):
        return TurnSemanticHint("respond", "terminal_punctuation", True)
    if any(compact.endswith(connector) for connector in _TRAILING_CONNECTORS):
        return TurnSemanticHint("hold", "trailing_connector", True)
    return TurnSemanticHint("respond", "no_unfinished_signal", True)
