# Munea Current Development Plan

> Updated: 2026-06-30
> Purpose: current execution plan for turning the runnable prototype into a first TestFlight path.

## Current Truth

- Product core: **AI health care + family interaction + `聊聊`**.
- First market wedge: family/older-adult care, but Munea is not an "elderly-only app."
- Language priority: **Taiwan Mandarin first, English second**.
- Taiwanese Hokkien: research only for now; no v1/v2 commitment and no self-trained language model.
- Voice direction: Gemini 3.1 Flash Live direction, subject to live API integration testing.
- App delivery: iOS first through Capacitor; Android later.
- Compliance line: companion and life reminder, not diagnosis, treatment, prescription, or therapy.

## Progress Snapshot

| Track | Status | Progress |
|---|---|---:|
| Product direction / PRD | Current authority exists in README + SPEC | 85-90% |
| Runnable web prototype | Home, status, chat, family, settings, onboarding, landing | 65-70% |
| Prototype AI engine | Local Python Gemini chat/TTS demo works | 35-45% |
| iOS shell | Capacitor config scaffolded; native project still requires Mac/Xcode | 5-10% |
| Data backend | Supabase schema 001-007 + adapter table audit exist; live env/schema apply still pending | 45-55% |
| Real-time avatar | Avatar Runtime now consumes backend `/avatar-session`; engine PoCs still pending | 35-45% |
| First TestFlight path | Not ready yet | 30-35% |

## 2026-06-30 Update

- Added developer-only AI context diagnostics in Settings, visible through local developer mode or `?debug=ai`.
- The diagnostics panel shows persona template, relationship rapport, Guardian risk, memory count, perception domains, tone overrides, and compact raw diagnostic JSON.
- Connected `/voice-session`, `/chat`, `/voice-note`, and `/butler/post-turn` responses to the latest `aiContext` display.
- Added a manual `/persona/context` refresh so developers can inspect persona + relationship state without storing raw transcript analytics.
- Verified that normal mode hides the panel and `?debug=ai` shows it in Settings.

## 2026-07-01 Update

- Locked the subscription ladder as Free / Plus / Premium / Concierge.
- Added `docs/BILLING-CREDITS-ENTITLEMENT-v1.md` as the source of truth for plan names, entitlement gates, credits direction, deduction order, service architecture, prior-plan review, and future product ids.
- Added `supabase/sql/006_billing_credits_foundation.sql` for `entitlement_policy_versions`, `credit_wallets`, `credit_transactions`, and `credit_ledger`.
- Added the first local runtime credits API: `/credits/balance`, `/credits/grant`, and `/credits/consume`, backed by `engine/credits_store.json`.
- Connected `/avatar-session` to the credits deduction path: monthly premium Avatar allowance first, purchased/included credits for overage, then graceful fallback to `2d-viseme`.
- Added Supabase adapter support for credits runtime tables: `credit_wallets`, `credit_transactions`, and `credit_ledger`.
- Added token-gated Admin MVP read contracts: `/admin/usage` for product usage/North Star composition and `/admin/credits` for subscription, entitlements, usage ledger, wallets, and recent credit ledger lookup.
- Added production-mode billing mutation guard: `MUNEA_REQUIRE_AUTH=1` separates normal bearer-auth user reads from privileged entitlement/credits/provider writes using admin/provider tokens.
- Added audit event writes for privileged billing mutations, using Supabase `audit_events` when configured and local ignored fallback during prototype mode.
- Clarified that subscriptions should protect the trust-building base experience, while credits should only apply to expensive or bursty add-ons such as premium Avatar/GPU minutes.

## 2026-07-02 Update

