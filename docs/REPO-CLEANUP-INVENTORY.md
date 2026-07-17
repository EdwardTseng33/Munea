# Munea Repo Cleanup Inventory

This is a read-only cleanup evidence snapshot. It identifies callers, lifecycle uncertainty, duplication, and safe next actions. It does not authorize deletion, relocation, renaming, archiving, or automatic deduplication.

Snapshot baseline: `origin/main@ad3c2e8`

Verified: `2026-07-17 13:00 Asia/Taipei`

Tracked files: `880`

Confirmed owners: none. Roles below are suggested accountability roles, not assignments to a person.

## Safety rules

1. `unknown` means keep in place.
2. Exact file hashes prove equal bytes, not equal lifecycle or deployment semantics.
3. Runtime, migration, build, release-gate, and externally published paths are never bulk-cleaned.
4. A safe removal requires repository callers, CI callers, deployment callers, and external consumers all to be resolved.
5. Cleanup changes use one scoped PR per owner/workflow and include a rollback path.
6. Historical documents retain their original claims; add lifecycle metadata or successor links instead of rewriting history.

## Repository shape

| Segment | Tracked files | Current interpretation |
|---|---:|---|
| `docs/` | 173 | Mixed authority, dated plans, evidence, and history; authority clarity is the main issue, not size |
| `design-import/` | 145 | Imported design handoff/reference |
| `web/` | 92 | App WebView runtime, assets, admin shell, and browser test surfaces |
| `ds-bundle/` | 80 | Generated/local design handoff source |
| `scripts/` | 76 | Release, smoke, deployment, data, and operations tooling |
| `engine/` | 61 | Brain, Voice, AI, admin, adapters, and tests |
| `deploy/` | 60 | Cloud Run, Gateway, Avatar, RunPod, GLOWS, and PoC infrastructure source |
| `ios/` | 39 | Native iOS source and packaging assets |
| `app-site/` | 37 | Public Firebase-hosted website source |
| remaining segments and root | 117 | Database, CI, demos, prototypes, sales, publication, tooling, and unclassified assets |

## P0: paths that must not move or lose files without evidence

| Path | Classification | Caller evidence | Failure risk | Safe action | Suggested role |
|---|---|---|---|---|---|
| `web/` | `runtime/source` | `Dockerfile` copies it; Capacitor `webDir` packages it; App and admin assets load by path | Break Cloud Run, iOS binary, or WebView | Keep path; build a per-file caller manifest before any asset change | App / Release |
| `ios/` | `runtime/source` | Xcode project, Asset Catalog, entitlements, archive/export scripts | Break signing, packaging, permissions, or App Store binary | Mac/Xcode verification is mandatory for any structural change | App / Apple Release |
| `engine/` | `runtime/source` | Docker entrypoints and launch tests import Brain/Voice modules | Break Brain, Voice, admin, AI, or data paths | Structural work only in a dedicated backend PR | Backend / AI |
| `deploy/` | `infrastructure-source` | Live Cloud Run, Gateway, RunPod, GLOWS, and Avatar workflows | Break deployment, probes, rollback, or GPU control | Preserve; first map each active script to service and owner | Platform |
| `supabase/` | `migration-source` | Manifest order/checksums and release doctor gates | Irreversible schema/data error | Add ledger evidence only; do not rename, merge, or reorder migrations | Data / Security |
| `.github/`, `scripts/`, `tools/`, root build configs | `release-tooling/source` | Package scripts, CI, release gates, Docker, Firebase, and Capacitor call these paths | A file may look unused while still controlling release safety | Require both caller graph and recent workflow evidence before orphan status | Platform / Release |
| `app-site/` | `runtime/source-public-site` | `firebase.json` sets `public: app-site` | Break public web/legal/marketing pages | Keep; verify hosting build and live URLs after asset work | Growth Web / Release |
| `web/avatars/motion/` | `runtime-asset` | 13 MP4, about 27.75 MiB; `FACE_MOTION` and landing page reference character files | Break character intro/idle behavior and App binary | Compression may be evaluated separately; do not rename or remove | App / Avatar |
| `web/flashhead/` | `runtime-asset` | App, FlashHead test page, and Modal test service reference the five files | Break live face composition or QA | Keep; canonicalization requires updating every caller and visual QA | Avatar / App |

## P1: classify before cleanup

