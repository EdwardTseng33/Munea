# Munea Billing, Credits, And Entitlement v1

> Updated: 2026-07-01
> Scope: subscription tier names, App Store entitlement, credits wallet direction, usage/cost ledger, and the first service architecture for paid Munea.

## Decision

Munea will use this subscription ladder:

```text
Free -> Plus -> Premium -> Concierge
```

User-facing labels:

| Plan id | English label | Chinese label | Product role |
|---|---|---|---|
| `free` | Munea Free | 免費版 | Trial and basic companion access |
| `plus` | Munea Plus | Plus 進階版 | More daily utility, family support, and higher voice/AI allowance |
| `premium` | Munea Premium | Premium 尊享版 | Premium AI care features, deeper memory, and real-time Avatar allowance |
| `concierge` | Munea Concierge | Concierge 專屬照護版 | Highest-touch service layer for heavy Avatar, family care, priority support, and future hardware/service bundles |

`Concierge` is intentional. It should feel like a dedicated care companion and service layer, not a gamer-style, storage-style, or generic "Ultra" plan.

## Previous Planning Review

The repo already had several billing directions before this decision:

| Prior file | Earlier direction | Current interpretation |
|---|---|---|
| `docs/商業模式-點數制-v2-2026-06-27.md` | Freemium + subscription + credits; CFO warning that basic chat should not feel metered | Keep the warning. Basic companionship should not feel like every sentence costs coins. |
| `docs/定案-商業模式與開發路線圖-2026-06-27.md` | Four paid/credit buckets, one wallet, dynamic face usage consumes credits | Keep the two-bucket wallet idea, but revise plan names and avoid making credits the whole product identity. |
| `docs/商業模式-v3-成本現實與訂價修正-2026-06-27.md` | Real-time voice/avatar cost can break unlimited pricing if not gated | Keep cost guardrails through usage ledger, allowance, fallback, and credits. |
| `docs/訂價重算-Gemini成本-2026-06-28.md` | Gemini Live assumption improves margin but still requires usage calibration | Keep cost assumptions as provisional. Actual model/avatar cost must be measured after live integration. |
| `docs/體檢報告-城堡四方-2026-06-27.md` | B2C uses Apple IAP; RevenueCat is a reasonable first subscription state layer; entitlement service must be multi-source | Keep RevenueCat/StoreKit as provider layer, but Munea backend remains entitlement source of truth. |

Final v1 stance:

```text
Subscription = trust-building base access and predictable care service
Credits = expensive, bursty, optional, or concierge add-on capacity
```

This is more appropriate for an AI health-care companion than a pure game-credit model.

## Current Implementation Status

Implemented now:

- `POST /entitlements` returns the backend-owned subscription state, entitlements, and usage ledger.
- `subscription_ledger` stores plan state, provider, product id, transaction id, renewal, and entitlement JSON.
- `usage_ledger` stores monthly usage by metric.
- `cost_ledger` stores provider/service cost observations for analytics/admin.
- `POST /avatar-session` gates premium Avatar modes and records premium Avatar minutes.
- `POST /credits/balance`, `POST /credits/grant`, and `POST /credits/consume` define the local prototype runtime contract for wallet balance, idempotent grants, and graceful insufficient-credit fallback.
- `/avatar-session` now checks credits when premium Avatar monthly allowance is exhausted and consumes overage credits only on completed premium sessions.
- Local fallback uses `engine/billing_store.json`.
- Local credits fallback uses `engine/credits_store.json`.

Added as schema foundation:

- `supabase/sql/006_billing_credits_foundation.sql`
- `credit_wallets`
- `credit_ledger`
- `credit_transactions`
- `entitlement_policy_versions`

Not implemented yet:

- App Store Connect products.
- RevenueCat / StoreKit SDK integration.
- Signed App Store Server API or RevenueCat webhook verification.
- Restore purchases UX.
- Supabase adapter for runtime credits is implemented for `credit_wallets`, `credit_transactions`, and `credit_ledger`.
- Refund/revoke handling for credits.
- Admin console screens for manual adjustment.

## Service Architecture

Paid access should flow through a backend entitlement service:

```text
iOS StoreKit / RevenueCat
  -> verified server event
  -> subscription_ledger
  -> entitlement policy
  -> usage_ledger + credit_wallets
  -> /entitlements response
  -> app feature gates
```

Core rules:

- The frontend can display plan state but cannot grant paid access.
- Subscription and credit state must be account-scoped.
- Family and care-recipient usage can be person-scoped when needed.
- Billing events must not contain raw transcript text.
- Admin changes must write `audit_events`.
- Developer, QA, internal, and demo accounts must be excluded from operating dashboards.

## Plan Shape

Exact quotas and prices are not final. Treat the values below as product-contract placeholders.

| Entitlement | Free | Plus | Premium | Concierge |
|---|---:|---:|---:|---:|
| Voice companion | limited | yes | yes | yes |
| Routine reminders | basic | yes | yes | yes |
| Family dashboard | limited | expanded | expanded | concierge |
| Family members max | 2 | 4 | 8 | custom/high |
| Long-term memory depth | basic | standard | deeper | highest |
| Reflex model priority | basic | standard | priority | highest practical tier |
| Butler review depth | basic | standard | deeper | concierge review options |
| Real-time premium Avatar | no | limited trial only | yes | yes |
| Premium Avatar minutes | 0 | small/month | monthly grant | large/custom grant |
| Future hardware/service bundle | no | no | optional | primary target |

## Credits Direction

Credits should be used for:

