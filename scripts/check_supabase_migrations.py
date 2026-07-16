#!/usr/bin/env python3
"""Offline integrity check for the canonical Supabase migration manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FILENAME_PATTERN = re.compile(r"^(?P<identity>\d{3})_[a-z0-9_]+\.sql$")
CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")
NORMALIZATION = "lf-v1"


def normalized_sha256(path: Path) -> str:
    """Hash SQL bytes after normalizing CRLF and CR line endings to LF."""
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def _load_manifest(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"manifest is missing: {path}"]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"manifest cannot be read: {exc}"]
    if not isinstance(value, dict):
        return None, ["manifest root must be a JSON object"]
    return value, []


def validate(repo_root: Path = ROOT, manifest_path: Path | None = None) -> list[str]:
    """Return every governance violation without requiring network or database access."""
    repo_root = Path(repo_root).resolve()
    manifest_path = Path(manifest_path or repo_root / "supabase" / "migration-manifest.json")
    manifest, errors = _load_manifest(manifest_path)
    if manifest is None:
        return errors

    if manifest.get("manifest_version") != 1:
        errors.append("manifest_version must be 1")

    checksum = manifest.get("checksum")
    if checksum != {"algorithm": "sha256", "normalization": NORMALIZATION}:
        errors.append("checksum policy must be sha256 with lf-v1 normalization")

    migration_directory = manifest.get("migration_directory")
    if not isinstance(migration_directory, str) or Path(migration_directory).is_absolute():
        errors.append("migration_directory must be a relative repository path")
        return errors
    sql_directory = (repo_root / migration_directory).resolve()
    try:
        sql_directory.relative_to(repo_root)
    except ValueError:
        errors.append("migration_directory must remain inside the repository")
        return errors

    allowed_types = manifest.get("allowed_types")
    if allowed_types != ["schema", "data-cleanup", "seed"]:
        errors.append("allowed_types must be the canonical schema/data-cleanup/seed list")
        valid_types: set[str] = set()
    else:
        valid_types = set(allowed_types)

    duplicate_allowlist = manifest.get("legacy_duplicate_identities")
    if not isinstance(duplicate_allowlist, dict):
        errors.append("legacy_duplicate_identities must be a JSON object")
        duplicate_allowlist = {}

    migrations = manifest.get("migrations")
    if not isinstance(migrations, list):
        errors.append("migrations must be a JSON array")
        return errors

    entries_by_filename: dict[str, dict[str, Any]] = {}
    manifest_filenames: list[str] = []
    manifest_identity_groups: dict[str, list[str]] = defaultdict(list)

    for index, entry in enumerate(migrations, start=1):
        label = f"migration entry {index}"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be a JSON object")
            continue

        if entry.get("order") != index:
            errors.append(f"{label} has non-deterministic order; expected order={index}")

        filename = entry.get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename:
            errors.append(f"{label} filename must be a plain basename")
            continue
        manifest_filenames.append(filename)
        if filename in entries_by_filename:
            errors.append(f"migration is listed more than once: {filename}")
        entries_by_filename[filename] = entry

        match = FILENAME_PATTERN.fullmatch(filename)
        if not match:
            errors.append(f"migration filename is not canonical: {filename}")
            continue
        filename_identity = match.group("identity")
        identity = entry.get("identity")
        if identity != filename_identity:
            errors.append(
                f"migration identity mismatch for {filename}: manifest={identity!r}, filename={filename_identity}"
            )
        manifest_identity_groups[filename_identity].append(filename)

        if entry.get("type") not in valid_types:
            errors.append(f"migration type is invalid for {filename}: {entry.get('type')!r}")
        expected_checksum = entry.get("sha256")
        if not isinstance(expected_checksum, str) or not CHECKSUM_PATTERN.fullmatch(expected_checksum):
            errors.append(f"migration checksum is invalid for {filename}")

    if not sql_directory.is_dir():
        errors.append(f"migration directory is missing: {sql_directory}")
        return errors

    discovered_paths = sorted(sql_directory.glob("*.sql"), key=lambda path: path.name)
    discovered_filenames = [path.name for path in discovered_paths]
    discovered_set = set(discovered_filenames)
    manifest_set = set(manifest_filenames)
    for filename in sorted(discovered_set - manifest_set):
        errors.append(f"unlisted migration: {filename}")
    for filename in sorted(manifest_set - discovered_set):
        errors.append(f"listed migration is missing: {filename}")

    discovered_identity_groups: dict[str, list[str]] = defaultdict(list)
    for path in discovered_paths:
        match = FILENAME_PATTERN.fullmatch(path.name)
        if not match:
            errors.append(f"migration filename is not canonical: {path.name}")
            continue
        discovered_identity_groups[match.group("identity")].append(path.name)

        entry = entries_by_filename.get(path.name)
        if entry and CHECKSUM_PATTERN.fullmatch(str(entry.get("sha256", ""))):
            actual_checksum = normalized_sha256(path)
            if actual_checksum != entry["sha256"]:
                errors.append(
                    f"migration checksum mismatch for {path.name}: "
                    f"expected {entry['sha256']}, got {actual_checksum}"
                )

    for identity, filenames in sorted(discovered_identity_groups.items()):
        declared = duplicate_allowlist.get(identity)
        if len(filenames) > 1:
            if (
                not isinstance(declared, list)
                or len(declared) != len(filenames)
                or set(declared) != set(filenames)
            ):
                errors.append(
                    f"duplicate migration identity {identity} is not explicitly allowlisted: "
                    + ", ".join(filenames)
                )
        elif declared is not None:
            errors.append(f"legacy duplicate allowlist {identity} does not describe a duplicate identity")

    for identity, declared in sorted(duplicate_allowlist.items()):
        if not isinstance(identity, str) or not re.fullmatch(r"\d{3}", identity):
            errors.append(f"legacy duplicate identity is invalid: {identity!r}")
            continue
        if not isinstance(declared, list) or not all(isinstance(name, str) for name in declared):
            errors.append(f"legacy duplicate allowlist {identity} must be an ordered filename array")
            continue
        actual = discovered_identity_groups.get(identity, [])
        if (len(declared) != len(actual) or set(declared) != set(actual)) and len(actual) <= 1:
            errors.append(f"legacy duplicate allowlist {identity} does not match repository files")

    duplicate_rank = {
        (identity, filename): rank
        for identity, filenames in duplicate_allowlist.items()
        if isinstance(filenames, list)
        for rank, filename in enumerate(filenames)
    }

    def canonical_key(filename: str) -> tuple[int, int, str]:
        match = FILENAME_PATTERN.fullmatch(filename)
        if not match:
            return (10**9, 10**9, filename)
        identity = match.group("identity")
        return (int(identity), duplicate_rank.get((identity, filename), 0), filename)

    expected_order = sorted(manifest_filenames, key=canonical_key)
    if manifest_filenames != expected_order:
        errors.append("migrations are not in deterministic identity/allowlist order")

    for identity, filenames in manifest_identity_groups.items():
        if len(filenames) > 1 and duplicate_allowlist.get(identity) != filenames:
            errors.append(f"manifest order for duplicate identity {identity} does not match its allowlist")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    errors = validate(args.repo_root, args.manifest)
    if errors:
        print("Supabase migration governance: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    manifest_path = args.manifest or args.repo_root / "supabase" / "migration-manifest.json"
    migration_count = len(json.loads(Path(manifest_path).read_text(encoding="utf-8"))["migrations"])
    print(f"Supabase migration governance: PASS ({migration_count} migrations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
