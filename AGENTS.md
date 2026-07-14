# Munea lightweight collaboration rules

These rules apply to Codex, Claude, and every computer or session that edits this repository.

Before editing:

1. Run `git fetch origin` and read `docs/協作看板-雙AI分工.md` plus the currently open GitHub pull requests.
2. Use one uniquely named branch per session. When the checkout is dirty or another session is active on the same computer, use a separate worktree.
3. In the task message, Draft PR, or the board entry for longer work, state the task and the files you expect to change. One implementation task uses one PR; there is no separate lock PR.
4. If another active task is changing the same file, do not start a competing edit. Let the first task merge, then update from `origin/main` and continue. Different files may proceed in parallel.

While working:

- Keep commits small and scoped. Do not reformat or include unrelated files.
- Do not force-push `main`, reset another branch, overwrite another worktree, or discard changes you do not own.
- Before merging, update the branch with current `origin/main`, run relevant tests, and review any conflict using both tasks' intent. Never resolve a conflict by blindly choosing one side.
- Mark longer board entries complete when the PR merges. GitHub PRs are the live cross-computer handoff record.

Read-only inspection does not need a branch or board entry. See `docs/AGENT-COLLABORATION-PROTOCOL.md` for the short workflow and examples.
