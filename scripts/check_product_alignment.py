#!/usr/bin/env python3
"""Offline governance checks for Munea current authorities and product alignment."""

from __future__ import annotations

import ast
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = Path("docs/CURRENT-AUTHORITIES.json")
REQUIRED_TOPICS = {
    "docs-entry",
    "product-spec",
    "billing-entitlements",
    "quality-confidence",
    "release-state",
    "product-alignment",
    "ai-design-intent",
    "ai-provider-reality",
    "backend-architecture",
    "cloudrun-topology",
    "collaboration",
}


def _read(root: Path, relative_path: str | Path) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _read_json(root: Path, relative_path: str | Path) -> Any:
    return json.loads(_read(root, relative_path))


def _safe_repo_path(root: Path, value: Any, label: str, errors: list[str]) -> Path | None:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        errors.append(f"{label} must be a non-empty repository-relative path")
        return None
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        errors.append(f"{label} escapes the repository: {value!r}")
        return None
    if not resolved.is_file():
        errors.append(f"{label} does not exist: {value}")
        return None
    return resolved


def _unique_matches(source: str, pattern: str) -> list[str]:
    return sorted({match.strip() for match in re.findall(pattern, source)})


def _products_from_python(source: str) -> dict[str, dict[str, Any]]:
    tree = ast.parse(source)
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "PRODUCTS" for target in statement.targets):
                value = ast.literal_eval(statement.value)
                if isinstance(value, dict):
                    return value
    raise ValueError("PRODUCTS assignment not found")


