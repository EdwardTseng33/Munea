# Munea Billing, Credits, and Entitlements

Updated: 2026-07-18 for App `1.0.40 (Build 47)`

This document is the billing source of truth for the current app. Historical plan names such as Premium and Concierge are retired and must not be used by code, migrations, tests, or App Store metadata.

## Current Plan Ladder

```text
Free -> Plus -> Pro
```

| Plan | Customer price | Included points | Family circle |
|---|---:|---:|---:|
| Munea Free | NT$0 | One-time 5-point signup trial | Account owner only |
| Munea Plus monthly | NT$599 | 100 per month | Up to 4 people |
| Munea Plus yearly | NT$5,750 | 100 per month | Up to 4 people |
| Munea Pro monthly | NT$1,199 | 200 per month | Up to 12 people |
| Munea Pro yearly | NT$11,500 | 200 per month | Up to 12 people |

One point is approximately one Voice + Avatar call minute. The server wallet and call-control ledger, not the browser countdown, must enforce the final balance.

## Point Packs

Apple Product IDs are immutable identifiers. Their numeric suffixes are historical and do not equal the current grant.

Pack pricing rule (Edward, 2026-07-17): packs are always priced above the subscription per-minute anchor (NT$6/min), because the subscription price includes product features while packs are pure extra minutes.

| Grant | Price | App Store Product ID |
|---:|---:|---|
| 100 | NT$790 | `net.munea.app.points.200` |
| 300 | NT$2,190 | `net.munea.app.points.500` |
| 600 | NT$4,190 | `net.munea.app.points.1000` |
| 1,000 | NT$6,490 | `net.munea.app.points.1800` |

## Billing Rules

```text
Subscription = base access and trust
Credits = metered Voice + Avatar capacity
```

- Free trial credits are granted once per account with an idempotency key.
- Subscription points are a monthly allowance. Each billing period receives a fresh allowance; unused points expire at the period boundary and never roll into the next period, including for yearly subscriptions.
- Included monthly points are used before purchased points.
- Purchased points accumulate and remain available after a subscription ends while the account remains active.
- Safety, privacy controls, data export, and account deletion are never blocked by points.
- Paid status, grants, balances, and family limits are server-owned values.
- The frontend may display a balance but cannot create paid entitlement by itself.

## Purchase Contract

1. StoreKit 2 returns a signed transaction.
2. The app sends the JWS and transaction ID to `/apple/transaction` with the signed-in account token.
3. The backend verifies Apple signature, bundle ID, Product ID, transaction ID, revocation state, and `appAccountToken` ownership.
4. The backend records an idempotent credit transaction or subscription entitlement.
5. Only after server acceptance does the app finish the StoreKit transaction and refresh the displayed wallet.

The current Product ID mapping lives in `engine/apple_store.py`; browser/native mapping lives in `web/src/store.js` and `ios/App/App/StorePlugin.swift`.

## Data Model

The foundation is created by `supabase/sql/006_billing_credits_foundation.sql`:

- `entitlement_policy_versions`
- `subscription_ledger`
- `usage_ledger`
- `credit_wallets`
- `credit_transactions`
- `credit_ledger`

The current Free / Plus / Pro policy is version 4 in `supabase/sql/019_pricing_plus100_pro200.sql`. Version 3 remains historical migration evidence in `supabase/sql/013_current_app_billing_policy.sql`; migration history must not be rewritten.

## Deduction Order

1. Active `included_monthly` wallet for the current period.
2. Non-expiring `purchased` wallet.
3. Stop the paid call when the server-authoritative balance reaches zero.

Every mutation requires an idempotency key. Apple transaction IDs are provider references and may not be credited twice.

The server derives each allowance window from the verified Apple purchase anchor. When a new period is first observed, it closes the previous `included_monthly` wallet, records any unused amount as expired, and creates one idempotent wallet for the new period. Purchased wallets are never closed by subscription expiry.

## Launch Gates

- ✅ Direct StoreKit transaction signature verification and account binding are implemented.
- ✅ Current Product IDs and grants are covered by automated tests.
- ✅ Restore purchases only restores active subscriptions and re-verifies them on the server.
- ✅ The current Supabase policy migration is defined.
- ❌ Policy version 4 (`019`) still needs an approved backup, migration-ledger entry, application to the Tokyo Supabase project, and a read-only post-apply verification. Its presence in source or the migration manifest is not live-database proof.
- ✅ App Store Server Notifications V2 JWS verification and renewal, expiration, cancellation, grace-period, refund, refund-reversal, and revocation state transitions are implemented with idempotent credit handling.
- ❌ The V2 endpoint still needs Brain deployment, App Store Connect production/Sandbox URL configuration, a TEST notification, and real Sandbox lifecycle acceptance.
- ❌ StoreKit Sandbox purchase, renewal, cancellation, refund, and restore still need real-device acceptance tests.
- ❌ Server-authoritative per-minute call deduction is not yet a completed end-to-end production gate.

No App Store submission may describe these failed gates as complete.