- Added the P0-6 frontend consent baseline for overseas AI/voice services: onboarding requires explicit consent before entering the app, Settings can show/update consent state, and the app links to an in-app privacy policy.
- The consent state is stored under a versioned browser key as a prototype bridge; production should persist this to backend account consent records once Supabase Auth/user identity is live.
- The privacy policy now states the Gemini/OpenAI overseas provider boundary, health/safety limits, family visibility, data export, and account deletion expectations.
- Added backend fallback logging so Supabase adapter failures, model reply failures, and TTS failures leave warning logs before prototype fallbacks are used.
- Added smoke coverage to prevent silent `except ...: pass` handlers from returning in `engine/server.py` and `engine/chat_engine.py`.
- Added `docs/TESTFLIGHT-MAC-HANDOFF-2026-07-02.md` now that Xcode and Apple Developer Program access are available on Edward's Mac. The next iOS gate is Mac-side Capacitor project generation, purpose strings, signing, and real-iPhone microphone/playback QA.

## 2026-07-06 Update

- Added `supabase/sql/007_family_cloud_state_foundation.sql` as the Codex-owned family cloud schema bridge for invites, consent records, wellbeing signals, `/family/state` cloud entries, family activities, and activity participants.
- Extended `persons` schema planning with `auth_user_id`, `region_code`, and `attributes` so family-account linking can move from local prototype to Supabase without relying on user-editable metadata.
- Extended Supabase doctor live mode with read-only table reachability checks for every expected table, including the 007 family cloud tables. This should make future "missing table" incidents report exact table names instead of producing vague fallback symptoms.
- Live database apply is still pending: the repo now has the SQL and verification contract, but the staging/live Supabase project must run SQL 001-007 in order before `npm run supabase:doctor:live` can pass.

## 2026-07-07 Update

- Reduced GitHub Actions smoke notification noise: push runs now report smoke issues in the workflow summary while pull requests and manual workflow runs remain strict gates.
- Fixed the current frontend ID smoke false alarm by allowing guarded optional selectors that remain in JavaScript while the active UI is being redesigned.
- Upgraded `npm run supabase:doctor:live` so missing cloud tables map back to the repo SQL files that should be applied next. The current live project has base profile/billing/privacy tables, and the doctor now recommends applying SQL 003-007 to finish analytics, AI memory, persona, credits, and family cloud state foundations.
- Added `npm run supabase:bundle:missing` to generate a paste-ready SQL bundle at `dist/supabase/munea_missing_foundations.sql` from the current live doctor result. This lets the remaining Supabase schema apply happen through SQL Editor without guessing file order or exposing secrets.
- Added the first `/family/state` Supabase bridge: the API now reads/writes `family_state_entries` when the 007 table exists, while preserving JSON fallback until the live database apply is complete. This keeps the current family UI contract stable while moving shared family state toward the cloud source of truth.
- Added the `/wellbeing/*` Supabase bridge: manual mood check-ins, recent wellbeing signals, and trend reads now use `wellbeing_signals` when the 007 table exists, while preserving JSON fallback and the existing frontend response shape. This lets Claude/UI work continue without touching backend storage details.

## 2026-07-08 Update