def validate(repo_root: Path = ROOT) -> list[str]:
    root = Path(repo_root).resolve()
    errors: list[str] = []

    try:
        authority = _read_json(root, AUTHORITY_PATH)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"authority index cannot be read: {exc}"]

    if not isinstance(authority, dict):
        return ["authority index root must be a JSON object"]
    if authority.get("schema") != "munea.docs-authority.v1":
        errors.append("authority index schema must be munea.docs-authority.v1")

    updated = authority.get("updated")
    try:
        updated_date = date.fromisoformat(str(updated))
        if updated_date > date.today():
            errors.append("authority index updated date cannot be in the future")
        if (date.today() - updated_date).days > 45:
            errors.append("authority index is older than 45 days")
    except ValueError:
        errors.append("authority index updated must be YYYY-MM-DD")

    entries = authority.get("authorities")
    if not isinstance(entries, list):
        errors.append("authority index authorities must be an array")
        entries = []

    topics: dict[str, dict[str, Any]] = {}
    current_paths: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        label = f"authority entry {index}"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        topic = entry.get("topic")
        if not isinstance(topic, str) or not topic:
            errors.append(f"{label} topic must be non-empty")
            continue
        if topic in topics:
            errors.append(f"authority topic is duplicated: {topic}")
        topics[topic] = entry
        path_value = entry.get("path")
        if _safe_repo_path(root, path_value, f"{label} path", errors):
            current_paths.add(str(path_value))
        if not isinstance(entry.get("ownerRole"), str) or not entry["ownerRole"].strip():
            errors.append(f"{label} ownerRole must be non-empty")

    missing_topics = sorted(REQUIRED_TOPICS - set(topics))
    unexpected_topics = sorted(set(topics) - REQUIRED_TOPICS)
    if missing_topics:
        errors.append("required authority topics are missing: " + ", ".join(missing_topics))
    if unexpected_topics:
        errors.append("authority topics are not governed: " + ", ".join(unexpected_topics))

    historical = authority.get("historical")
    if not isinstance(historical, list):
        errors.append("authority index historical must be an array")
        historical = []
    for index, entry in enumerate(historical, start=1):
        label = f"historical entry {index}"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        path_value = entry.get("path")
        superseded_by = entry.get("supersededBy")
        path = _safe_repo_path(root, path_value, f"{label} path", errors)
        _safe_repo_path(root, superseded_by, f"{label} supersededBy", errors)
        if path_value in current_paths:
            errors.append(f"historical document is also current authority: {path_value}")
        if superseded_by not in current_paths:
            errors.append(f"historical replacement is not a current authority: {superseded_by}")
        if path and "historical snapshot" not in path.read_text(encoding="utf-8").lower():
            errors.append(f"historical document lacks a Historical snapshot marker: {path_value}")

    try:
        package = _read_json(root, "package.json")
        package_lock = _read_json(root, "package-lock.json")
        version_source = _read(root, "web/src/version.js")
        xcode_source = _read(root, "ios/App/App.xcodeproj/project.pbxproj")
        web_version = re.search(r"current\s*:\s*['\"]([^'\"]+)['\"]", version_source)
        source_versions = {
            str(package.get("version") or ""),
            str(package_lock.get("version") or ""),
            str((package_lock.get("packages") or {}).get("", {}).get("version") or ""),
            web_version.group(1) if web_version else "",
        }
        source_versions.discard("")
        ios_versions = _unique_matches(xcode_source, r"MARKETING_VERSION\s*=\s*([^;]+);")
        ios_builds = _unique_matches(xcode_source, r"CURRENT_PROJECT_VERSION\s*=\s*([^;]+);")
        if len(source_versions) != 1:
            errors.append("source version does not resolve to one value")
            source_version = "unresolved"
        else:
            source_version = next(iter(source_versions))
        if ios_versions != [source_version]:
            errors.append(f"iOS marketing version is not aligned to source {source_version}: {ios_versions}")
        if len(ios_builds) != 1:
            errors.append(f"iOS build does not resolve to one value: {ios_builds}")
            ios_build = "unresolved"
        else:
            ios_build = ios_builds[0]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"release metadata cannot be inspected: {exc}")
        source_version = "unresolved"
        ios_build = "unresolved"

    expected_build = f"`{source_version} (Build {ios_build})`"
    current_doc_markers = {
        "docs/RELEASE-STATE.md": f"| Latest source | {expected_build}",
        "docs/PRODUCT-QUALITY-CONFIDENCE.md": f"| Latest source | {expected_build}",
        "docs/PRODUCT-ALIGNMENT-REGISTER.md": f"| App source lane | {expected_build}",
        "docs/00-總綱-從這裡開始.md": f"current source 為 {expected_build}",
    }
    for path_value, marker in current_doc_markers.items():
        try:
            source = _read(root, path_value)
            if marker not in source:
                errors.append(f"current source marker is stale in {path_value}: expected {marker}")
        except (OSError, UnicodeError) as exc:
            errors.append(f"current source document cannot be read: {path_value}: {exc}")

    expected_products = {
        "net.munea.app.points.200": {"kind": "points", "points": 100},
        "net.munea.app.points.500": {"kind": "points", "points": 300},
        "net.munea.app.points.1000": {"kind": "points", "points": 600},
        "net.munea.app.points.1800": {"kind": "points", "points": 1000},
        "net.munea.app.plus.monthly": {"kind": "subscription", "plan": "plus", "monthlyPoints": 100},
        "net.munea.app.plus.yearly": {"kind": "subscription", "plan": "plus", "monthlyPoints": 100},
        "net.munea.app.pro.monthly": {"kind": "subscription", "plan": "pro", "monthlyPoints": 200},
        "net.munea.app.pro.yearly": {"kind": "subscription", "plan": "pro", "monthlyPoints": 200},
    }
    try:
        actual_products = _products_from_python(_read(root, "engine/apple_store.py"))
        if actual_products != expected_products:
            errors.append("engine/apple_store.py PRODUCTS does not match the approved pricing contract")
    except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
        errors.append(f"Apple product contract cannot be inspected: {exc}")

    billing_tokens = [
        "| Munea Plus monthly | NT$599 | 100 per month |",
        "| Munea Pro monthly | NT$1,199 | 200 per month |",
        "| 100 | NT$790 | `net.munea.app.points.200` |",
        "| 300 | NT$2,190 | `net.munea.app.points.500` |",
        "| 600 | NT$4,190 | `net.munea.app.points.1000` |",
        "| 1,000 | NT$6,490 | `net.munea.app.points.1800` |",
        "policy is version 4 in `supabase/sql/019_pricing_plus100_pro200.sql`",
    ]
    try:
        billing_source = _read(root, "docs/BILLING-CREDITS-ENTITLEMENT-v1.md")
        for token in billing_tokens:
            if token not in billing_source:
                errors.append(f"billing authority is missing approved token: {token}")
        app_source = _read(root, "web/src/app.js")
        if not re.search(r"PT_PRICE\s*=\s*\{\s*100:\s*790,\s*300:\s*2190,\s*600:\s*4190,\s*1000:\s*6490\s*\}", app_source):
            errors.append("web point-pack prices do not match the approved pricing contract")
        sql_source = _read(root, "supabase/sql/019_pricing_plus100_pro200.sql")
        for token in ['"monthlyPoints": 100', '"monthlyPoints": 200']:
            if token not in sql_source:
                errors.append(f"pricing migration 019 is missing approved token: {token}")
        if not re.search(
            r"values\s*\(\s*'munea_app_store_v1'\s*,\s*4\s*,\s*true\s*,",
            sql_source,
            re.IGNORECASE | re.DOTALL,
        ):
            errors.append("pricing migration 019 does not install active policy version 4")
        migration_manifest = _read_json(root, "supabase/migration-manifest.json")
        migrations = migration_manifest.get("migrations") if isinstance(migration_manifest, dict) else None
        if not isinstance(migrations, list) or not any(
            entry.get("identity") == "019" and entry.get("filename") == "019_pricing_plus100_pro200.sql"
            for entry in migrations
            if isinstance(entry, dict)
        ):
            errors.append("pricing migration 019 is not governed by the migration manifest")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"billing alignment cannot be inspected: {exc}")

    ai_reality = topics.get("ai-provider-reality", {})
    if ai_reality.get("path") != "docs/PRODUCT-ALIGNMENT-REGISTER.md":
        errors.append("AI provider reality must be owned by PRODUCT-ALIGNMENT-REGISTER.md")
    try:
        alignment_source = _read(root, "docs/PRODUCT-ALIGNMENT-REGISTER.md")
        if not re.search(r"\| Butler \|.*Google GenAI.*\| `blocked` \|", alignment_source):
            errors.append("Butler provider reality must remain blocked until executable provider evidence exists")
        if not re.search(r"\| Guardian \|.*deterministic.*\|.*\| `partial` \|", alignment_source):
            errors.append("Guardian provider reality must remain partial until the provider pipeline is evidenced")
        docs_entry = _read(root, "docs/00-總綱-從這裡開始.md")
        if "不得再把 `claude-sonnet-5` 的字串宣告寫成 production provider 已驗證" not in docs_entry:
            errors.append("docs entry must distinguish AI model declarations from production provider evidence")
        if "本頁 §2 已加註「以 code 為準」" in docs_entry:
            errors.append("docs entry still claims an AI model string is authoritative runtime evidence")
    except (OSError, UnicodeError) as exc:
        errors.append(f"AI alignment cannot be inspected: {exc}")

    return errors


def main() -> int:
    errors = validate(ROOT)
    if errors:
        print("Product alignment governance: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    package = _read_json(ROOT, "package.json")
    xcode = _read(ROOT, "ios/App/App.xcodeproj/project.pbxproj")
    builds = _unique_matches(xcode, r"CURRENT_PROJECT_VERSION\s*=\s*([^;]+);")
    authority = _read_json(ROOT, AUTHORITY_PATH)
    print(
        "Product alignment governance: PASS "
        f"({len(authority['authorities'])} authorities, source {package['version']} Build {builds[0]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
