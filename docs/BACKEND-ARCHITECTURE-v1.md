# Munea Backend Architecture v1

Updated: 2026-06-29

Purpose: define the first production backend architecture for Munea before App Store/TestFlight, subscriptions, family care loops, real-time voice, Avatar usage, and admin operations become hard to change.

## Executive Decision

Munea should now move from prototype JSON stores to a production backend shape.

Current state:

- Local JSON stores keep the prototype runnable.
- Supabase schema draft exists in `supabase/sql/001_initial_munea_schema.sql`.
- Supabase-ready backend adapter exists in `engine/supabase_adapter.py`.
- Supabase adapter now covers companion/app profile, subscription/usage ledger reads, billing save mapping, and privacy request creation/listing with JSON fallback.
- Backend startup can load private values from `engine/.env.local`, and `npm run supabase:doctor` validates Supabase wiring without printing backend secrets.
- `/avatar-session` now provides the backend contract for selecting Avatar runtime mode, falling back to `2d-viseme`, and recording premium Avatar minute usage.
- `/product-event` now records product analytics events, and `/admin/north-star` provides the first token-gated North Star summary contract.
- The web prototype now emits safe product events for Chat start/completion, voice turns, voice-note upload, Avatar session start/completion, and routine completion. It does not send raw transcript text to analytics.
- `/account-bootstrap` now defines the backend-owned account/member/person/family/companion creation contract for the future Supabase Auth or Apple Sign-In flow. In production it requires a verified `auth.users.id`; local prototype fallback can preview/create a JSON store.
- `/auth-status` now defines the backend token verification contract. Supabase mode verifies `Authorization: Bearer <access_token>` against Supabase Auth and derives the real `auth.users.id`; local developer bypass is env-gated and marked as developer mode.
- `/ai/brain-status`, `/memory/extract`, `/memory/retrieve`, and `/guardian/evaluate` now define the first AI service contracts for three-brain routing, memory lifecycle, and Guardian risk policy.
- `/persona/context` now defines the companion persona context contract, so six-character identity, user naming, voice/avatar assets, style directives, and retrieved relationship state are available to the AI service layer instead of living only in the UI.
- `/voice-session` now returns the persona-aware `aiContext` and speech-first session context needed by the future Gemini Live path.
- `/butler/post-turn` now defines the background review contract for structured memory extraction and `companion_relationship_states` updates without retaining raw transcripts by default; the next context build reads those states back into persona delivery.
- The Supabase adapter now includes `memory_items` load/save mapping, so Butler memory extraction can persist structured memories through the backend when Supabase env is configured, with JSON fallback for local development.
- The perception design is now domain-aware rather than movie-specific: books, travel, outings, exercise, finance, video entertainment, music/audio, food, news, and wisdom/reflection topics share the same anti-fabrication contract.
- `/perception/snapshot` now provides the API and adapter contract for storing/listing real-world perception facts through Supabase `perception_snapshots` or JSON fallback.
- The web onboarding/settings flow now calls the `/account-bootstrap` contract through a one-time browser bootstrap flag. Local JSON mode can create the prototype account graph immediately; Supabase mode returns `auth_user_required` until a verified Auth / Apple Sign-In bearer token is available.
- Auth/onboarding v1 is now locked in `docs/AUTH-ONBOARDING-ARCHITECTURE-v1.md`: v1 providers are Sign in with Apple, Google, and email magic link/OTP fallback; Facebook is intentionally out of v1.
- Billing/credits v1 is now locked in `docs/BILLING-CREDITS-ENTITLEMENT-v1.md`: the product ladder is Free / Plus / Premium / Concierge, subscriptions are the trust-building base, credits are reserved for expensive/bursty add-ons, and `supabase/sql/006_billing_credits_foundation.sql` adds the first credit wallet and entitlement policy tables.
- `/credits/balance`, `/credits/grant`, and `/credits/consume` now define the local runtime credit wallet API with JSON fallback, idempotent grants/consumes, included-first deduction, and insufficient-credit fallback.
- `/avatar-session` now uses the deduction order for premium Avatar: included monthly Avatar allowance first, then credits for overage, then `2d-viseme` fallback.
- Supabase adapter now maps runtime credits to `credit_wallets`, `credit_transactions`, and `credit_ledger`, while keeping JSON fallback for local development.
- Production API contracts are partially represented in `engine/server.py`.
- Admin and analytics are not built yet, but their data model must be planned now.

