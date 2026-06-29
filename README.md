# Munea (沐寧)

> 會記得你，也在乎你在乎的人。

**Munea (沐寧)** is an iOS-first AI health-care companion app: a personal AI butler that lives in the phone, talks like a warm presence, remembers the person over time, helps with daily health routines, and keeps family connected when care should not be carried alone.

The first product starts as an App Store app, then extends toward a wider smart-health service layer: family dashboards, health-data connections, proactive care workflows, and future hardware / home-care integrations.

Munea is positioned as **smart care and companionship, not medical software**. It does not diagnose, treat, prescribe, or replace clinicians.

---

## Product Direction

- **Core user:** people who want daily AI health-care companionship, plus the family members who care about them.
- **First platform:** iOS first, Android later.
- **First experience:** open the app and use `聊聊`: a fullscreen butler face with speech-to-speech voice, memory, and gentle proactive care.
- **MVP scope:** Taiwan Mandarin voice companionship, health-routine reminders, family interaction, emotional safety referral, onboarding, and a family dashboard.
- **Language priority:** Taiwan Mandarin first, English second. Taiwanese Hokkien is research-only for now because there is no mature enough real-time product path, and Munea will not self-train a language model.
- **Future moat:** a warmer Taiwan Mandarin / English voice experience, richer avatar engines, deeper memory, health-data integrations, and hardware-assisted care services.

The working north star is an AI health-care companion for everyday life. Older-adult care is an important first scenario, not the product boundary. Munea should feel like a capable 30-35-year-old butler: warm, attentive, calm, and useful without making the user feel labeled.

---

## What Makes Munea Different

1. **Memory with boundaries**
   Munea remembers names, habits, preferences, family context, life stories, and recent emotional signals, but uses that memory to support daily life rather than diagnose.

2. **Family-aware care**
   Munea is designed for both individual use and family care. The person using Munea and the person checking in may be different, but the product should keep both sides calm, informed, and connected.

3. **Three brains, one face**
   The live conversation, background care planning, and safety referral logic are separated so the app can feel responsive while still becoming personal over time.

4. **Proactive, but iOS-realistic**
   When the app is closed, Munea reaches out through iOS push notifications. When opened, it becomes a full voice conversation with a talking face.

5. **Non-medical by design**
   Medication features are reminders, not advice. Emotional support is companionship, not therapy. Crisis handling routes to family or proper hotlines such as 1925 / 119.

---

## Current Prototype Status

As of 2026-06-29, this repo is no longer just pre-build planning. It contains a runnable local prototype:

- landing page, onboarding, app home, and family dashboard
- fullscreen butler-face conversation screen
- six selectable characters
- Gemini-backed prototype chat and TTS flow
- local memory demo through `engine/user_profile.json`
- Munea-style visual system and app shell

Run locally:

```bat
run-munea-app.bat
```

Or:

```powershell
$env:GEMINI_API_KEY="..."
py engine/server.py
```

Then open:

```text
http://localhost:8200
```

Secrets are expected in `engine/.env.local`, which is ignored by Git.

To check whether the backend is still using local JSON fallback or is wired to Supabase, run:

```powershell
npm run supabase:doctor
```

After `engine/.env.local` contains the real backend-only Supabase values, use the read-only live check:

```powershell
npm run supabase:doctor:live
```

---

## Architecture Snapshot

| Layer | Purpose | Current direction |
|---|---|---|
| Reflex brain | Live voice conversation | Gemini 3.1 Flash Live direction; local demo currently uses Gemini generation + TTS |
| Butler brain | Memory, schedules, context, daily care | Background rules + cheap AI when judgment is needed |
| Guardian brain | Crisis / anomaly referral | Family notification and hotline referral, not medical judgment |
| Face | Fullscreen butler presence | 2D/static now; Ditto / LiveAvatar PoCs decide real lip-sync path |
| Account bootstrap | First account/family/person creation after auth | `/account-bootstrap` previews or creates the backend-owned account graph; Supabase path requires verified `auth.users.id` |
| Companion identity | User-visible name, template, voice, and avatar asset | User can name the companion; template changes appearance / voice / personality without forcing a fixed public name |
| Subscription entitlement | App Store subscription and usage ledger | `/entitlements` is the backend source of truth; frontend does not own paid status or Avatar minutes |
| Avatar session | Runtime mode and premium Avatar usage decision | Chat startup calls `/avatar-session`; backend selects `static-css`, `2d-viseme`, `ditto`, or `liveavatar`, with premium fallback and usage ledger recording |
| Product analytics | North Star and Admin MVP data | Web core emits safe Chat/Voice/Avatar/routine events to `/product-event`; `/admin/north-star` is token-gated and summarizes Weekly Meaningful Companion Days |
| App shell | App Store delivery | Capacitor iOS shell planned; microphone bridge is the next go/no-go |

Critical principle: **conversation continuity beats face fidelity**. If avatar rendering is slow or unavailable, the app should keep the voice conversation alive and degrade the face gracefully.

Companion identity is intentionally split: `display_name` is what the user calls the companion, while `template_id`, `avatar_asset`, and `voice_profile` define how that companion looks, sounds, and behaves. This prevents Settings from becoming a repeated "choose a character" flow and keeps future family profiles flexible.

