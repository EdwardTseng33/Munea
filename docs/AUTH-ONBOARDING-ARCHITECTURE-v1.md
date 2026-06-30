# Munea Auth And Onboarding Architecture v1

Updated: 2026-06-30

Purpose: lock the first production direction for login, registration, guest mode, progressive onboarding, and account bootstrap before Munea moves deeper into Supabase Auth, App Store subscriptions, family care, health data, and cross-device memory.

## Executive Decision

Munea v1 should use a progressive account model:

```text
Try first -> feel the companion -> sign in when value needs persistence, family, health, or payment
```

The app should not force account creation on first launch. The core product is the S2S "chat" companion experience, so the first session should reduce friction and let the user choose/name a companion before the hard auth gate.

## v1 Auth Providers

Approved providers for v1:

| Provider | v1 status | Why |
|---|---|---|
| Sign in with Apple | required for iOS | App Store-friendly, privacy-forward, natural for iPhone users |
| Google | required | familiar, fast, useful for family/caregiver accounts |
| Email magic link / OTP | fallback | supports users who do not want Apple/Google and avoids password friction |
| Facebook | not v1 | not needed for first trust posture; adds privacy perception and setup surface |
| Email password | not preferred for v1 | higher support/reset burden; can be added later if needed |
| Phone OTP | later | useful for older users, but adds SMS cost, deliverability, and region handling |

Decision:

- Use Supabase Auth as the identity layer.
- Configure Apple and Google OAuth first.
- Keep email magic link or OTP as the non-social fallback.
- Do not include Facebook in v1 unless marketing acquisition later proves it is necessary.

## Product Account Model

Supabase `auth.users` owns identity.

Munea application data is owned by:

```text
auth.users.id
  -> account_members.user_id
  -> accounts.id
  -> persons / family_groups / companion_profiles / subscription_ledger / usage_ledger / privacy_requests
```

Important:

- `auth.users` is not the product profile.
- `persons` stores the app-facing person profile.
- `accounts` is the tenant boundary.
- `account_members` is the permission bridge.
- `companion_profiles` stores the user-named companion identity.
- Authorization must not use user-editable `user_metadata`.
- Production APIs must verify the access token and derive the real auth user id server-side.

## Guest Mode

Guest mode is allowed for low-risk, local-only discovery.

Guest can:

- view landing/home shell.
- choose "self" or "help family" setup path.
- choose a companion template.
- name the companion.
- try a short local/demo `chat` experience.
- view basic settings and upgrade prompts.

Guest cannot:

- save cloud memory.
- sync across devices.
- invite family.
- use family dashboard.
- create health reminders that persist.
- connect Apple Health.
- use paid/premium Avatar minutes.
- start subscription or restore purchase.
- request privacy export or account deletion.
- store durable conversation summaries.
- receive proactive cross-session care notifications.

Auth gate triggers:

| Trigger | Auth requirement |
|---|---|
| Save companion/profile to cloud | sign in required |
| Continue after first meaningful chat | soft sign-in prompt |
| Invite family or open family dashboard | sign in required |
| Add medication/routine reminders | sign in required |
| Connect Apple Health / device data | sign in required + consent |
| Start subscription / restore purchase | sign in required |
| Premium Avatar mode | sign in required + entitlement |
| Data export / account deletion | sign in required + reauth |
| Cross-device memory | sign in required |

## Production Login UI Foundation

The first app-facing login surface lives in Settings so the home and S2S chat loop can remain usable in guest mode.

Current UI contract:

- Settings account card shows guest, signed-in, or developer-mode state.
- Sign-in sheet offers Sign in with Apple, Google, and email magic link/OTP.
- Sign-out is available from the account card after a session exists.
- Developer-mode entry is hidden unless local developer bypass is explicitly allowed.
- The UI calls `window.MuneaAuth` only; it does not know Supabase secrets or backend-only credentials.
- Auth state changes close the sheet, refresh the account card, and retry `/account-bootstrap` when onboarding is already complete.

Not complete yet:

- Real Supabase provider configuration must still be tested end-to-end.
- Backend must still verify `Authorization: Bearer <access_token>` and derive `auth.users.id` server-side.

## Developer Mode And Test Accounts

Munea needs a developer/tester path so Edward, designers, and engineers can move quickly without repeatedly completing registration and onboarding.

Rules:

- Developer mode is disabled by default.
- Developer mode must only run on localhost, `127.0.0.1`, or `file:` preview unless `allowNonLocalhost` is explicitly set for a controlled staging build.
- Developer mode must never use server-only secrets in browser code.
- Developer mode may mark onboarding as complete and may create a deterministic local developer session.
- Developer mode must not be treated as real production authentication.
- Developer/test activity must be excluded from North Star and operating metrics.

Browser config:

```js
window.MUNEA_DEV_CONFIG = {
  enabled: true,
  autoSignIn: true,
  skipOnboarding: true,
  analyticsExcluded: true,
  authUserId: '00000000-0000-4000-8000-000000000001',
  email: 'developer@munea.local'
};
```

Analytics rule:

- Frontend product events from developer mode include `analyticsExcluded: true`, `developerMode: true`, and `accountType: developer`.
- Backend North Star summaries exclude events with `analyticsExcluded`, `developerMode`, `accountType=developer/internal/test/qa/ops`, or ids listed in the backend exclusion env variables.
- Developer clicks, logins, registration attempts, chats, Avatar sessions, and reminders must not count toward operating dashboards.

Backend exclusion env:

