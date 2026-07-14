# Munea multi-agent collaboration protocol

## Goal

Multiple Codex, Claude, Mac, Windows, backend, App, deployment, and design sessions may work at the same time without sharing uncommitted files or discovering conflicts only at merge time.

This protocol makes coordination explicit in the repository. It replaces the old practice of using one large collaboration-board file as a live lock.

## Sources of truth

1. `.agent/locks/active/*.json` — current exclusive workstream locks.
2. GitHub pull requests — implementation scope, review, validation, and handoff.
3. Product or architecture SSOT documents — durable decisions.
4. `docs/協作看板-雙AI分工.md` — historical context only; it is not an active lock registry.

Chat messages are useful notifications, but they do not replace a merged lock file.

## When a lock is required

A lock is required before any tracked-file edit. Read-only inspection, diagnosis, and status reporting do not require a lock.

Scopes are repository-relative exact files or directory prefixes:

- Exact file: `web/src/app.js`
- Directory: `app-site/`

Glob characters are intentionally forbidden. Clear prefixes are easier to review and compare reliably.

## Mandatory workflow

### 1. Inspect before claiming

```bash
git fetch origin
python scripts/agent-lock.py list
python scripts/agent-lock.py check \
  --branch codex/example-task \
  --path web/src/app.js \
  --path web/src/styles.css
```

If the check reports an active or stale overlap, stop. Notify the owner using the contact in the lock file. Either wait for release, receive an explicit transfer, or agree on non-overlapping paths.

### 2. Create the isolated branch, then acquire the lock first

Create the feature worktree and branch from current `origin/main`, but do not edit product files yet:

```bash
git worktree add ../Munea-worktrees/example-task -b codex/example-task origin/main
cd ../Munea-worktrees/example-task
```

Generate one lock in that worktree:

```bash
python scripts/agent-lock.py create \
  --task-id example-task-20260714 \
  --owner codex-session-name \
  --branch codex/example-task \
  --contact codex-thread-or-pr-url \
  --lease-hours 24 \
  --path web/src/app.js \
  --path web/src/styles.css \
  --note "Settings account UI"
```

Commit only that new `.agent/locks/active/*.json` file, open a lock-only PR from the feature branch, and merge it into `main`. Do not start implementation until the lock appears on `origin/main`.

One active lock maps to one implementation branch. Default lease is 24 hours; maximum lease is 7 days. Renew before expiry through another lock-only PR. Expired locks remain blocking until explicitly renewed, transferred, or removed so abandoned work cannot be silently overwritten.

### 3. Sync the same worktree, then implement

After the lock is visible on `main`, update the same feature branch and confirm the lock before editing:

```bash
git fetch origin
git rebase origin/main
python scripts/agent-lock.py check --branch codex/example-task --path web/src/app.js
```

Never edit in the shared dirty `main` checkout. Never use another agent's worktree. Keep commits scoped and do not reformat unrelated files.

### 4. Coordinate unavoidable overlap

If two tasks truly need the same file, use one of these patterns before either agent edits:

1. **Serial handoff** — current owner commits, pushes, validates, and releases or transfers the lock; the next agent rebases and starts.
2. **Scope split** — split into different exact files or directory prefixes and update locks before editing.
3. **Declared stacked branch** — the child branch starts from the parent branch, records the dependency in both PRs, and merges only after the parent. This is exceptional, not the default.

Do not copy partial uncommitted changes between sessions and do not resolve product conflicts by choosing one side of a Git conflict without the other owner's confirmation.

### 5. Finish and release atomically

Before the implementation PR is ready:

```bash
git fetch origin
git rebase origin/main
python scripts/agent-lock.py check --branch codex/example-task --path web/src/app.js
```

Run relevant tests, remove the branch's own lock file, and open the implementation PR. The coordination CI verifies that:

- the branch had exactly one lock on the PR base;
- every changed product file is inside that lock;
- no changed path overlaps another lock;
- the completion PR removes its own lock;
- lock-only PRs do not collide with existing locks.

Merge through PR. Never force-push `main` and never use a shared dirty checkout as a merge source.

## User-facing coordination behavior

When work is blocked by another lock, tell the user immediately:

- which task owns the path;
- which exact files or directory overlap;
- whether the safe choice is waiting, scope splitting, or serial handoff;
- what useful non-overlapping work can continue.

When acquiring a broad lock that may affect other sessions, notify those sessions before implementation and ask them to acknowledge. The merged lock remains authoritative even if a chat acknowledgement is delayed.

## Emergency and stale locks

- Do not silently delete another agent's lock.
- Contact the owner first. If the owner cannot respond, Edward may authorize transfer or removal.
- A P0 incident does not automatically override an active lock. Record the explicit handoff, preserve the current branch, then transfer the lock.
- If a session ends unexpectedly, its branch is preserved. The next owner starts only after the lock is explicitly transferred or removed.

## Branch protection requirement

The GitHub check named `agent-coordination` should be required for merges into `main`, together with the existing smoke checks. Requiring the branch to be up to date closes the race where two lock-only PRs were checked against an older `main`.
