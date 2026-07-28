#!/usr/bin/env python3

import asyncio
import importlib.util
import os
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path


SOURCE = Path(__file__).with_name("voice_chain_probe.py")
SPEC = importlib.util.spec_from_file_location("voice_chain_probe", SOURCE)
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def main():
    assert probe.redact_endpoint("wss://voice.example/ws?token=secret") == "wss://voice.example/ws"
    assert "secret" not in probe.redact_endpoint("https://avatar.example/offer?key=secret")
    assert probe.redact_endpoint("wss://user:secret@voice.example/ws?token=hidden") == "wss://voice.example/ws"

    canary = "wss://canary-0716-1804---munea-voice-staging-fiu65jd4da-de.a.run.app"
    assert probe.validate_voice_canary_url(canary + "/") == canary
    legacy_canary = "wss://canary-0716-1804---munea-voice-staging-491603544409.asia-east1.run.app"
    assert probe.validate_voice_canary_url(legacy_canary) == legacy_canary
    for unsafe in (
        "ws://canary-0716-1804---munea-voice-staging-fiu65jd4da-de.a.run.app",
        "wss://voice.example",
        canary + "?token=caller-supplied",
        "wss://canary-x---munea-voice-staging-other-project.a.run.app",
    ):
        try:
            probe.validate_voice_canary_url(unsafe)
            raise AssertionError("unsafe Voice canary URL was accepted: " + unsafe)
        except ValueError:
            pass

    captured_request = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    original_urlopen = probe.urllib.request.urlopen
    try:
        def fake_urlopen(request, timeout):
            captured_request.update(headers=dict(request.header_items()), timeout=timeout)
            return FakeResponse()

        probe.urllib.request.urlopen = fake_urlopen
        status, payload = probe.get_json("https://gateway.example/health", 7, bearer="user-access-token")
        assert status == 200 and payload["ok"] is True
        assert captured_request["headers"]["Authorization"] == "Bearer user-access-token"
        assert captured_request["timeout"] == 7
    finally:
        probe.urllib.request.urlopen = original_urlopen

    sanitized = probe.ProbeReport("production", "2026-07-15T00:00:00Z")
    original_get_json = probe.get_json
    try:
        probe.get_json = lambda *_args, **_kwargs: (200, {"ok": True, "durable_ready": True})
        probe.probe_http_health(
            sanitized, "gateway_health", "https://gateway.example", "", 7,
            durable=True, bearer="user-access-token",
        )
    finally:
        probe.get_json = original_get_json
    assert sanitized.stages[-1].status == "PASS"

    # STATUS 125 defense line 1: call_token= must be used instead of key=
    # (not alongside it) so an expired/clock-skewed call token cannot be
    # masked by the legacy universal key= bypass.
    token_probe = probe.ProbeReport("production", "2026-07-15T00:00:00Z")
    captured_health_urls = []
    original_get_json = probe.get_json
    try:
        def fake_get_json(url, timeout, bearer=""):
            captured_health_urls.append(url)
            return 200, {"ok": True}
        probe.get_json = fake_get_json
        probe.probe_http_health(
            token_probe, "avatar_call_token_health", "https://avatar.example", "unused-legacy-key", 7,
            call_token="real-call-token",
        )
    finally:
        probe.get_json = original_get_json
    assert token_probe.stages[-1].status == "PASS"
    assert captured_health_urls[-1].endswith("?token=real-call-token")
    assert "key=" not in captured_health_urls[-1]

    original_post_json = probe.post_json
    malformed_calls = []
    try:
        def malformed_post(url, payload, timeout, bearer=""):
            malformed_calls.append((url, payload, bearer))
            if url.endswith("/v1/calls"):
                return 200, {
                    "status": "connect",
                    "call_id": "call-malformed",
                    "lease_version": 7,
                    "voice": {"url": "wss://voice.example"},
                    "worker": {"url": "https://avatar.example"},
                }
            assert url.endswith("/v1/calls/call-malformed/release")
            return 200, {"ok": True}

        probe.post_json = malformed_post
        malformed_report = probe.ProbeReport("production", "2026-07-15T00:00:00Z")
        assert probe.acquire_gateway_lease(
            malformed_report, "https://gateway.example", "user-access-token", 2,
        ) is None
    finally:
        probe.post_json = original_post_json
    assert malformed_calls[-1][0].endswith("/v1/calls/call-malformed/release")
    assert malformed_calls[-1][1]["lease_version"] == 7
    assert any(stage.name == "gateway_cleanup" and stage.status == "PASS" for stage in malformed_report.stages)

    queued_calls = []
    original_monotonic = probe.time.monotonic
    original_sleep = probe.time.sleep
    ticks = iter((0.0, 0.0, 0.0, 2.0, 2.0, 2.0, 2.0))
    try:
        def queued_post(url, payload, timeout, bearer=""):
            queued_calls.append((url, payload, bearer))
            if url.endswith("/v1/calls"):
                return 200, {"status": "queued", "call_id": "call-queued"}
            assert url.endswith("/v1/calls/call-queued/cancel")
            return 200, {"ok": True}

        probe.post_json = queued_post
        probe.time.monotonic = lambda: next(ticks, 2.0)
        probe.time.sleep = lambda _seconds: None
        queued_report = probe.ProbeReport("production", "2026-07-15T00:00:00Z")
        assert probe.acquire_gateway_lease(
            queued_report, "https://gateway.example", "user-access-token", 1,
        ) is None
    finally:
        probe.post_json = original_post_json
        probe.time.monotonic = original_monotonic
        probe.time.sleep = original_sleep
    assert queued_calls[-1][0].endswith("/v1/calls/call-queued/cancel")
    assert any(stage.name == "gateway_cleanup" and stage.status == "PASS" for stage in queued_report.stages)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "web" / "src").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "web" / "src" / "app.js").write_text(
            "const LIVE_VOICE_URL_DEFAULT = 'wss://prod.voice';\n"
            "const FLASHHEAD_URL_DEFAULT = 'https://avatar';\n"
            "const CALL_CONTROL_URL_DEFAULT = 'https://gateway';\n"
            "const MUNEA_APP_KEY = 'public-client-key';\n",
            encoding="utf-8",
        )
        (root / "scripts" / "enable-ios-development-profile.mjs").write_text(
            "const cfg = { voiceUrl: 'wss://dev.voice' };\n", encoding="utf-8"
        )
        development = probe.load_repo_profile("development", root)
        production = probe.load_repo_profile("production", root)
        assert development["voice_url"] == "wss://dev.voice"
        assert development["gateway_url"] == ""
        assert production["voice_url"] == "wss://prod.voice"
        assert production["gateway_url"] == "https://gateway"

    report = probe.ProbeReport("development", "2026-07-15T00:00:00Z")
    started = probe.time.monotonic()
    report.add("voice_ready", "PASS", started, endpoint="wss://voice.example?key=secret")
    report.add("avatar_health", "FAIL", started, "HTTP 500", "https://avatar.example?key=secret")
    assert report.passed is False
    assert report.first_failure == "avatar_health"
    serialized = str(report.payload())
    assert "secret" not in serialized
    assert report.payload()["scope"]["realDeviceMediaGate"] is False

    production = probe.ProbeReport("production", "2026-07-15T00:00:00Z")
    production.add("gateway_health", "PASS", started)
    production.add("gateway_lease", "SKIP", started, "missing test identity")
    production.add("voice_ready", "SKIP", started)
    production.add("avatar_health", "PASS", started)
    assert production.passed is False
    assert production.first_failure == ""
    assert production.first_blocker == "gateway_lease"

    unreleased = probe.ProbeReport("production", "2026-07-15T00:00:00Z")
    for stage in ("gateway_health", "gateway_lease", "voice_ready", "avatar_health"):
        unreleased.add(stage, "PASS", started)
    unreleased.add("gateway_release", "FAIL", started, "release failed")
    assert unreleased.passed is False and unreleased.first_failure == "gateway_release"

    # STATUS 125 defense line 1: a production report that never ran the
    # call-token health probe at all must not be able to report PASS, even
    # if every other stage (including the legacy key= avatar_health) is
    # green -- that green-everywhere-except-token shape is exactly what the
    # 2026-07-23 tw-06 outage would have produced under the old required set.
    missing_token_probe = probe.ProbeReport("production", "2026-07-15T00:00:00Z")
    for stage in ("gateway_health", "gateway_lease", "voice_ready", "avatar_health", "gateway_release"):
        missing_token_probe.add(stage, "PASS", started)
    assert missing_token_probe.passed is False
    assert missing_token_probe.first_blocker == "avatar_call_token_health"

    seen = {}

    def fake_profile(profile, root):
        return {
            "voice_url": "wss://production.voice",
            "avatar_url": "https://avatar",
            "gateway_url": "https://gateway",
            "app_key": "public-client-key",
        }

    def fake_health(report, name, base_url, app_key, timeout, durable=False, bearer="", call_token=""):
        seen[name + "_bearer"] = bearer
        seen[name + "_call_token"] = call_token
        report.add(name, "PASS", probe.time.monotonic(), "ok", base_url)

    def fake_lease(report, gateway_url, access_token, timeout):
        report.add("gateway_lease", "PASS", probe.time.monotonic(), "lease assigned", gateway_url)
        return {
            "call_id": "call-1",
            "lease_version": 1,
            "call_token": "signed-call-token",
            "voice": {"url": "wss://production.voice"},
            "worker": {"url": "https://avatar"},
        }

    async def fake_voice_ready(report, voice_url, app_key, timeout, call_token=""):
        seen.update(voice_url=voice_url, call_token=call_token)
        report.add("voice_ready", "PASS", probe.time.monotonic(), "ready", voice_url)

    def fake_release(report, gateway_url, access_token, lease, timeout):
        seen["released"] = lease["call_id"]
        report.add("gateway_release", "PASS", probe.time.monotonic(), "released", gateway_url)

    probe.load_repo_profile = fake_profile
    probe.probe_http_health = fake_health
    probe.acquire_gateway_lease = fake_lease
    probe.probe_voice_ready = fake_voice_ready
    probe.release_gateway_lease = fake_release
    args = SimpleNamespace(
        profile="production",
        root=".",
        voice_url="",
        voice_canary_url=canary,
        avatar_url="",
        gateway_url="",
        app_key="",
        timeout=12,
    )
    previous_access_token = os.environ.get("MUNEA_ACCESS_TOKEN")
    os.environ["MUNEA_ACCESS_TOKEN"] = "real-access-token"
    try:
        canary_report = asyncio.run(probe.run_probe(args))
        assert canary_report.passed is True
    finally:
        if previous_access_token is None:
            os.environ.pop("MUNEA_ACCESS_TOKEN", None)
        else:
            os.environ["MUNEA_ACCESS_TOKEN"] = previous_access_token
    assert seen == {
        "gateway_health_bearer": "real-access-token",
        "gateway_health_call_token": "",
        "avatar_health_bearer": "",
        "avatar_health_call_token": "",
        # STATUS 125 defense line 1: the token-based re-probe must run with
        # the real Gateway call token, not the legacy key=, and must be the
        # stage that actually receives it (avatar_health above never should).
        "avatar_call_token_health_bearer": "",
        "avatar_call_token_health_call_token": "signed-call-token",
        "voice_url": canary,
        "call_token": "signed-call-token",
        "released": "call-1",
    }
    assert any(stage.name == "voice_route" and stage.status == "PASS" for stage in canary_report.stages)
    assert any(
        stage.name == "avatar_call_token_health" and stage.status == "PASS"
        for stage in canary_report.stages
    )

    async def failing_voice_ready(report, voice_url, app_key, timeout, call_token=""):
        raise RuntimeError("unexpected Voice failure")

    seen.clear()
    probe.probe_voice_ready = failing_voice_ready
    os.environ["MUNEA_ACCESS_TOKEN"] = "real-access-token"
    try:
        try:
            asyncio.run(probe.run_probe(args))
            raise AssertionError("unexpected Voice failure should propagate")
        except RuntimeError as error:
            assert str(error) == "unexpected Voice failure"
    finally:
        if previous_access_token is None:
            os.environ.pop("MUNEA_ACCESS_TOKEN", None)
        else:
            os.environ["MUNEA_ACCESS_TOKEN"] = previous_access_token
    assert seen["released"] == "call-1"
    assert seen["gateway_health_bearer"] == "real-access-token"
    assert "avatar_health_bearer" not in seen
    assert "avatar_call_token_health_bearer" not in seen

    wrapper = SOURCE.with_name("voice-chain-auth-probe.ps1").read_text(encoding="utf-8")
    assert "Refusing to run while MUNEA_ACCESS_TOKEN is already set" in wrapper
    assert "auth/v1/admin/users" in wrapper and "grant_type=password" in wrapper
    assert 'action = "create"' in wrapper and 'purpose = "voice_chain_probe"' in wrapper
    assert 'probe_marker = $probeMarker' in wrapper
    assert 'accountName = $expectedAccountName' in wrapper
    assert "account_members?account_id=eq.$accountIdFilter&user_id=eq.$userIdFilter" in wrapper
    assert "accounts?id=eq.$accountIdFilter&select=id,name" in wrapper
    assert 'if ($accountId -and $accountDeleteAuthorized)' in wrapper
    assert 'user_metadata.probe_marker -ne $probeMarker' in wrapper
    assert wrapper.index("Verify isolated account ownership before cleanup") < wrapper.index("Delete isolated staging account")
    assert 'SetEnvironmentVariable("MUNEA_ACCESS_TOKEN", $accessToken, "Process")' in wrapper
    assert 'SetEnvironmentVariable("MUNEA_ACCESS_TOKEN", $null, "Process")' in wrapper
    assert 'SetEnvironmentVariable("MUNEA_GATEWAY_ADMIN_KEY", $null, "Process")' in wrapper
    assert "--access-token" not in wrapper
    assert "--access-token" not in SOURCE.read_text(encoding="utf-8")
    assert "munea-gateway-admin-key" not in wrapper
    assert "VoiceCanaryUrl must be a query-free wss://canary-*" in wrapper
    assert "fespbkdwafueyonppzwq.supabase.co" in wrapper
    print("Voice chain probe contracts: PASS")


if __name__ == "__main__":
    main()