Chat is designed as speech-to-speech by default. The main experience should feel like a video call, not a transcript reader; visible text is limited to call state, safety prompts, and future optional accessibility captions.

The prototype now uses one Companion Profile across onboarding, Home, Chat, and Settings. Static preview stores it in local storage; full app mode also syncs it through `/companion-profile`. The local backend now mirrors that profile into `engine/app_profile_store.json`, which keeps account, family group, primary person, and companion profiles in one shape before the same model moves into the production database.

For App Store readiness, the local backend also includes `engine/billing_store.json`, `/entitlements`, `/subscription-event`, and `/healthz` contracts. These are prototype contracts for the production StoreKit / App Store Server API / RevenueCat path; production must verify signed subscription events server-side before granting paid entitlements.

The production database path is Supabase Postgres with Row Level Security. The first SQL schema draft lives in `supabase/sql/001_initial_munea_schema.sql`, and the deterministic demo seed lives in `supabase/sql/002_demo_bootstrap.sql`, with setup notes in `docs/supabase/SETUP.md`. These are SQL Editor-ready; once Supabase CLI is installed and authenticated, convert them into formal migrations.

Backend architecture v1 is tracked in `docs/BACKEND-ARCHITECTURE-v1.md`. It defines the API surface, Supabase/RLS model, subscription entitlement flow, data rights contracts, admin console MVP, and North Star analytics plan.

The backend now includes `engine/supabase_adapter.py`. By default the prototype still uses JSON fallback; setting `MUNEA_DATABASE_PROVIDER=supabase` with backend-only Supabase environment variables enables the Supabase path for companion profile reads/writes and `/app-profile` aggregation.

---

## Roadmap

### Phase 0 — Validate the hard gates

- Capacitor microphone bridge on iPhone
- avatar FPS / latency retest on proper GPU setup
- App Store privacy and non-medical copy review

### Phase 1 — First TestFlight path

- real-time voice loop
- basic butler memory
- fullscreen face state machine
- child-led onboarding
- health-routine reminder flow
- family dashboard skeleton

### Phase 2 — Product depth

- durable database-backed memory
- Apple Health / health-data connections
- push notification workflows
- safety referral flows
- points / subscription system
- six-character production quality

### Phase 3 — Service expansion

- improved Taiwan Mandarin / English voice quality
- richer avatar rendering
- B2B2C care partnerships
- optional hardware and home-care extensions

---

## Repository Map

```text
Munea/
├── README.md
├── STATUS.md
├── BACKLOG.md
├── docs/
│   ├── 00-總綱-從這裡開始.md
│   ├── SPEC-沐寧-v1-2026-06-28.md
│   ├── ARCHITECTURE.md
│   └── ROADMAP.md
├── engine/
│   ├── server.py
│   ├── chat_engine.py
│   ├── characters.json
│   └── user_profile.json
├── web/
│   ├── index.html
│   ├── family.html
│   ├── onboarding.html
│   ├── landing.html
│   └── src/
└── avatar-candidates/
```

For current planning truth, read these first:

1. `docs/00-總綱-從這裡開始.md`
2. `docs/SPEC-沐寧-v1-2026-06-28.md`
3. `docs/CURRENT-DEVELOPMENT-PLAN.md`
4. `docs/ARCHITECTURE.md`
5. `docs/PRODUCT-ARCHITECTURE-AVATAR-FIRST-PLAN.md`
6. `docs/AVATAR-RUNTIME-QA.md`
7. `docs/RUNPOD-AVATAR-POC-SCHEDULE.md`
8. `docs/TECH-STACK-EVALUATION-2026-06-29.md`
9. `docs/VOICE-PROVIDER-ADAPTER.md`
10. `docs/MOBILE-VOICE-BRIDGE.md`
11. `docs/APP-STORE-PRODUCTION-READINESS.md`
12. `docs/BACKEND-ARCHITECTURE-v1.md`
13. `docs/supabase/SETUP.md`
14. `docs/CODEX-SKILLS-SETUP.md`
15. `STATUS.md`
16. `BACKLOG.md`

Some older documents still preserve research history and may contain superseded assumptions, especially around GPT-Realtime, full self-hosting language, old character names, and pre-6/28 screen structure. The SPEC file is the current authority.

---

## Development Notes

- Windows/local prototype: use `run-munea-app.bat`.
- iOS packaging: requires macOS, Xcode, Apple Developer access, and Capacitor.
- Repeatable baseline check: `npm run smoke` when the local engine is running, or `npm run smoke:no-api` for static checks only.
- Codex operating skills for CTO/Munea development are repo-backed under `codex-skills/`. To continue on another Windows computer, run `powershell -ExecutionPolicy Bypass -File .\scripts\install-codex-skills.ps1` and restart Codex.
- The local development folder may still contain historical `PeiNing/peining` path names; GitHub and product naming are now **Munea / 沐寧**.
- Do not commit `engine/.env.local`.

---

## Compliance Line

Munea is a companion and life-reminder product. It does not provide medical diagnosis, treatment, prescriptions, dosage advice, or psychological counseling. Health concerns should be handled by qualified professionals; emergencies should be routed to appropriate services such as 119 or 1925.