- Added the `/family/activity` backend contract for family activity list/save/participant updates, backed by `family_activities` and `family_activity_participants` when the 007 tables exist.
- Preserved JSON fallback for family activities so Claude/UI work can continue before live Supabase SQL 007 is applied.
- Added smoke coverage for the Supabase adapter and server fallback path, including local-to-Supabase id preservation for future frontend handoff.
- Added the `/family/invitations` backend contract for list/create/update of family invite links and six-digit elder-friendly codes, backed by `family_invitations` when SQL 007 exists and JSON fallback before live apply.
- Added the `/consent-records` backend contract for list/grant/revoke of family sharing and AI/voice capability consent, backed by `consent_records` when SQL 007 exists and JSON fallback before live apply.
- Added the `/routine-reminders` backend contract for list/save/update/archive of medication, check-in, and routine reminders, backed by the existing `routine_reminders` table with JSON fallback and legacy `/care-schedule` compatibility.
- Connected the medication and visit reminder UI to `/routine-reminders`: manual settings, chat-created reminders, deletion/archive, and startup hydration now use the backend bridge while preserving localStorage fallback for offline/static preview.
- Added the `/family-members` backend contract for listing, adding, role/permission updates, and removal of family care-circle members, backed by `family_memberships` + `persons` with JSON fallback through the app profile store.
- Added the `/conversation-summary` backend contract for summary-only conversation memory: save/list/archive now uses `conversation_summaries` in Supabase with JSON fallback, explicitly avoiding raw transcript retention by default.
- Connected `/butler/post-turn` to the conversation summary contract so post-turn reviews now create summary-only records and link new memory items through `sourceConversationSummaryId`.
- Added the `/admin/conversation-summaries` read contract so operators can review summary-only companion memory records, tag counts, and safety-relevant totals without exposing raw transcripts.
- Added the `/admin/privacy-requests` read contract so operators can review export/deletion request status, reauth requirements, subscription notice needs, and retention policy from the Admin MVP trust surface.
- Added the `/admin/safety-events` read contract so operators can review Guardian risk events and safety-relevant summaries by risk level/category without exposing raw transcripts.

## 2026-07-09 Update

- Added the `/admin/audit-events` read contract so operators can review privileged entitlement, credits, subscription, and admin actions by event type, actor type, and target table.
- Extended the Supabase adapter with `audit_events` reads while preserving JSON fallback, keeping Admin MVP traceability available before the live schema is fully applied.
- Added the `/admin/accounts` read contract so operators can look up account, family group, primary person, companion identity, and family role counts without exposing conversation transcripts.
- Extended Admin MVP smoke coverage so account lookup is admin-token gated and works through both Supabase and JSON fallback.

## 2026-06-29 Update

