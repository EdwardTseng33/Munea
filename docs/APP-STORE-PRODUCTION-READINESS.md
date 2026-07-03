# Munea App Store Production Readiness

Updated: 2026-07-02

Purpose: turn Munea from prototype into an App Store product with subscriptions, health-care boundaries, user data safety, and maintainable backend contracts.

## Launch Position

Munea should enter TestFlight as an iOS-first AI health-care companion, not as medical software.

The app can provide:

- AI companionship and daily check-ins.
- Routine and medication reminders.
- Family interaction and care-circle updates.
- Safety referral and escalation prompts.
- Optional premium voice/avatar capacity through subscriptions.

The app must not provide:

- diagnosis.
- treatment.
- prescription or dosage advice.
- psychotherapy or crisis counseling.
- emergency-service replacement.

## Apple Review Requirements Mapped To Munea

Apple's App Review Guidelines are organized around Safety, Performance, Business, Design, and Legal. For Munea, the highest-risk sections are health safety, privacy, subscriptions, app completeness, backend availability, and clear in-app purchase explanation.

Munea requirements before App Review:

- App Review demo account or full demo mode.
- Backend services live and reachable during review.
- Subscription products visible, functional, and explained in review notes.
- Privacy policy URL in App Store Connect and inside the app.
- App privacy details aligned with actual data collection and third-party SDKs.
- Clear disclosure that Munea is companion/reminder/referral, not medical advice.
- Purpose strings for microphone, notifications, and future HealthKit permissions.
- On-device QA for iPhone microphone, playback, push prompt, login, subscription restore, and account deletion path.

Sources:

- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Account deletion in apps: https://developer.apple.com/support/offering-account-deletion-in-your-app/
- App privacy details: https://developer.apple.com/help/app-store-connect/reference/app-privacy-details
- StoreKit: https://developer.apple.com/documentation/storekit
- App Store Server API: https://developer.apple.com/documentation/appstoreserverapi

## Subscription Architecture

Munea's subscription should be treated as a backend entitlement, not a frontend flag.

Recommended first path:

1. iOS app uses StoreKit 2 or RevenueCat SDK to start purchase and restore flows.
2. Backend receives App Store Server Notifications V2 or RevenueCat webhooks.
3. Backend verifies signed transaction and renewal information.
4. Backend updates subscription state and entitlements.
5. App calls `/entitlements` to decide what is available.

Current local prototype:

- `engine/billing_store.json` is the local billing ledger placeholder.
- `POST /entitlements` returns subscription state, entitlement gates, and usage ledger.
- `POST /subscription-event` accepts local notification-shaped events but marks them as requiring production JWS verification.

Production rule:

- The frontend must never be the source of truth for paid status, Avatar minutes, family member limits, or premium feature gates.

Initial subscription ladder:

```text
Free -> Plus -> Premium -> Concierge
```

Detailed billing, credits, and entitlement rules are tracked in `docs/BILLING-CREDITS-ENTITLEMENT-v1.md`.

Billing design principle:

```text
Subscription = base access and trust
Credits = expensive or bursty premium capacity
```

Credits should not gate safety/referral flows, basic privacy controls, account deletion, data export, or essential companion access.

Initial entitlement gates:

| Entitlement | Free | Plus | Premium | Concierge |
|---|---:|---:|---:|---:|
| Voice companion | yes | yes | yes | yes |
| Routine reminders | basic | yes | yes | yes |
| Family dashboard | limited | expanded | expanded | concierge |
| Family members | 2 | 4 | 8 | custom/high |
| Real-time premium Avatar | no | limited trial only | yes | yes |
| Premium Avatar minutes | 0 | small/month | monthly grant | large/custom grant |

## Data Safety Model

Munea handles sensitive personal and health-adjacent data. The production backend must use tenant-scoped access control and explicit retention.

Minimum data domains:

- account profile.
- family group and roles.
- companion profile.
- voice session metadata.
- conversation summaries.
- health/routine reminders.
- safety events.
- subscription and usage ledger.
- audit events.

Default retention stance:

- Do not make raw transcripts the primary retained record.
- Store short conversation summaries when needed for memory.
- Store safety events separately with reason, timestamp, and escalation state.
- Allow user export and deletion.
- Keep payment transaction identifiers in billing records, not chat records.

Health data rule:

- HealthKit or health-adjacent data must only be used to benefit the user directly.
- Do not use health data for advertising, marketing, or data mining.
- Do not store personal health information in iCloud.

## API Security Baseline

Current implemented guardrails:

- `MAX_JSON_BODY_BYTES` limits request body size.
- `MAX_AUDIO_NOTE_BYTES` limits recorded audio payloads.
- `ALLOWED_AUDIO_MIMES` restricts accepted audio formats.
- `/healthz` exposes lightweight service and contract status.
- API errors return stable `ok:false` payloads with `requestId`; exception details are hidden unless `MUNEA_DEBUG_API=1`.
- `/app-profile`, `/companion-profile`, and `/entitlements` are separate contracts.
- `/privacy-export` returns a local JSON export package for the account/family/profile/billing/privacy ledger.
- `/account-deletion` returns the deletion status contract and production deletion steps.
- Frontend onboarding and sign-in now disclose AI/voice provider processing before entering the app, Settings keeps the privacy-policy entry and safety disclaimer, and the app links to `web/privacy.html` for the in-app privacy policy.

