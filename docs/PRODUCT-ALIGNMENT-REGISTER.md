# Munea Product Alignment Register

This register answers whether the current product promise, source, binary, AI behavior, service deployment, data state, and human verification still describe the same product. It complements `docs/RELEASE-STATE.md`; volatile release identities remain authoritative there.

Snapshot baseline: `origin/main@ad3c2e8`

Source verified: `2026-07-17 13:00 Asia/Taipei`

Runtime evidence window: `2026-07-17 12:43 Asia/Taipei`

Confirmed owners: none. Roles below are suggested accountability roles, not assignments to a person.

## Alignment vocabulary

| State | Meaning |
|---|---|
| `aligned-source` | Product documentation and current source agree; deployment or human proof may still be separate |
| `partial` | Some layers agree, but one or more required layers remain unproved or behind |
| `runtime-behind` | Serving runtime has a verified identity older than the source capability being assessed |
| `blocked` | A known dependency prevents the intended product behavior from completing |
| `unknown` | The authoritative system was not available or did not expose enough evidence |

`merged`, `packaged`, `deployed`, and `human-verified` are independent facts. This register never promotes one into another.

## Distribution and service alignment

| Surface | Product/source authority | Current source or binary | Runtime / external evidence | Alignment | Next gate | Suggested role |
|---|---|---|---|---|---|---|
| App source/upload lane | `package.json`, `web/src/version.js`, Xcode project | `1.0.32 (Build 39)` is aligned across source; archive and Edward iPhone installation are recorded | Upload succeeded at 12:45 and Apple processing is recorded; repo evidence says review submission remains pending | `aligned-source` | Human Voice gate; confirm processing completion and whether Build 39 is selected/submitted | App / Release |
| App Store review lane | App Store Connect | Exact selected Build and current review state are `unknown`; user confirmed that one build was submitted | Repo evidence cannot identify that binary; Build 39 is separately recorded as uploaded/processing with submission pending. A binary older than Build 34 may predate the production-target switch | `unknown` | Mac/App Store Connect evidence: Version, Build, state, binary targets | Apple Release |
| Packaged service targets | `web/src/app.js` plus release package gates | Packaged defaults point to non-suffixed production Brain, Voice, and Call Control | Actual review-binary targets and real client request flow are not observed | `partial` | Inspect selected review binary; authenticated production call trace | App / Platform |
| Production Brain | `engine/server.py`, `deploy/cloudrun/prod-deploy.sh` | Brain runtime source is content-equivalent between deployed commit `500c819` and current main | `munea-brain-00002-sul`, `1.0.31@500c819`, 100% service routing | `partial` | Do not redeploy for metadata alone; verify real App/API flow and carry current identity with the next approved Brain change | Backend / Platform |
| Production Voice | `engine/live_voice_server.py`, `deploy/cloudrun/prod-deploy.sh` | Current main contains later Voice behavior including #145 | `munea-voice-00002-sub`, `1.0.31@500c819`, 100% service routing | `runtime-behind` | Deploy exact intended commit; authenticated Voice and human gate | Voice / Platform |
| Staging Brain and operations console | Open PR #149, `engine/server.py`, admin assets | Serving staging commit `962a667` is not in `origin/main` | `munea-brain-staging-00059-jeh`, 100% service routing; `/version` and admin security headers verified | `partial` | Merge/rebase #149, redeploy final main identity, privileged smoke | Backend / Operations |
| Staging Voice | `engine/live_voice_server.py` | #145 source commit is present in current main | `munea-voice-staging-00049-pob`, `1.0.30@736593a`, 100% service routing | `partial` | Human Voice gate; production deployment decision | Voice |
| Call Control / Gateway | `deploy/gateway/`, packaged App default | App source requires the production Gateway outside development bypass | `munea-call-control-00008-bek`, 100% service routing; anonymous health rejects with 401; release identity unknown | `partial` | Add public release identity; authenticated lease/call/cleanup trace | Platform |
| Avatar worker fleet | `deploy/runpod-avatar/`, App `CallControl` and FlashHead mapping | FlashHead is the default for two realistic launch characters; other characters use 2D behavior | Worker version identity and current real-client traffic are not exposed in this snapshot | `unknown` | Gateway-to-worker release identity, capacity snapshot, long-call human QA | Avatar / Platform |

## Product, AI, data, and operations alignment