- Added the first mobile microphone bridge path.
- Added `POST /voice-note` as a backend validation endpoint for recorded audio payloads.
- Updated smoke tests so the audio payload route is checked in full API verification.
- Added `docs/MOBILE-VOICE-BRIDGE.md` for iOS handoff and next device test steps.
- Ran local `npm install`, full smoke test, and Capacitor Doctor.
- Moved product architecture and Avatar development forward.
- Replaced `docs/ARCHITECTURE.md` with the current product/service architecture.
- Added `docs/PRODUCT-ARCHITECTURE-AVATAR-FIRST-PLAN.md`.
- Added frontend `MuneaAvatarRuntime` as the future insertion point for 2D viseme, Ditto, and LiveAvatar.
- Added Avatar engine modes and the first mock 2D viseme mouth-state layer.
- Added `docs/AVATAR-RUNTIME-QA.md` for local and iPhone visual QA.
- Added `docs/RUNPOD-AVATAR-POC-SCHEDULE.md` to anchor Ditto retest and first LiveAvatar benchmark around the RunPod console.
- Added `docs/TECH-STACK-EVALUATION-2026-06-29.md` to review the full product stack and confirm the best path.
- Added `docs/VOICE-PROVIDER-ADAPTER.md` and the first `window.MuneaVoiceProvider` / `/voice-session` contract.
- Split companion identity into user-chosen display name plus selectable character template, and redesigned Settings around product domains instead of duplicated role rows.
- Reduced Home visual density, redesigned the chat entry module, and split thumbnail avatar assets from fullscreen chat avatar assets.
- Reframed Chat as S2S call-first: visible text is state feedback only; transcript/captions are future accessibility options, not the default product surface.
- Added a shared browser-side Companion Profile contract so onboarding, Home, Chat, and Settings use the same `templateId` and `displayName`.
- Added local backend `/companion-profile` persistence as the bridge from prototype local storage to the future account database.
- Added `engine/app_profile_store.json` plus `/app-profile` so account, family group, primary person, and companion profiles share one local store before the production database move.
- Added App Store production readiness baseline: local `/entitlements`, `/subscription-event`, `/privacy-export`, `/account-deletion`, `/healthz`, `engine/billing_store.json`, `engine/privacy_requests.json`, and `docs/APP-STORE-PRODUCTION-READINESS.md`.
- Added Supabase production database bootstrap files: `supabase/sql/001_initial_munea_schema.sql`, `docs/supabase/SETUP.md`, and `docs/supabase/munea-env.example.txt`.
- Added `docs/BACKEND-ARCHITECTURE-v1.md` to lock the backend API, data, RLS, subscription, admin, and North Star analytics plan before deeper feature work.
- Added `engine/supabase_adapter.py` and wired companion profile load/save through a Supabase-ready adapter with JSON fallback.
- Extended the Supabase adapter so `/app-profile` can aggregate account, person, family group, family membership, and companion profile data when Supabase env is configured.
- Extended the Supabase adapter so `/entitlements`, subscription/usage ledger mapping, `/privacy-export`, and `/account-deletion` request creation can use Supabase when backend env is configured, with JSON fallback preserved.
- Added `supabase/sql/002_demo_bootstrap.sql` and demo env ids so a real Supabase project can be seeded for first backend adapter testing.
- Added `/avatar-session` as the backend contract for Avatar runtime selection, premium entitlement gating, `2d-viseme` fallback, and Avatar minute usage recording.
- Connected the frontend Avatar Runtime to backend `/avatar-session` so Chat startup consumes the backend-selected runtime mode instead of relying only on local browser choice.
- Added `?debug=avatar` runtime diagnostics and smoke coverage for the frontend Avatar session bridge.
- Added backend `engine/.env.local` loading plus `npm run supabase:doctor` / `npm run supabase:doctor:live` so Supabase wiring can be checked without exposing secrets.
- Added `supabase/sql/003_analytics_admin_foundation.sql`, `/product-event`, and token-gated `/admin/north-star` as the first North Star/Admin MVP data contract.
- Connected the web prototype to `/product-event` for safe Chat, Voice, Avatar, and routine-completion analytics without sending transcript text.
- Added `/account-bootstrap` as the backend-owned contract for creating account/member/person/family/companion rows after Supabase Auth or Apple Sign-In.
- Connected onboarding/settings to the account bootstrap contract with a one-time frontend bootstrap flag. Local JSON mode now creates the prototype account graph from the selected companion profile; Supabase mode fails safely with `auth_user_required` until verified Auth exists.
- Added `docs/AUTH-ONBOARDING-ARCHITECTURE-v1.md` to lock progressive onboarding, guest mode, v1 auth providers, registration fields, and the future Supabase Auth bridge. v1 providers are Sign in with Apple, Google, and email magic link/OTP fallback; Facebook is intentionally out of v1.
- Added browser Auth Bridge v0: `web/src/auth.js` exposes `window.MuneaAuth` for Apple, Google, email magic link/OTP, guest mode, sign-out, and Bearer-token API headers when a Supabase session exists. `web/src/auth-config.example.js` documents publishable-key-only browser configuration.
- Added local-only developer mode foundation: `MUNEA_DEV_CONFIG` can auto sign-in, skip onboarding, and mark all developer/test events as analytics-excluded. North Star summaries now exclude developer/internal/test/QA/ops events and configured excluded ids.
- Added Settings account UI foundation: guest/signed-in/developer status card, Apple/Google/email sign-in sheet, sign-out control, and developer-mode entry when local bypass is allowed.
- Documented the AI model boundary: the "three brains" are product responsibility layers, not three fixed models. Reflex is real-time conversation, Butler is background care context, Guardian is safety/referral, and Ditto/LiveAvatar are face engines.
- Added backend Auth verification foundation: `/auth-status` validates bearer-token auth context, and Supabase `/account-bootstrap` derives `auth.users.id` from verified auth instead of trusting a body-supplied id.
- Added `docs/AI-SERVICE-DESIGN-v1.md` to define Munea's AI service moat: three-brain model selection, effort profiles, long-term memory lifecycle, perception layer, Wisdom Lens, Guardian policy, and MVP implementation order.
- Added `engine/model_router.py` plus `/ai/brain-status`, `/memory/extract`, `/memory/retrieve`, and `/guardian/evaluate` contracts so Butler and Guardian can be tested before live model/provider wiring.
- Updated Butler and Guardian default target model to Claude Sonnet 5.
- Added `supabase/sql/004_ai_memory_service_foundation.sql` for `memory_items`, `perception_snapshots`, and `ai_brain_runs`.
- Added Supabase adapter support for `memory_items`, so `/memory/extract?action=store` and `/memory/retrieve` can use the production database path when env is configured, with JSON fallback preserved.
- Expanded Perception Layer from a movie example into a domain-aware topic framework for books, travel, outings, exercise, finance, video entertainment, music/audio, food, news, and wisdom/reflection, with anti-fabrication rules for recommendations.
- Added `/perception/snapshot` plus Supabase adapter path for `perception_snapshots`, giving time/weather/topic/current-fact providers a shared storage contract.

