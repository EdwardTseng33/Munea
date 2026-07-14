# Munea Agent Collaboration Rules

These rules apply to every Codex agent and every task that can edit this repository.

Before editing any tracked file:

1. Read `docs/AGENT-COLLABORATION-PROTOCOL.md` completely.
2. Fetch `origin/main`; never develop in the shared dirty `main` checkout.
3. Create a dedicated worktree and a uniquely named branch from current `origin/main`.
4. Run `python scripts/agent-lock.py list` and check the intended paths.
5. Acquire a repository lock as described in the protocol. The lock-only PR must be merged to `main` before implementation starts.
6. If another active or stale lock overlaps any intended path, do not edit those paths. Notify the owner and wait for an explicit handoff or split the scope into non-overlapping paths.

While working:

- Stay inside the paths declared by the lock.
- Do not use another agent's worktree or uncommitted files.
- Do not force-push, reset, overwrite, delete, or reformat unrelated user or agent changes.
- Use one feature branch per lock. Stacked branches are allowed only when the dependency is declared and the parent branch merges first.
- Rebase on current `origin/main` before final validation and PR handoff.
- The completion PR must remove its own active lock. Git history and the PR are the audit trail.

Read-only inspection does not require a lock. The legacy `docs/協作看板-雙AI分工.md` is historical context, not the live locking authority.