Backend v1 goal:

```text
Capacitor App -> Munea API -> Supabase Postgres + RLS
                         -> AI/Voice/Avatar providers
                         -> App Store subscription verification
                         -> Admin and North Star dashboards
```

Do not build more product features that create important data before the account, family, entitlement, audit, and analytics contracts are stable.

## Core Backend Principles

1. The backend is the source of truth.
2. The app can render state, but it must not own paid status, Avatar minutes, family permissions, deletion/export status, or safety decisions.
3. Every user row must be scoped by `account_id`; family/person rows also carry `person_id` or `family_group_id` where relevant.
4. Supabase public tables must have RLS enabled and explicit role grants.
5. Never authorize using user-editable `user_metadata`.
6. Never expose service role keys to Capacitor or browser code.
7. Conversation continuity matters, but raw transcripts should not become the default retained record.
8. Every manual admin operation must create an audit event.

## API Surface v1

### Auth And Onboarding

Munea should use progressive account creation:

```text
guest companion trial -> auth gate when persistence/family/health/subscription is needed -> account bootstrap after verified auth
```

Auth provider decision:

- v1: Sign in with Apple, Google, email magic link/OTP fallback.
- not v1: Facebook and email password.
- future: phone OTP if Taiwan older-user support requires it.

Production auth rule:

- frontend may hold a Supabase session, but backend APIs must receive `Authorization: Bearer <access_token>`.
- backend must verify the token through `/auth-status` / shared auth context helpers and derive the real `auth.users.id`.
- production `/account-bootstrap` must not trust `authUserId` supplied in the JSON body.
- user-editable metadata must not drive authorization.
- Current backend foundation: setting `MUNEA_REQUIRE_AUTH=1` makes sensitive POST endpoints require verified bearer auth. Local prototype mode remains permissive by default so design/dev previews do not break before the iOS auth flow is wired.
- Admin endpoints remain separate and require `MUNEA_ADMIN_API_TOKEN` through `X-Munea-Admin-Token`.
- Billing mutation routes are separated from normal user bearer auth: direct credit grants/consumption and entitlement saves require `X-Munea-Admin-Token` when `MUNEA_REQUIRE_AUTH=1`; subscription provider events may use `X-Munea-Provider-Token` from trusted webhook infrastructure.
- Successful privileged billing mutations append audit events to Supabase `audit_events` when available, with local ignored JSON fallback for prototype mode.

All production API responses should use this envelope:

```json
{
  "ok": true,
  "data": {}
}
```

Errors:

```json
{
  "ok": false,
  "error": {
    "code": "invalid_request",
    "message": "Request could not be processed",
    "requestId": "req_..."
  }
}
```

### Profile And Family

| Endpoint | Method | Purpose | Auth | Production source |
|---|---|---|---|---|
| `/auth-status` | POST | Verify bearer token and return safe auth context | optional/required by caller | Supabase Auth |
| `/app-profile` | GET/POST | Account, family group, primary person, companion profile aggregate | required | `accounts`, `persons`, `family_groups`, `family_memberships`, `companion_profiles` |
| `/account-bootstrap` | POST | Create first account/member/person/family/companion rows after auth | required | `accounts`, `account_members`, `persons`, `family_groups`, `family_memberships`, `companion_profiles` |
| `/family/invitations` | POST | Create/list/update family invite links and six-digit join codes | required | `family_invitations` |
| `/consent-records` | POST | List, grant, and revoke family sharing / AI capability consent records | required | `consent_records` |
| `/companion-profile` | GET/POST | Active companion identity for current person | required | `companion_profiles` |
| `/family-members` | GET/POST/PATCH | Invite/list/update family contacts | required | `family_memberships`, `persons` |
| `/routine-reminders` | GET/POST/PATCH | Routine and medication reminders | required | `routine_reminders` |

