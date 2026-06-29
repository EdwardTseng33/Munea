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
| `/app-profile` | GET/POST | Account, family group, primary person, companion profile aggregate | required | `accounts`, `persons`, `family_groups`, `family_memberships`, `companion_profiles` |
| `/companion-profile` | GET/POST | Active companion identity for current person | required | `companion_profiles` |
| `/family-members` | GET/POST/PATCH | Invite/list/update family contacts | required | `family_memberships`, `persons` |
| `/routine-reminders` | GET/POST/PATCH | Routine and medication reminders | required | `routine_reminders` |

Prototype coverage:

- `/app-profile`
- `/companion-profile`

Missing:

- family invite/update route.
- reminder CRUD route.

### Voice, Avatar, And Memory

| Endpoint | Method | Purpose | Auth | Production source |
|---|---|---|---|---|
| `/voice-session` | POST | Create a voice provider session | required | `voice_sessions`, provider token service |
| `/voice-note` | POST | Recorded voice fallback | required | object storage + `voice_sessions` |
| `/chat` | POST | Current fallback chat | required | AI provider + `conversation_summaries` |
| `/avatar-session` | POST | Select Avatar runtime/provider and entitlement gate | required | `entitlements`, `usage_ledger`, Avatar provider |
| `/conversation-summary` | POST | Store memory summary, not raw transcript by default | required | `conversation_summaries` |
| `/product-event` | POST | Record product analytics events without raw transcript text | required | `product_events` |

Prototype coverage:

- `/voice-session`
- `/voice-note`
- `/chat`
- `/avatar-session`

Missing:

- memory summary persistence.
- cost and usage ledger integration.

### Subscription And Entitlements

| Endpoint | Method | Purpose | Auth | Production source |
|---|---|---|---|---|
| `/entitlements` | GET | Current plan and feature gates | required | `subscription_ledger`, `usage_ledger` |
| `/subscription-event` | POST | StoreKit / App Store Server Notifications / RevenueCat webhook | server only | verified signed event |
| `/purchase-restore` | POST | Reconcile client restore result with backend | required | App Store Server API |

Prototype coverage:

- `/entitlements`
- `/subscription-event`

Production rule:

- Client purchase state is a signal, not authority.
- Entitlements change only after server verification.

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
| `/admin/usage` | Voice/avatar/cost usage lookup |
| `/admin/privacy-requests` | Track export/deletion requests |
| `/admin/safety-events` | Review high-risk events |
| `/admin/audit-events` | Review admin actions |
| `/admin/north-star` | Product health dashboard data |

Admin access should use admin-only roles stored outside user-editable metadata. Sensitive mutations should run through backend service functions and write to `audit_events`.

Prototype coverage:

- `/admin/north-star` exists, but it is closed unless `MUNEA_ADMIN_API_TOKEN` is configured and sent in `X-Munea-Admin-Token`.

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

- voice/S2S companion session reaches minimum duration or successful turn count.
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

## Admin Console MVP

Build after the backend contracts are stable, before public App Store launch.

MVP modules:

1. North Star dashboard.
2. Account and family lookup.
3. Subscription and entitlement lookup.
4. Voice/avatar usage and cost.
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
- [x] Add privacy requests adapter for export/deletion request creation and listing.

### Phase C: Auth And Family

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