| Path | Classification | Evidence / uncertainty | Safe next action | Suggested role |
|---|---|---|---|---|
| `deploy/cloudrun/*.sh` | `active-but-conflicting` | `prod-deploy.sh` and App defaults use non-suffixed production services; other executable staging/canary/promote scripts and comments contain conflicting environment-role statements | Platform PR: verify every active/retired role against live topology, add routing/identity tests, and never delete a script from comments alone | Platform / Release |
| `app-site/assets/` | `runtime-asset-public-site` | 27 files, about 12.35 MiB; pages reference them; some are exact copies of `web/` assets | Generate page reference graph; only classify a file unused after live-site verification | Growth Web / Design |
| `design-import/` | `imported-reference` | 145 files; 77 exact-hash matches with `ds-bundle/`; handoff README still directs agents here | Add source/import date/successor/checksum metadata; Design confirms canonical workflow | Design |
| `ds-bundle/` | `generated-reference / handoff-source` | 80 files; `.design-sync/config.json` points to it and says keep | Document regeneration command and canonical owner; keep in place | Design / Engineering |
| `prototypes/` | `prototype/reference` | 9 files match `ds-bundle/_preview`; lifecycle and external links are unknown | Add lifecycle/source labels; archive only after Product/Design approval | Product / Design |
| `.design-sync/` | `generated-reference + active-tool-state` | Config points to `ds-bundle`; `engine/server.py` writes captures | Keep config/conventions; captures only through the owning sync workflow | Design Tooling |
| `App store pic/` | `publication-artifact` | 5 PNG, about 12.93 MiB; no runtime caller; selected Version/Build association unknown | Add Version/Build, locale, size, upload date, and current/retired manifest | Apple Release / Marketing |
| `_SalesKit-2026-07/` | `dated-commercial-artifact` | 8 files, about 17.50 MiB; no runtime caller; product/price freshness unknown | Add product baseline and commercial owner; dated archive only after confirmation | Sales / Product Marketing |
| `demo-cloud/` | `executable-demo` | Independent deploy scripts and docs; duplicate avatars may be necessary for isolated deployment | Confirm live consumer, credential handling, and retirement conditions; separate security review | Demo / Sales Engineering / Security |
| `deploy/flashhead-poc/` | `poc-source + reference-assets` | Its own HTML/create workflow plus RunPod, GLOWS, and technical documents reference the PoC path | Record last reproducible date and successor; preserve until replacement is proven | Avatar / Platform |
| `docs/`, `STATUS.md`, collaboration board | `mixed-authority + historical` | `STATUS.md` and board are large; current and historical claims are interleaved | Add authority/lifecycle/superseded links; never bulk-rewrite history | Product / Release / Documentation |
| `assets/`, root preview images | `unclassified` | Root icon/logo match `web/icons`; repo caller absent, external consumer unknown | Record hash, dimensions, and external-consumer check; keep until confirmed | App / Design |
| `voice-samples/` | `engineering-tooling/source` | Generator is referenced by voice-cast workflow; generated audio is ignored | Keep; add README, output path, and credential prerequisites | Voice / AI |

## Duplicate evidence that is not deletion evidence

| Duplicate group | Evidence | Why it must stay for now |
|---|---|---|
| `design-import/` vs `ds-bundle/` | 77 of 80 bundle files have exact-hash matches | Both are referenced by separate design handoff/sync semantics |
| `prototypes/` vs `ds-bundle/_preview` | Nine prototype files match preview outputs | Product comparison and external-link lifecycle are unknown |
| `app-site/assets/` vs `web/` / `demo-cloud/` | Multiple character and screen assets are byte-identical | Separate deploy roots may require local copies |
| root `assets/icon.png` and `assets/logo.png` vs `web/icons/` | Exact hashes match | Repo-external packaging/design consumers are unknown |
| iOS Splash 1x/2x/3x files | Some slots contain identical bytes | Asset Catalog slots have semantic scale/appearance roles; automatic dedupe would break packaging expectations |

## High-value cleanup queue

| Priority | Task | Completion proof | Destructive action allowed? |
|---|---|---|---|
| P0 | Resolve Cloud Run service-role/script conflict | One topology document, tested script entrypoints, `/version` identity checks, rollback path | No deletion in the first PR |
| P0 | Establish database applied-migration ledger and recovery evidence | Live ledger, backup timestamp, restore owner, doctor check | No migration rewrite |
| P1 | App Store publication manifest | Every screenshot mapped to Version/Build/locale/state | Only owner-approved archival later |
| P1 | Design canonical workflow | `design-import`, `ds-bundle`, prototypes, and captures have source/successor/regeneration metadata | Only after Design approval |
| P1 | Public-site/demo asset reference graph | All local and external callers resolved; live deployments verified | Only proven orphans in a separate PR |
| P1 | Document lifecycle headers | Current, supporting, snapshot, historical, and superseded documents are routed | No historical rewrite |
| P2 | Runtime media size optimization | Before/after App size and six-character visual/voice QA | Compression only; preserve paths/contracts |

## 90-point acceptance gates

The previous `64` Repo-structure score is a dated snapshot. This inventory improves classification but does not justify a 90 score. Repo structure reaches 90 only when:

1. Critical directories and release scripts have confirmed accountable owners.
2. Every deployment entrypoint has one environment role, source identity check, and rollback path.
3. Current documents have automated freshness/lifecycle validation.
4. Database files map to a live applied-migration ledger.
5. Publication, design, demo, sales, and prototype assets have external-consumer manifests.
6. Any deletion or relocation is backed by caller analysis, owner approval, targeted tests, and rollback evidence.

## Update protocol

1. Add evidence; do not convert `unknown` to unused without caller and owner proof.
2. Recalculate counts and hashes when source baseline changes materially.
3. Keep cleanup PRs owner/workflow-specific; never combine App assets, database migrations, deployment scripts, and historical docs.
4. Record removed paths and successors in the PR and relevant authority document.
