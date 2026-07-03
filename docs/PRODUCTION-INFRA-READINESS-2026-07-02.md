# Munea Production Infrastructure Readiness - 2026-07-02

Purpose: map the non-App infrastructure work that can move in parallel with the Mac/TestFlight lane and Claude / 城堡's current product-engine work.

This document avoids the active collision zones:

- `engine/server.py`
- `engine/perception_engine.py`
- `engine/memory_engine.py`
- `engine/chat_engine.py`
- `web/`
- `supabase/sql/`

## Current Snapshot

| Lane | Status | Meaning |
|---|---|---|
| Source control | Ready | `main` is the active collaboration branch; small commits are expected. |
| Local verification | Good | `npm run release:check` now runs the clean pre-release bundle: static smoke, auth-gate smoke, and Supabase doctor. |
| CI verification | Improved | `.github/workflows/smoke.yml` now runs static smoke, Supabase doctor, and auth-gate smoke on push / PR. |
| Staging backend | Not ready | No hosted Munea API URL is configured yet. |
| Supabase live wiring | Partially ready | SQL and adapter exist; live env verification remains pending. |
| Auth live E2E | Not ready | Supabase Auth providers and backend token verification still need live-session testing. |
| Billing provider verification | Not ready | StoreKit / RevenueCat webhook signature verification is not implemented yet. |
| Scheduled jobs | Partially ready | Daily briefing logic exists, but production 06:30 scheduler / host is not wired. |
| Observability | Early | Fallback logging exists; external error monitoring, uptime checks, and log retention are not set. |
| Admin operations | Contract only | `/admin/usage`, `/admin/credits`, and `/admin/north-star` exist; admin UI / ops playbook still missing. |
| Privacy jobs | Contract only | Export/deletion contracts exist; async workers and reauth enforcement are not production-ready. |

New handoff:

- Staging backend runbook: `docs/STAGING-BACKEND-RUNBOOK-2026-07-02.md`.
- It defines the minimum hosted backend contract, required staging env, Supabase gate, TestFlight backend strategy, hosted smoke expectations, and rollback plan.
- Hosted staging smoke: `npm run smoke:staging -- -BaseUrl https://YOUR-STAGING-API.example.com`.
- Scheduled staging smoke can also use `MUNEA_STAGING_API_URL` so the same command can run from CI or a hosting scheduler without hard-coding the URL in arguments.
- Release checklist: `docs/RELEASE-CHECKLIST.md`.
- Release record draft: `npm run release:record -- -SmokeRun "GITHUB_ACTIONS_RUN_URL" -BackendMode json -Risk "none"`.

## What Can Move Now Without Overlap

### 1. CI And Release Hygiene

Done in this pass:

- Add GitHub Actions smoke workflow for push / pull request.
- Run static smoke and Supabase doctor without secrets.
- Keep the smoke guardrail green by logging invalid daily-briefing expiration timestamps and opener time-context failures instead of silently swallowing them.
- Add auth-gate CI smoke so formal-mode user/admin/provider authorization is checked automatically.
- Allow the local Python engine to use `MUNEA_PORT`, so auth-gate smoke can run on a separate port when 8200 is already occupied.
- Add `npm run release:check` as a clean pre-release verification bundle that skips local `.env.local`, runs static smoke, auth-gate smoke, and Supabase doctor.
- Harden `npm run smoke:no-api` so it also skips local `.env.local` and stays on the deterministic JSON/static verification path.

Next safe improvements:

1. Add branch protection requiring the smoke workflow before merging.
2. Keep release records for push/TestFlight/staging changes using `npm run release:record`.
3. Add an optional nightly Supabase live doctor after the live schema is fully applied.

### 2. Staging Backend Decision

The repo currently has no deployment target. Before TestFlight, Munea needs a reachable staging API for reviewer/device testing.

Runbook:

- `docs/STAGING-BACKEND-RUNBOOK-2026-07-02.md`

Decision needed:

1. Where the Python API runs for staging.
2. How secrets are stored.
3. What URL the app points to in TestFlight.
4. Whether the first TestFlight is static-shell-only or staging-backend-connected.

Minimum staging requirements:

- `GEMINI_API_KEY`
- `MUNEA_SKIP_ENV_LOCAL=1`
- `MUNEA_DATABASE_PROVIDER=supabase`
- `MUNEA_REQUIRE_AUTH=1` for any real-user environment.
- `MUNEA_ENABLE_DEV_AUTH_BYPASS=false` for real-device external testers.
- `MUNEA_ADMIN_API_TOKEN`
- `MUNEA_PROVIDER_WEBHOOK_TOKEN` before billing webhook tests.
- Supabase backend env values, service role kept backend-only.
- Uptime check for `/healthz`.

