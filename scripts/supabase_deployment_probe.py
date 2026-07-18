#!/usr/bin/env python3
"""Secret-safe, read-only observations for Tokyo migrations 017-019."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
sys.path.insert(0, str(ENGINE))

from env_loader import load_engine_env


SCHEMA = "munea.supabase-deployment-observation.v1"
TOKYO_PROJECT_REF = "fespbkdwafueyonppzwq"


def _project_ref(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    suffix = ".supabase.co"
    return host[: -len(suffix)] if host.endswith(suffix) else ""


def _source_commit() -> str | None:
    value = str(os.environ.get("MUNEA_RELEASE_COMMIT") or "").strip()
    if value:
        return value
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"http_{exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return "unreachable"
    return type(exc).__name__


def _get(
    base_url: str,
    service_key: str,
    table: str,
    query: list[tuple[str, str]],
    *,
    exact_count: bool = False,
) -> tuple[list[dict[str, Any]], int | None]:
    url = f"{base_url.rstrip('/')}/rest/v1/{urllib.parse.quote(table)}?{urllib.parse.urlencode(query)}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }
    if exact_count:
        headers["Prefer"] = "count=exact"
        headers["Range"] = "0-0"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8") or "[]")
        if not isinstance(payload, list):
            raise ValueError("unexpected_response_shape")
        total = None
        if exact_count:
            content_range = str(response.headers.get("Content-Range") or "")
            tail = content_range.rsplit("/", 1)[-1]
            total = int(tail) if tail.isdigit() else None
        return payload, total


def _policy_matches(rows: list[dict[str, Any]]) -> bool:
    if len(rows) != 1:
        return False
    row = rows[0]
    policy = row.get("policy")
    if isinstance(policy, str):
        try:
            policy = json.loads(policy)
        except json.JSONDecodeError:
            return False
    return bool(
        row.get("active") is True
        and int(row.get("version") or 0) == 4
        and isinstance(policy, dict)
        and (policy.get("plus") or {}).get("monthlyPoints") == 100
        and (policy.get("pro") or {}).get("monthlyPoints") == 200
    )


def probe(target_project_ref: str = TOKYO_PROJECT_REF) -> dict[str, Any]:
    load_engine_env()
    base_url = str(os.environ.get("SUPABASE_URL") or "").strip()
    service_key = str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    observed_ref = _project_ref(base_url)
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "capturedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceCommit": _source_commit(),
        "targetProjectRef": target_project_ref,
        "observedProjectRef": observed_ref or None,
        "readOnly": True,
        "requestIssued": False,
        "ok": False,
        "ledgerPromotionAllowed": False,
        "promotionBlockers": ["018_requires_approved_backup_and_full_before_after_evidence"],
        "checks": {},
    }
    if not base_url or not service_key:
        result["error"] = "supabase_environment_incomplete"
        return result
    if observed_ref != target_project_ref:
        result["error"] = "target_project_mismatch"
        return result

    checks = result["checks"]
    result["requestIssued"] = True
    try:
        _get(base_url, service_key, "notification_settings", [("select", "person_id"), ("limit", "1")])
        checks["017_notification_settings"] = {"tableReachable": True}
    except Exception as exc:
        checks["017_notification_settings"] = {"tableReachable": False, "error": _safe_error(exc)}

    try:
        _, photo_rows = _get(
            base_url,
            service_key,
            "routine_reminders",
            [("select", "id"), ("schedule->photo", "not.is.null"), ("limit", "1")],
            exact_count=True,
        )
        checks["018_strip_medication_photos"] = {
            "photoKeyRows": photo_rows,
            "partialOnly": True,
            "reason": "data_image_scan_and_approved_before_after_record_still_required",
        }
    except Exception as exc:
        checks["018_strip_medication_photos"] = {"photoKeyRows": None, "partialOnly": True, "error": _safe_error(exc)}

    try:
        rows, _ = _get(
            base_url,
            service_key,
            "entitlement_policy_versions",
            [
                ("select", "version,active,policy"),
                ("policy_key", "eq.munea_app_store_v1"),
                ("version", "eq.4"),
                ("active", "is.true"),
                ("limit", "1"),
            ],
        )
        checks["019_pricing_plus100_pro200"] = {"policyV4Matches": _policy_matches(rows)}
    except Exception as exc:
        checks["019_pricing_plus100_pro200"] = {"policyV4Matches": False, "error": _safe_error(exc)}

    result["ok"] = bool(
        checks.get("017_notification_settings", {}).get("tableReachable")
        and checks.get("019_pricing_plus100_pro200", {}).get("policyV4Matches")
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-project-ref", default=TOKYO_PROJECT_REF)
    args = parser.parse_args()
    result = probe(args.target_project_ref)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