Prototype coverage:

- `/app-profile`
- `/account-bootstrap`
- `/family/invitations`
- `/family-members`
- `/consent-records`
- `/companion-profile`
- `/routine-reminders`

Frontend bridge:

- `web/onboarding.html` saves the selected companion template/name, marks onboarding complete, and attempts `/account-bootstrap`.
- `web/src/app.js` retries account bootstrap on app init when onboarding is complete or Auth was previously required.
- Companion name/template edits update `/companion-profile`; they do not recreate the account graph after bootstrap succeeds.
- Medication and visit reminder settings now save/archive through `/routine-reminders` and hydrate active reminders back into local UI state at startup, while localStorage remains the offline/static-preview fallback.
- Supabase production bootstrap must be triggered only after verified Auth, not from user-editable local metadata.

Missing:

- production UI binding for family membership role updates.

### Voice, Avatar, And Memory

| Endpoint | Method | Purpose | Auth | Production source |
|---|---|---|---|---|
| `/voice-session` | POST | Create a voice provider session with persona-aware context | required | `voice_sessions`, provider token service |
| `/voice-note` | POST | Recorded voice fallback | required | object storage + `voice_sessions` |
| `/chat` | POST | Current fallback chat with persona + memory + perception + Guardian context composition | required | AI provider + `conversation_summaries` |
| `/avatar-session` | POST | Select Avatar runtime/provider and entitlement gate | required | `entitlements`, `usage_ledger`, Avatar provider |
| `/ai/brain-status` | POST | Return current Reflex/Butler/Guardian model service plan | admin/dev initially | `ai_brain_runs`, config |
| `/persona/context` | POST | Return selected companion persona context for Reflex/Butler/Guardian composition | required | `companion_profiles`, persona template config, `companion_relationship_states` |
| `/memory/extract` | POST | Extract structured memory candidates from conversation context | required | `memory_items` |
| `/memory/retrieve` | POST | Retrieve scoped memories for the next interaction | required | `memory_items`, vector/graph later |
| `/butler/post-turn` | POST | Background post-turn memory extraction and relationship-state update | required | `memory_items`, `companion_relationship_states`, `product_events` |
| `/guardian/evaluate` | POST | Evaluate safety risk and response policy | required | `safety_events`, `ai_brain_runs` |
| `/perception/snapshot` | POST | Store/list real-world perception facts for recommendations | required | `perception_snapshots` |
| `/conversation-summary` | POST | Store memory summary, not raw transcript by default | required | `conversation_summaries` |
| `/product-event` | POST | Record product analytics events without raw transcript text | required | `product_events` |

Prototype coverage:

- `/voice-session`
- `/voice-note`
- `/chat`
- `/avatar-session`
- `/ai/brain-status`
- `/persona/context`
- `/memory/extract`
- `/memory/retrieve`
- `/conversation-summary`
- `/butler/post-turn`
- `/guardian/evaluate`

Missing:

- vector/temporal graph retrieval.
- cost and usage ledger integration.

### Subscription And Entitlements

| Endpoint | Method | Purpose | Auth | Production source |
|---|---|---|---|---|
| `/entitlements` | GET | Current plan and feature gates | required | `subscription_ledger`, `usage_ledger` |
| `/subscription-event` | POST | StoreKit / App Store Server Notifications / RevenueCat webhook | server only | verified signed event |
| `/purchase-restore` | POST | Reconcile client restore result with backend | required | App Store Server API |
| `/credits/balance` | POST | Return wallet balances for safe UI display | required | `credit_wallets`, `credit_ledger` |
| `/credits/consume` | POST | Consume credits for costly Avatar/add-on features | backend/internal | `credit_transactions`, `credit_ledger` |
| `/credits/grant` | POST | Grant included, purchased, promo, B2B, or admin credits | webhook/admin only | `credit_transactions`, `credit_wallets`, `audit_events` |
| `/credits/refund-reversal` | POST | Reverse credits after refund/revoke events | webhook/admin only | `credit_transactions`, `credit_ledger`, `audit_events` |

