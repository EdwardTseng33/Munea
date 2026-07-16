# Supabase migration governance

`migration-manifest.json` is the canonical offline inventory for every
`supabase/sql/*.sql` file. It records application order, migration identity,
primary type, and an LF-normalized SHA-256 checksum.

Run the integrity gate before adding or shipping migration SQL:

```powershell
python scripts/check_supabase_migrations.py
python scripts/test_supabase_migration_governance.py
```

Existing migrations are immutable. Add a new, uniquely numbered SQL file and
its manifest entry instead of editing a published file. The two historical
`011` files are intentionally preserved and ordered in
`legacy_duplicate_identities`; no other duplicate identity is accepted.

`lf-v1` checksum normalization converts CRLF or CR line endings to LF before
hashing, so the integrity result is stable across Windows and macOS checkouts.
This gate is offline only: it does not claim that a migration was applied to a
live Supabase project.
