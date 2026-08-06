"""Privacy-safe hints for possibly unfinished voice turns.

The classifier never returns transcript text.  ``shadow`` keeps observation
available, while the active gate may add a short, bounded playout grace period
for high-confidence unfinished Mandarin turns.  Gemini still owns speech
detection and barge-in; this module only prevents a reply that has already been
generated from becoming audible while the user is continuing the same thought.
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

_DEFAULT_HOLD_MS_BY_REASON = {
    "explicit_hold": 850,
    "short_filler": 600,
    "open_punctuation": 450,
    "trailing_connector": 600,
}


@dataclass(frozen=True)
class TurnSemanticHint:
    decision: str
    reason: str
    supported: bool


def semantic_turn_shadow_enabled(value=None):
    """Return whether observation-only semantic turn logging is enabled."""
    raw = os.environ.get("MUNEA_VOICE_SEMANTIC_TURN_SHADOW", "1") if value is None else value
    return str(raw).strip().lower() not in _FALSE_VALUES


def semantic_turn_active_enabled(value=None):
    """Whether the bounded audible-reply gate is active.

    This is deliberately separate from provider VAD.  It has an emergency
    kill switch and only applies to supported ``hold`` hints.
    """
    raw = os.environ.get("MUNEA_VOICE_SEMANTIC_TURN_ACTIVE", "1") if value is None else value
    return str(raw).strip().lower() not in _FALSE_VALUES


def semantic_hold_ms(hint, value=None):
    """Return a bounded grace period for a supported high-confidence hint."""
    if not hint or not hint.supported or hint.decision != "hold":
        return 0
    default = _DEFAULT_HOLD_MS_BY_REASON.get(hint.reason, 0)
    if not default:
        return 0
    raw = os.environ.get("MUNEA_VOICE_SEMANTIC_HOLD_MS", "") if value is None else value
    if str(raw or "").strip():
        try:
            configured = int(raw)
        except (TypeError, ValueError):
            configured = default
        return max(200, min(1200, configured))
    return default


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
