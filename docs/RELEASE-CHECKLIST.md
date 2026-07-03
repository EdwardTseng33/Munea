# Munea Release Checklist

Purpose: keep every push, TestFlight build, and staging backend change easy to review without relying on memory or chat history.

Use this checklist before pushing release-sensitive changes, uploading a TestFlight build, or pointing the app at a hosted backend.

## 1. Scope

- What changed:
- Owner:
- Commit:
- Target: `main`, staging backend, TestFlight, or production.
- Backend mode: `json`, `static-shell`, `supabase-staging`, or `supabase-production`.

## 2. Verification

Run:

```powershell
npm run release:check
```

Then confirm:

1. Local release check passed.
2. GitHub Smoke workflow is green.
3. No service/admin/provider secrets are in `web/` or Capacitor assets.
4. Backend mode matches the release target.
5. Known risks are written down before push or upload.

To check the latest GitHub Smoke run from the terminal:

```powershell
npm run smoke:status
```

After a fresh push, wait for the matching commit:

```powershell
npm run smoke:status -- -Wait
```

## 3. Release Record

Generate a record draft:

```powershell
npm run release:record -- -SmokeRun "GITHUB_ACTIONS_RUN_URL" -BackendMode json -Risk "none"
```

Use `-BackendMode supabase-staging` only after the staging Supabase live gate passes.

## 4. Go / No-Go

Go when:

1. `npm run release:check` passes.
2. `npm run smoke:status -- -Wait` confirms the GitHub Smoke workflow passed.
3. The release target and backend mode are clear.
4. There is a rollback path.

No-go when:

1. Smoke or auth-gate fails.
2. The app depends on a partially configured Supabase project.
3. A backend secret appears in client assets.
4. Claude / Codex ownership boundaries are unclear for touched files.

## 5. Rollback Note

For normal GitHub pushes, rollback is a new revert commit.

For TestFlight, rollback is removing the build from tester distribution or switching the next build back to static-shell mode.
