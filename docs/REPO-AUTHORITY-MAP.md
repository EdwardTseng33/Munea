# Munea Repo Authority Map

This map classifies repository areas and documents without moving or deleting them. It defines where to look first and which files must not be treated as current runtime truth.

Snapshot baseline: `origin/main@c0b43d5`

Confirmed owners: none. Role names below are suggested accountability roles, not assignments to a person.

## Authority levels

| Level | Meaning |
|---|---|
| `authority` | Controls the stated decision for its scope |
| `supporting` | Provides implementation detail or evidence but cannot override the authority |
| `snapshot` | Accurate only for its stated date / commit |
| `historical` | Preserved decision or execution history |
| `generated-reference` | Tool output, synchronized bundle, or imported reference; not runtime source |
| `unclassified` | Purpose or owner is not sufficiently verified; do not delete or move |

## Runtime and source directories

| Path | Classification | Release impact | Suggested accountable role | Handling rule |
|---|---|---:|---|---|
| `web/` | App WebView runtime and frontend source | Critical | App | Do not reorganize while App work is active; changes may require Capacitor sync and a new binary. |
| `ios/` | Native iOS project and packaged resources | Critical | App / Release | Do not move; version, entitlements, native parts, and signing gates depend on these paths. |
| `engine/` | Brain, Voice, admin API, AI and data adapters | Critical | Backend / AI | Do not move; deployment and contract tests reference these modules. |
| `deploy/` | Cloud Run, Gateway, Avatar and infrastructure source | Critical | Platform | Treat scripts and defaults as release-affecting code. |
| `supabase/sql/` | Intended database migration source | Critical / potentially irreversible | Data / Security | `supabase/migration-manifest.json` controls file order and checksums; live state requires a separate ledger and probe. |
| `.github/` | CI, watchdog and repository automation | High | Platform / Release | Gate changes require independent review. |
| root deployment files | `Dockerfile`, `firebase.json`, Capacitor and package metadata | Critical | Platform / Release | Keep at stable paths; these can affect packaging or deployment. |
| `app-site/` | Public website runtime | High | Growth / Web | Separate from the iOS App WebView runtime. |
| `demo-cloud/` | Executable demo environment | Not App production; external demo impact is unknown | Demo | Do not present as production behavior or move until external consumers are verified. |
| `scripts/`, `tools/` | Tests, release checks and operations tooling | Up to Critical | Engineering / Release | A tool used by a hard gate is release-critical even if it is not runtime code. |
| `codex-skills/`, `.claude/` | Agent and collaboration tooling | Medium; can become High | Engineering | Preserve until callers and workflows are inventoried. |

## Assets and reference directories

| Path | Classification | Current conclusion | Handling rule |
|---|---|---|---|
| `design-import/` | Imported design reference | Not production runtime authority | Keep in place until the source-of-design workflow is confirmed. |
| `ds-bundle/` | `generated-reference` design synchronization bundle | Must not be used as App release truth | Regenerate or archive only through the owning design workflow. |
| `.design-sync/` | Tool state and generated captures | Active tooling may write here | Do not delete without tracing current tooling. |
| `prototypes/` | Prototype / reference | Per-file lifecycle is not verified | Do not bulk-archive or delete based on directory name alone. |
| `App store pic/` | External publication artifact | Does not prove current App Store selection | Verify campaign / Build association before reuse. |
| `_SalesKit-2026-07/` | Sales artifact | Does not define product behavior or pricing authority | Preserve as dated collateral until commercial owner confirms lifecycle. |
| `voice-samples/` | Engineering tooling / source | Contains the voice-sample generation tool; all callers and output locations are not fully classified | Do not move until generation and QA workflows are traced. |
| `assets/` and root images | `unclassified` asset | External consumers are not fully known | No deletion or move in the first cleanup phase. |

## Document authority