| Capability | Product promise and source evidence | Deployed / verified evidence | Alignment | Known drift or blocker | Next gate | Suggested role |
|---|---|---|---|---|---|---|
| Voice microphone and dead-line recovery (#136) | Included in Build 39: uplink is prepared before greeting, dead uplink rebuilds, dead-line call retries | Archive and Edward iPhone installation recorded | `partial` | Human call result is not recorded | Test immediate speech pickup, forced uplink recovery, and silent/dead-line recovery on iPhone | App / Voice QA |
| Same-voice lookup transition (#145) | Merged in main and present in staging Voice `736593a` | Not present in production Voice `500c819` | `runtime-behind` | Production users cannot be assumed to hear the same-voice cue | Deploy intended Voice commit, then five human lookup turns | Voice / AI |
| Live lookup fallback | Voice source has bounded model fallback, timeout, breaker, and source-bearing lookup response | Staging Voice identity contains the implementation | `partial` | Production Voice is older; human latency and failure behavior are not verified | Production canary plus grounded-answer and failure-mode human gate | Voice / AI |
| Reflex Brain | `engine/live_voice_server.py` uses Gemini Live and source-level turn/Guardian policies | Production Voice identity is known, but exact model/config response was not probed | `partial` | Runtime model/config and end-to-end Call Token path are not evidenced | Authenticated live probe exposing safe release/model metadata plus human QA | Voice / AI |
| Butler Brain | `engine/model_router.py` declares Anthropic / `claude-sonnet-5`; memory, chat, and perception source include local contracts plus Google GenAI calls | No Anthropic client call or production provider trace was found in the declared router path | `blocked` | Executable provider behavior is Gemini/deterministic while current authority documents declare Claude Butler | Decide provider authority, then align adapter, tests, cost/safety telemetry, docs, and deployed trace | AI / Backend |
| Guardian Brain | Deterministic rules and Google GenAI semantic review are implemented; source also declares Claude and independent moderation plans | Rule behavior is testable; no production Anthropic or OpenAI-moderation provider trace was found in the declared router path | `partial` | The safety foundation exists, but provider authority and the claimed multi-layer pipeline are not aligned | Keep deterministic authority; align semantic/moderation providers, audit events, and red-team gate | Safety / AI |
| Memory and perception | Memory reconciliation, Supabase adapter paths, perception snapshots, and daily briefing code exist | Live schema application is not fully ledgered; #149 maintenance path is deployed to staging before merge | `partial` | Scheduler, final main identity, live data freshness, and full migration state are unknown | Merge final code, ledger DB, configure scheduler, verify one full daily cycle | AI / Data |
| Family invitations and family care loop | App/backend invitation, family, relay, and consent contracts exist | Real-account entitlement and purchase-backed invitation flow are not evidenced end to end | `blocked` | StoreKit/entitlement production proof is missing | Sandbox purchase -> entitlement -> invite -> approval -> family relay verification | Product / Backend |
| Notification platform | Source migrations 016-017, notification APIs, inbox, devices, and Apple server receiver exist | 016 marker observed; 017 missing; production receiver rejects empty POST with 400 | `blocked` | Missing 017 makes settings silently fall back to non-durable container-local JSON; APNs and Apple lifecycle proof are also absent | Backup, ledger, apply 017, verify durable settings, APNs, and Apple TEST/Sandbox lifecycle | Data / Notifications |
| Billing and credits | Free/Plus/Pro policy, StoreKit mapping, ledger and verification contracts exist | Automated contracts pass in repo history | `partial` | Real Sandbox purchase, renewal, cancellation, restore, and refund reversal are not verified | Full StoreKit Sandbox lifecycle with server ledger reconciliation | Billing / Apple Release |
| Apple Health | Native HealthKit and App connection/disconnect UX exist in source | No current manual consent/refusal/sync/reinstall evidence in this snapshot | `partial` | Source capability is ahead of human acceptance evidence | iPhone consent, refusal, disconnect, future-sync stop, and reinstall tests | App / Privacy QA |
| Six-character experience | Character/persona assets and source mappings exist; realistic FlashHead maps Ningning/Ahong, others retain 2D behavior | Cross-character Voice/avatar human acceptance is not current | `partial` | Design docs still mix Ditto-era and current FlashHead terminology | Publish current character matrix; verify persona, TTS, realtime Voice, face, and fallback per character | Product / Design / Voice |
| Operations console | Staging shell is reachable; serving revision identity and CSP/frame/nosniff/referrer headers are verified | Privileged APIs, Tokyo data source, empty-state truth, timestamps, and fallback status were not probed | `partial` | A secure shell is not yet operational-truth evidence | Privileged read-only smoke with source project, freshness, and fallback assertions | Operations / Data |
| Medication photo privacy | App and Brain strip medication photos from cloud payloads; migration 018 is the historical cleanup source | Medication data source exists, but applied state of cleanup migration 018 is unknown | `partial` | Existing cloud photos cannot be claimed clean without ledger/probe evidence | Backup, approve 018, dry-run counts, apply, and zero-photo verification | Privacy / Data |
| Authentication and data rights | Apple/Google auth bridge, account bootstrap, export, and deletion contracts exist | Automated contracts exist; current live account E2E is not evidenced | `partial` | True Apple/Google sign-in, bootstrap, scoped export, and deletion remain unverified | Controlled production-like test account from sign-in through deletion | Identity / Privacy |

## AI provider reality matrix

| Brain | Declared design | Implemented source | Deployed evidence | Verified evidence | Current conclusion |
|---|---|---|---|---|---|
| Reflex | Gemini Live through `MuneaVoiceProvider` | `engine/live_voice_server.py` makes the realtime Google GenAI connection and implements turn, lookup, and safety policies | Production and staging Voice identities are observable | Source and automated contracts only; authenticated chain and human gate remain open | Real provider path exists; deployment is behind current source and not fully verified |
| Butler | Claude Sonnet 5 through `MuneaBrainRouter` | Router metadata/local contracts plus executable Google GenAI paths in memory, chat, and perception; no Anthropic client call was found | No provider-specific deployed trace | None for Claude execution | Actual Gemini/deterministic behavior and declared Claude authority are not aligned |
| Guardian | Deterministic policy plus Claude Sonnet 5 and a moderation layer | Deterministic rules plus Google GenAI semantic review; no Anthropic/OpenAI-moderation call was found in the declared router path | Rule layer may ship with Brain; provider-specific identity is absent | Rule contracts exist; independent Claude/moderation runtime is unproved | Safety foundation exists, provider authority and multi-provider pipeline are incomplete |

## Confirmed documentation drift

- `docs/APP-STORE-PRODUCTION-READINESS.md` is behind the current source/binary lane and must be refreshed from App Store Connect evidence, not from `STATUS.md` alone.
- `docs/CURRENT-DEVELOPMENT-PLAN.md` contains early Sprint 1 tasks that current source has passed; it is planning history until a product owner refreshes it.
- `docs/00-總綱-從這裡開始.md` still mixes Ditto-era Avatar language with the current FlashHead default and describes Butler/Guardian model plans more strongly than the executable provider path supports.
- `docs/AVATAR-RUNTIME-QA.md` still describes a static/2D-era runtime and does not represent the current FlashHead/Gateway production path.
- `docs/BILLING-CREDITS-ENTITLEMENT-v1.md` contains deployment wording that is behind the current production Brain endpoint state; live payment verification remains separate.
- Cloud Run scripts disagree about whether the suffixed staging pair or non-suffixed pair is production. Current App defaults and `prod-deploy.sh` use the non-suffixed pair; conflicting comments and entrypoints must not override verified runtime and source behavior.

## 90-point acceptance gates

The previous `60` product-alignment score is a dated snapshot. This register improves observability but does not by itself raise the implementation score. A new score may reach 90 only when all of these are evidenced:

1. App Store review Build, source commit, packaged service targets, and Apple state are known.
2. Each critical capability has separate source, deployed, and human-verification evidence.
3. Butler and Guardian documentation matches executable provider behavior; declared model names are not counted as integration.
4. Production Brain, Voice, Gateway, and Avatar expose release identity and are covered by an authenticated chain probe.
5. Database migrations have an authoritative ledger and recovery proof.
6. Operations metrics prove data source, freshness, empty-state behavior, and fallback status.
7. Product, UX, AI, billing, privacy, and service documents link to this register or a confirmed topic authority without contradictory current claims.

## Update protocol

1. Update a row in the same handoff as a binary, deployment, migration, product gate, or authority change.
2. Cite the authoritative layer used; never promote `merged` to `deployed` or `deployed` to `human-verified`.
3. Keep unavailable evidence as `unknown` and assign a next gate.
4. Reverify runtime rows older than 24 hours before release decisions.
5. Do not store tokens, user data, privileged payloads, or commercial secrets here.
