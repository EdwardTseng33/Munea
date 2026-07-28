import json
import unittest
from pathlib import Path

try:
    from engine.voice_locale_session import VoiceLocaleSession
except ModuleNotFoundError:
    from voice_locale_session import VoiceLocaleSession


ENGINE_DIR = Path(__file__).resolve().parent


class VoiceLocaleSessionTests(unittest.TestCase):
    def test_integration_manifest_keeps_shipping_handlers_and_e2e_closed(self):
        manifest = json.loads(
            (ENGINE_DIR / "voice-locale-integration-manifest.json").read_text(
                encoding="utf-8",
            ),
        )
        self.assertEqual(manifest["schema"], "munea.voice-locale-integration.v1")
        self.assertEqual(manifest["bridgeStatus"], "integrated")
        self.assertEqual(manifest["appRequestPolicyStatus"], "integrated")
        self.assertEqual(manifest["appRequestPolicyWiringStatus"], "pending-pr-270")
        self.assertEqual(manifest["liveVoiceServerStatus"], "pending-pr-270")
        self.assertEqual(manifest["gatewayResolverStatus"], "integrated")
        self.assertEqual(manifest["gatewayClaimsStatus"], "pending-pr-258")
        self.assertEqual(manifest["legacyTokenMode"], "compatibility")
        self.assertEqual(manifest["appE2EStatus"], "pending")
        self.assertTrue(manifest["callPathRisk"])

    def test_verified_claim_initializes_complete_session_profile(self):
        session = VoiceLocaleSession.from_verified_call_payload({
            "call_id": "call-1",
            "locale_context": {
                "version": 1,
                "uiLocale": "ja",
                "conversationLocale": "en",
                "preferredLanguages": ["ja", "en"],
                "countryCode": "JP",
                "timeZone": "Asia/Tokyo",
                "currency": "JPY",
                "safetyRegion": "JP",
                "legalRegion": "JP",
                "dataRegion": "jp-primary",
            },
        })

        profile = session.current_profile()
        self.assertEqual(profile["sessionLocale"], "en")
        self.assertEqual(profile["speechLanguageCode"], "en-US")
        self.assertEqual(profile["localeContext"]["uiLocale"], "ja")
        self.assertEqual(profile["localeContext"]["countryCode"], "JP")
        self.assertNotIn("119", profile["regionalSafetyInstruction"])

    def test_top_level_client_locale_aliases_are_never_trusted(self):
        session = VoiceLocaleSession.from_verified_call_payload({
            "locale": "ja",
            "countryCode": "JP",
            "safetyRegion": "JP",
        })

        self.assertEqual(session.locale_context["conversationLocale"], "zh-TW")
        self.assertEqual(session.locale_context["countryCode"], "TW")
        self.assertIn("119", session.current_profile()["regionalSafetyInstruction"])

    def test_rollout_can_fail_closed_when_verified_claim_is_missing(self):
        with self.assertRaisesRegex(ValueError, "missing locale_context"):
            VoiceLocaleSession.from_verified_call_payload(
                {"call_id": "call-1"},
                allow_legacy=False,
            )

    def test_mixed_turn_changes_response_only_not_session_or_policy(self):
        session = VoiceLocaleSession({
            "uiLocale": "en",
            "conversationLocale": "en",
            "countryCode": "US",
            "timeZone": "America/Los_Angeles",
            "safetyRegion": "US",
            "legalRegion": "US",
            "dataRegion": "us-central",
        })

        turn = session.resolve_turn(detected_languages=["ja-JP", "en-US"])

        self.assertTrue(turn["decision"]["codeSwitchDetected"])
        self.assertEqual(turn["profile"]["responseLocale"], "ja")
        self.assertEqual(turn["profile"]["speechLanguageCode"], "ja-JP")
        self.assertEqual(session.state["sessionLocale"], "en")
        self.assertEqual(session.locale_context["conversationLocale"], "en")
        self.assertEqual(session.locale_context["safetyRegion"], "US")
        self.assertIsNone(turn["persistenceRequest"])

    def test_temporary_voice_switch_survives_later_turns_without_saving(self):
        session = VoiceLocaleSession({
            "uiLocale": "zh-TW",
            "conversationLocale": "zh-TW",
            "safetyRegion": "TW",
        })

        switched = session.resolve_turn(switch_locale="es-MX")
        follow_up = session.resolve_turn()

        self.assertEqual(switched["profile"]["responseLocale"], "es")
        self.assertEqual(session.state["sessionLocale"], "es")
        self.assertEqual(follow_up["profile"]["responseLocale"], "es")
        self.assertEqual(session.locale_context["conversationLocale"], "zh-TW")
        self.assertIsNone(switched["persistenceRequest"])
        self.assertIn("119", follow_up["profile"]["regionalSafetyInstruction"])

    def test_permanent_switch_requires_confirmation_before_storage_patch(self):
        session = VoiceLocaleSession({
            "uiLocale": "en",
            "conversationLocale": "en",
            "preferredLanguages": ["en", "ja"],
            "countryCode": "US",
            "safetyRegion": "US",
            "legalRegion": "US",
            "dataRegion": "us-central",
        })

        requested = session.resolve_turn(
            switch_locale="ja",
            permanent=True,
        )
        self.assertTrue(requested["decision"]["confirmationRequired"])
        self.assertIsNone(requested["persistenceRequest"])
        self.assertEqual(session.locale_context["conversationLocale"], "en")

        confirmed = session.resolve_turn(confirmation=True)
        request = confirmed["persistenceRequest"]

        self.assertEqual(confirmed["decision"]["persistedLocale"], "ja")
        self.assertEqual(session.locale_context["conversationLocale"], "ja")
        self.assertEqual(session.locale_context["preferredLanguages"], ["ja", "en"])
        self.assertEqual(request["storageFields"]["account"]["locale"], "en")
        self.assertEqual(request["storageFields"]["person"]["locale"], "ja")
        self.assertEqual(
            request["storageFields"]["person"]["attributes"]["localeContext"]["safetyRegion"],
            "US",
        )


if __name__ == "__main__":
    unittest.main()
