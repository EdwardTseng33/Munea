#!/usr/bin/env python3

import importlib.util
import sys
import tempfile
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
    print("Voice chain probe contracts: PASS")


if __name__ == "__main__":
    main()