Production guardrails still required:

- authenticated requests with account and family scope.
- row-level isolation in Postgres.
- rate limits by account and device.
- signed webhook verification for App Store Server Notifications.
- no API keys in the app bundle.
- server-side model/provider keys only.
- backend account-level consent records for AI/voice provider processing.
- audit logging for entitlement changes, family permission changes, safety events, and account deletion.
- encryption at rest for production DB and object storage.

## Data Rights: Export And Account Deletion

Apple expects apps that support account creation to also let users initiate account deletion from inside the app. Munea should treat this as a first-class product surface, not a support-only workflow.

Current local prototype:

- `engine/privacy_requests.json` is the local data-rights ledger.
- `POST /privacy-export` returns a JSON export preview package.
- `POST /account-deletion` returns current deletion status and the required production steps.

Production account deletion flow:

1. User opens Settings -> Account -> Delete account.
2. App explains what will be deleted, what may be retained for legal/payment/audit obligations, and how active subscriptions are handled.
3. User reauthenticates.
4. Backend records an `account_deletion` request.
5. Backend cancels or guides cancellation for App Store subscription where applicable.
6. Backend soft-deletes user-facing records immediately.
7. Backend hard-deletes or anonymizes eligible data after the retention window.
8. Backend sends confirmation.

Production data export flow:

1. User opens Settings -> Account -> Export my data.
2. User reauthenticates.
3. Backend creates an asynchronous export job.
4. Export package includes profile, family group, companion profile, reminder data, conversation summaries, safety events, subscription ledger, and usage ledger.
5. Export package excludes provider secrets, raw internal logs, model prompts that are not user data, and unrelated family-member private data.

Retention boundary:

- Raw transcripts should not become the default retained record.
- Conversation summaries may be retained for memory until deletion or retention expiry.
- Safety events may need a separate retention policy for user protection and audit.
- Billing records may be retained as required for refund, tax, platform, and abuse-prevention obligations.

## Production Database Shape

Recommended production tables:

- `accounts`
- `persons`
- `family_groups`
- `family_memberships`
- `companion_profiles`
- `voice_sessions`
- `conversation_summaries`
- `safety_events`
- `routine_reminders`
- `subscription_ledger`
- `usage_ledger`
- `audit_events`

Every row that contains user data should carry:

- `account_id`
- `family_group_id` when family-scoped.
- `person_id` when person-scoped.
- `created_at`
- `updated_at`
- `deleted_at` where soft delete is needed.

## App Store Submission Checklist

Before TestFlight:

- iPhone microphone capture verified.
- playback route verified.
- permission prompts reviewed.
- restore purchases flow designed.
- `/healthz`, `/app-profile`, `/entitlements`, `/voice-session` reachable.
- `supabase/sql/006_billing_credits_foundation.sql` reviewed/applied if credits will appear in TestFlight.
- privacy policy draft complete.
- account deletion and data export requirements written.
- Mac handoff checklist completed or actively in progress: `docs/TESTFLIGHT-MAC-HANDOFF-2026-07-02.md`.

Before App Review:

- production backend deployed.
- demo account or demo mode prepared.
- subscription products configured in App Store Connect.
- App Review notes explain AI, subscriptions, and medical boundary.
- App privacy details match actual SDKs and data use.
- support URL and privacy policy URL live.
- app does not include placeholder text or incomplete paywalled flows.

Before public launch:

- subscription webhook verification live.
- backend entitlement ledger live.
- credit wallet ledger live if consumable credits are sold.
- database RLS or equivalent tenant isolation verified.
- crash and error monitoring installed.
- delete/export request path ready.
- safety escalation copy reviewed.

## Current TestFlight Readiness - 2026-07-02

Munea is not ready for TestFlight upload yet, but the next practical gate is now clear because Xcode and Apple Developer Program access are available on Edward's Mac.

Recommended order:

1. Generate or sync the Capacitor iOS project on Mac.
2. Run `npm run mac:doctor` on Mac to confirm Git, Node/npm, PowerShell, Xcode, xcrun, and Capacitor config are ready.
3. Add required iOS purpose strings for microphone, speech recognition, and notifications.
4. Run on a real iPhone and verify bundled web shell, `聊聊`, microphone prompt, voice-note fallback, playback, and privacy link.
5. Decide whether the first TestFlight build is a static UI shell QA build or a staging-backend build.
6. Only after that, prepare App Store Connect metadata, support URL, privacy URL, subscriptions, and reviewer notes.

The detailed Mac-side handoff lives in `docs/TESTFLIGHT-MAC-HANDOFF-2026-07-02.md`.
