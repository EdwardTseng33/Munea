#!/usr/bin/env python3
"""Capture and validate public, secret-free Munea release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = Path("docs/RELEASE-EVIDENCE-TARGETS.json")
LATEST_PATH = Path("docs/RELEASE-EVIDENCE-LATEST.json")
EVIDENCE_SCHEMA = "munea.release-evidence.v1"
TARGET_SCHEMA = "munea.release-evidence-targets.v1"
USER_AGENT = "MuneaReleaseEvidence/1.0"

FetchResult = tuple[int, dict[str, str], bytes]
Fetcher = Callable[[str, int], FetchResult]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _parse_version(value: Any) -> tuple[int, ...] | None:
    text = str(value or "").strip()
    parts = text.split(".")
    if not text or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def compare_source_version(evidence_version: Any, source_version: Any) -> tuple[str, str]:
    """Classify committed evidence against the current source version.

    Evidence can only be refreshed by GETting live services, so a version bump always
    lands before the next capture. That lag is normal development, not drift: only a
    missing, unreadable, or ahead-of-source version proves the file is wrong.
    """
    evidence_text = str(evidence_version or "").strip()
    source_text = str(source_version or "").strip()
    if not evidence_text:
        return "missing", "release evidence sourceVersion is missing"
    if evidence_text == source_text:
        return "aligned", ""
    captured = _parse_version(evidence_text)
    current = _parse_version(source_text)
    if captured is None or current is None:
        return (
            "unreadable",
            f"release evidence sourceVersion {evidence_text} cannot be compared with package version {source_text or 'unset'}",
        )
    if captured > current:
        return (
            "ahead",
            f"release evidence sourceVersion {evidence_text} is ahead of package version {source_text}",
        )
    return (
        "behind",
        f"release evidence was captured for {evidence_text} and package version is now {source_text}; "
        "run `npm run release:evidence:capture` before calling the next build released",
    )


def _source_commit(root: Path) -> str:
    github_sha = os.environ.get("GITHUB_SHA", "").strip()
    if github_sha:
        return github_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _fetch(url: str, timeout: int) -> FetchResult:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return int(response.status), headers, response.read()
    except urllib.error.HTTPError as exc:
        headers = {key.lower(): value for key, value in exc.headers.items()}
        return int(exc.code), headers, exc.read()


def capture_target(target: dict[str, Any], fetcher: Fetcher = _fetch, timeout: int = 20) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": target.get("id"),
        "kind": target.get("kind"),
        "url": target.get("url"),
        "ok": False,
    }
    try:
        status, headers, body = fetcher(str(target["url"]), timeout)
        result["status"] = status
        if status != 200:
            result["error"] = f"unexpected HTTP status {status}"
            return result

        if target.get("kind") == "service-version":
            payload = json.loads(body.decode("utf-8"))
            release = payload.get("release") if isinstance(payload, dict) else None
            if payload.get("ok") is not True or not isinstance(release, dict):
                raise ValueError("version response does not contain ok=true and release")
            observed = {
                key: release.get(key)
                for key in ("schema", "service", "version", "commit", "revision", "environment")
            }
            if observed["schema"] != "munea.service-release.v1":
                raise ValueError("unsupported service release schema")
            if observed["service"] != target.get("expectedService"):
                raise ValueError("service identity mismatch")
            if observed["environment"] != target.get("expectedEnvironment"):
                raise ValueError("service environment mismatch")
            result["observed"] = observed
        elif target.get("kind") == "admin-shell":
            text = body.decode("utf-8")
            required_headers = target.get("requiredHeaders") or {}
            for name, expected in required_headers.items():
                if headers.get(str(name).lower()) != expected:
                    raise ValueError(f"admin header mismatch: {name}")
            required_tokens = target.get("requiredBodyTokens") or []
            for token in required_tokens:
                if token not in text:
                    raise ValueError(f"admin body token missing: {token}")
            result["observed"] = {
                "headers": {str(name).lower(): headers.get(str(name).lower()) for name in required_headers},
                "bodySha256": hashlib.sha256(body).hexdigest(),
                "checkedBodyTokens": list(required_tokens),
            }
        else:
            raise ValueError(f"unsupported target kind: {target.get('kind')}")

        result["ok"] = True
        return result
    except (KeyError, UnicodeError, ValueError, json.JSONDecodeError, OSError) as exc:
        result["error"] = str(exc)
        return result


def capture(root: Path = ROOT, fetcher: Fetcher = _fetch, now: datetime | None = None) -> dict[str, Any]:
    targets_document = _read_json(root / TARGETS_PATH)
    if not isinstance(targets_document, dict):
        raise ValueError("release evidence targets document is invalid")
    targets = targets_document.get("targets")
    if targets_document.get("schema") != TARGET_SCHEMA or not isinstance(targets, list):
        raise ValueError("release evidence targets document is invalid")
    package = _read_json(root / "package.json")
    return {
        "schema": EVIDENCE_SCHEMA,
        "capturedAt": _format_utc(now or _utc_now()),
        "capturedBySourceCommit": _source_commit(root),
        "sourceVersion": package.get("version"),
        "targetConfigSha256": _canonical_hash(targets_document),
        "results": [capture_target(target, fetcher=fetcher) for target in targets],
    }


def validate_evidence(
    document: Any,
    targets_document: Any,
    *,
    source_version: str,
    max_age_hours: float | None = None,
    now: datetime | None = None,
    strict_version: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["release evidence root must be an object"]
    if document.get("schema") != EVIDENCE_SCHEMA:
        errors.append(f"release evidence schema must be {EVIDENCE_SCHEMA}")
    if not isinstance(targets_document, dict) or targets_document.get("schema") != TARGET_SCHEMA:
        return errors + [f"release evidence targets schema must be {TARGET_SCHEMA}"]
    targets = targets_document.get("targets")
    if not isinstance(targets, list):
        return errors + ["release evidence targets must be an array"]
    if document.get("targetConfigSha256") != _canonical_hash(targets_document):
        errors.append("release evidence was captured with a different target configuration")
    version_state, version_message = compare_source_version(document.get("sourceVersion"), source_version)
    if version_state in {"missing", "unreadable", "ahead"}:
        errors.append(version_message)
    elif version_state == "behind" and strict_version:
        errors.append(
            f"release evidence sourceVersion must match package version {source_version} "
            f"but was captured for {document.get('sourceVersion')}"
        )
    commit = str(document.get("capturedBySourceCommit") or "")
    if commit != "unknown" and (len(commit) < 7 or any(char not in "0123456789abcdef" for char in commit.lower())):
        errors.append("capturedBySourceCommit must be a Git SHA or unknown")

    current_time = (now or _utc_now()).astimezone(timezone.utc)
    try:
        captured_at = _parse_utc(document.get("capturedAt"))
        if captured_at > current_time + timedelta(minutes=5):
            errors.append("release evidence capturedAt cannot be in the future")
        if max_age_hours is not None and current_time - captured_at > timedelta(hours=max_age_hours):
            errors.append(f"release evidence is older than {max_age_hours:g} hours")
    except (TypeError, ValueError):
        errors.append("release evidence capturedAt must be an ISO-8601 timestamp with timezone")

    results = document.get("results")
    if not isinstance(results, list):
        return errors + ["release evidence results must be an array"]
    result_by_id: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            errors.append("every release evidence result must have an id")
            continue
        if result["id"] in result_by_id:
            errors.append(f"release evidence result is duplicated: {result['id']}")
        result_by_id[result["id"]] = result

    target_ids: set[str] = set()
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("id"), str):
            errors.append("every release evidence target must have an id")
            continue
        target_id = target["id"]
        if target_id in target_ids:
            errors.append(f"release evidence target is duplicated: {target_id}")
        target_ids.add(target_id)
        result = result_by_id.get(target_id)
        if result is None:
            errors.append(f"release evidence result is missing: {target_id}")
            continue
        if result.get("url") != target.get("url") or result.get("kind") != target.get("kind"):
            errors.append(f"release evidence target metadata drifted: {target_id}")
        if result.get("ok") is not True or result.get("status") != 200:
            errors.append(f"release evidence target did not pass: {target_id}")
            continue
        observed = result.get("observed")
        if not isinstance(observed, dict):
            errors.append(f"release evidence observation is missing: {target_id}")
            continue
        if target.get("kind") == "service-version":
            if observed.get("service") != target.get("expectedService"):
                errors.append(f"release evidence service identity drifted: {target_id}")
            if observed.get("environment") != target.get("expectedEnvironment"):
                errors.append(f"release evidence environment drifted: {target_id}")
            for field in ("version", "commit", "revision"):
                if not isinstance(observed.get(field), str) or not observed[field].strip():
                    errors.append(f"release evidence {field} is missing: {target_id}")
        elif target.get("kind") == "admin-shell":
            observed_headers = observed.get("headers") or {}
            for name, expected in (target.get("requiredHeaders") or {}).items():
                if observed_headers.get(str(name).lower()) != expected:
                    errors.append(f"release evidence admin header drifted: {name}")
            if not isinstance(observed.get("bodySha256"), str) or len(observed["bodySha256"]) != 64:
                errors.append("release evidence admin body hash is missing")
            if observed.get("checkedBodyTokens") != target.get("requiredBodyTokens"):
                errors.append("release evidence admin body-token contract drifted")

    for extra_id in sorted(set(result_by_id) - target_ids):
        errors.append(f"release evidence has an ungoverned result: {extra_id}")
    return errors


def check(
    root: Path = ROOT,
    input_path: Path = LATEST_PATH,
    max_age_hours: float | None = None,
    strict_version: bool = False,
) -> tuple[list[str], list[str]]:
    try:
        document = _read_json(root / input_path)
        targets = _read_json(root / TARGETS_PATH)
        package = _read_json(root / "package.json")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"release evidence cannot be read: {exc}"], []
    source_version = str(package.get("version") or "")
    errors = validate_evidence(
        document,
        targets,
        source_version=source_version,
        max_age_hours=max_age_hours,
        strict_version=strict_version,
    )
    warnings: list[str] = []
    if isinstance(document, dict) and not strict_version:
        state, message = compare_source_version(document.get("sourceVersion"), source_version)
        if state == "behind":
            warnings.append(message)
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture_parser = subparsers.add_parser("capture", help="GET public targets and emit secret-free JSON")
    capture_parser.add_argument("--output", type=Path, help="optional output path; stdout is always safe JSON")
    check_parser = subparsers.add_parser("check", help="validate committed release evidence")
    check_parser.add_argument("--input", type=Path, default=LATEST_PATH)
    check_parser.add_argument("--max-age-hours", type=float)
    check_parser.add_argument(
        "--strict-version",
        action="store_true",
        help="require the evidence to be captured from the current package version (use before a release)",
    )
    args = parser.parse_args(argv)

    if args.command == "capture":
        document = capture()
        rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            output = args.output if args.output.is_absolute() else ROOT / args.output
            output.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        return 0 if all(result.get("ok") is True for result in document["results"]) else 1

    errors, warnings = check(
        input_path=args.input,
        max_age_hours=args.max_age_hours,
        strict_version=args.strict_version,
    )
    for warning in warnings:
        print(f"WARN {warning}")
    if errors:
        print("Release evidence: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    freshness = f", max age {args.max_age_hours:g}h" if args.max_age_hours is not None else ""
    strictness = ", strict version" if args.strict_version else ""
    print(f"Release evidence: PASS ({len(_read_json(ROOT / TARGETS_PATH)['targets'])} targets{freshness}{strictness})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
