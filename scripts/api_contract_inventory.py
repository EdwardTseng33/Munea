#!/usr/bin/env python3
"""Generate and validate Munea's source-derived API contract inventory.

The runtime handlers remain authoritative for route existence.  The committed
inventory adds the review metadata that cannot be inferred safely from syntax
alone, and this validator prevents the two views from drifting apart.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = Path("docs/API-CONTRACT-INVENTORY.json")
SCHEMA = "munea.api-contract-inventory.v1"
SOURCE_PATHS = {
    "brain": "engine/server.py",
    "gateway": "deploy/gateway/gateway_server.py",
    "voice": "engine/live_voice_server.py",
}
FIELDS = {
    "surface", "method", "path", "auth", "criticality", "idempotency",
    "rateLimit", "pii", "envelope", "tests",
}
AUTH_STRENGTH = {
    "public": 0,
    "public-test-surface": 0,
    "developer-only": 0,
    "operator-credentials": 1,
    "legacy-key": 1,
    "user-or-client-key-or-operator": 1,
    "user": 2,
    "user-or-developer": 2,
    "user-and-operator-write": 2,
    "provider-jws": 3,
    "provider-or-operator": 3,
    "internal": 3,
    "operator": 3,
    "call-token-or-app-key": 3,
}


@dataclass(frozen=True, order=True)
class Route:
    surface: str
    method: str
    path: str

    @property
    def key(self) -> tuple[str, str, str]:
        return self.surface, self.method, self.path


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _canonical_path(value: str) -> str:
    path = "/" + str(value).strip().lstrip("/")
    return path.rstrip("/") or "/"


def _literal_strings(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values: list[str] = []
        for item in node.elts:
            values.extend(_literal_strings(item))
        return values
    return []


def _expression_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _expression_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise ValueError(f"source function not found: {name}")


def _comparison_paths(function: ast.AST, names: set[str]) -> set[str]:
    paths: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
            continue
        if _expression_name(node.left) not in names:
            continue
        if not isinstance(node.ops[0], (ast.Eq, ast.In)):
            continue
        for value in _literal_strings(node.comparators[0]):
            if value:
                paths.add(_canonical_path(value))
    return paths


def extract_brain_routes(root: Path) -> set[Route]:
    tree = ast.parse(_read(root, SOURCE_PATHS["brain"]), filename=SOURCE_PATHS["brain"])
    post_paths = _comparison_paths(_function(tree, "do_POST"), {"self.path", "request_path"})
    get_paths = _comparison_paths(_function(tree, "do_GET"), {"path"})
    routes = {Route("brain", "POST", path) for path in post_paths}
    routes.update(Route("brain", "GET", path) for path in get_paths if path in {"/healthz", "/version"})
    return routes


def extract_gateway_routes(root: Path) -> set[Route]:
    tree = ast.parse(_read(root, SOURCE_PATHS["gateway"]), filename=SOURCE_PATHS["gateway"])
    routes: set[Route] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
                continue
            if func.value.id != "app" or func.attr.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            values = _literal_strings(decorator.args[0])
            if len(values) != 1:
                raise ValueError(f"gateway route on {node.name} must use one literal path")
            routes.add(Route("gateway", func.attr.upper(), _canonical_path(values[0])))
    return routes


def extract_voice_routes(root: Path) -> set[Route]:
    tree = ast.parse(_read(root, SOURCE_PATHS["voice"]), filename=SOURCE_PATHS["voice"])
    paths = _comparison_paths(_function(tree, "process_request"), {"path"})
    api_paths = {path for path in paths if path in {"/version", "/healthz", "/chat-test"}}
    routes = {Route("voice", "GET", path) for path in api_paths}
    routes.add(Route("voice", "WS", "/"))
    return routes


def extract_routes(root: Path = ROOT) -> set[Route]:
    root = Path(root).resolve()
    return extract_brain_routes(root) | extract_gateway_routes(root) | extract_voice_routes(root)


def _brain_auth(path: str) -> str:
    if path in {"/healthz", "/version", "/auth-status"}:
        return "public"
    if path == "/account-bootstrap":
        return "user-or-developer"
    if path == "/apple/notifications":
        return "provider-jws"
    if path == "/subscription-event":
        return "provider-or-operator"
    if path.startswith("/voice/"):
        return "internal"
    if path == "/admin/login":
        return "operator-credentials"
    if path.startswith("/admin/") or path in {"/credits/grant", "/credits/consume"}:
        return "operator"
    if path == "/entitlements":
        return "user-and-operator-write"
    if path == "/dev/page-capture":
        return "developer-only"
    return "user"


def _gateway_auth(path: str) -> str:
    if path.startswith("/v1/internal/") or path.startswith("/v1/admin/") or path == "/metrics":
        return "operator"
    if path == "/health":
        return "user-or-client-key-or-operator"
    if path.startswith("/v1/calls"):
        return "user"
    return "legacy-key"


def _auth(route: Route) -> str:
    if route.surface == "brain":
        return _brain_auth(route.path)
    if route.surface == "gateway":
        return _gateway_auth(route.path)
    if route.method == "WS":
        return "call-token-or-app-key"
    if route.path == "/chat-test":
        return "public-test-surface"
    return "public"


def _criticality(route: Route) -> str:
    critical_brain = {
        "/account-bootstrap", "/account-deletion", "/apple/notifications", "/apple/transaction",
        "/auth-status", "/credits/balance", "/credits/consume", "/credits/grant",
        "/entitlements", "/privacy-export", "/subscription-event",
        "/voice/call-memory", "/voice/call-recap", "/voice/health-context",
    }
    if route.surface == "gateway" and route.path.startswith(("/v1/calls", "/v1/internal/calls", "/v1/internal/reap")):
        return "critical"
    if route.surface == "voice" and route.method == "WS":
        return "critical"
    if route.surface == "brain" and route.path in critical_brain:
        return "critical"
    if route.path in {"/health", "/healthz", "/version", "/metrics"}:
        return "high"
    if route.path.startswith(("/admin/", "/v1/admin/", "/v1/internal/", "/family", "/notifications", "/push/")):
        return "high"
    if route.surface == "brain" and route.path.startswith(("/guardian/", "/memory/", "/voice-")):
        return "high"
    return "standard"


def _idempotency(route: Route) -> str:
    if route.method == "GET":
        return "safe"
    if route.method == "WS":
        return "connection-scoped"
    if route.surface == "gateway":
        if route.path == "/v1/calls":
            return "required-key"
        if route.path.startswith("/v1/calls/") or route.path.startswith("/v1/internal/calls"):
            return "required-event"
        return "operation-defined"
    if route.path in {"/account-bootstrap", "/apple/transaction", "/apple/notifications", "/subscription-event"}:
        return "provider-or-operation-key"
    if route.path.startswith("/credits/"):
        return "required-key"
    return "operation-defined"


def _rate_limit(route: Route) -> str:
    ai_paths = {
        "/open", "/chat", "/voice-note", "/persona/context", "/memory/extract",
        "/memory/retrieve", "/conversation-summary", "/butler/post-turn",
        "/guardian/evaluate", "/perception/topic-plan", "/perception/snapshot", "/proactive/opening",
    }
    return "actor-per-route-minute" if route.surface == "brain" and route.path in ai_paths else "none"


def _pii(route: Route) -> str:
    path = route.path
    if path in {"/health", "/healthz", "/version", "/metrics"}:
        return "none"
    if any(token in path for token in ("credits", "subscription", "apple/transaction", "entitlements")):
        return "billing"
    if any(token in path for token in ("health", "medication", "wellbeing", "care-schedule", "safety")):
        return "health"
    if any(token in path for token in ("chat", "voice", "memory", "conversation", "persona", "perception")):
        return "conversation"
    if route.surface == "gateway":
        return "operations"
    return "account"


def _envelope(route: Route) -> str:
    if route.method == "WS":
        return "websocket-events"
    if route.path == "/metrics":
        return "prometheus-text"
    if route.path == "/chat-test":
        return "html"
    if route.path == "/version":
        return "munea.service-release.v1"
    return "json-object"


def _tests(route: Route) -> list[str]:
    path = route.path
    if route.surface == "gateway":
        return ["scripts/test_gateway_http.py", "scripts/test_call_control.py"]
    if route.surface == "voice":
        if route.method == "WS":
            return ["scripts/test_voice_chain_probe.py", "scripts/test_voice_call_token_auth.py"]
        if path in {"/healthz", "/version"}:
            return ["engine/test_service_metadata.py"]
        return []
    if path in {"/healthz", "/version"}:
        return ["engine/test_service_metadata.py"]
    if path.startswith("/admin/"):
        return ["scripts/admin-smoke.ps1"]
    mapping = {
        "/account-bootstrap": ["scripts/auth-gate-smoke.ps1", "scripts/test-native-auth.js"],
        "/account-deletion": ["engine/test_privacy_export.py"],
        "/apple/notifications": ["engine/test_apple_store.py"],
        "/apple/transaction": ["engine/test_apple_store.py", "scripts/test-store-verification.js"],
        "/auth-status": ["scripts/auth-gate-smoke.ps1"],
        "/credits/balance": ["scripts/test_call_control.py"],
        "/credits/consume": ["scripts/test_call_control_sql.py"],
        "/credits/grant": ["scripts/test_call_control_sql.py"],
        "/entitlements": ["scripts/test-store-verification.js", "engine/test_subscription_expiry.py"],
        "/privacy-export": ["engine/test_privacy_export.py"],
        "/subscription-event": ["engine/test_subscription_expiry.py", "scripts/test-store-verification.js"],
        "/voice/call-memory": ["engine/test_voice_call_memory.py", "scripts/test_voice_chain_probe.py"],
        "/voice/call-recap": ["engine/test_voice_call_memory.py", "scripts/test_voice_chain_probe.py"],
        "/voice/health-context": ["engine/test_voice_health_context.py", "scripts/test_voice_chain_probe.py"],
    }
    return mapping.get(path, [])


def metadata(route: Route) -> dict[str, Any]:
    return {
        "surface": route.surface,
        "method": route.method,
        "path": route.path,
        "auth": _auth(route),
        "criticality": _criticality(route),
        "idempotency": _idempotency(route),
        "rateLimit": _rate_limit(route),
        "pii": _pii(route),
        "envelope": _envelope(route),
        "tests": _tests(route),
    }


def build_inventory(root: Path = ROOT, routes: Iterable[Route] | None = None) -> dict[str, Any]:
    actual = sorted(set(routes) if routes is not None else extract_routes(root))
    counts = {surface: sum(route.surface == surface for route in actual) for surface in SOURCE_PATHS}
    return {
        "schema": SCHEMA,
        "sources": SOURCE_PATHS,
        "policyNotes": [
            "AST extraction governs route existence, method, path, and surface only; auth is a reviewed declaration.",
            "Listed route tests own auth behavior and downgrade evidence; an empty tests list means no claimed coverage.",
        ],
        "routeCounts": counts,
        "routes": [metadata(route) for route in actual],
    }


def _route_from_entry(entry: dict[str, Any]) -> Route | None:
    try:
        return Route(str(entry["surface"]), str(entry["method"]), str(entry["path"]))
    except (KeyError, TypeError):
        return None


def validate_inventory(
    inventory: dict[str, Any], root: Path = ROOT, actual_routes: Iterable[Route] | None = None
) -> list[str]:
    root = Path(root).resolve()
    errors: list[str] = []
    if inventory.get("schema") != SCHEMA:
        errors.append(f"inventory schema must be {SCHEMA}")
    entries = inventory.get("routes")
    if not isinstance(entries, list):
        return errors + ["inventory routes must be an array"]

    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"route entry {index} must be an object")
            continue
        missing_fields = sorted(FIELDS - set(entry))
        extra_fields = sorted(set(entry) - FIELDS)
        if missing_fields:
            errors.append(f"route entry {index} missing fields: {', '.join(missing_fields)}")
        if extra_fields:
            errors.append(f"route entry {index} has unknown fields: {', '.join(extra_fields)}")
        route = _route_from_entry(entry)
        if route is None:
            errors.append(f"route entry {index} has invalid identity")
            continue
        if route.key in indexed:
            errors.append(f"duplicate route: {' '.join(route.key)}")
        else:
            indexed[route.key] = entry

    actual = set(actual_routes) if actual_routes is not None else extract_routes(root)
    actual_by_key = {route.key: route for route in actual}
    for key in sorted(set(actual_by_key) - set(indexed)):
        errors.append(f"source route is not registered: {' '.join(key)}")
    for key in sorted(set(indexed) - set(actual_by_key)):
        errors.append(f"inventory route no longer exists: {' '.join(key)}")

    for key in sorted(set(indexed) & set(actual_by_key)):
        entry = indexed[key]
        expected = metadata(actual_by_key[key])
        actual_auth = str(entry.get("auth") or "")
        expected_auth = expected["auth"]
        if actual_auth != expected_auth:
            if AUTH_STRENGTH.get(actual_auth, -1) < AUTH_STRENGTH[expected_auth]:
                errors.append(
                    f"auth downgrade for {' '.join(key)}: expected {expected_auth}, got {actual_auth or '<missing>'}"
                )
            else:
                errors.append(f"auth policy drift for {' '.join(key)}: expected {expected_auth}, got {actual_auth}")
        for field in sorted(FIELDS - {"surface", "method", "path", "auth", "tests"}):
            if entry.get(field) != expected[field]:
                errors.append(
                    f"metadata drift for {' '.join(key)} field {field}: expected {expected[field]!r}, got {entry.get(field)!r}"
                )
        tests = entry.get("tests")
        if not isinstance(tests, list) or any(not isinstance(item, str) or not item for item in tests):
            errors.append(f"route tests must be a string array: {' '.join(key)}")
            continue
        if entry.get("criticality") == "critical" and not tests:
            errors.append(f"critical route has no test: {' '.join(key)}")
        expected_tests = expected["tests"]
        if tests != expected_tests:
            errors.append(f"test coverage drift for {' '.join(key)}")
        for test_id in tests:
            test_path = test_id.split("::", 1)[0]
            if not (root / test_path).is_file():
                errors.append(f"route test target does not exist for {' '.join(key)}: {test_path}")

    expected_counts = {surface: sum(route.surface == surface for route in actual) for surface in SOURCE_PATHS}
    if inventory.get("routeCounts") != expected_counts:
        errors.append(f"routeCounts drift: expected {expected_counts}, got {inventory.get('routeCounts')}")
    if inventory.get("sources") != SOURCE_PATHS:
        errors.append("inventory sources must match the governed source paths")
    expected_notes = build_inventory(root, actual)["policyNotes"]
    if inventory.get("policyNotes") != expected_notes:
        errors.append("inventory policyNotes must explain the route/auth evidence boundary")
    return errors


def write_inventory(root: Path = ROOT) -> Path:
    destination = Path(root) / INVENTORY_PATH
    destination.write_text(
        json.dumps(build_inventory(root), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("check", "write", "render"), nargs="?", default="check")
    args = parser.parse_args()
    if args.command == "write":
        path = write_inventory(ROOT)
        print(f"API contract inventory written: {path.relative_to(ROOT)}")
        return 0
    if args.command == "render":
        print(json.dumps(build_inventory(ROOT), ensure_ascii=False, indent=2))
        return 0
    try:
        inventory = json.loads((ROOT / INVENTORY_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"API contract inventory cannot be read: {exc}")
        return 1
    errors = validate_inventory(inventory, ROOT)
    if errors:
        print("API contract inventory: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    counts = inventory["routeCounts"]
    print(
        "API contract inventory: PASS "
        f"({sum(counts.values())} routes: brain={counts['brain']}, gateway={counts['gateway']}, voice={counts['voice']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
