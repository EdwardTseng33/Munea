# Munea Release State

This file is the current cross-surface release snapshot. It answers what is in source, what is packaged, what is serving traffic, and what is still unknown. It does not replace deployment logs, `STATUS.md`, App Store Connect, Cloud Run, or a database migration ledger.

Snapshot time: `2026-07-17 12:24 Asia/Taipei`

Source verified at: `2026-07-17 12:15 Asia/Taipei`

Runtime last refreshed at: `2026-07-17 12:24 Asia/Taipei` (per-row evidence times control)

Source baseline: `origin/main@23395f0`

Maintenance role: `Release / Platform` (`unassigned`)

## Status vocabulary

| Status | Meaning |
|---|---|
| `coded` | Present in a branch or source file only |
| `merged` | Reachable from `origin/main` |
| `staged` | Deployed outside production, but not carrying production traffic |
| `deployed` | Deployed to the named environment and revision |
| `in-review-binary` | Included in the exact binary selected in App Store Connect |
| `production` | Carrying production traffic with a verified release identity |
| `verified` | The intended end-to-end behavior has passed its required live or human gate |
| `unknown` | The authoritative source was unavailable or could not prove the value |

`merged`, `deployed`, and `verified` are different states. A lower state must never be presented as a higher one.

## App lanes

| Lane | Version / Build | State | Evidence | Last verified |
|---|---|---|---|---|
| App Store review lane | Exact Build `unknown` | User confirmed that one build was submitted for review. Repo evidence only proves that `1.0.25 (Build 32)` was uploaded and entered processing; it does not prove which Build is selected or the current Apple state. | User statement; `STATUS.md`; `docs/APP-STORE-PRODUCTION-READINESS.md` | 2026-07-17 |
| Next source / binary | `1.0.31 (Build 38)` | Source, Web, package metadata, and iOS Debug / Release agree. Archive and iPhone installation are recorded; upload is explicitly frozen. | `package.json`; `web/src/version.js`; `ios/App/App.xcodeproj/project.pbxproj`; `STATUS.md` | 2026-07-17 |

The review lane is tracked independently and may only be updated from App Store Connect or explicit user-confirmed evidence. The next-binary lane must not overwrite its state.

## Runtime services

| Environment | Service | Traffic revision | Release identity | State and interpretation | Evidence time |
|---|---|---|---|---|---|
| staging | Brain | `munea-brain-staging-00055-vuc` receives 100% of this service's routing | `unknown`; serving `/version` returns 404 | Cloud Run routing is verified; actual staging workload and source version / commit are unknown. | 2026-07-17 12:01 |
| staging | Brain canary | `munea-brain-staging-00058-jid` at 0% | `1.0.28@741fec79c67a` | Exact-revision canary only. It is not current main and carries no default traffic. | 2026-07-17 12:01 |
| staging | Voice | `munea-voice-staging-00049-pob` receives 100% of this service's routing | `1.0.30@736593a6b382` | Cloud Run routing is verified; actual staging workload is unknown. The commit is an ancestor of current main, but the runtime is behind App source `1.0.31`. | 2026-07-17 12:01 |
| production | Brain | `munea-brain-00002-sul` receives 100% of this service's routing | `1.0.31@500c819f367d` | Deployed to the named production service with a verified release identity. Actual App / user workload is unknown, so this is not evidence that the review binary uses it. | 2026-07-17 12:24 |
| production | Voice | `munea-voice-00002-sub` receives 100% of this service's routing | `1.0.31@500c819f367d` | Deployed to the named production service with a verified release identity. Actual App / user workload is unknown, so this is not evidence that the review binary uses it. | 2026-07-17 12:24 |
| production | Call Control / Gateway | `munea-call-control-00008-bek` receives 100% of this service's routing | Source version / commit `unknown` | Anonymous `/health` correctly rejects with 401. Actual client traffic and public release identity are unknown. | 2026-07-17 12:01 |

Cloud Run service descriptions and public `/version` requests are the authority for the rows above. A tagged 0% revision must never be described as the serving revision.

## Database

