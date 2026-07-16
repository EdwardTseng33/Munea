#!/usr/bin/env python3

import asyncio
import importlib.util
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

    seen = {}

    def fake_profile(profile, root):
        return {
            "voice_url": "wss://production.voice",
            "avatar_url": "https://avatar",
            "gateway_url": "https://gateway",
            "app_key": "public-client-key",
        }

    def fake_health(report, name, base_url, app_key, timeout, durable=False):
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
        access_token="real-access-token",
        timeout=12,
    )
    canary_report = asyncio.run(probe.run_probe(args))
    assert canary_report.passed is True
    assert seen == {"voice_url": canary, "call_token": "signed-call-token", "released": "call-1"}
    assert any(stage.name == "voice_route" and stage.status == "PASS" for stage in canary_report.stages)
    print("Voice chain probe contracts: PASS")


if __name__ == "__main__":
    main()
