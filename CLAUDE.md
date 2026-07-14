# Claude entrypoint for Munea

Before changing this repository, follow `AGENTS.md` and read `docs/AGENT-COLLABORATION-PROTOCOL.md` completely.

The active lock files under `.agent/locks/active/` are authoritative. Do not start editing an overlapping path until the lock is released or explicitly transferred. Use a separate worktree and branch; never develop in the shared dirty `main` checkout.