## Tech Stack Verdict

- Keep Capacitor + Web Core for first iOS TestFlight.
- Add a Voice Provider Adapter instead of hard-coding one Gemini model/version.
- Move data from local JSON to Postgres + RLS before multi-user testing.
- Keep Avatar Runtime and 2D viseme as the first TestFlight-safe face path.
- Keep Ditto / LiveAvatar behind measured RunPod PoC gates.
- Implement push and subscription/ledger foundations earlier than visual polish.

## Sprint 1-B: Handoff Baseline

Goal: make the repo safe for continued development.

- [x] Align README and SPEC to the current product direction.
- [x] Align language strategy to Taiwan Mandarin first, English second.
- [x] Mark old gpt-realtime / Taiwanese Hokkien assumptions as historical.
- [x] Fix `/open` role fallback.
- [x] Remove stale frontend id references.
- [x] Add repeatable smoke test script.
- [x] Add minimal Capacitor scaffold.

Definition of done:
- `git status -sb` is clean.
- Python files compile.
- JSON files parse.
- Frontend id refs are not broken.
- Static preview reaches `聊聊` without console errors.
- `/open` and `/chat` can be tested when the local engine is running.

## Sprint 1-C: Capacitor / iOS Shell

Goal: prepare the iOS app wrapper.

Work items:
- [x] Run `npm install`.
- [x] Verify Capacitor CLI and iOS package with `npx cap doctor`.
- [x] Prepare Mac-side TestFlight handoff checklist.
- [ ] On macOS with Xcode: run `npm run cap:add:ios`.
- [ ] Verify app opens the bundled `web/` shell.
- [ ] Add iOS usage descriptions for microphone and future HealthKit.
- [ ] Confirm WKWebView can load local assets and play audio after user gesture.

Go/no-go:
- iPhone can open Munea shell from Xcode.
- Existing static app UI works inside Capacitor.

## Sprint 1-D: Microphone Bridge PoC

Goal: validate the riskiest native bridge before building too much around it.

Work items:
- [ ] Add a minimal microphone test screen or hidden diagnostic route.
- [ ] Request iOS microphone permission.
- [ ] Capture microphone audio in WKWebView / Capacitor.
- [ ] Confirm audio can be passed to the voice layer.
- [x] Add backend `/voice-note` bridge endpoint for captured audio payloads.
- [x] Add smoke-test coverage for the voice payload route.
- [ ] Measure start latency and permission friction.

Go/no-go:
- If microphone capture is stable on device, proceed to Gemini Live loop.
- If unstable, evaluate native audio capture plugin or a small native bridge.

## Sprint 1-E: Gemini Live Voice Loop

Goal: shift from current POST-based demo to real-time speech interaction.

Work items:
- [x] Define `MuneaVoiceProvider` adapter.
- [ ] Confirm Gemini Live / Interactions API shape and auth model.
- [ ] Define frontend audio stream format.
- [ ] Build smallest loop: listen -> send -> receive voice -> play.
- [ ] Preserve fallback to typed/static demo mode.
- [ ] Track latency: first response, interruption, and recovery after network failure.

