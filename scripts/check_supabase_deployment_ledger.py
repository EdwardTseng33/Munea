#!/usr/bin/env python3
"""Fail-closed offline validation for the Supabase environment deployment ledger."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = Path("supabase/deployment-ledger.json")
MANIFEST_PATH = Path("supabase/migration-manifest.json")
SCHEMA = "munea.supabase-deployment-ledger.v1"
ALLOWED_STATUSES = {"unknown", "historical-claim", "verified", "blocked"}
PROJECT_REF = re.compile(r"^[a-z]{20}$")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


def _taipei_today() -> date:
    return datetime.now(timezone(timedelta(hours=8))).date()


def _read_json(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} cannot be read: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} root must be a JSON object")
        return None
    return value


def _safe_evidence(root: Path, value: Any, label: str, errors: list[str]) -> Path | None:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        errors.append(f"{label} must be a repository-relative file")
        return None
    target = (root / value).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        errors.append(f"{label} escapes the repository")
        return None
    if not target.is_file():
        errors.append(f"{label} does not exist: {value}")
        return None
    return target


def _iso_datetime(value: Any, label: str, errors: list[str]) -> None:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} must be an ISO-8601 datetime")


def validate(repo_root: Path = ROOT) -> list[str]:
    root = Path(repo_root).resolve()
    errors: list[str] = []
    ledger = _read_json(root / LEDGER_PATH, "deployment ledger", errors)
    manifest = _read_json(root / MANIFEST_PATH, "migration manifest", errors)
    if ledger is None or manifest is None:
        return errors

    if ledger.get("schema") != SCHEMA:
        errors.append(f"deployment ledger schema must be {SCHEMA}")
    _safe_evidence(root, ledger.get("documentationRef"), "deployment ledger documentationRef", errors)
    try:
        updated = date.fromisoformat(str(ledger.get("updated")))
        if updated > _taipei_today():
            errors.append("deployment ledger updated date cannot be in the future")
    except ValueError:
        errors.append("deployment ledger updated must be YYYY-MM-DD")
    if ledger.get("statusVocabulary") != ["unknown", "historical-claim", "verified", "blocked"]:
        errors.append("deployment ledger status vocabulary is not canonical")

    manifest_entries = manifest.get("migrations")
    if not isinstance(manifest_entries, list):
        return errors + ["migration manifest migrations must be an array"]

    environments = ledger.get("environments")
    if not isinstance(environments, list) or not environments:
        return errors + ["deployment ledger environments must be a non-empty array"]
    ids: set[str] = set()
    for env_index, environment in enumerate(environments, start=1):
        label = f"environment {env_index}"
        if not isinstance(environment, dict):
            errors.append(f"{label} must be an object")
            continue
        env_id = environment.get("id")
        if not isinstance(env_id, str) or not env_id:
            errors.append(f"{label} id must be non-empty")
        elif env_id in ids:
            errors.append(f"deployment environment is duplicated: {env_id}")
        else:
            ids.add(env_id)
        if not PROJECT_REF.fullmatch(str(environment.get("projectRef") or "")):
            errors.append(f"{label} projectRef must be a 20-letter Supabase ref")
        if not isinstance(environment.get("region"), str) or not environment["region"].strip():
            errors.append(f"{label} region must be non-empty")

        migrations = environment.get("migrations")
        if not isinstance(migrations, list):
            errors.append(f"{label} migrations must be an array")
            continue
        if len(migrations) != len(manifest_entries):
            errors.append(f"{label} must cover every manifest migration exactly once")

        ledger_statuses: list[str | None] = []
        for index, manifest_entry in enumerate(manifest_entries):
            item_label = f"{label} migration {index + 1}"
            if index >= len(migrations) or not isinstance(migrations[index], dict):
                errors.append(f"{item_label} is missing or invalid")
                continue
            item = migrations[index]
            filename = manifest_entry.get("filename")
            if item.get("filename") != filename:
                errors.append(f"{item_label} must match manifest order and filename {filename}")
            if item.get("sha256") != manifest_entry.get("sha256"):
                errors.append(f"deployment checksum drift for {filename}")
            status = item.get("status")
            ledger_statuses.append(status if isinstance(status, str) else None)
            if status not in ALLOWED_STATUSES:
                errors.append(f"deployment status is invalid for {filename}: {status!r}")
                continue

            if status == "unknown":
                forbidden = {"evidenceRef", "verifiedAt", "captureMethod", "sourceCommit"}.intersection(item)
                if forbidden:
                    errors.append(f"unknown migration cannot carry verification evidence: {filename}")
            elif status == "historical-claim":
                _safe_evidence(root, item.get("evidenceRef"), f"historical evidence for {filename}", errors)
            elif status == "blocked":
                if not isinstance(item.get("blocker"), str) or not item["blocker"].strip():
                    errors.append(f"blocked migration must name a blocker: {filename}")
                if "evidenceRef" in item:
                    _safe_evidence(root, item.get("evidenceRef"), f"blocked evidence for {filename}", errors)
            elif status == "verified":
                _safe_evidence(root, item.get("evidenceRef"), f"verified evidence for {filename}", errors)
                _iso_datetime(item.get("verifiedAt"), f"verifiedAt for {filename}", errors)
                if item.get("captureMethod") not in {"read-only-probe", "approved-migration-run"}:
                    errors.append(f"verified migration has invalid captureMethod: {filename}")
                if not COMMIT.fullmatch(str(item.get("sourceCommit") or "")):
                    errors.append(f"verified migration must bind a source commit: {filename}")

            if manifest_entry.get("type") == "data-cleanup":
                if item.get("requiresApproval") is not True:
                    errors.append(f"data-cleanup migration must require approval: {filename}")
                if status == "verified":
                    for field in ("approvalRef", "backupEvidenceRef"):
                        if field not in item:
                            errors.append(f"verified data-cleanup migration is missing {field}: {filename}")
                        else:
                            _safe_evidence(root, item.get(field), f"{field} for {filename}", errors)
                    pre_check = item.get("preCheck")
                    post_check = item.get("postCheck")
                    for field, check in (("preCheck", pre_check), ("postCheck", post_check)):
                        if not isinstance(check, dict):
                            errors.append(f"verified data-cleanup migration is missing {field}: {filename}")
                            continue
                        for count_field in ("totalRows", "photoKeyRows", "dataImageRows"):
                            value = check.get(count_field)
                            if not isinstance(value, int) or value < 0:
                                errors.append(f"{field}.{count_field} must be a non-negative integer: {filename}")
                    if isinstance(post_check, dict):
                        if post_check.get("photoKeyRows") != 0 or post_check.get("dataImageRows") != 0:
                            errors.append(f"verified data-cleanup postCheck must prove zero residual images: {filename}")
                    if isinstance(pre_check, dict) and isinstance(post_check, dict):
                        if pre_check.get("totalRows") != post_check.get("totalRows"):
                            errors.append(f"verified data-cleanup must preserve total row count: {filename}")

        contiguous_verified: list[str] = []
        for manifest_entry, status in zip(manifest_entries, ledger_statuses):
            if status != "verified":
                break
            contiguous_verified.append(str(manifest_entry.get("filename")))
        expected_head = contiguous_verified[-1] if contiguous_verified else None
        verified_head = environment.get("verifiedHead")
        if verified_head != expected_head:
            if expected_head is None:
                errors.append(f"{label} verifiedHead must be null without a contiguous verified chain")
            else:
                errors.append(f"{label} verifiedHead must equal contiguous verified head {expected_head}")

        observation = environment.get("lastObservation")
        if not isinstance(observation, dict):
            errors.append(f"{label} lastObservation must be an object")
        else:
            if observation.get("status") not in {"historical-only", "partial", "verified"}:
                errors.append(f"{label} lastObservation status is invalid")
            _iso_datetime(observation.get("observedAt"), f"{label} observedAt", errors)
            _safe_evidence(root, observation.get("evidenceRef"), f"{label} observation evidence", errors)

        probe_attempt = environment.get("latestProbeAttempt")
        if probe_attempt is not None:
            if not isinstance(probe_attempt, dict):
                errors.append(f"{label} latestProbeAttempt must be an object")
            else:
                if probe_attempt.get("status") not in {"blocked", "verified"}:
                    errors.append(f"{label} latestProbeAttempt status is invalid")
                _iso_datetime(probe_attempt.get("capturedAt"), f"{label} latestProbeAttempt capturedAt", errors)
                evidence_path = _safe_evidence(
                    root,
                    probe_attempt.get("evidenceRef"),
                    f"{label} latestProbeAttempt evidence",
                    errors,
                )
                if probe_attempt.get("readOnly") is not True:
                    errors.append(f"{label} latestProbeAttempt must be read-only")
                if not COMMIT.fullmatch(str(probe_attempt.get("sourceCommit") or "")):
                    errors.append(f"{label} latestProbeAttempt must bind a source commit")
                for field in ("targetProjectRef", "observedProjectRef"):
                    if not PROJECT_REF.fullmatch(str(probe_attempt.get(field) or "")):
                        errors.append(f"{label} latestProbeAttempt {field} is invalid")
                if probe_attempt.get("status") == "verified":
                    if probe_attempt.get("targetProjectRef") != environment.get("projectRef"):
                        errors.append(f"{label} verified probe target must match environment projectRef")
                    if probe_attempt.get("observedProjectRef") != environment.get("projectRef"):
                        errors.append(f"{label} verified probe observation must match environment projectRef")
                    if probe_attempt.get("requestIssued") is not True:
                        errors.append(f"{label} verified probe must issue read-only requests")
                elif not isinstance(probe_attempt.get("reason"), str) or not probe_attempt["reason"].strip():
                    errors.append(f"{label} blocked probe must name a reason")

                if evidence_path is not None and evidence_path.suffix.lower() == ".json":
                    evidence = _read_json(evidence_path, f"{label} latestProbeAttempt evidence JSON", errors)
                    if evidence is not None:
                        if evidence.get("schema") != "munea.supabase-deployment-observation.v1":
                            errors.append(f"{label} latestProbeAttempt evidence schema is invalid")
                        for field in (
                            "capturedAt",
                            "sourceCommit",
                            "targetProjectRef",
                            "observedProjectRef",
                            "readOnly",
                            "requestIssued",
                        ):
                            if probe_attempt.get(field) != evidence.get(field):
                                errors.append(f"{label} latestProbeAttempt {field} does not match evidence")
                        if probe_attempt.get("status") == "verified" and evidence.get("ok") is not True:
                            errors.append(f"{label} verified probe evidence must be ok")
                        if probe_attempt.get("status") == "blocked" and evidence.get("ok") is not False:
                            errors.append(f"{label} blocked probe evidence must not be ok")

        rollback = environment.get("rollback")
        if not isinstance(rollback, dict):
            errors.append(f"{label} rollback must be an object")
        else:
            if not PROJECT_REF.fullmatch(str(rollback.get("projectRef") or "")):
                errors.append(f"{label} rollback projectRef must be a 20-letter Supabase ref")
            if rollback.get("status") not in {"unknown", "historical-claim", "verified"}:
                errors.append(f"{label} rollback status is invalid")
            if rollback.get("status") in {"historical-claim", "verified"}:
                _safe_evidence(root, rollback.get("evidenceRef"), f"{label} rollback evidence", errors)
                _iso_datetime(rollback.get("lastObservedAt"), f"{label} rollback lastObservedAt", errors)
            requirements = rollback.get("requirements")
            if not isinstance(requirements, list) or not all(isinstance(value, str) and value for value in requirements):
                errors.append(f"{label} rollback requirements must be a non-empty string array")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    errors = validate(args.repo_root)
    if errors:
        print("Supabase deployment ledger: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    ledger = json.loads((Path(args.repo_root) / LEDGER_PATH).read_text(encoding="utf-8"))
    environment = ledger["environments"][0]
    statuses: dict[str, int] = {}
    for item in environment["migrations"]:
        statuses[item["status"]] = statuses.get(item["status"], 0) + 1
    summary = ", ".join(f"{key}={statuses[key]}" for key in sorted(statuses))
    print(f"Supabase deployment ledger: PASS ({environment['id']}: {summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
