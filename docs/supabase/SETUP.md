# Munea Supabase Setup

Updated: 2026-07-01

This folder documents the first production database path for Munea.

Current status:

- Supabase account exists.
- Cloud project has been created manually in the Supabase dashboard.
- Repo now contains the initial SQL schema draft at `supabase/sql/001_initial_munea_schema.sql`.
- Repo now contains a deterministic demo bootstrap seed at `supabase/sql/002_demo_bootstrap.sql`.
- Repo now contains analytics/admin foundation SQL at `supabase/sql/003_analytics_admin_foundation.sql`.
- Repo now contains AI memory/service foundation SQL at `supabase/sql/004_ai_memory_service_foundation.sql`.
- Repo now contains companion persona layer foundation SQL at `supabase/sql/005_companion_persona_layer.sql`.
- Repo now contains billing credits foundation SQL at `supabase/sql/006_billing_credits_foundation.sql`.
- Repo now contains family cloud state foundation SQL at `supabase/sql/007_family_cloud_state_foundation.sql`.
- The SQL bootstrap has been tested through the dashboard SQL Editor flow.
- Supabase CLI is not installed in this Windows environment yet, so this is a SQL Editor-ready schema, not an official migration history entry.
- The backend can now load `engine/.env.local` directly, and `npm run supabase:doctor` can validate local Supabase wiring without printing secrets.

## Recommended Project

Use one Supabase project for the first TestFlight backend.

Recommended settings:

- Region: closest stable region to Taiwan users, likely Northeast Asia if available.
- Database password: generated strong password, stored in a password manager only.
- Auth: Sign in with Apple, Google, and email magic link/OTP fallback for v1. Facebook and email password are not v1.
- Exposed schema: `public`.
- Data API: if public tables are not automatically exposed, grant access explicitly and keep RLS enabled.

## First SQL Setup

1. Open Supabase dashboard.
2. Create or open the Munea project.
3. Go to SQL Editor.
4. Paste and run:

```text
supabase/sql/001_initial_munea_schema.sql
```

This schema creates:

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

All public tables have RLS enabled. `anon` is explicitly revoked. `authenticated` gets table grants, then row access is restricted by account membership policies.

## Demo Bootstrap Seed

After `001_initial_munea_schema.sql` succeeds, run:

```text
supabase/sql/002_demo_bootstrap.sql
```

This creates a deterministic backend-test account, primary person, family group, companion profile, free subscription ledger row, usage ledger rows, and a seed audit event.

Then run:

```text
supabase/sql/003_analytics_admin_foundation.sql
```

Then run the AI memory/service foundation:

```text
supabase/sql/004_ai_memory_service_foundation.sql
```

This adds `memory_items`, `perception_snapshots`, and `ai_brain_runs` for Butler/Guardian service design, long-term memory, perception, and model run auditing.

Then run the companion persona layer foundation:

```text
supabase/sql/005_companion_persona_layer.sql
```

This adds `companion_persona_templates` and `companion_relationship_states`. Persona templates keep the six characters as product-owned structured config, while relationship state lets a specific user and selected companion grow a shared style over time.

Then run the billing credits foundation:

```text
supabase/sql/006_billing_credits_foundation.sql
```

This adds `entitlement_policy_versions`, `credit_wallets`, `credit_transactions`, and `credit_ledger`. The v1 plan ladder is Free / Plus / Premium / Concierge. Subscriptions remain the base access model; credits are reserved for expensive or bursty add-ons such as premium Avatar/GPU minutes, and every mutation must be server-side and idempotent.

Then run the family cloud state foundation:

```text
supabase/sql/007_family_cloud_state_foundation.sql
```

This adds the Codex-owned family cloud bridge for `family_invitations`, `consent_records`, `wellbeing_signals`, `family_state_entries`, `family_activities`, and `family_activity_participants`. It also extends `persons` with `auth_user_id`, `region_code`, and `attributes`.

