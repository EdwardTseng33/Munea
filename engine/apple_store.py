"""Apple StoreKit 2 signed transaction verification for Munea billing."""
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


BUNDLE_ID = "net.munea.app"
APP_APPLE_ID = 6788658125

PRODUCTS = {
    # Product IDs cannot be renamed after creation in App Store Connect. Their
    # numeric suffixes are legacy identifiers; these values are the current
    # customer-visible grants from Edward's 2026-07-13 pricing update.
    "net.munea.app.points.200": {"kind": "points", "points": 150},
    "net.munea.app.points.500": {"kind": "points", "points": 300},
    "net.munea.app.points.1000": {"kind": "points", "points": 600},
    "net.munea.app.points.1800": {"kind": "points", "points": 1000},
    "net.munea.app.plus.monthly": {"kind": "subscription", "plan": "plus", "monthlyPoints": 150},
    "net.munea.app.plus.yearly": {"kind": "subscription", "plan": "plus", "monthlyPoints": 150},
    "net.munea.app.pro.monthly": {"kind": "subscription", "plan": "pro", "monthlyPoints": 300},
    "net.munea.app.pro.yearly": {"kind": "subscription", "plan": "pro", "monthlyPoints": 300},
}


class AppleStoreVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedAppleTransaction:
    transactionId: str
    originalTransactionId: str
    productId: str
    appAccountToken: str
    environment: str
    kind: str
    points: int = 0
    plan: str = ""
    expiresDate: str | None = None
    purchaseDate: str | None = None
    originalPurchaseDate: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class VerifiedAppleNotification:
    notificationType: str
    subtype: str
    notificationUUID: str
    signedDate: str | None
    environment: str
    productId: str = ""
    transactionId: str = ""
    originalTransactionId: str = ""
    appAccountToken: str = ""
    kind: str = ""
    points: int = 0
    plan: str = ""
    expiresDate: str | None = None
    purchaseDate: str | None = None
    originalPurchaseDate: str | None = None
    revocationDate: str | None = None
    willRenew: bool | None = None
    gracePeriodExpiresDate: str | None = None
    status: int | None = None

    def to_dict(self):
        return asdict(self)


def _root_certificates():
    cert_dir = os.environ.get("APPLE_ROOT_CA_DIR") or os.path.join(os.path.dirname(__file__), "certs")
    names = ("AppleIncRootCertificate.cer", "AppleRootCA-G2.cer", "AppleRootCA-G3.cer")
    roots = []
    for name in names:
        path = os.path.join(cert_dir, name)
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                roots.append(handle.read())
    if not roots:
        raise AppleStoreVerificationError("apple_root_certificates_missing")
    return roots


def _default_verifiers():
    try:
        from appstoreserverlibrary.models.Environment import Environment
        from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier
    except ImportError as exc:
        raise AppleStoreVerificationError("apple_server_library_missing") from exc

    roots = _root_certificates()
    online_checks = str(os.environ.get("APPLE_STORE_ONLINE_CHECKS") or "true").lower() not in {"0", "false", "no"}
    return (
        SignedDataVerifier(roots, online_checks, Environment.PRODUCTION, BUNDLE_ID, APP_APPLE_ID),
        SignedDataVerifier(roots, online_checks, Environment.SANDBOX, BUNDLE_ID),
    )


def _millis_to_iso(value):
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AppleStoreVerificationError("apple_expiration_date_invalid") from exc


def _enum_value(value, fallback=""):
    return getattr(value, "value", None) or str(value or fallback)