Prototype coverage:

- `/entitlements`
- `/subscription-event`
- `/credits/balance`
- `/credits/grant`
- `/credits/consume`

Production rule:

- Client purchase state is a signal, not authority.
- Entitlements change only after server verification.
- In auth-required mode, `/subscription-event`, `/credits/grant`, `/credits/consume`, and entitlement save/replace actions are privileged writes and cannot be performed by a normal app bearer token alone.
- Privileged billing writes should leave audit events (`entitlements_changed`, `subscription_event_accepted`, `credits_granted`, `credits_consumed_directly`) so Admin can trace who changed access or wallet balance.
- Basic companionship, routine reminders, privacy controls, and safety/referral flows must not depend on purchased credits.
- Expensive Avatar/GPU add-ons should consume included monthly allowance first, then purchased credits, then degrade gracefully to lower-cost mode.

### Data Rights And Trust

| Endpoint | Method | Purpose | Auth | Production source |
|---|---|---|---|---|
| `/privacy-export` | POST | Request/export user data package | required + reauth | `privacy_requests`, async export job |
| `/account-deletion` | POST | Request/check account deletion | required + reauth | `privacy_requests`, deletion job |
| `/audit-events` | GET | Internal audit lookup | admin only | `audit_events` |

Prototype coverage:

- `/privacy-export`
- `/account-deletion`

Missing:

- async jobs.
- reauth enforcement.
- backend deletion worker.

### Admin And Operations

Admin APIs should not be available to normal app clients.

| Endpoint | Purpose |
|---|---|
| `/admin/accounts` | Search account, family, primary user |
| `/admin/subscriptions` | Inspect entitlements and subscription ledger |
| `/admin/usage` | Product usage, event counts, voice/avatar minutes, North Star composition, and developer/test exclusion summary |
| `/admin/credits` | Subscription, entitlement, usage ledger, credit wallets, and recent credit ledger lookup |
| `/admin/conversation-summaries` | Review summary-only companion memory records, tags, and safety-relevant counts without raw transcripts |
| `/admin/privacy-requests` | Track export/deletion requests |
| `/admin/safety-events` | Review high-risk events |
| `/admin/audit-events` | Review admin actions |
| `/admin/north-star` | Product health dashboard data |

Admin access should use admin-only roles stored outside user-editable metadata. Sensitive mutations should run through backend service functions and write to `audit_events`.

Prototype coverage:

- `/admin/north-star`, `/admin/usage`, `/admin/credits`, `/admin/conversation-summaries`, `/admin/privacy-requests`, and `/admin/safety-events` exist, but they are closed unless `MUNEA_ADMIN_API_TOKEN` is configured and sent in `X-Munea-Admin-Token`.

## Supabase Data Model v1

Already drafted in `supabase/sql/001_initial_munea_schema.sql`:

- `accounts`
- `account_members`
- `persons`
- `family_groups`
- `family_memberships`
- `companion_profiles`
- `routine_reminders`
- `voice_sessions`
- `conversation_summaries`
- `safety_events`
- `subscription_ledger`
- `usage_ledger`
- `privacy_requests`
- `audit_events`

Analytics/admin foundation added in `supabase/sql/003_analytics_admin_foundation.sql`:

- `product_events`
- `daily_user_metrics`
- `voice_session_metrics`
- `reminder_events`
- `family_interaction_events`
- `cost_ledger`
- `admin_notes`

These tables are the data base for the first Admin MVP and North Star dashboard. They should be applied after the initial schema and demo bootstrap seed.