Go/no-go:
- Taiwan Mandarin voice feels natural enough for a first TestFlight.
- Latency is acceptable before avatar integration.

## Sprint 1-E2: Avatar Runtime MVP

Goal: move real-time Avatar development forward without blocking on GPU PoC.

Work items:
- [x] Define frontend Avatar Runtime contract.
- [x] Route idle/listening/thinking/speaking through the runtime.
- [x] Route character switching through the runtime.
- [x] Expose `window.MuneaAvatarRuntime` for development diagnostics.
- [x] Add avatar engine mode enum: `static-css`, `2d-viseme`, `ditto`, `liveavatar`.
- [x] Add a mock avatar engine that consumes audio duration and state events.
- [x] Add first 2D viseme / mouth-state PoC.
- [x] Add mobile visual QA checklist for idle/listen/think/speak.
- [x] Add backend `/avatar-session` contract for entitlement-gated Avatar mode selection.
- [x] Connect frontend Avatar Runtime to backend `/avatar-session`.
- [x] Add visible runtime diagnostics in development mode.
- [x] Add smoke coverage for Avatar session frontend bridge.
- [ ] Test idle/listen/think/speak on iPhone WKWebView.

Go/no-go:
- If 2D viseme is smooth on iPhone, use it as the first TestFlight avatar path.
- If Ditto / LiveAvatar PoC clears fps and cold-start gates, attach it behind the same runtime.

## Sprint 1-E3: RunPod Avatar PoC

Goal: turn the prior Ditto RunPod test and the unscheduled LiveAvatar benchmark into measurable go/no-go gates.

Work items:
- [x] Record RunPod console as the operating reference: `https://console.runpod.io/pods`.
- [x] Create a unified Ditto / LiveAvatar RunPod schedule and measurement form.
- [ ] Reopen or recreate the prior Ditto RTX 4090 pod and run online fps retest.
- [ ] Schedule LiveAvatar first benchmark on H100/H200 80GB+ single-card FP8 path.
- [ ] Record fps, cold start, VRAM, output path, quality verdict, and stop pod immediately after testing.

Go/no-go:
- Ditto online `>=25 it/s` with acceptable mouth sync: promote `ditto` from reserved mode to integration candidate.
- LiveAvatar `>=40 fps` and cold start can be hidden: keep `liveavatar` as premium candidate.
- Otherwise keep first TestFlight on `2d-viseme` + `static-css` fallback.

## Sprint 1-F: Data And Safety Foundation

Goal: stop relying on local JSON before multi-user work starts.

