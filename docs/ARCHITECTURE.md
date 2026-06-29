# Munea System Architecture

> Updated: 2026-06-29
> Scope: product and service architecture for the iOS-first Munea app.

## Product Position

Munea is an AI health-care companion app built around three product pillars:

1. AI health care.
2. Family interaction.
3. `聊聊` as the core daily relationship loop.

Family and older-adult care remain the first high-value market wedge, but Munea is not an elderly-only product. The app should support future expansion into broader family health, assisted living, clinics, pharmacies, and hardware-assisted services.

## User-Facing App Layers

| Layer | Purpose | Current State |
|---|---|---|
| Home | Daily greeting, reminders, quick entry into `聊聊` | Runnable prototype |
| 聊聊 | Fullscreen face, voice, subtitles, emotional companionship | Local Gemini chat/TTS demo + microphone bridge |
| Health Status | Health routines, Apple Health entry, trend summaries | Prototype UI |
| Family | Family view, encouragement, shared care loop | Prototype UI |
| Settings / Onboarding | Profile, avatar choice, family setup, device setup | Prototype UI |

The first-screen experience should lead with Munea as a living companion, not with an elderly-care label.

## Service Architecture

Munea is organized as four core layers:

```mermaid
flowchart TD
  App["iOS App Shell<br/>Capacitor + Web Core"]
  Conversation["Conversation Layer<br/>listen, respond, voice, subtitles"]
  Brains["AI Brains<br/>reflex, butler, guardian"]
  Data["Data Layer<br/>profile, memory, family, health, ledger"]
  Avatar["Avatar Runtime<br/>static fallback, 2D viseme, Ditto, LiveAvatar"]
  Safety["Safety Layer<br/>medical boundary, crisis referral, audit"]

  App --> Conversation
  Conversation --> Brains
  Conversation --> Avatar
  Brains --> Data
  Data --> Safety
  Brains --> Safety
```

## Three Brains

### Reflex Brain

Hot path for `聊聊`.

- Taiwan Mandarin first.
- English second.
- Taiwanese Hokkien remains research only.
- Current prototype uses Gemini generation + TTS.
- Target direction is a real-time voice loop behind a `MuneaVoiceProvider` adapter, with Gemini Live / Interactions as the first candidate rather than a hard-coded dependency.
- Current app contract exposes `window.MuneaVoiceProvider`; backend exposes `/voice-session` for capability metadata and future ephemeral real-time sessions.

### Butler Brain

Background context layer.

- Prepares today: health routines, appointments, weather, family notes, reminders.
- Reads from profile, memory, family, and health data.
- Must not block the live conversation.

### Guardian Brain

Safety and referral layer.

- Watches for crisis language, abnormal routine signals, and escalation needs.
- Refers to family or external help.
- Does not diagnose, prescribe, treat, or act as therapy.

## One Face: Avatar Runtime

Avatar is now moved forward as a core architecture track, but it must be staged correctly.

Current runtime contract:

| State | Meaning | Current Fallback |
|---|---|---|
| `idle` | Present and breathing | Static image + CSS breathing/blink |
| `listening` | User is speaking | Listening cue |
| `thinking` | AI is preparing a response | Thinking cue |
| `speaking` | Munea is speaking | Wave cue + face motion |

This state contract is the insertion point for future engines:

1. Static CSS fallback.
2. 2D viseme / lightweight live face.
3. Ditto standard talking head.
4. LiveAvatar high-end engine if PoC proves viable.

Principle: conversation continuity beats face fidelity. If an avatar engine is slow or unavailable, Munea keeps talking and degrades the face gracefully.

## iOS Shell

Munea uses Capacitor so the web core can become an iOS app first, Android later.

Native responsibilities:

- Microphone permission and capture.
- Push notifications.
- Future HealthKit bridge.
- App Store packaging.
- Optional native audio bridge if WKWebView microphone capture is unstable.

## Data Layer

The local JSON demo must be replaced before multi-user testing.

Recommended first production path: Postgres with row-level tenant isolation.

Minimum tables / collections:

- user profile.
- companion profile.
- family group.
- memory items.
- transcript references.
- health data snapshots.
- safety events.
- subscription / usage ledger.

Every production API must carry a tenant scope such as `family_group_id` and user/person scope. Cross-family memory leakage is a P0 failure.

## Development Order

The updated order is:

1. Stabilize the runnable prototype and smoke tests.
2. Define product/service architecture and runtime contracts.
3. Move Avatar Runtime forward with state-driven fallback.
4. Validate iOS microphone and app shell.
5. Build the real-time voice loop.
6. Attach the selected avatar engine to the already-defined runtime.
7. Replace local JSON with scoped data storage.

This brings avatar development forward without betting the product on an unproven GPU path.
