# Munea App Store Production Readiness

Updated: 2026-06-29

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

Initial entitlement gates:

| Entitlement | Free | Paid |
|---|---:|---:|
| Voice companion | yes | yes |
| Routine reminders | yes | yes |
| Family dashboard | limited | expanded |
| Family members | 2 | configurable |
| Real-time premium Avatar | no | yes |
| Premium Avatar minutes | 0 | monthly grant + ledger |

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

Production guardrails still required:

- authenticated requests with account and family scope.
- row-level isolation in Postgres.
- rate limits by account and device.
- signed webhook verification for App Store Server Notifications.
- no API keys in the app bundle.
- server-side model/provider keys only.
- audit logging for entitlement changes, family permission changes, safety events, and account deletion.
- encryption at rest for production DB and object storage.

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
- privacy policy draft complete.
- account deletion and data export requirements written.

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
- database RLS or equivalent tenant isolation verified.
- crash and error monitoring installed.
- delete/export request path ready.
- safety escalation copy reviewed.

