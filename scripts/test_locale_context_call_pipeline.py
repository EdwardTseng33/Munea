"""Pre-handler LocaleContext call-pipeline contract tests.

These tests compose the real App preference policy, storage mapper, Gateway
resolver/claim builder, JSON token-payload boundary, and VoiceLocaleSession.
They do not claim to test token signing, shipping handlers, or a real call.
"""

import inspect
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = REPO_ROOT / "deploy" / "gateway"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(GATEWAY_DIR))

from engine import localization  # noqa: E402
from engine.voice_locale_session import VoiceLocaleSession  # noqa: E402
from locale_context_claims import (  # noqa: E402
    build_verified_locale_context,
    locale_context_call_claims,
)


POLICY_FIELDS = (
    "countryCode",
    "timeZone",
    "units",
    "currency",
    "safetyRegion",
    "legalRegion",
    "dataRegion",
)


class LocaleContextCallPipelineTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "id": "account-test",
            "locale": "zh-TW",
            "preferred_languages": ["zh-TW"],
        }
        self.person = {
            "id": "person-test",
            "locale": "zh-TW",
            "timezone": "Europe/Madrid",
            "region_code": "JP",
            "attributes": {
                "careRole": "parent",
                "localeContext": {
                    "version": 1,
                    "units": "us",
                    "currency": "EUR",
                    "safetyRegion": "ES",
                    "legalRegion": "US",
                    "dataRegion": "eu-primary",
                },
            },
        }

    def _pipeline(self, app_request):
        app_context = localization.locale_context_from_app_preferences(
            app_request,
            self.account,
            self.person,
        )
        storage = localization.locale_context_storage_fields(
            app_context,
            self.person["attributes"],
        )
        stored_account = {**self.account, **storage["account"]}
        stored_person = {**self.person, **storage["person"]}
        gateway_context = build_verified_locale_context(
            stored_account,
            stored_person,
            allow_legacy=False,
        )
        claims = locale_context_call_claims(gateway_context)
        token_payload = json.loads(json.dumps({
            "sub": "account-test",
            "call_id": "call-local-contract",
            **claims,
        }))
        session = VoiceLocaleSession.from_verified_call_payload(
            token_payload,
            allow_legacy=False,
        )
        return app_context, storage, token_payload, session

    def test_all_four_app_languages_survive_storage_gateway_and_voice(self):
        cases = (
            ("zh-Hant-TW", "zh-TW", ["zh-Hant-TW", "en-US"]),
            ("en-US", "en", ["en-US", "es-MX"]),
            ("ja-JP", "ja", ["ja-JP", "en-US"]),
            ("es-ES", "es", ["es-ES", "en-US"]),
        )
        for ios_language, expected_locale, preferred in cases:
            with self.subTest(ios_language=ios_language):
                app_context, storage, payload, session = self._pipeline({
                    "locale": ios_language,
                    "conversationLocale": ios_language,
                    "preferredLanguages": preferred,
                    "timeZone": "Asia/Tokyo",
                })

                self.assertEqual(app_context["uiLocale"], expected_locale)
                self.assertEqual(app_context["conversationLocale"], expected_locale)
                self.assertEqual(storage["account"]["locale"], expected_locale)
                self.assertEqual(storage["person"]["locale"], expected_locale)
                self.assertEqual(list(payload["locale_context"]), list(app_context))
                self.assertEqual(session.locale_context, app_context)
                self.assertEqual(session.current_profile()["sessionLocale"], expected_locale)
                self.assertEqual(session.locale_context["countryCode"], "JP")
                self.assertEqual(session.locale_context["currency"], "EUR")
                self.assertEqual(session.locale_context["safetyRegion"], "ES")
                self.assertEqual(session.locale_context["legalRegion"], "US")
                self.assertEqual(session.locale_context["dataRegion"], "eu-primary")

    def test_language_and_policy_regions_remain_intentionally_decoupled(self):
        app_context, _, _, session = self._pipeline({
            "locale": "en-GB",
            "conversationLocale": "ja-JP",
            "preferredLanguages": ["en-GB", "ja-JP", "es-ES"],
            "timeZone": "Asia/Tokyo",
        })

        self.assertEqual(app_context["uiLocale"], "en")
        self.assertEqual(app_context["conversationLocale"], "ja")
        self.assertEqual(app_context["preferredLanguages"], ["ja", "en", "es"])
        self.assertEqual(app_context["countryCode"], "JP")
        self.assertEqual(app_context["safetyRegion"], "ES")
        self.assertEqual(app_context["legalRegion"], "US")
        self.assertEqual(app_context["currency"], "EUR")
        self.assertEqual(app_context["dataRegion"], "eu-primary")
        self.assertEqual(session.locale_context, app_context)

    def test_app_cannot_smuggle_policy_overrides_into_gateway_claims(self):
        attempts = (
            {"countryCode": "TW"},
            {"localeContext": {"currency": "TWD"}},
            {"locale_context": {"safetyRegion": "TW"}},
            {"legal_region": "TW"},
            {"dataRegion": "tw-primary"},
        )
        for attempt in attempts:
            with self.subTest(attempt=attempt), self.assertRaisesRegex(
                ValueError,
                "cannot change server policy fields",
            ):
                self._pipeline({"locale": "en-US", **attempt})

    def test_gateway_has_no_untrusted_request_override_channel(self):
        self.assertEqual(
            list(inspect.signature(build_verified_locale_context).parameters),
            ["account", "person", "allow_legacy"],
        )
        with self.assertRaises(TypeError):
            build_verified_locale_context(
                self.account,
                self.person,
                request={"locale_context": {"dataRegion": "tw-primary"}},
            )

    def test_top_level_client_aliases_are_ignored_after_json_boundary(self):
        app_context, _, payload, _ = self._pipeline({
            "locale": "en-US",
            "conversationLocale": "ja-JP",
        })
        payload.update({
            "locale": "es",
            "countryCode": "TW",
            "currency": "TWD",
            "safetyRegion": "TW",
            "legalRegion": "TW",
            "dataRegion": "tw-primary",
        })

        session = VoiceLocaleSession.from_verified_call_payload(
            json.loads(json.dumps(payload)),
            allow_legacy=False,
        )

        self.assertEqual(session.locale_context, app_context)
        self.assertEqual(session.locale_context["conversationLocale"], "ja")
        self.assertEqual(session.locale_context["safetyRegion"], "ES")
        self.assertEqual(session.locale_context["dataRegion"], "eu-primary")

    def test_strict_voice_mode_fails_closed_without_nested_claim(self):
        with self.assertRaisesRegex(ValueError, "missing locale_context"):
            VoiceLocaleSession.from_verified_call_payload(
                {
                    "locale": "en",
                    "countryCode": "US",
                    "safetyRegion": "US",
                },
                allow_legacy=False,
            )

    def test_code_switch_and_temporary_command_never_mutate_saved_policy(self):
        app_context, _, _, session = self._pipeline({
            "locale": "en-US",
            "conversationLocale": "ja-JP",
            "preferredLanguages": ["en-US", "ja-JP", "es-ES"],
        })
        original = deepcopy(session.locale_context)

        mixed = session.resolve_spoken_turn(
            "今日は少し tired, but I am okay.",
            detected_languages=["en-US", "ja-JP"],
        )
        self.assertEqual(mixed["intent"]["kind"], "none")
        self.assertEqual(mixed["profile"]["responseLocale"], "en")
        self.assertEqual(session.state["sessionLocale"], "ja")
        self.assertEqual(session.locale_context, original)
        self.assertIsNone(mixed["persistenceRequest"])

        temporary = session.resolve_spoken_turn("Please speak Spanish")
        self.assertEqual(temporary["intent"]["kind"], "switch")
        self.assertEqual(temporary["profile"]["responseLocale"], "es")
        self.assertEqual(session.state["sessionLocale"], "es")
        self.assertEqual(session.locale_context, app_context)
        self.assertIsNone(temporary["persistenceRequest"])

    def test_confirmed_permanent_command_changes_only_language_storage(self):
        _, _, _, session = self._pipeline({
            "locale": "en-US",
            "conversationLocale": "ja-JP",
            "preferredLanguages": ["en-US", "ja-JP"],
        })
        before = session.locale_context

        requested = session.resolve_spoken_turn(
            "Please speak Spanish from now on",
        )
        self.assertTrue(requested["decision"]["confirmationRequired"])
        self.assertIsNone(requested["persistenceRequest"])
        self.assertEqual(session.locale_context, before)

        confirmed = session.resolve_spoken_turn("yes, confirm")
        persistence = confirmed["persistenceRequest"]

        self.assertEqual(confirmed["decision"]["persistedLocale"], "es")
        self.assertEqual(session.locale_context["uiLocale"], before["uiLocale"])
        self.assertEqual(session.locale_context["conversationLocale"], "es")
        for field in POLICY_FIELDS:
            self.assertEqual(session.locale_context[field], before[field])
        self.assertEqual(persistence["storageFields"]["account"]["locale"], "en")
        self.assertEqual(persistence["storageFields"]["person"]["locale"], "es")
        for field in ("units", "currency", "safetyRegion", "legalRegion", "dataRegion"):
            self.assertEqual(
                persistence["storageFields"]["person"]["attributes"]["localeContext"][field],
                before[field],
            )


if __name__ == "__main__":
    unittest.main()