Work items:
- [x] Choose backend database stack.
- [ ] Implement Profile and Memory tables first.
- [x] Define first `family_group_id` and account-member permission model baseline.
- [ ] Add conversation memory and retention policy without making raw transcripts the default user-facing surface.
- [x] Define AI service design v1 for Reflex, Butler, Guardian, memory, perception, Wisdom Lens, and safety boundaries.
- [x] Add local AI Brain Router framework with deterministic memory extraction/retrieval and Guardian risk evaluation contracts.
- [x] Add Supabase AI memory/service schema draft for structured memories, perception snapshots, and model run logs.
- [x] Add Supabase adapter load/save path for `memory_items`.
- [ ] Wire Butler Brain to Claude Sonnet for live memory extraction and care summaries.
- [ ] Wire Guardian Brain to rules + Claude Sonnet + moderation/classifier layer.
- [ ] Add live perception tools for time, weather, current-topic retrieval, and regional recommendations.
- [x] Define domain-aware topic perception contract so recommendations are not movie-only and do not fabricate real-world availability, streaming catalogs, prices, schedules, market data, or news.
- [x] Add perception snapshot API and Supabase adapter path for real-world context facts.
- [x] Persist prototype companion template/name across onboarding, Home, Chat, and Settings.
- [x] Add local backend companion profile load/save route.
- [x] Add local account/family/person/companion profile store placeholder.
- [x] Add local subscription entitlement and usage ledger placeholder.
- [x] Add App Store production readiness checklist and API safety baseline.
- [x] Add deletion/export requirements and local data-rights API contracts.
- [x] Draft Supabase Postgres schema and RLS policy baseline.
- [x] Document Backend Architecture v1, including admin console and North Star dashboard plan.
- [x] Add Supabase-ready backend adapter with JSON fallback.
- [x] Add Supabase app profile aggregate adapter.
- [x] Add Supabase subscription/usage ledger adapter.
- [x] Add Supabase privacy request adapter.
- [x] Add deterministic Supabase demo bootstrap seed and env ids.
- [x] Add backend `.env.local` loading and Supabase doctor scripts.
- [x] Create Supabase project and run initial SQL through dashboard SQL Editor.
- [x] Add analytics/admin foundation schema for product events, North Star metrics, cost ledger, and admin notes.
- [x] Add backend `/product-event` and token-gated `/admin/north-star` contracts.
- [x] Emit safe frontend product events from Chat / Voice / Avatar / routine flows.
- [x] Add account bootstrap contract with local preview/create and Supabase adapter path.
- [x] Connect onboarding/settings to `/account-bootstrap` with safe retry and Auth-required handling.
- [x] Lock auth/onboarding product architecture: Apple, Google, email magic link/OTP fallback, guest mode, and progressive profile gates.
- [x] Implement Supabase Auth frontend bridge foundation for Sign in with Apple, Google, and email magic link/OTP.
- [x] Add local-only developer bypass and analytics exclusion for test/developer accounts.
- [x] Add production login UI foundation for Apple, Google, email OTP, sign-out, and local developer entry.
- [x] Add backend token verification foundation and derive `auth.users.id` from `Authorization: Bearer <access_token>` before Supabase account bootstrap.
- [ ] Test configured Supabase Auth providers end-to-end.
- [ ] Test backend token verification against a live Supabase Auth session.
- [ ] Convert remaining production endpoints away from body-provided identity fields.
- [ ] Add real local `engine/.env.local` values and run `npm run supabase:doctor:live`.
- [ ] Apply `supabase/sql/007_family_cloud_state_foundation.sql` to staging/live Supabase and confirm all table checks pass.
- [ ] Convert SQL draft into official Supabase migration after CLI/MCP authentication.

## Sprint 1-G: App Store Subscription And Trust Layer

Goal: make the product safe enough to move toward TestFlight and paid subscription design.

Work items:
- [x] Add `/entitlements` as backend source of truth for paid feature gates.
- [x] Add `/subscription-event` placeholder for StoreKit / App Store Server Notifications / RevenueCat webhook flow.
- [x] Lock Free / Plus / Premium / Concierge as the v1 subscription ladder.
- [x] Add `/healthz` service contract check.
- [x] Add request-size, audio MIME, audio-size, and safe API error guardrails.
- [x] Add `/privacy-export` and `/account-deletion` contracts for App Store account/data rights readiness.
- [ ] Choose StoreKit 2 direct validation vs RevenueCat for first paid launch.
- [ ] Configure App Store Connect subscription products and restore-purchase UX.
- [ ] Implement signed subscription event verification in production backend.
- [ ] Add account deletion and data export flow before App Review.

## Immediate Priority Order

1. Keep docs aligned to README + SPEC + `ARCHITECTURE.md`.
2. Lock the product architecture and Avatar Runtime contract.
3. Keep the runnable prototype stable with smoke tests.
4. Build Avatar Runtime MVP and 2D viseme fallback path.
5. Finish Capacitor shell setup and validate microphone on a real iPhone.
6. Build Gemini Live voice loop.
7. Attach Ditto / LiveAvatar only after PoC gates are real.
