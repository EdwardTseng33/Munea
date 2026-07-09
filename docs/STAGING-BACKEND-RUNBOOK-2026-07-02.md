# Munea Staging Backend Runbook - 2026-07-02

Purpose: define the first hosted backend path that can support internal QA, real-device testing, and a future TestFlight build without turning staging into production.

This runbook intentionally avoids active Claude / 城堡 work areas: memory internals, perception internals, family schema migration design, live voice wiring, and `web/` retheme.

## CTO Decision

Munea should have a reachable staging API before any backend-connected TestFlight build.

The first staging API is not the public production backend. Its job is to prove:

1. The app can reach a hosted API URL from a real iPhone.
2. Auth-required mode works outside local developer bypass.
3. Supabase live schema and backend adapter are wired correctly.
4. Secrets stay server-side.
5. Release checks are repeatable before each push and upload.

## Recommended Staging Shape

| Area | Staging rule |
|---|---|
| Backend runtime | Host the existing Python API as one small always-on service. |
| Public URL | Use one stable HTTPS staging URL, separate from production. |
| Database | Use Supabase project or Supabase staging schema dedicated to QA. |
| Auth | Enable real auth for external/device testers. |
| Secrets | Store only in backend hosting secrets, never in Capacitor or browser code. |
| App build | Decide per build: static-shell QA or staging-backend-connected QA. |
| Data | Treat staging data as test data, but protect it like user data. |

## Minimum Environment Contract

Required for staging backend:

```text
GEMINI_API_KEY=...
MUNEA_SKIP_ENV_LOCAL=1
MUNEA_DATABASE_PROVIDER=supabase
MUNEA_REQUIRE_AUTH=1
MUNEA_ENABLE_DEV_AUTH_BYPASS=false
MUNEA_ADMIN_API_TOKEN=...
MUNEA_PROVIDER_WEBHOOK_TOKEN=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
MUNEA_SUPABASE_ACCOUNT_ID=...
MUNEA_SUPABASE_PERSON_ID=...
MUNEA_SUPABASE_FAMILY_GROUP_ID=...
```

Optional but expected soon:

```text
CWA_API_KEY=...
MOENV_API_KEY=...
MUNEA_REGION=臺北市
MUNEA_ANALYTICS_EXCLUDED_ACCOUNT_IDS=...
MUNEA_ANALYTICS_EXCLUDED_PERSON_IDS=...
MUNEA_ANALYTICS_EXCLUDED_SESSION_IDS=...
```

Security notes:

1. `SUPABASE_SERVICE_ROLE_KEY` is backend-only.
2. Browser and Capacitor builds may use publishable Supabase config only.
3. `MUNEA_ENABLE_DEV_AUTH_BYPASS` must stay disabled for real-device external testers.
4. Admin/provider tokens must be long random secrets and rotated if exposed.

## Preflight Before First Deploy

Run locally before creating or updating the staging service:

```powershell
npm run release:check
npm run ai:doctor:live
```

Then verify the live database path only after the staging Supabase SQL files are applied:

```powershell
npm run supabase:doctor:live
```

Expected local result:

1. Static smoke passes.
2. Auth-gate smoke passes.
3. AI doctor confirms `GEMINI_API_KEY` is available to the backend without printing the key value.
4. Supabase doctor reports configured live env values without printing service-role secrets.

## Supabase Gate

Before pointing a real TestFlight build at staging:

1. Apply the current approved SQL files in order.
2. Do not apply or invent new family-account migrations until Claude / 城堡 schema coordination is settled.
3. Run `npm run supabase:doctor:live`.
4. Confirm `/app-profile`, `/companion-profile`, `/entitlements`, `/privacy-export`, and `/account-deletion` can use the Supabase adapter path.
5. Confirm missing-table errors do not appear in backend logs.

Staging should use a dedicated demo account/person/family group first. Do not reuse private production identities for QA.

## Hosted API Smoke

Once staging is deployed, the minimum hosted checks are:

1. `GET /healthz` returns `ok:true` over HTTPS.
2. `POST /auth-status` rejects invalid tokens and accepts a real Supabase Auth session.
3. User-scoped endpoints reject unauthenticated requests when `MUNEA_REQUIRE_AUTH=1`.
4. Admin endpoints reject normal user Bearer auth and require `X-Munea-Admin-Token`.
5. `/subscription-event` rejects normal user Bearer auth and requires provider/admin trust.
6. `/voice-session` returns a safe fallback capability response.
7. `/privacy-export` and `/account-deletion` return stable contract payloads.

Current repo gap:

- `npm run smoke:auth` is local-only and uses developer bearer bypass for deterministic CI.
- `npm run smoke:staging` tests a deployed API URL without starting a local server.

Run without secrets first:

```powershell
npm run smoke:staging -- -BaseUrl https://YOUR-STAGING-API.example.com
```

For a locked Cloud Run staging service, include local Google identity so the smoke reaches the app while still testing Munea's own API gates:

```powershell
npm run smoke:staging -- `
  -BaseUrl https://YOUR-LOCKED-CLOUD-RUN-URL `
  -UseGcloudIdentityToken
