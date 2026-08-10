"""Privacy-safe hints and per-call adaptation for unfinished voice turns.

The classifier never returns transcript text.  ``shadow`` keeps observation
available, while the active gate may add a short, bounded playout grace period
for high-confidence unfinished turns in shipped locales.  Gemini still owns speech
detection and barge-in; this module only prevents a reply that has already been
generated from becoming audible while the user is continuing the same thought.
"""

from dataclasses import dataclass
import os
import re


_FALSE_VALUES = {"0", "false", "off", "no"}
_TERMINAL_PUNCTUATION = ("。", "！", "？", "!", "?")
_OPEN_PUNCTUATION = ("…", "...", "，", ",", "、", "：", ":")
_RULES = {
    "zh": {
        "explicit": (
            "我想一下", "我再想一下", "讓我想一下", "先讓我想想",
            "等我一下", "先等一下", "先聽我說",
        ),
        "fillers": {"嗯", "恩", "呃", "痾", "那個", "就是", "然後"},
        "connectors": (
            "因為", "然後", "可是", "但是", "所以", "如果", "只是",
            "我想", "還有", "再來",
        ),
    },
    "en": {
        "explicit": (
            "let me think", "give me a second", "give me a moment",
            "hold on", "wait a second", "wait a moment", "let me see",
        ),
        "fillers": {"um", "uh", "hmm", "erm", "well", "so"},
        "connectors": ("because", "and", "but", "so", "if", "also", "then"),
    },
    "ja": {
        "explicit": (
            "ちょっと待って", "少し待って", "考えさせて", "考えてみると",
            "ええと待って", "まず聞いて",
        ),
        "fillers": {"えっと", "ええと", "あの", "その", "うーん", "んー"},
        "connectors": ("だから", "それで", "でも", "ただ", "もし", "あと", "それから"),
    },
    "es": {
        "explicit": (
            "déjame pensar", "dejame pensar", "dame un segundo",
            "dame un momento", "espera un segundo", "espera un momento",
            "a ver déjame", "a ver dejame",
        ),
        "fillers": {"eh", "mmm", "em", "este", "bueno", "pues"},
        "connectors": ("porque", "y", "pero", "entonces", "si", "además", "ademas"),
    },
}

FAST_TURN_MS = 650
NORMAL_TURN_MS = 800
PATIENT_TURN_MS = 1100
_SLOW_CONTINUATION_MS = 700


@dataclass(frozen=True)
class TurnSemanticHint:
    decision: str
    reason: str
    supported: bool


@dataclass
class AdaptiveTurnPolicy:
    """Learn a caller's continuation timing within one call only.

    The policy stores timing counters, never audio or transcript text.  It starts
    from the shipped defaults and adapts gradually after real continuations.
    """

    continuation_ewma_ms: float | None = None
    continuations: int = 0
    releases: int = 0

    def observe_continuation(self, delay_ms):
        delay = max(80.0, min(1500.0, float(delay_ms or 0.0)))
        if self.continuation_ewma_ms is None:
            self.continuation_ewma_ms = delay
        else:
            self.continuation_ewma_ms = (0.35 * delay) + (0.65 * self.continuation_ewma_ms)
        self.continuations += 1

    def observe_release(self):
        self.releases += 1

    def is_slow_caller(self):
        return (
            self.continuations >= 2
            and self.continuation_ewma_ms is not None
            and self.continuation_ewma_ms >= _SLOW_CONTINUATION_MS
        )

    def target_ms(self, hint):
        """Return the total end-of-turn target, not an additive delay."""
        if not hint or not hint.supported:
            return NORMAL_TURN_MS
        if hint.decision == "hold":
            return PATIENT_TURN_MS
        if hint.reason == "terminal_punctuation":
            return FAST_TURN_MS
        if self.is_slow_caller():
            return PATIENT_TURN_MS
        return NORMAL_TURN_MS

    def hold_ms(self, hint, base_silence_ms=FAST_TURN_MS):
        """Return only the grace still needed after provider VAD has waited.

        Gemini's session-level AAD cannot be changed after every transcript.
        We therefore run it at the 650 ms floor and gate the first PCM until
        the selected 650/800/1100 ms *total* target.  This avoids the previous
        800 ms provider wait plus another 350-850 ms semantic delay.
        """
        operator_override = os.environ.get("MUNEA_VOICE_SEMANTIC_HOLD_MS", "").strip()
        if operator_override:
            return semantic_hold_ms(hint, operator_override)
        target = self.target_ms(hint)
        if not semantic_turn_adaptive_enabled() and hint and hint.decision != "hold":
            target = NORMAL_TURN_MS
        return max(0, int(target) - max(0, int(base_silence_ms or 0)))

    def snapshot(self):
        return {
            "continuations": self.continuations,
            "releases": self.releases,
            "continuation_ewma_ms": (
                round(self.continuation_ewma_ms)
                if self.continuation_ewma_ms is not None
                else None
            ),
            "slow_caller": self.is_slow_caller(),
        }


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


def semantic_turn_adaptive_enabled(value=None):
    """Whether per-call timing adaptation is active; separate rollout switch."""
    raw = os.environ.get("MUNEA_VOICE_SEMANTIC_TURN_ADAPTIVE", "1") if value is None else value
    return str(raw).strip().lower() not in _FALSE_VALUES


def semantic_hold_ms(hint, value=None):
    """Legacy operator override for additive semantic grace.

    New code should use ``AdaptiveTurnPolicy.hold_ms`` so 650/800/1100 are
    treated as total targets.  The helper remains for rollback compatibility.
    """
    if not hint or not hint.supported or hint.decision != "hold":
        return 0
    default = PATIENT_TURN_MS - FAST_TURN_MS
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


def _locale_family(locale):
    normalized = str(locale or "").strip().lower().replace("_", "-")
    for family in _RULES:
        if normalized == family or normalized.startswith(family + "-"):
            return family
    return None


def _normalized_text(text, family):
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if family in {"zh", "ja"}:
        normalized = normalized.replace(" ", "")
    return normalized


def _ends_with_phrase(text, phrase, family):
    if family in {"zh", "ja"}:
        return text.endswith(phrase)
    return bool(re.search(r"(?:^|\s)" + re.escape(phrase) + r"$", text))


def classify_turn_end(text, locale="zh-TW"):
    """Return a low-cardinality hint without retaining or echoing ``text``."""
    family = _locale_family(locale)
    if family is None:
        return TurnSemanticHint("respond", "unsupported_locale", False)

    normalized = _normalized_text(text, family)
    if not normalized:
        return TurnSemanticHint("respond", "empty", True)

    rules = _RULES[family]
    without_punctuation = normalized.rstrip("….,，、:：。！？!?").strip()
    if any(_ends_with_phrase(without_punctuation, phrase, family) for phrase in rules["explicit"]):
        return TurnSemanticHint("hold", "explicit_hold", True)
    if without_punctuation in rules["fillers"]:
        return TurnSemanticHint("hold", "short_filler", True)
    if normalized.endswith(_OPEN_PUNCTUATION):
        return TurnSemanticHint("hold", "open_punctuation", True)
    if normalized.endswith(_TERMINAL_PUNCTUATION):
        return TurnSemanticHint("respond", "terminal_punctuation", True)
    if any(_ends_with_phrase(normalized, connector, family) for connector in rules["connectors"]):
        return TurnSemanticHint("hold", "trailing_connector", True)
    return TurnSemanticHint("respond", "no_unfinished_signal", True)