AI memory/service foundation added in `supabase/sql/004_ai_memory_service_foundation.sql`:

- `memory_items`
- `perception_snapshots`
- `ai_brain_runs`

These tables support long-term companion memory, time/weather/topic perception, Guardian decisions, model cost tracking, and privacy export/deletion requirements.

Perception snapshots must be domain-aware. `current_topic` is a generic fallback, but the schema also supports `book_context`, `travel_context`, `local_activity_context`, `exercise_context`, `finance_context`, `media_context`, `food_context`, `news_context`, and `wisdom_context`. `media_context` covers broad video entertainment such as Korean dramas, Japanese dramas, Chinese dramas, Taiwan dramas, Netflix/streaming series, films, documentaries, variety, and anime.

Companion persona layer foundation added in `supabase/sql/005_companion_persona_layer.sql`:

- `companion_persona_templates`
- `companion_relationship_states`

These tables separate product-owned persona templates from user-owned relationship state. This keeps the six characters durable while allowing a specific user and companion to grow a shared style over time.

Billing credits foundation added in `supabase/sql/006_billing_credits_foundation.sql`:

- `entitlement_policy_versions`
- `credit_wallets`
- `credit_transactions`
- `credit_ledger`

These tables keep paid access backend-authoritative while allowing Munea to support App Store subscriptions, RevenueCat or StoreKit provider events, monthly included credits, purchased credits, refund/reversal handling, idempotency, and admin audit trails. Credits are a cost-control and add-on mechanism, not the identity of the core companion product.

## RLS And Permission Matrix

| Data | User access | Family access | Admin access |
|---|---|---|---|
| account profile | active account member | active account member | admin backend only |
| person profile | account member | scoped by family/account | admin backend only |
| companion profile | account member | account member if permitted | admin backend only |
| routine reminders | account member | caregiver/family role later | admin backend only |
| voice sessions | owner/family scoped summary | summary only unless permitted | admin backend only |
| conversation summaries | account scoped | limited summary later | admin backend only |
| safety events | account scoped | family notification scoped | admin backend only |
| subscription ledger | account owner/admin in app | no direct family edit | admin backend only |
| credit wallets/ledger | account owner/admin in app | no direct family edit unless payer role is added | admin backend only |
| privacy requests | account owner | no family deletion unless owner | admin backend only |
| audit events | no normal write | no normal write | admin backend only |

RLS baseline:

- Use `TO authenticated`.
- Combine with `account_members.user_id = auth.uid()`.
- Use `USING` and `WITH CHECK` for writable policies.
- Revoke `anon` for user data tables.
- Grant `authenticated` explicitly where Data API should be usable.

## North Star Metrics

North Star:

```text
Weekly Meaningful Companion Days
```

Definition:

> Number of user-days in a week where a primary user completes at least one meaningful companion interaction.

A meaningful companion day is true when at least one of the following occurs:

- voice/S2S companion session reaches minimum duration or successful turn count. Current prototype threshold: `durationMs >= 60000` or `turnCount >= 3`.
- routine/reminder is acknowledged or completed.
- family interaction is sent, viewed, or replied.
- AI companion creates a useful care summary without triggering unsafe behavior.

Admin dashboard first screen:

| Card | Why it matters |
|---|---|
| Weekly Meaningful Companion Days | North Star |
| 7-day retained primary users | Habit formation |
| Voice/S2S success rate | Core experience reliability |
| AI cost per active user | Unit economics |
| Free-to-paid conversion | Subscription viability |

Supporting dashboards:

- Companion loop: sessions, minutes, success/fallback/interruption.
- Health routine loop: reminder completion, missed routines, proactive check-ins.
- Family loop: invitations, accepted invites, dashboard views, replies, safety notification delivery.
- Subscription loop: trial, paid conversion, renewal, churn, restore issues.
- Cost loop: model tokens, TTS minutes, Avatar minutes, RunPod cost, cost per meaningful day.
- Trust loop: account deletion, data export, safety event response time, API error rate.

