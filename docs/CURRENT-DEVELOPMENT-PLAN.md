# Munea Current Development Plan

> Updated: 2026-06-28
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
| Data backend | Local JSON demo only | 10-15% |
| Real-time avatar | PoC docs exist; not integrated | 15-25% |
| First TestFlight path | Not ready yet | 30-35% |

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
- [ ] Run `npm install`.
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
- [ ] Measure start latency and permission friction.

Go/no-go:
- If microphone capture is stable on device, proceed to Gemini Live loop.
- If unstable, evaluate native audio capture plugin or a small native bridge.

## Sprint 1-E: Gemini Live Voice Loop

Goal: shift from current POST-based demo to real-time speech interaction.

Work items:
- [ ] Confirm Gemini Live API shape and auth model.
- [ ] Define frontend audio stream format.
- [ ] Build smallest loop: listen -> send -> receive voice -> play.
- [ ] Preserve fallback to typed/static demo mode.
- [ ] Track latency: first response, interruption, and recovery after network failure.

Go/no-go:
- Taiwan Mandarin voice feels natural enough for a first TestFlight.
- Latency is acceptable before avatar integration.

## Sprint 1-F: Data And Safety Foundation

Goal: stop relying on local JSON before multi-user work starts.

Work items:
- [ ] Choose backend database stack.
- [ ] Implement Profile and Memory tables first.
- [ ] Define `family_group_id` and permission model.
- [ ] Add transcript retention policy.
- [ ] Add deletion/export requirements to the backlog.

## Immediate Priority Order

1. Keep docs aligned to README + SPEC.
2. Keep the runnable prototype stable with smoke tests.
3. Finish Capacitor shell setup.
4. Validate microphone on a real iPhone.
5. Build Gemini Live voice loop.
6. Only then connect real-time avatar.