`family_state_entries` is the production bridge for the current `/family/state` local JSON prototype keys: `activities`, `familyFeed`, `meds`, `visit`, `routine`, and `wallet`. This lets the existing app sync path move to Supabase later without changing the user-facing family UI first.

This creates the first Admin/North Star analytics tables:

- `product_events`
- `daily_user_metrics`
- `voice_session_metrics`
- `reminder_events`
- `family_interaction_events`
- `cost_ledger`
- `admin_notes`

Use these backend env values for first Supabase adapter testing:

```text
MUNEA_SUPABASE_ACCOUNT_ID=11111111-1111-4111-8111-111111111111
MUNEA_SUPABASE_PERSON_ID=22222222-2222-4222-8222-222222222222
MUNEA_SUPABASE_FAMILY_GROUP_ID=33333333-3333-4333-8333-333333333333
```

The seed does not require a Supabase Auth user because the local backend adapter uses the service role key. To test authenticated RLS from a client session, edit `demo_user_id` inside `002_demo_bootstrap.sql` and set it to a real `auth.users.id` before running it.

For real onboarding after Supabase Auth or Apple Sign-In, use the backend `/account-bootstrap` contract instead of copying the demo seed. The Supabase adapter requires a verified `auth.users.id` and creates the first `accounts`, `account_members`, `persons`, `family_groups`, `family_memberships`, and `companion_profiles` rows from the backend service-role environment.

Auth/onboarding source of truth:

```text
docs/AUTH-ONBOARDING-ARCHITECTURE-v1.md
```

The v1 product direction is progressive onboarding:

- guest users can choose/name a companion and try a limited local/demo experience.
- sign-in is required for cloud persistence, family, health reminders, Apple Health, subscriptions, premium Avatar, data export, and account deletion.
- production APIs should use `Authorization: Bearer <access_token>` and derive the auth user id server-side.

## RLS Model

Main rule:

```text
auth.uid() must match account_members.user_id for the row's account_id.
```

This means family data is separated by `account_id`. A logged-in user can only see rows for accounts where they are an active member.

Important:

- Do not use `user_metadata` for authorization.
- Do not expose `service_role` to the app.
- Do not grant `anon` access to user data tables.
- Subscription and usage ledger writes should be server-side only.
- Credit wallet writes should be server-side only.
- Data export and account deletion jobs should be server-side only.

## Bootstrap Note

The first account/member/person creation should be handled by backend onboarding logic using server credentials, not by letting any authenticated user create arbitrary account rows directly.

For the local prototype, JSON files still exist:

- `engine/app_profile_store.json`
- `engine/companion_profile.json`
- `engine/billing_store.json`
- `engine/privacy_requests.json`

The migration path is:

```text
local JSON prototype -> Supabase tables -> backend API reads/writes Supabase
```

## Backend Adapter Status

The repo now includes `engine/supabase_adapter.py`.

Current behavior:

- Default backend remains JSON fallback.
- Set `MUNEA_DATABASE_PROVIDER=supabase` plus Supabase URL, service role key, account id, and person id to enable the adapter.
- `/healthz`, `/app-profile`, and `/companion-profile` expose backend status so we can verify whether the process is using JSON fallback or Supabase.
- `/app-profile` can aggregate `accounts`, `persons`, `family_groups`, `family_memberships`, and `companion_profiles` from Supabase when env is complete.

Required backend-only environment values:

```text
MUNEA_DATABASE_PROVIDER=supabase
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
MUNEA_SUPABASE_ACCOUNT_ID=...
MUNEA_SUPABASE_PERSON_ID=...
MUNEA_SUPABASE_FAMILY_GROUP_ID=...
```

Security rule:

- `SUPABASE_SERVICE_ROLE_KEY` must only exist in backend environment files or hosting secrets.
- It must never be copied into `web/`, Capacitor bundles, public JavaScript, screenshots, or chat.

## Environment Variables

Use the template:

```text
docs/supabase/munea-env.example.txt
```

Never commit real Supabase secrets. The publishable/anon key can be used by a public client only after RLS is correct. The service role key must stay on the backend only.