## Analytics Event Model

Recommended `product_events` shape:

```text
id
account_id
person_id
family_group_id
event_name
event_time
source
session_id
properties jsonb
created_at
```

Core events:

- `app_opened`
- `onboarding_started`
- `onboarding_completed`
- `companion_profile_updated`
- `voice_session_started`
- `voice_session_completed`
- `voice_session_fallback_used`
- `routine_reminder_sent`
- `routine_reminder_completed`
- `family_invite_sent`
- `family_invite_accepted`
- `family_dashboard_viewed`
- `subscription_started`
- `subscription_renewed`
- `subscription_cancelled`
- `avatar_session_started`
- `avatar_session_completed`
- `privacy_export_requested`
- `account_deletion_requested`
- `safety_event_created`

Do not put raw transcript text in analytics events.

Developer and internal usage exclusion:

- Developer mode, QA, internal ops, and demo/test accounts must be excluded from operating dashboards.
- Frontend developer mode sends `analyticsExcluded: true`, `developerMode: true`, and `accountType: developer`.
- `north_star_summary` excludes developer/internal/test/QA/ops events before calculating meaningful days, active people, voice success, Avatar usage, family interactions, and routine completions.
- `/admin/usage` uses the same exclusion logic so internal testing does not inflate usage, conversion, or engagement dashboards.
- Backend env can exclude known accounts, people, or sessions:

```text
MUNEA_ANALYTICS_EXCLUDED_ACCOUNT_IDS=...
MUNEA_ANALYTICS_EXCLUDED_PERSON_IDS=...
MUNEA_ANALYTICS_EXCLUDED_SESSION_IDS=...
```

## Admin Console MVP

Build after the backend contracts are stable, before public App Store launch.

MVP modules:

1. North Star dashboard.
2. Account and family lookup.
3. Subscription and entitlement lookup.
4. Credits wallet, usage, Avatar cost, and provider event lookup.
5. Privacy requests.
6. Safety events.
7. Audit events.

Technical path:

- Fastest start: Supabase dashboard + SQL views for internal inspection.
- Productized MVP: internal web app with Supabase Auth, admin role checks, and backend-only mutation functions.

Do not build a broad CRM first. The admin MVP should answer: what happened, who is affected, what did it cost, is entitlement correct, is user data safe?

## Development Phases

### Phase A: Backend Contract Lock

- Finalize `BACKEND-ARCHITECTURE-v1.md`.
- Keep smoke checks for API and schema contracts.
- Apply Supabase SQL to a real project.
- Decide StoreKit 2 vs RevenueCat.

### Phase B: Database Adapter

- [x] Add backend config for JSON fallback vs Supabase.
- [x] Implement Supabase adapter for companion profile.
- [x] Implement Supabase app profile aggregate adapter for account, person, family group, family memberships, and companion profile.
- [x] Keep JSON fallback active until Supabase env and seeded ids are configured.
- [x] Add entitlements adapter for subscription and usage ledger reads/writes.
- [x] Add credits adapter for credit wallet, transaction, and ledger reads/writes.
- [x] Add privacy requests adapter for export/deletion request creation and listing.

### Phase C: Auth And Family

- [x] Add backend auth verification helper and `MUNEA_REQUIRE_AUTH=1` gate for sensitive endpoints.
- Add Supabase Auth.
- Create account/member bootstrap flow.
- Add family invitation and membership roles.
- Make Settings account/privacy/subscription entries real.

### Phase D: Analytics And Admin

- Add `product_events` and metric rollups.
- Build North Star SQL views.
- Add internal admin dashboard MVP.
- Add audit logging for admin mutations.

### Phase E: App Store Readiness

- Signed subscription event verification.
- Account deletion worker.
- Data export worker.
- Privacy policy and App Store privacy labels.
- Real iPhone microphone/playback/push/restore-purchase QA.
