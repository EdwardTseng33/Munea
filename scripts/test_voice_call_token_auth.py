# -*- coding: utf-8 -*-
"""Focused regression tests for realtime voice call-token authentication."""
import asyncio
import base64
import hashlib
import hmac
import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"


class _Dummy:
    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        return self


def _load_live_voice_server():
    dummy = _Dummy()
    fake_modules = {
        "env_loader": types.SimpleNamespace(load_engine_env=lambda: None),
        "chat_engine": types.SimpleNamespace(CHARS={"寧寧": {"voice": "Leda", "persona": ""}}),
        "localization": types.SimpleNamespace(display_text=lambda text, locale: text),
        "server": types.SimpleNamespace(),
        "notify": types.SimpleNamespace(),
        "perception_engine": types.SimpleNamespace(),
        "google": types.ModuleType("google"),
        "google.genai": types.SimpleNamespace(Client=lambda **kwargs: dummy, types=dummy),
        "google.genai.types": dummy,
    }
    fake_modules["google"].genai = fake_modules["google.genai"]
    module_name = "live_voice_server_token_auth_test"
    spec = importlib.util.spec_from_file_location(module_name, ENGINE / "live_voice_server.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, fake_modules), patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        sys.path.insert(0, str(ENGINE))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(ENGINE))
    return module


class FakeWebSocket:
    def __init__(self, path):
        self.request = types.SimpleNamespace(path=path)
        self.closed = []

    async def close(self, *, code, reason):
        self.closed.append((code, reason))


MODULE = _load_live_voice_server()


def _issue_token(secret):
    payload = {
        "call_id": "call-1",
        "lease_version": 1,
        "voice_shard_id": "voice-1",
        "exp": int(time.time()) + 60,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    return encoded + "." + signature


def _run(path, env):
    ws = FakeWebSocket(path)
    reached_voice_setup = []

    def stop_at_voice_setup(*args, **kwargs):
        reached_voice_setup.append(True)
        raise RuntimeError("stop after authentication")

    clean_env = {
        "MUNEA_CALL_CONTROL_REQUIRED": "0",
        "MUNEA_CALL_TOKEN_SECRET": "",
        "MUNEA_VOICE_SHARD_ID": "",
        "MUNEA_APP_KEY": "",
    }
    clean_env.update(env)
    with patch.dict(os.environ, clean_env, clear=False), patch.object(
        MODULE, "live_config", stop_at_voice_setup
    ), patch.object(MODULE, "post_internal", return_value={}), patch.object(
        MODULE, "_diag", return_value=None
    ):
        asyncio.run(MODULE.handle(ws))
    return ws.closed, bool(reached_voice_setup)


def test_invalid_supplied_token_fails_closed():
    closed, reached_voice_setup = _run(
        "/?token=invalid-token&key=legacy-key",
        {"MUNEA_CALL_TOKEN_SECRET": "unit-secret", "MUNEA_APP_KEY": "legacy-key"},
    )
    assert closed == [(4403, "invalid call token")]
    assert not reached_voice_setup


def test_missing_required_token_fails_closed_even_with_legacy_key():
    closed, reached_voice_setup = _run(
        "/?key=legacy-key",
        {"MUNEA_CALL_CONTROL_REQUIRED": "1", "MUNEA_APP_KEY": "legacy-key"},
    )
    assert closed == [(4403, "call token required")]
    assert not reached_voice_setup


def test_valid_token_reaches_voice_setup_when_control_is_required():
    secret = "unit-secret"
    token = _issue_token(secret)
    closed, reached_voice_setup = _run(
        "/?token=" + token,
        {
            "MUNEA_CALL_CONTROL_REQUIRED": "1",
            "MUNEA_CALL_TOKEN_SECRET": secret,
            "MUNEA_VOICE_SHARD_ID": "voice-1",
        },
    )
    assert closed == []
    assert reached_voice_setup


def test_configured_legacy_key_remains_allowed_when_control_is_optional():
    closed, reached_voice_setup = _run(
        "/?key=legacy-key",
        {"MUNEA_CALL_CONTROL_REQUIRED": "0", "MUNEA_APP_KEY": "legacy-key"},
    )
    assert closed == []
    assert reached_voice_setup


def main():
    test_invalid_supplied_token_fails_closed()
    test_missing_required_token_fails_closed_even_with_legacy_key()
    test_valid_token_reaches_voice_setup_when_control_is_required()
    test_configured_legacy_key_remains_allowed_when_control_is_optional()
    print("Voice call-token auth: ALL PASS")


if __name__ == "__main__":
    main()