| Scope | File | Level | Current interpretation |
|---|---|---|---|
| Cloud Run service topology | `deploy/cloudrun/SERVICE-TOPOLOGY.md` | `authority` for service roles and repo entrypoints | Defines production/staging names, active deploy/promote lanes, retired paths, release identity and rollback rules. Live Cloud Run state and `/version` remain runtime authority. |
| Cross-surface release truth | `docs/RELEASE-STATE.md` | `authority` | Current version, App lanes, live revisions, DB frontier, admin state, conflicts, and unknowns. Volatile facts require timestamps. |
| Product implementation alignment | `docs/PRODUCT-ALIGNMENT-REGISTER.md` | `authority` for alignment mapping and gates | Maps product promises to source, deployment evidence, verification state, and next gate. Exact versions and runtime revisions are timestamped references governed by `docs/RELEASE-STATE.md`; this register cannot override App Store Connect, Cloud Run, or the database ledger. |
| Repo cleanup evidence | `docs/REPO-CLEANUP-INVENTORY.md` | `snapshot` / supporting | Caller and lifecycle inventory for safe cleanup. It grants no permission to delete, move, or archive a path. |
| Activity and execution history | `STATUS.md` | `historical` / supporting log | Append-only evidence and handoff history. It is not the single current release answer. |
| Documentation navigation | `docs/00-總綱-從這裡開始.md` | routing `authority` | Its 2026-07-18 current override and current snapshot route version, pricing, runtime, DB and quality facts to the topic authorities. Older counts and dated sections remain historical context and cannot override those files. |
| App Store checklist | `docs/APP-STORE-PRODUCTION-READINESS.md` | `supporting`, `current-stale` | Detailed release checklist; its recorded candidate and source lanes are behind current source. App Store Connect remains authoritative for Apple state. |
| Development plan | `docs/CURRENT-DEVELOPMENT-PLAN.md` | `authority` for current execution order | The 2026-07-18 header states the source／uploaded lanes, approved points, P0 gates and next actions. Dated sections below it are preserved execution history and cannot override release, quality or billing authorities. The path is machine-governed as `development-plan`. |
| Backend architecture | `docs/BACKEND-ARCHITECTURE-v1.md` | `supporting` | Architecture reference; parts predate the current admin and production topology. |
| Health assessment | `docs/HEALTH-90-SCORECARD-2026-07-16.md` | `snapshot` | Evidence-based assessment at its stated baseline, not a live release registry. |
| Voice experience plan | `docs/聊聊查資料與清晨備料-體驗計畫-2026-07-16.md` | `supporting`; declared feature SSOT, routing pending | PR #144 is merged, but this file must be routed by the documentation navigation authority before it is treated as the discoverable feature authority. It never controls global release state. |
| Archived decisions | `docs/archive/*` | `historical` | Lifecycle is governed by `docs/archive/README.md`. |
| Root overview | `README.md` | `supporting`, currently stale in places | Developer entry point; version or prototype statements must not override release state. |
| Backlog | `BACKLOG.md` | `supporting`, currently stale | Planning history; completion must be checked against current source and rollout state. |

## Confirmed conflicts

- Cross-surface source, binary, runtime, database, and admin state are not aligned. The exact volatile values belong only in `docs/RELEASE-STATE.md`.
- App Store readiness, README and backlog still contain stale version or progress statements. The development-plan header and documentation-entry current snapshot were refreshed on 2026-07-18, but neither may replace volatile facts in `docs/RELEASE-STATE.md`.
- Product claims, implementation state, deployment state, and human verification are separate columns in `docs/PRODUCT-ALIGNMENT-REGISTER.md`; none may be inferred from another.
- Architecture, health, activity logs, and feature plans answer different questions but were previously read as interchangeable SSOTs.
- Repo migration authority and live database evidence differ. See `docs/RELEASE-STATE.md`; repo source authority never implies live application.
- There is no confirmed `CODEOWNERS` mapping, so role suggestions must not be presented as assigned owners.

## First-phase cleanup boundary

The first cleanup phase may:

- add authority and lifecycle labels;
- add caller and external-consumer evidence to `docs/REPO-CLEANUP-INVENTORY.md`;
- add `supersededBy`, verification date, and scope notes after topic-owner review;
- add freshness checks for files explicitly declared current;
- create an approved migration ledger and release-state validator in later scoped PRs.

The first cleanup phase must not:

- move or delete runtime, design, prototype, demo, externally published, sales, App Store, or unclassified assets;
- rewrite `STATUS.md` history;
- archive a dated file merely because its filename is old;
- invent owners, App Store state, deployment identity, or database application state;
- combine unrelated App, Voice, database, and documentation edits in one PR.

## Safe follow-up queue

1. Refresh `docs/APP-STORE-PRODUCTION-READINESS.md` against App Store Connect and the selected review Build in a dedicated PR.
2. Keep the Cloud Run topology contract and retired-entrypoint guards in CI; any later script deletion requires caller evidence and a separate Platform review.
3. ✅ Refresh the `docs/CURRENT-DEVELOPMENT-PLAN.md` current header and machine-govern its path／source／pricing boundary; refresh `README.md` and `BACKLOG.md` only after each topic owner confirms scope and successor documents.
4. Add a machine-readable release-state schema and CI validator after the manual fields stabilize.
5. Establish confirmed ownership / `CODEOWNERS` separately; do not infer people from historical authorship.
6. Complete external-consumer checks in `docs/REPO-CLEANUP-INVENTORY.md` before moving design bundles, prototypes, sales assets, App Store images, voice samples, or root assets.

## Change protocol

1. Before editing a current or authority file, fetch `origin/main` and inspect open PR file lists.
2. State the intended files and authority scope in the task, board entry, or Draft PR.
3. Use a separate worktree when another session or a dirty checkout is active.
4. Preserve history; update authority pointers instead of rewriting old evidence to look current.
5. Reverify volatile release facts immediately before merge.
