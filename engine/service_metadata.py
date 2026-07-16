"""Safe, stable release metadata shared by Munea services.

Deployments should inject ``MUNEA_RELEASE_*`` values.  Local development and
older deployment jobs remain useful through package.json and git fallbacks.
Only the allowlisted fields below are ever returned by service endpoints.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Mapping


SCHEMA = "munea.service-release.v1"
UNKNOWN = "unknown"
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SAFE_COMMIT = re.compile(r"^[0-9a-fA-F]{7,64}$")


def _first_safe(environ: Mapping[str, str], names: tuple[str, ...], pattern: re.Pattern[str]) -> str:
    for name in names:
        value = str(environ.get(name) or "").strip()
        if pattern.fullmatch(value):
            return value
    return UNKNOWN


def _package_version(repo_root: Path) -> str:
    try:
        payload = json.loads((repo_root / "package.json").read_text(encoding="utf-8"))
        value = str(payload.get("version") or "").strip()
        return value if _SAFE_LABEL.fullmatch(value) else UNKNOWN
    except (OSError, ValueError, TypeError):
        return UNKNOWN


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        value = result.stdout.strip()
        return value.lower() if _SAFE_COMMIT.fullmatch(value) else UNKNOWN
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN


def build_service_metadata(
    service: str,
    *,
    environ: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
    version_reader: Callable[[Path], str] = _package_version,
    commit_reader: Callable[[Path], str] = _git_commit,
) -> dict[str, str]:
    """Return the public release identity for one service.

    Readers are injectable so tests never need a real git checkout.  Environment
    values win over fallbacks, which lets an immutable image identify the source
    commit even when its ``.git`` directory isn't included.
    """

    env = os.environ if environ is None else environ
    root = Path(__file__).resolve().parents[1] if repo_root is None else Path(repo_root)
    safe_service = service.strip() if _SAFE_LABEL.fullmatch(service.strip()) else UNKNOWN

    version = _first_safe(env, ("MUNEA_RELEASE_VERSION", "MUNEA_VERSION"), _SAFE_LABEL)
    if version == UNKNOWN:
        fallback = str(version_reader(root) or "").strip()
        version = fallback if _SAFE_LABEL.fullmatch(fallback) else UNKNOWN

    commit = _first_safe(
        env,
        ("MUNEA_RELEASE_COMMIT", "MUNEA_GIT_COMMIT", "COMMIT_SHA", "GIT_SHA"),
        _SAFE_COMMIT,
    )
    if commit != UNKNOWN:
        commit = commit.lower()
    else:
        fallback = str(commit_reader(root) or "").strip()
        commit = fallback.lower() if _SAFE_COMMIT.fullmatch(fallback) else UNKNOWN

    revision = _first_safe(env, ("MUNEA_RELEASE_REVISION", "K_REVISION"), _SAFE_LABEL)
    environment = _first_safe(
        env,
        ("MUNEA_RELEASE_ENVIRONMENT", "MUNEA_ENVIRONMENT", "MUNEA_ENV_NAME"),
        _SAFE_LABEL,
    )

    return {
        "schema": SCHEMA,
        "service": safe_service,
        "version": version,
        "commit": commit,
        "revision": revision,
        "environment": environment,
    }