```

For scheduled or hosted CI checks, set the URL once and run the same script without repeating arguments:

```powershell
$env:MUNEA_STAGING_API_URL = "https://YOUR-STAGING-API.example.com"
npm run smoke:staging
```

This verifies `/healthz`, unauthenticated rejection, invalid bearer rejection, admin rejection, and provider webhook rejection.

Run with real staging credentials when available:

```powershell
npm run smoke:staging -- `
  -BaseUrl https://YOUR-STAGING-API.example.com `
  -BearerToken "<REAL_SUPABASE_ACCESS_TOKEN>" `
  -AdminToken "<STAGING_ADMIN_TOKEN>" `
  -ProviderToken "<STAGING_PROVIDER_TOKEN>"
```

The script does not print tokens. For non-local URLs it requires HTTPS and requires `/healthz` to report `runtime.authRequired=true` and a non-JSON backend.

## Cloud Run Inventory Check

When staging runs on Google Cloud Run, first check the hosting layer without touching user data or printing secrets:

```powershell
npm run cloudrun:status
```

The command verifies the active gcloud account, project, Cloud Run service readiness, service URLs, visible environment variable names, Secret Manager secret existence, and `secretAccessor` IAM bindings for the checked runtime service accounts. Use strict mode when this becomes a required release gate:

```powershell
npm run cloudrun:status -- -Strict
```

When the service is healthy but you need to know whether it is ready for staging QA and Admin MVP use, run:

```powershell
npm run cloudrun:readiness
```

Readiness checks the visible environment-variable contract for the brain and voice services and uses a short-lived `gcloud auth print-identity-token` token to verify whether the locked brain service serves `/admin.html`. Use `-StrictReadiness` when the missing staging pieces should fail a release gate.

## Admin Console Smoke

After the Admin MVP shell is deployed, verify the internal dashboard and read-only admin endpoints:

```powershell
npm run smoke:admin -- `
  -BaseUrl https://YOUR-STAGING-API.example.com `
  -AdminToken "<STAGING_ADMIN_TOKEN>"
```

For a locked Cloud Run service, let the script request a short-lived Google identity token from local `gcloud`:

```powershell
npm run smoke:admin -- `
  -BaseUrl https://YOUR-LOCKED-CLOUD-RUN-URL `
  -AdminToken "<STAGING_ADMIN_TOKEN>" `
  -UseGcloudIdentityToken
```

This confirms `/admin.html` is served, unauthenticated admin reads are rejected, and the token-gated account, usage, credits, conversation-summary, privacy, safety, and audit read contracts return `ok:true`. The script never prints the admin token.

## Clean Staging Deploy

Use a clean git snapshot for staging deploys so local scratch files, Avatar PoC folders, and generated media do not enter the Cloud Run build context:

```powershell
npm run cloudrun:deploy:staging -- -DryRun
```

When the dry run looks right and staging is allowed to change:

```powershell
npm run cloudrun:deploy:staging
```

The script exports committed `HEAD` to a temporary source directory, deploys the brain service from that clean copy, and sets the staging auth flags. It will attach `MUNEA_ADMIN_API_TOKEN` only when the `munea-admin-token-staging` Secret Manager secret already exists. Pass `-IncludeVoice` when the voice service also needs a refresh.

## TestFlight Backend Strategy

There are two valid first TestFlight tracks:

| Track | Use when | Backend risk |
|---|---|---|
| Static shell QA | We only need iPhone shell, layout, microphone permission, playback, privacy link, and navigation QA. | Low |
| Staging-connected QA | We need real auth, hosted `/healthz`, entitlements, voice-session fallback, and data-rights contracts on device. | Medium |

Recommended order:

1. Ship static shell QA first if Mac/iPhone wrapper risk is still unknown.
2. Connect to staging after iPhone shell, microphone permission, and playback are verified.
3. Do not use JSON fallback as a real-user backend mode for external TestFlight testers.

## Go / No-Go

| Gate | Go | No-go |
|---|---|---|
| Release check | `npm run release:check` passes. | Any smoke step fails. |
| Backend URL | `/healthz` reachable over HTTPS. | HTTP only, unstable URL, or unreachable host. |
| Auth | Real auth session verified. | External testers rely on dev bypass. |
| Supabase | Live doctor passes after approved SQL. | Missing tables or service role exposed. |
| App secrets | No service/admin/provider secrets in app bundle. | Any backend secret appears in `web/` or Capacitor assets. |
| Privacy | Export/deletion contracts reachable. | Data-rights routes broken. |
| Logs | Fallback/errors visible in backend logs. | Failures disappear silently. |

## Rollback

If staging-connected QA fails:

1. Pull the staging-connected build from tester distribution or stop using that build.
2. Return to static-shell QA while backend is fixed.
3. Keep the staging database intact for investigation unless it contains accidental private data.
4. Rotate affected secrets if logs, screenshots, or app bundles exposed them.

Do not "rollback" by sending real testers to local JSON fallback. JSON fallback is for local development and deterministic smoke only.

## Next Engineering Tasks

1. Choose the staging host and create the staging service.
2. Add backend hosting secrets using the minimum environment contract above.
3. Apply approved Supabase SQL to the staging project.
4. Run live Supabase doctor.
5. Run `npm run smoke:staging` against the hosted staging API.
6. Decide first TestFlight mode: static shell QA or staging-connected QA.
