#!/usr/bin/env python3
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "apple-store-test-key")
sys.path.insert(0, os.path.dirname(__file__))

import apple_store
import server


AUTH_USER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class FakeVerifier:
    def __init__(self, decoded=None, error=None):
        self.decoded = decoded
        self.error = error

    def verify_and_decode_signed_transaction(self, _signed):
        if self.error:
            raise self.error
        return self.decoded


def decoded_transaction(**overrides):
    values = {
        "transactionId": "100000000000001",
        "originalTransactionId": "100000000000001",
        "bundleId": apple_store.BUNDLE_ID,
        "productId": "net.munea.app.points.200",
        "appAccountToken": AUTH_USER,
        "environment": SimpleNamespace(value="Sandbox"),
        "revocationDate": None,
        "expiresDate": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AppleStoreVerificationTests(unittest.TestCase):
    def test_existing_subscription_event_placeholder_still_persists(self):
        with patch.object(server, "load_billing_store", return_value={}), \
             patch.object(server, "save_billing_store") as save_store:
            response = server.subscription_event_response({"event": {"notificationType": "TEST"}})

        self.assertTrue(response["ok"])
        self.assertTrue(response["accepted"])
        save_store.assert_called_once()
        saved = save_store.call_args.args[0]
        self.assertEqual(saved["lastSubscriptionEvent"]["eventType"], "TEST")

    def test_verified_points_transaction(self):
        result = apple_store.verify_transaction(
            "header.payload.signature",
            AUTH_USER,
            verifiers=[FakeVerifier(decoded_transaction())],
        )
        self.assertEqual(result.productId, "net.munea.app.points.200")
        self.assertEqual(result.points, 200)
        self.assertEqual(result.kind, "points")

    def test_pro_subscription_uses_current_monthly_allowance(self):
        result = apple_store.verify_transaction(
            "header.payload.signature",
            AUTH_USER,
            verifiers=[FakeVerifier(decoded_transaction(
                productId="net.munea.app.pro.monthly",
                expiresDate=1780000000000,
            ))],
        )
        self.assertEqual(result.plan, "pro")
        self.assertEqual(result.points, 400)
        self.assertEqual(result.kind, "subscription")

    def test_invalid_signature_fails_closed(self):
        with self.assertRaisesRegex(apple_store.AppleStoreVerificationError, "apple_signature_verification_failed"):
            apple_store.verify_transaction(
                "header.payload.signature",
                AUTH_USER,
                verifiers=[FakeVerifier(error=ValueError("bad signature"))],
            )

    def test_cross_account_transaction_is_rejected(self):
        with self.assertRaisesRegex(apple_store.AppleStoreVerificationError, "apple_account_token_mismatch"):
            apple_store.verify_transaction(
                "header.payload.signature",
                AUTH_USER,
                verifiers=[FakeVerifier(decoded_transaction(appAccountToken="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))],
            )

    def test_revoked_transaction_is_rejected(self):
        with self.assertRaisesRegex(apple_store.AppleStoreVerificationError, "apple_transaction_revoked"):
            apple_store.verify_transaction(
                "header.payload.signature",
                AUTH_USER,
                verifiers=[FakeVerifier(decoded_transaction(revocationDate=1780000000000))],
            )

    def test_unknown_product_is_rejected(self):
        with self.assertRaisesRegex(apple_store.AppleStoreVerificationError, "apple_product_not_allowed"):
            apple_store.verify_transaction(
                "header.payload.signature",
                AUTH_USER,
                verifiers=[FakeVerifier(decoded_transaction(productId="net.munea.app.fake"))],
            )

    def test_server_grants_verified_transaction_with_apple_idempotency_key(self):
        verified = apple_store.VerifiedAppleTransaction(
            transactionId="100000000000001",
            originalTransactionId="100000000000001",
            productId="net.munea.app.points.200",
            appAccountToken=AUTH_USER,
            environment="Sandbox",
            kind="points",
            points=200,
        )
        captured = {}

        def fake_grant(data):
            captured.update(data)
            return {"ok": True, "walletSummary": {"purchased": 200}, "idempotentReplay": False}

        with patch.object(server.apple_store, "verify_transaction", return_value=verified), \
             patch.object(server, "credits_grant_response", side_effect=fake_grant), \
             patch.object(server, "append_audit_event", return_value={}):
            response = server.apple_transaction_response(
                {"signedTransaction": "header.payload.signature", "transactionId": verified.transactionId},
                auth_gate={"auth": {"authUserId": AUTH_USER}},
            )

        self.assertTrue(response["ok"])
        self.assertTrue(response["verified"])
        self.assertEqual(captured["idempotencyKey"], "apple:100000000000001")
        self.assertEqual(captured["source"], "apple_iap")
        self.assertEqual(captured["amount"], 200)

    def test_claimed_transaction_id_must_match_signed_jws(self):
        verified = apple_store.VerifiedAppleTransaction(
            transactionId="100000000000001",
            originalTransactionId="100000000000001",
            productId="net.munea.app.points.200",
            appAccountToken=AUTH_USER,
            environment="Sandbox",
            kind="points",
            points=200,
        )
        with patch.object(server.apple_store, "verify_transaction", return_value=verified):
            response = server.apple_transaction_response(
                {"signedTransaction": "header.payload.signature", "transactionId": "999"},
                auth_gate={"auth": {"authUserId": AUTH_USER}},
            )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "apple_transaction_id_mismatch")


if __name__ == "__main__":
    unittest.main()