Browser Auth Bridge:

- `web/src/auth.js` expects optional public config at `window.MUNEA_SUPABASE_CONFIG`.
- Use the shape in `web/src/auth-config.example.js`.
- Only the Supabase publishable/anon key belongs in browser config.
- `SUPABASE_SERVICE_ROLE_KEY` must stay backend-only.
- When configured, app/onboarding API calls send `Authorization: Bearer <access_token>` for the next backend verification step.

Developer mode and analytics exclusion:

- Local testing can use `window.MUNEA_DEV_CONFIG` from `web/src/auth-config.example.js`.
- Developer mode is off by default and should only be enabled in local/private development builds.
- `autoSignIn` can create a local developer session for fast testing.
- `skipOnboarding` can mark onboarding complete so the developer account can jump directly into the app.
- `analyticsExcluded` should stay `true` for developer, ops, QA, and internal test accounts.
- Frontend product events include `developerMode`, `analyticsExcluded`, and `accountType` so clicks, sign-ins, registrations, voice use, Avatar use, and reminder usage can be separated from real customer metrics.
- Backend North Star summaries exclude events marked as developer/internal/test/QA/ops activity.
- For known accounts or sessions, add ids to backend env:

```text
MUNEA_ANALYTICS_EXCLUDED_ACCOUNT_IDS=...
MUNEA_ANALYTICS_EXCLUDED_PERSON_IDS=...
MUNEA_ANALYTICS_EXCLUDED_SESSION_IDS=...
```

This keeps operational and developer usage available for debugging while preventing it from entering the Admin MVP, North Star, conversion, login, registration, click, and usage statistics.

Create a private local file:

```text
engine/.env.local
```

Minimum values for live backend adapter testing:

```text
GEMINI_API_KEY=...
MUNEA_DATABASE_PROVIDER=supabase
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
MUNEA_ADMIN_API_TOKEN=...
MUNEA_SUPABASE_ACCOUNT_ID=11111111-1111-4111-8111-111111111111
MUNEA_SUPABASE_PERSON_ID=22222222-2222-4222-8222-222222222222
MUNEA_SUPABASE_FAMILY_GROUP_ID=33333333-3333-4333-8333-333333333333
```

Then run:

```powershell
npm run supabase:doctor
```

This reports whether the backend is still using JSON fallback or is fully configured for Supabase. It never prints `SUPABASE_SERVICE_ROLE_KEY`.

When all env values are present and the SQL seed has been applied, run the read-only live check:

```powershell
npm run supabase:doctor:live
```

The live doctor now performs read-only table reachability checks for every expected table, including the 007 family cloud tables. If a table is missing, the output lists the table name without printing `SUPABASE_SERVICE_ROLE_KEY`.
When missing tables map to known repo schema files, the doctor also prints a recommended SQL apply order, for example `supabase/sql/003_analytics_admin_foundation.sql` before later dependent foundation files. Treat this as a database setup checklist: apply the listed files in Supabase SQL Editor, then rerun `npm run supabase:doctor:live`.

## After SQL Runs

Run these checks in Supabase SQL Editor:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
order by tablename;
```

Every Munea table should show `rowsecurity = true`.

Then run:

```sql
select table_name, privilege_type, grantee
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee in ('anon', 'authenticated')
order by table_name, grantee, privilege_type;
```

Expected:

- `authenticated` has normal table privileges.
- `anon` should not have access to Munea user data tables.

## Next Implementation Step

Once the Supabase project is created:

1. Add env values to local backend environment.
2. Add a Supabase database adapter in `engine/`.
3. `/app-profile`, `/companion-profile`, `/entitlements`, `/privacy-export`, and `/account-deletion` now have Supabase adapter paths behind the `MUNEA_DATABASE_PROVIDER=supabase` feature flag, with JSON fallback preserved.
4. Run `002_demo_bootstrap.sql` and copy the demo ids into backend env for first live adapter testing.
5. Keep JSON fallback for local offline prototype only.
