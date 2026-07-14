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
    def __init__(self, decoded=None, error=None, notification=None, renewal=None):
        self.decoded = decoded
        self.error = error
        self.notification = notification
        self.renewal = renewal

    def verify_and_decode_signed_transaction(self, _signed):
        if self.error:
            raise self.error
        return self.decoded

    def verify_and_decode_notification(self, _signed):
        if self.error:
            raise self.error
        return self.notification

    def verify_and_decode_renewal_info(self, _signed):
        if self.error:
            raise self.error
        return self.renewal


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
        "purchaseDate": None,
        "originalPurchaseDate": None,
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
        self.assertEqual(result.points, 150)
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
        self.assertEqual(result.points, 300)
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
            points=150,
        )
        captured = {}

        def fake_grant(data):
            captured.update(data)
            return {"ok": True, "walletSummary": {"purchased": 150}, "idempotentReplay": False}

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
        self.assertEqual(captured["amount"], 150)

    def test_claimed_transaction_id_must_match_signed_jws(self):
        verified = apple_store.VerifiedAppleTransaction(
            transactionId="100000000000001",
            originalTransactionId="100000000000001",
            productId="net.munea.app.points.200",
            appAccountToken=AUTH_USER,
            environment="Sandbox",
            kind="points",
            points=150,
        )
        with patch.object(server.apple_store, "verify_transaction", return_value=verified):
            response = server.apple_transaction_response(
                {"signedTransaction": "header.payload.signature", "transactionId": "999"},
                auth_gate={"auth": {"authUserId": AUTH_USER}},
            )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "apple_transaction_id_mismatch")

    def test_server_notification_verifies_outer_and_nested_jws(self):
        tx = decoded_transaction(
            productId="net.munea.app.pro.monthly",
            expiresDate=1780000000000,
            purchaseDate=1777000000000,
            originalPurchaseDate=1777000000000,
        )
        renewal = SimpleNamespace(
            productId="net.munea.app.pro.monthly",
            originalTransactionId=tx.originalTransactionId,
            appAccountToken=AUTH_USER,
            autoRenewStatus=SimpleNamespace(value=1),
            gracePeriodExpiresDate=None,
        )
        notification = SimpleNamespace(
            notificationType=SimpleNamespace(value="DID_RENEW"),
            rawNotificationType=None,
            subtype=None,
            notificationUUID="notice-1",
            signedDate=1777000000000,
            data=SimpleNamespace(
                signedTransactionInfo="signed.tx.value",
                signedRenewalInfo="signed.renewal.value",
                environment=SimpleNamespace(value="Sandbox"),
                rawEnvironment=None,
                rawStatus=1,
            ),
        )
        result = apple_store.verify_notification(
            "header.payload.signature",
            verifiers=[FakeVerifier(decoded=tx, notification=notification, renewal=renewal)],
        )
        self.assertEqual(result.notificationType, "DID_RENEW")
        self.assertEqual(result.plan, "pro")
        self.assertEqual(result.points, 300)
        self.assertEqual(result.appAccountToken, AUTH_USER)
        self.assertTrue(result.willRenew)

    def test_server_notification_rejects_bad_nested_transaction(self):
        notification = SimpleNamespace(
            notificationType=SimpleNamespace(value="DID_RENEW"), rawNotificationType=None,
            subtype=None, notificationUUID="notice-2", signedDate=None,
            data=SimpleNamespace(
                signedTransactionInfo="signed.tx.value", signedRenewalInfo=None,
                environment=SimpleNamespace(value="Sandbox"), rawEnvironment=None, rawStatus=1,
            ),
        )
        verifier = FakeVerifier(notification=notification)
        verifier.decoded = None
        with self.assertRaisesRegex(apple_store.AppleStoreVerificationError, "apple_notification_transaction_verification_failed"):
            apple_store.verify_notification("header.payload.signature", verifiers=[verifier])

    def test_unmatched_point_refund_never_claws_back_other_purchases(self):
        credits = server.normalize_credits_store({
            "wallets": [{"id": "purchased", "type": "purchased", "balance": 90, "status": "active"}],
            "transactions": [{
                "id": "other-grant", "type": "grant", "walletId": "purchased", "walletType": "purchased",
                "amount": 90, "providerTransactionId": "100000000000099", "idempotencyKey": "apple:other",
            }],
        })
        with patch.object(server, "load_credits_store", return_value=credits), \
             patch.object(server, "save_credits_store") as save_store:
            response = server.credits_refund_response({
                "amount": 150, "providerTransactionId": "100000000000001",
                "idempotencyKey": "apple-refund:notice-unmatched",
            })
        self.assertTrue(response["ok"])
        self.assertFalse(response["matchedOriginalGrant"])
        self.assertEqual(response["refunded"], 0)
        self.assertEqual(response["walletSummary"]["purchased"], 90)
        save_store.assert_not_called()

    def test_point_refund_reversal_restores_only_previously_refunded_credits(self):
        credits = server.normalize_credits_store({
            "wallets": [{"id": "purchased", "type": "purchased", "balance": 10, "status": "active"}],
            "transactions": [{
                "id": "refund", "type": "refund", "walletId": "purchased", "walletType": "purchased",
                "amount": -40, "providerTransactionId": "100000000000001", "idempotencyKey": "apple-refund:notice-1:0",
            }],
        })
        with patch.object(server, "load_credits_store", return_value=credits), \
             patch.object(server, "save_credits_store", side_effect=lambda value: value):
            response = server.credits_refund_reversal_response({
                "amount": 150, "providerTransactionId": "100000000000001",
                "idempotencyKey": "apple-refund-reversed:notice-2",
            })
        self.assertTrue(response["ok"])
        self.assertTrue(response["matchedPriorRefund"])
        self.assertEqual(response["restored"], 40)
        self.assertEqual(response["walletSummary"]["purchased"], 50)

    def test_expired_notification_revokes_paid_access_and_monthly_points(self):
        verified = apple_store.VerifiedAppleNotification(
            notificationType="EXPIRED", subtype="VOLUNTARY", notificationUUID="notice-expired",
            signedDate=None, environment="Sandbox", productId="net.munea.app.plus.monthly",
            transactionId="100000000000002", originalTransactionId="100000000000001",
            appAccountToken=AUTH_USER, kind="subscription", points=150, plan="plus",
        )
        billing = server.normalize_billing_store({
            "accountId": "11111111-1111-4111-8111-111111111111",
            "activePlan": "plus", "subscription": {"status": "active"},
            "entitlements": {"familyCircleInvite": True, "familyCircleJoin": True},
        })
        credits = server.normalize_credits_store({
            "wallets": [
                {"id": "included", "type": "included_monthly", "balance": 80, "status": "active"},
                {"id": "purchased", "type": "purchased", "balance": 40, "status": "active"},
            ]
        })
        with patch.object(server, "_apple_notification_identity", return_value={"accountId": billing["accountId"], "personId": "22222222-2222-4222-8222-222222222222", "authUserId": AUTH_USER}), \
             patch.object(server, "load_billing_store", return_value=billing), \
             patch.object(server, "save_billing_store", side_effect=lambda value, reconcile=False: value), \
             patch.object(server, "load_credits_store", return_value=credits), \
             patch.object(server, "save_credits_store", side_effect=lambda value: value) as save_credits, \
             patch.object(server.supabase_adapter, "make_adapter") as adapter, \
             patch.object(server, "append_audit_event"):
            response = server.apply_verified_apple_notification(verified)
        self.assertTrue(response["ok"])
        self.assertEqual(response["billing"]["activePlan"], "free")
        saved = save_credits.call_args.args[0]
        self.assertEqual(server.credit_wallet_summary(saved)["includedMonthly"], 0)
        self.assertEqual(server.credit_wallet_summary(saved)["purchased"], 40)
        adapter.return_value.remove_external_family_memberships_for_account_unscoped.assert_called_once()


if __name__ == "__main__":
    unittest.main()
