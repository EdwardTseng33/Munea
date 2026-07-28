"""Stateful locale bridge for one verified Munea Live Voice call.

This module is intentionally independent from ``live_voice_server.py`` while
that shipping file is owned by another active PR. The eventual server wiring
should construct this bridge only from an already verified call-token payload,
then consume ``current_profile`` and ``resolve_turn`` for every ASR/model turn.
"""

from copy import deepcopy

try:
    from engine import localization
except ModuleNotFoundError:  # Engine services import sibling modules directly.
    import localization


class VoiceLocaleSession:
    """Keep stored, session, turn, and policy locale state separate."""

    def __init__(self, locale_context):
        self._context = localization.build_locale_context(locale_context)
        self._state = localization.new_conversation_locale_state(self._context)

    @classmethod
    def from_verified_call_payload(cls, payload, allow_legacy=True):
        """Build only from claims extracted after call-token verification."""
        context = localization.locale_context_from_verified_call_payload(
            payload,
            allow_legacy=allow_legacy,
        )
        return cls(context)

    @property
    def locale_context(self):
        return deepcopy(self._context)

    @property
    def state(self):
        return deepcopy(self._state)

    def snapshot(self):
        return {
            "localeContext": self.locale_context,
            "state": self.state,
        }

    def current_profile(self):
        """Return the active session profile without changing saved preference."""
        profile = localization.voice_session_locale_profile({
            **self._context,
            "conversationLocale": self._state["sessionLocale"],
        })
        profile["localeContext"] = self.locale_context
        profile["sessionLocale"] = self._state["sessionLocale"]
        return profile

    def resolve_turn(
        self,
        detected_languages=None,
        switch_locale=None,
        permanent=False,
        confirmation=False,
    ):
        """Advance one mixed-language turn and expose an explicit save request."""
        turn = localization.voice_turn_locale_profile(
            self._context,
            self._state,
            detected_languages=detected_languages,
            switch_locale=switch_locale,
            permanent=permanent,
            confirmation=confirmation,
        )
        self._state = deepcopy(turn["decision"]["state"])
        persisted_locale = turn["decision"]["persistedLocale"]
        persistence_request = None
        if persisted_locale is not None:
            self._context = localization.build_locale_context({
                **self._context,
                "conversationLocale": persisted_locale,
                "preferredLanguages": [
                    persisted_locale,
                    *self._context["preferredLanguages"],
                ],
            })
            persistence_request = {
                "localeContext": self.locale_context,
                "storageFields": localization.locale_context_storage_fields(
                    self._context,
                ),
            }

        result = deepcopy(turn)
        result["persistenceRequest"] = persistence_request
        return result
