#!/usr/bin/env python3
"""Focused tests for offline Supabase migration governance."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_supabase_migrations import normalized_sha256, validate


class SupabaseMigrationGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.temp_directory.name)
        (self.repo_root / "supabase").mkdir()
        shutil.copytree(ROOT / "supabase" / "sql", self.repo_root / "supabase" / "sql")
        shutil.copy2(
            ROOT / "supabase" / "migration-manifest.json",
            self.repo_root / "supabase" / "migration-manifest.json",
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @property
    def manifest_path(self) -> Path:
        return self.repo_root / "supabase" / "migration-manifest.json"

    def read_manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, manifest: dict) -> None:
        self.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def assert_has_error(self, needle: str) -> None:
        errors = validate(self.repo_root)
        self.assertTrue(any(needle in error for error in errors), errors)

    def test_canonical_manifest_passes(self) -> None:
        self.assertEqual(validate(self.repo_root), [])

    def test_unlisted_migration_fails(self) -> None:
        (self.repo_root / "supabase" / "sql" / "019_unlisted.sql").write_text("select 1;\n", encoding="utf-8")
        self.assert_has_error("unlisted migration: 019_unlisted.sql")

    def test_missing_listed_migration_fails(self) -> None:
        (self.repo_root / "supabase" / "sql" / "018_strip_medication_photos.sql").unlink()
        self.assert_has_error("listed migration is missing: 018_strip_medication_photos.sql")

    def test_modified_migration_fails_checksum(self) -> None:
        path = self.repo_root / "supabase" / "sql" / "018_strip_medication_photos.sql"
        path.write_bytes(path.read_bytes() + b"\n-- changed after publication\n")
        self.assert_has_error("migration checksum mismatch for 018_strip_medication_photos.sql")

    def test_line_ending_only_change_keeps_checksum_stable(self) -> None:
        path = self.repo_root / "supabase" / "sql" / "001_initial_munea_schema.sql"
        lf_content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        path.write_bytes(lf_content.replace(b"\n", b"\r\n"))
        self.assertEqual(validate(self.repo_root), [])

    def test_new_duplicate_identity_fails_without_allowlist(self) -> None:
        path = self.repo_root / "supabase" / "sql" / "018_unexpected_duplicate.sql"
        path.write_text("select 1;\n", encoding="utf-8")
        manifest = self.read_manifest()
        manifest["migrations"].append(
            {
                "order": 20,
                "identity": "018",
                "filename": path.name,
                "type": "schema",
                "sha256": normalized_sha256(path),
            }
        )
        self.write_manifest(manifest)
        self.assert_has_error("duplicate migration identity 018 is not explicitly allowlisted")

    def test_reordered_manifest_fails_deterministic_order(self) -> None:
        manifest = self.read_manifest()
        manifest["migrations"][0], manifest["migrations"][1] = (
            manifest["migrations"][1],
            manifest["migrations"][0],
        )
        self.write_manifest(manifest)
        self.assert_has_error("non-deterministic order")
        self.assert_has_error("not in deterministic identity/allowlist order")


if __name__ == "__main__":
    unittest.main()