- extra real-time Avatar / GPU minutes beyond monthly allowance.
- high-cost LiveAvatar or Ditto sessions.
- premium media/avatar rendering if added.
- concierge add-ons, hardware/service bundles, or human-supported care operations if added.

Credits should not be used for:

- basic daily companionship.
- normal family dashboard access.
- routine reminders.
- essential safety/referral flows.
- account deletion, data export, or privacy controls.

## Credit Wallet Model

Munea should keep two credit buckets:

| Bucket | Meaning | Expiry | Why |
|---|---|---|---|
| included_monthly | monthly plan allowance | expires at period end | predictable cost cap for subscriptions |
| purchased | consumable IAP / paid add-on | no normal expiry | avoids trust and consumer-protection risk |

Implementation rules:

- Keep wallet balances server-side only.
- Use idempotency keys for every grant, consume, refund, and reversal.
- Keep immutable ledger rows instead of editing old credit events.
- Store provider transaction ids, but do not store card data.
- If a subscription is refunded or revoked, reverse unused included credits first and then follow App Store/RevenueCat refund policy for purchased credits.

## Deduction Order

When a paid feature has usage cost:

1. Verify auth and account scope.
2. Load backend entitlement.
3. Check feature-specific allowance in `usage_ledger`.
4. Consume monthly included allowance first.
5. Consume purchased credits only after included allowance is exhausted.
6. If no allowance/credits remain, degrade gracefully.
7. For Avatar, degrade to `2d-viseme`, static face, or voice-only instead of ending the conversation.

Prototype Avatar conversion rule:

```text
1 MUNEA_CREDIT = 1 premium Avatar minute
```

This is a placeholder for engineering validation. Final credit-to-minute conversion must be recalibrated after Ditto/LiveAvatar cost tests and App Store price decisions.

No raw transcript text should be stored as part of billing or credit events.

## Backend Source Of Truth

Current source tables:

- `subscription_ledger`
- `usage_ledger`
- `cost_ledger`

Credits foundation tables:

- `credit_wallets`
- `credit_ledger`
- `credit_transactions`
- `entitlement_policy_versions`

Future credit records should include:

- `account_id`
- `person_id` when person-scoped
- `wallet_id`
- `source`: `apple_iap`, `revenuecat`, `promo`, `admin_adjustment`, `refund_reversal`, `b2b_contract`, `included_monthly`
- `direction`: `grant`, `consume`, `expire`, `refund`, `reversal`, `adjustment`
- `amount`
- `balance_after`
- `reason`
- `idempotency_key`
- `provider_transaction_id`
- `created_at`

Every admin adjustment must create an audit event.

## Product Ids

Subscription product ids:

```text
munea.plus.monthly
munea.plus.yearly
munea.premium.monthly
munea.premium.yearly
munea.concierge.monthly
munea.concierge.yearly
```

Consumable credit product ids, if/when credits are added:

```text
munea.credits.small
munea.credits.medium
munea.credits.large
```

Provider mapping can be RevenueCat first, but Munea backend still owns the authoritative entitlement, usage, and credit ledgers.

## API Direction

Current:

- `POST /entitlements`
- `POST /subscription-event`
- `POST /avatar-session`
- `POST /credits/balance`
- `POST /credits/grant`
- `POST /credits/consume`

Next production APIs:

| Endpoint | Purpose | Auth |
|---|---|---|
| `POST /purchase-restore` | reconcile restored App Store purchase with backend | required |
| `POST /credits/refund-reversal` | reverse credits after refund/revoke events | webhook/admin only |

All credit mutations should be server-side only and audit logged.

## Admin And Analytics

Admin MVP must be able to answer:

- Which plan is this account on?
- Which provider granted the entitlement?
- Did the latest App Store/RevenueCat event verify?
- How much voice/avatar usage did the account consume?
- Did the user run out of included allowance or purchased credits?
- Did an admin manually adjust a wallet?
- Are developer/internal/test events excluded from conversion, usage, and North Star metrics?

Recommended Admin modules:

- account subscription lookup.
- credit wallet balance and ledger.
- provider event audit.
- usage/cost summary.
- refund/revoke queue.
- entitlement policy version history.

## App Store And Trust Rules

- Subscription copy must clearly explain what each plan unlocks.
- Restore purchases must be available in app.
- Account deletion must explain what happens to active subscriptions and retained billing records.
- Credits should be described as service credits for premium capacity, not cash, currency, investment value, or gift certificate.
- Purchased credits need legal review before public launch in Taiwan.
- Safety/referral features must not stop working because the user has no credits.

## Implementation Order

1. Lock plan names and entitlement policy. Done.
2. Add credits schema foundation. Done as `006_billing_credits_foundation.sql`.
3. Keep `/entitlements` backend-authoritative. Done for prototype.
4. Add local credit wallet runtime API. Done for prototype.
5. Connect premium Avatar overage to credits. Done for prototype.
6. Add Supabase adapter mapping for credit wallets, transactions, and ledger. Done.
7. Implement StoreKit 2 or RevenueCat purchase/restore in Capacitor iOS.
8. Add signed provider event verification and production webhook validation.
9. Add Admin MVP views before public App Store launch.

## Open Decisions

- Final price points by market.
- Monthly voice allowance by tier.
- Monthly Avatar minutes by tier.
- Whether Plus includes a tiny Avatar trial or only Premium+.
- Whether Concierge is public self-serve, invitation/application only, or later tied to hardware/service packages.
- RevenueCat Virtual Currency timing versus keeping credits in Munea backend only for v1.
- Taiwan legal wording for purchased credits, refund, expiry, and inactive-account handling.