First backend-connected TestFlight should only happen after:

1. `npm run release:check` passes locally.
2. Approved Supabase SQL is applied to the staging project.
3. `npm run supabase:doctor:live` passes against staging secrets.
4. Hosted `GET /healthz` returns `ok:true` over HTTPS.
5. Real Supabase Auth session verification is tested against `/auth-status`.
6. `npm run smoke:staging` passes against the hosted API.

### 3. Supabase Live Gate

Ready foundations:

- SQL drafts `001` through current active schema files.
- Supabase adapter and `npm run supabase:doctor`.
- JSON fallback remains safe for local development.

Observed local blocker:

- If `MUNEA_DATABASE_PROVIDER=supabase` is enabled before every SQL file is applied, local smoke can fail when the backend tries to read missing tables such as `companion_relationship_states`.
- For CI/static checks, force `MUNEA_DATABASE_PROVIDER=json` so the smoke workflow verifies repo contracts without depending on a partially configured live database.
- `MUNEA_SKIP_ENV_LOCAL=1` is available for CI/clean verification so `engine/.env.local` secrets do not leak into static smoke assumptions.
- `npm run smoke:no-api` now sets this clean mode automatically; use `npm run supabase:doctor:live` when the goal is to validate real Supabase wiring.

Next safe work:

1. Run the SQL in the real project in order.
2. Fill backend-only `engine/.env.local` locally, never committing secrets.
3. Run `npm run supabase:doctor:live`.
4. Test one real Supabase Auth session against `/auth-status`.
5. Record RLS result and row counts in a private ops note.

Avoid for now:

- Writing new migrations while Claude / 城堡 is coordinating family-account fields and schema naming.

### 4. Billing And Entitlement Reliability

Current state:

- Backend-owned entitlements exist.
- Credit wallets are server-side.
- Admin/provider mutation gates exist.
- Smoke already tests included-first deduction, idempotent grants/consumes, insufficient-credit fallback, and Avatar overage consumption.

Next safe work:

1. Add a provider verification design for StoreKit Server Notifications V2 or RevenueCat.
2. Add purchase restore contract planning.
3. Add refund/revoke/reversal scenarios before public launch.
4. Add a known issue: duplicate Avatar completion events must not double-count usage.

Code note:

- Fixing duplicate Avatar completion currently touches `engine/server.py`; wait until the active server/perception/memory work settles or coordinate explicitly.

### 5. Scheduled Jobs

Current state:

- Daily briefing logic exists.
- The intended time is 06:30.
- No production scheduler host is wired.

Next safe work:

1. Decide where scheduled jobs run.
2. Add a private admin token for the scheduled job caller.
3. Call the daily briefing maintenance endpoint once per morning.
4. Log success/failure and expose a last-run timestamp in Admin.

Avoid for now:

- Changing perception internals while 城堡 is still moving perception and mood logic.

### 6. Observability And Incident Basics

Current state:

- Backend fallback failures now log warnings.
- API errors use stable `ok:false` responses with request ids.

Next safe work:

1. Add uptime monitor for `/healthz`.
2. Add external error reporting for backend exceptions.
3. Add frontend crash/error capture after web redesign stabilizes.
4. Track failed voice sessions, fallback voice sessions, Avatar fallback, subscription webhook failures, and privacy job failures.

### 7. Admin MVP

Current state:

- Read contracts exist.
- No admin screen exists.

Next safe work:

1. Keep using backend read contracts as the source.
2. Define the first Admin dashboard pages before building UI.
3. Prioritize account lookup, subscription lookup, credits ledger, safety events, privacy requests, and North Star.

Avoid for now:

- Building admin UI inside `web/` while 城堡 is doing the main app redesign.

## Recommended CTO Priority

1. Run `npm run release:check` before every push that affects backend, auth, billing, CI, or release readiness.
2. Keep CI smoke running on every push.
3. Decide staging backend host and URL strategy.
4. Finish Supabase live gate and Auth live E2E.
5. Lock billing provider verification path.
6. Wire production scheduled jobs.
7. Add uptime/error monitoring.
8. Build Admin MVP after web redesign and schema coordination settle.

## Near-Term Parking Lot

| Item | Why parked | Unblocker |
|---|---|---|
| Duplicate Avatar completion idempotency fix | Likely touches `engine/server.py` | Coordinate after active server/perception work calms down. |
| Family account migration `007` | Schema naming is under coordination | Align with `docs/家人帳號連動-架構設計-2026-07-02.md`. |
| Admin UI | `web/` is active under 城堡 redesign | Start after UI direction lands. |
| Push notification loop | Needs iOS, backend scheduler, and family permission model | Start after Mac shell and family account field alignment. |