def verify_notification(signed_payload, verifiers=None):
    """Verify an App Store Server Notifications V2 JWS and its nested JWS values."""
    signed_payload = str(signed_payload or "").strip()
    if signed_payload.count(".") != 2:
        raise AppleStoreVerificationError("invalid_signed_notification")

    decoded = None
    selected_verifier = None
    last_error = None
    for verifier in verifiers or _default_verifiers():
        try:
            decoded = verifier.verify_and_decode_notification(signed_payload)
            selected_verifier = verifier
            break
        except Exception as exc:
            last_error = exc
    if decoded is None or selected_verifier is None:
        raise AppleStoreVerificationError("apple_notification_signature_verification_failed") from last_error

    notification_type = _enum_value(getattr(decoded, "notificationType", None), getattr(decoded, "rawNotificationType", ""))
    subtype = _enum_value(getattr(decoded, "subtype", None))
    data = getattr(decoded, "data", None)
    transaction = None
    renewal = None
    if data and getattr(data, "signedTransactionInfo", None):
        try:
            transaction = selected_verifier.verify_and_decode_signed_transaction(data.signedTransactionInfo)
            if transaction is None:
                raise ValueError("empty transaction payload")
        except Exception as exc:
            raise AppleStoreVerificationError("apple_notification_transaction_verification_failed") from exc
    if data and getattr(data, "signedRenewalInfo", None):
        try:
            renewal = selected_verifier.verify_and_decode_renewal_info(data.signedRenewalInfo)
            if renewal is None:
                raise ValueError("empty renewal payload")
        except Exception as exc:
            raise AppleStoreVerificationError("apple_notification_renewal_verification_failed") from exc

    product_id = str(
        getattr(transaction, "productId", "")
        or getattr(renewal, "productId", "")
        or ""
    )
    product = PRODUCTS.get(product_id) or {}
    if product_id and not product:
        raise AppleStoreVerificationError("apple_product_not_allowed")
    if transaction and str(getattr(transaction, "bundleId", "") or "") != BUNDLE_ID:
        raise AppleStoreVerificationError("apple_bundle_mismatch")

    transaction_id = str(getattr(transaction, "transactionId", "") or "")
    original_transaction_id = str(
        getattr(transaction, "originalTransactionId", "")
        or getattr(renewal, "originalTransactionId", "")
        or transaction_id
    )
    if transaction_id and not transaction_id.isdigit():
        raise AppleStoreVerificationError("apple_transaction_id_invalid")
    if original_transaction_id and not original_transaction_id.isdigit():
        raise AppleStoreVerificationError("apple_transaction_id_invalid")

    app_account_token = str(
        getattr(transaction, "appAccountToken", "")
        or getattr(renewal, "appAccountToken", "")
        or ""
    ).lower()
    auto_renew_status = getattr(renewal, "autoRenewStatus", None)
    will_renew = None if auto_renew_status is None else getattr(auto_renew_status, "value", auto_renew_status) == 1
    environment = _enum_value(getattr(data, "environment", None), getattr(data, "rawEnvironment", "")) if data else ""

    return VerifiedAppleNotification(
        notificationType=notification_type or "UNKNOWN",
        subtype=subtype,
        notificationUUID=str(getattr(decoded, "notificationUUID", "") or ""),
        signedDate=_millis_to_iso(getattr(decoded, "signedDate", None)),
        environment=environment,
        productId=product_id,
        transactionId=transaction_id,
        originalTransactionId=original_transaction_id,
        appAccountToken=app_account_token,
        kind=str(product.get("kind") or ""),
        points=int(product.get("points") or product.get("monthlyPoints") or 0),
        plan=str(product.get("plan") or ""),
        expiresDate=_millis_to_iso(getattr(transaction, "expiresDate", None)),
        purchaseDate=_millis_to_iso(getattr(transaction, "purchaseDate", None)),
        originalPurchaseDate=_millis_to_iso(getattr(transaction, "originalPurchaseDate", None)),
        revocationDate=_millis_to_iso(getattr(transaction, "revocationDate", None)),
        willRenew=will_renew,
        gracePeriodExpiresDate=_millis_to_iso(getattr(renewal, "gracePeriodExpiresDate", None)),
        status=getattr(data, "rawStatus", None) if data else None,
    )


def verify_transaction(signed_transaction, expected_auth_user_id, verifiers=None):
    signed_transaction = str(signed_transaction or "").strip()
    expected_auth_user_id = str(expected_auth_user_id or "").strip().lower()
    if signed_transaction.count(".") != 2:
        raise AppleStoreVerificationError("invalid_signed_transaction")
    if not expected_auth_user_id:
        raise AppleStoreVerificationError("apple_account_token_required")

    decoded = None
    last_error = None
    for verifier in verifiers or _default_verifiers():
        try:
            decoded = verifier.verify_and_decode_signed_transaction(signed_transaction)
            break
        except Exception as exc:
            last_error = exc
    if decoded is None:
        raise AppleStoreVerificationError("apple_signature_verification_failed") from last_error

    product_id = str(getattr(decoded, "productId", "") or "")
    product = PRODUCTS.get(product_id)
    if not product:
        raise AppleStoreVerificationError("apple_product_not_allowed")
    if str(getattr(decoded, "bundleId", "") or "") != BUNDLE_ID:
        raise AppleStoreVerificationError("apple_bundle_mismatch")
    if getattr(decoded, "revocationDate", None) is not None:
        raise AppleStoreVerificationError("apple_transaction_revoked")

    app_account_token = str(getattr(decoded, "appAccountToken", "") or "").lower()
    if app_account_token != expected_auth_user_id:
        raise AppleStoreVerificationError("apple_account_token_mismatch")
    transaction_id = str(getattr(decoded, "transactionId", "") or "")
    original_transaction_id = str(getattr(decoded, "originalTransactionId", "") or transaction_id)
    if not transaction_id.isdigit() or not original_transaction_id.isdigit():
        raise AppleStoreVerificationError("apple_transaction_id_invalid")

    environment = getattr(decoded, "environment", None)
    environment_value = getattr(environment, "value", None) or str(environment or "")
    return VerifiedAppleTransaction(
        transactionId=transaction_id,
        originalTransactionId=original_transaction_id,
        productId=product_id,
        appAccountToken=app_account_token,
        environment=environment_value,
        kind=product["kind"],
        points=int(product.get("points") or product.get("monthlyPoints") or 0),
        plan=str(product.get("plan") or ""),
        expiresDate=_millis_to_iso(getattr(decoded, "expiresDate", None)),
        purchaseDate=_millis_to_iso(getattr(decoded, "purchaseDate", None)),
        originalPurchaseDate=_millis_to_iso(getattr(decoded, "originalPurchaseDate", None)),
    )
