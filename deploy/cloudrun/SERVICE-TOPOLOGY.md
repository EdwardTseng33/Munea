# Munea Cloud Run Service Topology

Status: `authority`

Verified source baseline: `origin/main@8feeac4` plus this scoped Platform change

This file is the repository authority for Cloud Run service roles and deployment entrypoints. Runtime revision, traffic, and health remain authoritative only in Google Cloud Run and each service's `/version` response.

## Service roles

| Environment | Brain | Voice | Client role |
|---|---|---|---|
| `production` | `munea-brain` | `munea-voice` | App Store / production Web defaults |
| `staging` | `munea-brain-staging` | `munea-voice-staging` | Development profile, canary, pre-release and human verification |

Shared Call Control currently uses `munea-call-control`. It is a separate service and must not be inferred from Brain or Voice revision state.

The packaged production defaults are owned by `web/src/app.js`, `web/src/store.js`, and `web/src/notify.js`. The explicit iOS development override is owned by `scripts/enable-ios-development-profile.mjs`. CI topology contracts must fail if production defaults regress to `-staging`.

## Operations console

The current operations console is served from the staging Brain host at `/admin.html`. Its hostname identifies the serving Brain service, not the sensitivity or freshness of the data it displays. Operational acceptance therefore requires separate evidence for:

- privileged authentication and authorization;
- actual Supabase project / data source;
- metric timestamp and freshness;
- truthful empty, unavailable and fallback states;
- serving Brain `/version` identity.

Do not treat an HTTP 200 admin shell or security headers alone as proof that the dashboard data is current or production-complete.

## Only active deployment lanes

### Staging

1. `bash deploy/cloudrun/canary-deploy.sh brain|voice`
2. Verify the printed tagged URL and complete the required human Gate.
3. Run the exact `promote.sh staging ... <tag> <version> <commit>` command printed by the deploy script.

### Production

1. First verify the same committed release on staging.
2. `bash deploy/cloudrun/prod-deploy.sh brain|voice`
3. Verify the production tagged URL and all production / human Gates.
4. Run the exact `promote.sh production ... <tag> <version> <commit>` command printed by the deploy script.

Both deploy scripts archive committed `HEAD`, create a 0% tagged revision, inject release metadata, and call `canary-verify.sh`. Neither may switch default traffic.

`promote.sh` must:

- reverify the exact tag, version, commit, environment and service;
- resolve the tag to an exact revision;
- capture the one actual 100% serving revision for rollback;
- switch with `--to-revisions <exact-revision>=100`;
- verify the service URL `/version` after the switch;
- automatically restore the captured serving revision when identity verification fails.

Floating promotion such as `--to-latest` is prohibited because another session can create a newer unverified revision after canary verification.

## Retired and historical entrypoints

The following paths stay in the repository so old links fail with a clear message. They are not deployment authority:

- `scripts/cloud-run-deploy-staging.ps1`
- `deploy/cloudrun/更新正式環境.sh`
- `deploy/cloudrun/更新測試環境.sh`
- `deploy/cloudrun/正式開門-點兩下.bat`
- `deploy/cloudrun/發鑰匙權限-點兩下.bat`
- `deploy/cloudrun/搬家配方-README.md`
- `docs/單一正式環境-部署SOP-2026-07-13.md`

Retired executable paths must fail before any `gcloud run deploy`, traffic mutation, Cloud Run IAM mutation, or Secret Manager IAM mutation. Historical documents must carry a do-not-execute successor notice.

## Release evidence and rollback

For every traffic change, retain:

- source commit and package version;
- environment, service, tag and exact target revision;
- pre-switch serving revision;
- canary verification result;
- post-switch `/version` result;
- human Gate result for App / Voice behavior;
- exact rollback command.

A merged PR is source evidence only. It does not prove deployment, traffic, database state, App Store review state, or human acceptance.

## Known remaining control gaps

- The staging human Gate is still procedural evidence. Before a 90-point release score, create a signed or repository-recorded staging attestation that binds environment, service, tag, revision, version, commit, test result and approver; `prod-deploy.sh` must consume that attestation.
- `promote.sh` rechecks tag and serving revision immediately before mutation, but Cloud Run traffic updates do not yet use a repository-level cross-session lease or compare-and-swap guard. A narrow control-plane race remains until a deployment lock is implemented.
