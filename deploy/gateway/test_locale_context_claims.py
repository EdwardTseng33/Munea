import inspect
import json
import sys
import unittest
from pathlib import Path


GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(REPO_ROOT))

from locale_context_claims import (  # noqa: E402
    LEGACY_DEFAULT_CONTEXT,
    build_verified_locale_context,
    locale_context_call_claims,
)


class GatewayLocaleContextClaimsTests(unittest.TestCase):
    def test_legacy_mode_preserves_current_taiwan_defaults(self):
        self.assertEqual(build_verified_locale_context(), LEGACY_DEFAULT_CONTEXT)

    def test_strict_mode_requires_all_trusted_policy_fields(self):
        with self.assertRaisesRegex(ValueError, "Trusted LocaleContext is incomplete"):
            build_verified_locale_context(
                account={"locale": "en"},
                person={"locale": "en"},
                allow_legacy=False,
            )

    def test_verified_records_keep_language_and_regions_independent(self):
        account = {
            "locale": "en-US",
            "preferred_languages": ["es-MX", "en-US", "es"],
        }
        person = {
            "locale": "ja-JP",
            "timezone": "America/Los_Angeles",
            "region_code": "JP",
            "attributes": {
                "localeContext": {
                    "version": 1,
                    "units": "us",
                    "currency": "EUR",
                    "safetyRegion": "ES",
                    "legalRegion": "US",
                    "dataRegion": "eu-primary",
                }
            },
        }

        context = build_verified_locale_context(
            account,
            person,
            allow_legacy=False,
        )

        self.assertEqual(context["uiLocale"], "en")
        self.assertEqual(context["conversationLocale"], "ja")
        self.assertEqual(context["preferredLanguages"], ["ja", "es", "en"])
        self.assertEqual(context["countryCode"], "JP")
        self.assertEqual(context["safetyRegion"], "ES")
        self.assertEqual(context["legalRegion"], "US")
        self.assertEqual(context["currency"], "EUR")
        self.assertEqual(context["dataRegion"], "eu-primary")

    def test_no_request_override_channel_exists(self):
        parameters = inspect.signature(build_verified_locale_context).parameters
        self.assertEqual(
            list(parameters),
            ["account", "person", "allow_legacy"],
        )
        with self.assertRaises(TypeError):
            build_verified_locale_context(
                {},
                {},
                request={"locale_context": {"safetyRegion": "US"}},
            )

    def test_unsupported_locale_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Unsupported LocaleContext uiLocale"):
            build_verified_locale_context(
                account={"locale": "fr-FR"},
                person={},
            )

    def test_signed_claim_has_one_nested_locale_context(self):
        claims = locale_context_call_claims(LEGACY_DEFAULT_CONTEXT)
        self.assertEqual(list(claims), ["locale_context"])
        self.assertEqual(claims["locale_context"], LEGACY_DEFAULT_CONTEXT)

    def test_gateway_defaults_match_engine_contract(self):
        from engine.localization import build_locale_context

        self.assertEqual(
            build_verified_locale_context(),
            build_locale_context(),
        )

    def test_gateway_image_packages_the_resolver(self):
        dockerfile = (GATEWAY_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("locale_context_claims.py", dockerfile)

    def test_voice_manifest_tracks_resolver_separately_from_handler_wiring(self):
        manifest = json.loads(
            (REPO_ROOT / "engine" / "voice-locale-integration-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["gatewayResolverStatus"], "integrated")
        self.assertEqual(manifest["gatewayClaimsStatus"], "pending-pr-258")


if __name__ == "__main__":
    unittest.main()
