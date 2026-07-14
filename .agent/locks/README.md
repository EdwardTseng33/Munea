# Active workstream locks

The live lock authority is `.agent/locks/active/*.json` on `main`.

Do not hand-edit lock files unless repairing the coordination tooling. Use:

```bash
python scripts/agent-lock.py list
python scripts/agent-lock.py check --branch <branch> --path <file-or-directory>
python scripts/agent-lock.py create --task-id <id> --owner <owner> --branch <branch> --contact <thread-or-pr> --path <scope>
```

See `docs/AGENT-COLLABORATION-PROTOCOL.md` for the required two-stage lock and implementation flow.
