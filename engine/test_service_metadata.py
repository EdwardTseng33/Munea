#!/usr/bin/env python3
"""Deterministic contract tests for Brain and Voice release observability."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "service-metadata-test-key")
os.environ.setdefault("MUNEA_DATABASE_PROVIDER", "json")

import service_metadata


FIXED_RELEASE = {
    "schema": "munea.service-release.v1",
    "service": "munea-test",
    "version": "9.8.7",
    "commit": "a" * 40,
    "revision": "munea-test-00042-abc",
    "environment": "staging",
}


def _unexpected_reader(_root):
    raise AssertionError("fallback reader should not be called")


def test_injected_release_identity_wins_and_is_allowlisted():
    env = {
        "MUNEA_RELEASE_VERSION": "9.8.7",
        "MUNEA_RELEASE_COMMIT": "A" * 40,
        "MUNEA_RELEASE_REVISION": "munea-test-00042-abc",
        "MUNEA_ENV_NAME": "staging",
        "GEMINI_API_KEY": "must-never-appear",
        "SUPABASE_SERVICE_ROLE_KEY": "also-must-never-appear",
    }
    result = service_metadata.build_service_metadata(
        "munea-test",
        environ=env,
        version_reader=_unexpected_reader,
        commit_reader=_unexpected_reader,
    )
    assert result == FIXED_RELEASE
    encoded = json.dumps(result)
    assert "must-never-appear" not in encoded
    assert "also-must-never-appear" not in encoded


def test_package_and_git_fallbacks_are_deterministic():
    roots = []

    def version_reader(root):
        roots.append(Path(root))
        return "1.0.26"

    def commit_reader(root):
        roots.append(Path(root))
        return "B" * 40

    repo_root = Path("C:/deterministic/repo")
    result = service_metadata.build_service_metadata(
        "munea-brain",
        environ={},
        repo_root=repo_root,
        version_reader=version_reader,
        commit_reader=commit_reader,
    )
    assert result == {
        "schema": "munea.service-release.v1",
        "service": "munea-brain",
        "version": "1.0.26",
        "commit": "b" * 40,
        "revision": "unknown",
        "environment": "unknown",
    }
    assert roots == [repo_root, repo_root]


def test_invalid_public_values_fail_closed():
    result = service_metadata.build_service_metadata(
        "bad/service",
        environ={
            "MUNEA_RELEASE_VERSION": "bad version",
            "MUNEA_RELEASE_COMMIT": "not-a-commit",
            "K_REVISION": "bad/revision",
            "MUNEA_ENVIRONMENT": "bad environment",
        },
        version_reader=lambda _root: "still bad",
        commit_reader=lambda _root: "still-not-a-commit",
    )
    assert set(result.values()) == {"munea.service-release.v1", "unknown"}


def test_brain_health_and_version_expose_the_same_release():
    import server

    def request(path):
        captured = []
        handler = server.H.__new__(server.H)
        handler.path = path
        handler._json = captured.append
        with mock.patch.object(server, "BRAIN_RELEASE_METADATA", FIXED_RELEASE), \
                mock.patch.object(server, "utc_now", return_value="2026-07-16T00:00:00Z"), \
                mock.patch.object(server, "data_backend_status", return_value={"enabled": False}), \
                mock.patch.object(server, "apns_status", return_value={"enabled": False}):
            server.H.do_GET(handler)
        assert len(captured) == 1
        return captured[0]

    health = request("/healthz?probe=1")
    version = request("/version")
    assert health["ok"] is True
    assert health["service"] == "munea-local-engine"
    assert health["release"] == FIXED_RELEASE
    assert version == {"ok": True, "release": FIXED_RELEASE}


def test_voice_health_and_version_preserve_websocket_upgrades():
    class DummyClient:
        pass

    with mock.patch("google.genai.Client", return_value=DummyClient()):
        import live_voice_server

    def request(path, headers=None):
        req = SimpleNamespace(path=path, headers=headers or {})
        response = live_voice_server.process_request(None, req)
        return response, json.loads(response.body.decode("utf-8"))

    with mock.patch.object(live_voice_server, "VOICE_RELEASE_METADATA", FIXED_RELEASE):
        health_response, health = request("/healthz?probe=1")
        version_response, version = request("/version/")
    assert health_response.status_code == 200
    assert health_response.headers["Cache-Control"] == "no-store"
    assert health["service"] == "munea-voice"
    assert health["release"] == FIXED_RELEASE
    assert version_response.status_code == 200
    assert version == {"ok": True, "release": FIXED_RELEASE}

    upgrade = SimpleNamespace(path="/healthz", headers={"Upgrade": "websocket"})
    assert live_voice_server.process_request(None, upgrade) is None


def main():
    tests = [
        test_injected_release_identity_wins_and_is_allowlisted,
        test_package_and_git_fallbacks_are_deterministic,
        test_invalid_public_values_fail_closed,
        test_brain_health_and_version_expose_the_same_release,
        test_voice_health_and_version_preserve_websocket_upgrades,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("Service release metadata: ALL PASS")


if __name__ == "__main__":
    main()
