#!/usr/bin/env python3
"""Repository-backed path locks for parallel Munea agents."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


LOCK_ROOT = Path(".agent/locks/active")
TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
REQUIRED_FIELDS = {
    "task_id",
    "owner",
    "branch",
    "contact",
    "status",
    "started_at",
    "lease_expires_at",
    "base_sha",
    "paths",
    "note",
}


class LockError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LockError(f"invalid ISO timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise LockError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(timezone.utc)


def normalize_scope(raw: str) -> str:
    scope = str(raw or "").strip().replace("\\", "/")
    while scope.startswith("./"):
        scope = scope[2:]
    is_dir = scope.endswith("/")
    scope = re.sub(r"/+", "/", scope)
    if not scope or scope.startswith("/") or re.match(r"^[A-Za-z]:", scope):
        raise LockError(f"scope must be repository-relative: {raw!r}")
    if any(part in {"", ".", ".."} for part in scope.rstrip("/").split("/")):
        raise LockError(f"scope contains unsafe path segments: {raw!r}")
    if any(char in scope for char in "*?[]{}"):
        raise LockError(f"glob characters are not allowed in scopes: {raw!r}")
    return scope.rstrip("/") + ("/" if is_dir else "")


def scope_contains(scope: str, repo_path: str) -> bool:
    scope = normalize_scope(scope)
    path = normalize_scope(repo_path).rstrip("/")
    return path.startswith(scope) if scope.endswith("/") else path == scope


def scopes_overlap(left: str, right: str) -> bool:
    left = normalize_scope(left)
    right = normalize_scope(right)
    if left.endswith("/"):
        return right.rstrip("/").startswith(left) or (
            right.endswith("/") and left.startswith(right)
        )
    if right.endswith("/"):
        return left.startswith(right)
    return left == right


@dataclass(frozen=True)
class Lock:
    task_id: str
    owner: str
    branch: str
    contact: str
    status: str
    started_at: str
    lease_expires_at: str
    base_sha: str
    paths: tuple[str, ...]
    note: str
    source: str = ""

    @property
    def expired(self) -> bool:
        return parse_iso(self.lease_expires_at) <= utc_now()


def validate_payload(payload: dict, source: str = "") -> Lock:
    missing = sorted(REQUIRED_FIELDS - payload.keys())
    extra = sorted(payload.keys() - REQUIRED_FIELDS)
    if missing:
        raise LockError(f"{source}: missing fields: {', '.join(missing)}")
    if extra:
        raise LockError(f"{source}: unsupported fields: {', '.join(extra)}")
    task_id = str(payload["task_id"])
    if not TASK_ID_RE.fullmatch(task_id):
        raise LockError(f"{source}: invalid task_id: {task_id}")
    branch = str(payload["branch"])
    if not BRANCH_RE.fullmatch(branch) or branch in {"main", "master"}:
        raise LockError(f"{source}: invalid feature branch: {branch}")
    if payload["status"] != "active":
        raise LockError(f"{source}: status must be active")
    paths = tuple(dict.fromkeys(normalize_scope(item) for item in payload["paths"]))
    if not paths:
        raise LockError(f"{source}: paths must not be empty")
    started = parse_iso(str(payload["started_at"]))
    expires = parse_iso(str(payload["lease_expires_at"]))
    if expires <= started:
        raise LockError(f"{source}: lease must expire after it starts")
    if expires - started > timedelta(days=7):
        raise LockError(f"{source}: lease cannot exceed 7 days")
    for field in ("owner", "contact", "base_sha", "note"):
        if not str(payload[field]).strip():
            raise LockError(f"{source}: {field} must not be empty")
    return Lock(
        task_id=task_id,
        owner=str(payload["owner"]).strip(),
        branch=branch,
        contact=str(payload["contact"]).strip(),
        status="active",
        started_at=iso_z(started),
        lease_expires_at=iso_z(expires),
        base_sha=str(payload["base_sha"]).strip(),
        paths=paths,
        note=str(payload["note"]).strip(),
        source=source,
    )


def lock_to_payload(lock: Lock) -> dict:
    return {
        "task_id": lock.task_id,
        "owner": lock.owner,
        "branch": lock.branch,
        "contact": lock.contact,
        "status": lock.status,
        "started_at": lock.started_at,
        "lease_expires_at": lock.lease_expires_at,
        "base_sha": lock.base_sha,
        "paths": list(lock.paths),
        "note": lock.note,
    }


def load_worktree_locks() -> list[Lock]:
    if not LOCK_ROOT.exists():
        return []
    locks = []
    for path in sorted(LOCK_ROOT.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LockError(f"cannot read {path}: {exc}") from exc
        locks.append(validate_payload(payload, path.as_posix()))
    validate_lock_set(locks)
    return locks


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode:
        raise LockError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def load_ref_locks(ref: str) -> list[Lock]:
    names = git("ls-tree", "-r", "--name-only", ref, "--", LOCK_ROOT.as_posix())
    locks = []
    for name in names.splitlines():
        if not name.endswith(".json"):
            continue
        raw = git("show", f"{ref}:{name}")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LockError(f"{ref}:{name}: invalid JSON: {exc}") from exc
        locks.append(validate_payload(payload, f"{ref}:{name}"))
    validate_lock_set(locks)
    return locks


def validate_lock_set(locks: Iterable[Lock]) -> None:
    locks = list(locks)
    branches: dict[str, str] = {}
    for lock in locks:
        previous = branches.get(lock.branch)
        if previous and previous != lock.task_id:
            raise LockError(f"branch {lock.branch} has more than one active lock")
        branches[lock.branch] = lock.task_id
    for index, left in enumerate(locks):
        for right in locks[index + 1 :]:
            for left_scope in left.paths:
                for right_scope in right.paths:
                    if scopes_overlap(left_scope, right_scope):
                        raise LockError(
                            f"locks {left.task_id} and {right.task_id} overlap: "
                            f"{left_scope} <> {right_scope}"
                        )


def conflicts_for(branch: str, paths: Iterable[str], locks: Iterable[Lock]) -> list[tuple[Lock, str, str]]:
    normalized = [normalize_scope(path) for path in paths]
    conflicts = []
    for lock in locks:
        if lock.branch == branch:
            continue
        for candidate in normalized:
            for locked in lock.paths:
                if scopes_overlap(candidate, locked):
                    conflicts.append((lock, candidate, locked))
    return conflicts


def print_locks(locks: Iterable[Lock]) -> None:
    locks = list(locks)
    if not locks:
        print("No active agent locks on this checkout.")
        return
    for lock in locks:
        state = "STALE-BLOCKING" if lock.expired else "ACTIVE"
        print(f"[{state}] {lock.task_id} | {lock.owner} | {lock.branch}")
        print(f"  paths: {', '.join(lock.paths)}")
        print(f"  contact: {lock.contact}")
        print(f"  lease: {lock.lease_expires_at}")
        print(f"  note: {lock.note}")


def command_list(_: argparse.Namespace) -> int:
    print_locks(load_worktree_locks())
    return 0


def command_check(args: argparse.Namespace) -> int:
    locks = load_worktree_locks()
    conflicts = conflicts_for(args.branch, args.path, locks)
    if not conflicts:
        print("CLEAR: no overlapping agent lock found.")
        return 0
    print("BLOCKED: intended scope overlaps another agent lock.", file=sys.stderr)
    for lock, candidate, locked in conflicts:
        state = "stale but still blocking" if lock.expired else "active"
        print(
            f"- {candidate} overlaps {locked} ({lock.task_id}, {state}, "
            f"owner={lock.owner}, branch={lock.branch}, contact={lock.contact})",
            file=sys.stderr,
        )
    return 2


def command_create(args: argparse.Namespace) -> int:
    if not 1 <= args.lease_hours <= 168:
        raise LockError("lease-hours must be between 1 and 168")
    locks = load_worktree_locks()
    if any(lock.branch == args.branch for lock in locks):
        raise LockError(f"branch already has an active lock: {args.branch}")
    conflicts = conflicts_for(args.branch, args.path, locks)
    if conflicts:
        for lock, candidate, locked in conflicts:
            print(f"BLOCKED: {candidate} overlaps {locked} owned by {lock.branch}", file=sys.stderr)
        return 2
    now = utc_now()
    lock = validate_payload(
        {
            "task_id": args.task_id,
            "owner": args.owner,
            "branch": args.branch,
            "contact": args.contact,
            "status": "active",
            "started_at": iso_z(now),
            "lease_expires_at": iso_z(now + timedelta(hours=args.lease_hours)),
            "base_sha": git("rev-parse", "HEAD"),
            "paths": args.path,
            "note": args.note,
        },
        f"new:{args.task_id}",
    )
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    destination = LOCK_ROOT / f"{lock.task_id}.json"
    if destination.exists():
        raise LockError(f"lock already exists: {destination}")
    destination.write_text(json.dumps(lock_to_payload(lock), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {destination}. Commit only this lock file and merge the lock PR before editing.")
    return 0


def changed_files(base_ref: str, head_ref: str) -> list[str]:
    output = git("diff", "--name-only", "--diff-filter=ACMRD", f"{base_ref}...{head_ref}")
    return [line.replace("\\", "/") for line in output.splitlines() if line]


def lock_map(locks: Iterable[Lock]) -> dict[str, Lock]:
    return {lock.task_id: lock for lock in locks}


def command_ci(args: argparse.Namespace) -> int:
    files = changed_files(args.base_ref, args.head_ref)
    base_has_tool = subprocess.run(
        ["git", "cat-file", "-e", f"{args.base_ref}:scripts/agent-lock.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0
    head_locks = load_ref_locks(args.head_ref)
    if not base_has_tool:
        print("BOOTSTRAP: coordination tooling is new; current head lock set is valid.")
        return 0
    base_locks = load_ref_locks(args.base_ref)
    base_by_id = lock_map(base_locks)
    head_by_id = lock_map(head_locks)
    lock_only = bool(files) and all(path.startswith(f"{LOCK_ROOT.as_posix()}/") for path in files)
    if lock_only:
        added = [lock for task, lock in head_by_id.items() if task not in base_by_id]
        removed = [lock for task, lock in base_by_id.items() if task not in head_by_id]
        changed = [
            (base_by_id[task], head_by_id[task])
            for task in base_by_id.keys() & head_by_id.keys()
            if lock_to_payload(base_by_id[task]) != lock_to_payload(head_by_id[task])
        ]
        for lock in added:
            if lock.branch != args.branch:
                raise LockError(f"new lock {lock.task_id} must name PR branch {args.branch}")
            if lock.expired:
                raise LockError(f"new lock is already expired: {lock.task_id}")
        for lock in removed:
            if lock.branch != args.branch:
                raise LockError(f"branch {args.branch} cannot remove lock owned by {lock.branch}")
        for before, after in changed:
            if before.branch != args.branch or after.branch != args.branch:
                raise LockError(f"branch {args.branch} cannot modify lock {before.task_id}")
            if before.paths != after.paths or before.task_id != after.task_id:
                raise LockError(f"renewal cannot change paths for {before.task_id}; release and reacquire")
        print("PASS: lock-only PR is valid and has no overlap.")
        return 0

    own = [lock for lock in base_locks if lock.branch == args.branch]
    if len(own) != 1:
        raise LockError(f"implementation PR requires exactly one base lock for {args.branch}; found {len(own)}")
    own_lock = own[0]
    if own_lock.expired:
        raise LockError(f"implementation lock expired and must be renewed first: {own_lock.task_id}")
    if own_lock.task_id in head_by_id:
        raise LockError(f"completion PR must remove its own lock: {own_lock.task_id}")
    other_locks = [lock for lock in base_locks if lock.branch != args.branch]
    product_files = [path for path in files if not path.startswith(f"{LOCK_ROOT.as_posix()}/")]
    outside = [path for path in product_files if not any(scope_contains(scope, path) for scope in own_lock.paths)]
    if outside:
        raise LockError("changed files outside owned lock: " + ", ".join(outside))
    collisions = conflicts_for(args.branch, product_files, other_locks)
    if collisions:
        details = ", ".join(f"{path} <> {locked} ({lock.branch})" for lock, path, locked in collisions)
        raise LockError("changed files overlap other locks: " + details)
    print(f"PASS: {len(product_files)} changed files stay inside lock {own_lock.task_id}; lock is released on merge.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List active and stale-blocking locks")
    list_parser.set_defaults(handler=command_list)

    check_parser = subparsers.add_parser("check", help="Check intended paths against active locks")
    check_parser.add_argument("--branch", required=True)
    check_parser.add_argument("--path", action="append", required=True)
    check_parser.set_defaults(handler=command_check)

    create_parser = subparsers.add_parser("create", help="Create one lock file for a lock-only PR")
    create_parser.add_argument("--task-id", required=True)
    create_parser.add_argument("--owner", required=True)
    create_parser.add_argument("--branch", required=True)
    create_parser.add_argument("--contact", required=True)
    create_parser.add_argument("--path", action="append", required=True)
    create_parser.add_argument("--note", required=True)
    create_parser.add_argument("--lease-hours", type=int, default=24)
    create_parser.set_defaults(handler=command_create)

    ci_parser = subparsers.add_parser("ci", help="Validate a PR against base locks")
    ci_parser.add_argument("--base-ref", required=True)
    ci_parser.add_argument("--head-ref", required=True)
    ci_parser.add_argument("--branch", required=True)
    ci_parser.set_defaults(handler=command_ci)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return int(args.handler(args))
    except LockError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
