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

## Chat-call App acceptance gate

- Any change that could affect the App chat-call path must be marked as call-path risk in the task or PR. This includes App/WebView code, iOS packaging, Auth, onboarding/account bootstrap, plans/credits, Gateway/Call Control, Voice, Avatar/GPU, URLs/environment variables, permissions, CORS, deployment, and fallback behavior.
- Unit tests, browser test pages, service health checks, and synthetic probes are prechecks only. Before the work is called verified, release-ready, or complete, install the exact build/profile in the iPhone App and pass an end-to-end call: tap call, obtain microphone access, pass Auth/account/credit and Gateway or declared direct-call routing, reach Voice and Avatar ready, hear the opening, send real microphone audio, receive an audible/visible AI response, and hang up with capacity released.
- A developer-direct build cannot certify the production Gateway path. Test the profile/environment affected by the change. If a physical-App gate cannot yet run, record `App E2E pending`; do not describe the change as fully verified or safe to ship.
- Record App version/build, profile, environment/service revisions, device, time, result, and evidence in the PR plus `STATUS.md` or `docs/RELEASE-STATE.md`.

Read-only inspection does not need a branch or board entry. See `docs/AGENT-COLLABORATION-PROTOCOL.md` for the short workflow and examples.