```text
MUNEA_ANALYTICS_EXCLUDED_ACCOUNT_IDS=...
MUNEA_ANALYTICS_EXCLUDED_PERSON_IDS=...
MUNEA_ANALYTICS_EXCLUDED_SESSION_IDS=...
```

## Registration Fields

Registration should be split into required, contextual, and deferred fields.

### Required At Auth / Account Bootstrap

Minimum required:

- auth provider identity: Apple, Google, or email magic link/OTP.
- terms of service consent.
- privacy policy consent.
- user display name or nickname.
- usage mode: `self` or `help_family`.
- companion template id.
- companion display name.
- locale, default `zh-TW`.
- timezone, default `Asia/Taipei`.

These fields are enough to create:

- account.
- account member.
- primary person.
- first family group.
- first companion profile.
- free entitlement baseline.

### Contextual Fields

Ask only when the user enters a relevant workflow:

- family contact name and relationship: when inviting family.
- emergency contact: when enabling safety handoff.
- routine/medication name and time: when creating a reminder.
- Apple Health consent: when connecting health data.
- subscription plan: when upgrading.

### Deferred Fields

Do not block first use on:

- age or birth year.
- city.
- health goals.
- activity baseline.
- avatar voice fine-tuning.
- detailed family graph.
- long-term care context.
- payment details before upgrade intent.

## Onboarding Flow

Recommended v1 flow:

```text
0. Welcome
1. Choose setup intent: self / help family
2. Choose companion template
3. Name the companion
4. Try short chat
5. Auth gate only if user wants persistence, family, reminders, health, or subscription
6. Account bootstrap after verified auth
7. Soft profile completion over time
```

The current prototype already supports steps 1-3 and stores companion identity locally. The next implementation step is to connect real Supabase Auth before calling production account bootstrap.

## API Contract Direction

Existing:

- `POST /account-bootstrap`
- `POST /app-profile`
- `POST /companion-profile`
- `POST /entitlements`
- `POST /privacy-export`
- `POST /account-deletion`

Auth work to add:

| Contract | Purpose |
|---|---|
| `Authorization: Bearer <access_token>` | every production user API must receive the Supabase access token |
| backend token verification | backend derives auth user id; frontend does not supply trusted `authUserId` |
| `auth_required` error | returned when a user action requires sign-in |
| `profile_incomplete` warning | returned when a signed-in account still needs required app fields |
| `reauth_required` error | required before export/delete and sensitive account operations |

Current prototype note:

- `web/src/app.js` can read `window.MuneaAuth` as a bridge.
- This bridge is temporary. Production must replace it with a real Supabase session and backend token verification.
- `/account-bootstrap` currently refuses Supabase create mode without a verified-looking auth id; the next version should derive that id from the verified token instead of trusting request body data.

## Supabase Auth Implementation Plan

Phase 1: Frontend session bridge

- [x] Add `web/src/auth.js` as the browser Auth runtime.
- [x] Support Sign in with Apple, Google, and email magic link/OTP methods behind `window.MuneaAuth`.
- [x] Keep guest mode active when Supabase public config is not injected.
- [x] Add `web/src/auth-config.example.js` for publishable/anon-key-only configuration.
- [x] Send Bearer-token API headers, `Authorization: Bearer <access_token>`, from app/onboarding API calls when a Supabase session exists.
- [x] Add sign-out method.
- [x] Add local-only developer mode with onboarding skip and analytics exclusion.
- [x] Add production login UI foundation in Settings.
- [ ] Test configured Supabase Auth provider redirects and callbacks.
- [ ] Store session using Supabase client session handling in a configured environment.

Phase 2: Backend auth verification

- Accept `Authorization: Bearer <access_token>`.
- Verify the token server-side using Supabase auth APIs or JWT validation.
- Derive `auth_user_id` from the verified token.
- Remove trust in frontend-provided `authUserId`.
- Return `auth_required` for missing/invalid tokens.

Phase 3: Account bootstrap

- After verified auth, call `/account-bootstrap`.
- Create the account graph once.
- Attach `account_members.user_id = auth.users.id`.
- Convert local guest companion profile into the signed-in account companion profile.
- Record audit event: `account_bootstrapped`.

Phase 4: Progressive profile completion

- Ask for deferred fields only when needed.
- Store consent timestamps.
- Add profile completion status to `/app-profile`.

## App Store And Trust Requirements

- If Google sign-in is offered on iOS, Sign in with Apple must also be offered.
- Account deletion must be reachable from inside the app after account creation.
- Privacy export and deletion require reauth.
- Subscription state must be verified server-side.
- Health data consent must be explicit and separate from normal account creation.
- Do not describe Munea as diagnosis, treatment, prescription, or therapy.

## Data Gaps To Close

The current schema is enough for account bootstrap, but production auth should add or formalize:

- user consent records: terms, privacy, health data, marketing.
- profile completion status.
- auth provider audit fields.
- account deletion worker status.
- optional session revocation policy for sensitive operations.

These can be added as a later migration after the first Supabase Auth bridge is working.

## Build Order

1. Add this file as the source-of-truth auth/onboarding direction.
2. Update README, Backend Architecture, Supabase Setup, and Current Development Plan.
3. Implement Supabase Auth frontend bridge.
4. Implement backend token verification.
5. Convert `/account-bootstrap` from body-provided auth id to verified-token-derived auth id.
6. Add auth-gated UX states.
7. Add smoke tests for guest, signed-in, auth-required, and reauth-required flows.