| Item | Current state | Evidence | Last verified |
|---|---|---|---|
| Repo migration head | `018` | `supabase/migration-manifest.json` | 2026-07-17 |
| Tokyo migration `016` marker | Observed | `notification_events` exists; anonymous access is rejected as expected. This does not prove the full migration was applied. | 2026-07-17 read-only probe |
| Tokyo migration `017` | Missing | `notification_settings` returns `404 PGRST205` | 2026-07-17 read-only probe |
| Tokyo migration `018` | `unknown` | No authoritative applied-migration ledger or approved execution evidence | 2026-07-17 |
| Migration ledger / backup proof | `unknown` | Required before applying `017` or the destructive data-cleanup migration `018` | 2026-07-17 |

Repo manifests prove intended files and checksums; they do not prove live application. No SQL was applied while creating this snapshot.

## Operations console

| Item | Current state | Interpretation |
|---|---|---|
| Serving URL | `https://munea-brain-staging-491603544409.asia-east1.run.app/admin.html#overview` returns 200 | Reachable does not prove asset or API identity. |
| Serving revision | Follows staging Brain 100% revision `00055-vuc` | `/version` is 404; current asset commit is unknown. |
| Security headers on serving traffic | CSP, frame protection, `nosniff`, and referrer policy are absent | Phase A headers are not on the serving staging revision. |
| Verified admin canary | Brain `00058-jid` at 0%, `1.0.28@741fec7` | Header contract and privileged smoke passed on this canary only. It is not default traffic. |
| Privileged data source / freshness | `unknown` | Must prove Tokyo Supabase source, last-event timestamps, and fallback status before the console can be treated as operational truth. |

## Critical feature rollout states

| Capability | Current state | Missing proof |
|---|---|---|
| Voice same-voice transition cue (#145) | `merged`; `deployed` to staging Voice `00049-pob`; current production Voice identity `500c819` predates #145 | Deploy an exact commit containing #145 to production; prove the review binary uses production Voice; human Voice gate |
| Authenticated Voice-chain probe (#139) | `merged` with CI and release-check coverage | Controlled live wrapper run; Gateway deployment if required by the approved rollout |
| Notification settings migration (#140 / migration 017) | Code and doctor gate `merged`; database state is not deployed | Approved Tokyo backup, ledger, migration execution, and post-apply verification |
| Admin security headers (#133) | `merged`, `staged` on 0% Brain canary | Serving-traffic promotion decision and post-promotion smoke |
| App Store server notification receiver | `deployed` on production Brain; an empty POST is rejected with 400 | Signed Apple TEST notification receipt and Sandbox lifecycle verification |

## Known conflicts

- App Store Connect is authoritative for the selected review Build and review status. Repo files currently cannot prove either value.
- `STATUS.md` records Build 38 as not uploaded; `docs/APP-STORE-PRODUCTION-READINESS.md` still summarizes Build 33 / Build 32 and is stale for the next-binary lane.
- The collaboration board contains historical environment statements. It is an activity log, not a release authority.
- The health scorecard includes evidence from a 0% admin canary. That evidence must not be interpreted as serving-traffic capability.

## Unknowns that block a 90-point release assessment

- Exact App Store Connect review state and selected Build.
- Actual App / client routing to production Brain and Voice, including the review binary's configured targets.
- Production Gateway source commit and actual client traffic.
- Tokyo migration `018` applied state and authoritative ledger.
- Serving admin asset identity, privileged data source, and metric freshness.
- A live authenticated Voice chain covering Gateway lease, Call Token, Gemini media, cleanup, and release.

## Update rules

1. Verify the authoritative system for the field being changed: Git for source, App Store Connect for Apple state, Cloud Run and service metadata for runtime, and the approved migration ledger plus live probe for database state.
2. Every volatile fact must include a verification time. Live facts older than 24 hours must be rechecked before a release decision.
3. Never infer `production` from `merged`, `staged`, a Ready revision, or a 0% canary.
4. Unknown values stay `unknown`; do not copy older documentation into a current field without new evidence.
5. App upload, traffic shift, production deployment, migration, or rollback must update this snapshot before the change completes or in the same atomic handoff. Do not defer the update to a later review.
6. Do not store tokens, project secrets, user data, or privileged response payloads in this file.
