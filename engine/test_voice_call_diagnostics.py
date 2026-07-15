#!/usr/bin/env python3

import os
import sys
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "voice-diagnostics-test-key")
os.environ.setdefault("MUNEA_DATABASE_PROVIDER", "json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import server


EVENTS = [
    {
        "eventName": "voice_call_diagnostic",
        "eventTime": "2026-07-15T10:02:00Z",
        "properties": {
            "callId": "call-failed",
            "outcome": "failed",
            "reason": "readiness_timeout",
            "firstFailedStage": "avatar_first_frame",
            "lastSuccessfulStage": "voice_ready",
            "totalMs": 30000,
            "context": {
                "appVersion": "1.0.18",
                "routeMode": "gateway",
                "voiceEndpoint": "wss://voice.example/",
                "avatarEndpoint": "https://avatar.example/",
            },
        },
    },
    {
        "eventName": "voice_call_diagnostic",
        "eventTime": "2026-07-15T10:01:00Z",
        "properties": {
            "callId": "call-ok",
            "outcome": "completed",
            "reason": "user_ended",
            "lastSuccessfulStage": "call_connected",
            "totalMs": 90000,
            "context": {"appVersion": "1.0.18", "routeMode": "development_direct"},
        },
    },
    {
        "eventName": "voice_call_diagnostic",
        "eventTime": "2026-07-15T10:00:00Z",
        "properties": {
            "callId": "call-malformed",
            "outcome": "failed",
            "reason": "invalid_client_payload",
            "firstFailedStage": "voice_socket_connecting",
            "totalMs": "not-a-number",
            "context": {
                "voiceEndpoint": "wss://user:super-secret@voice.example/connect?token=hidden-token",
                "avatarEndpoint": "https://avatar.example/offer?key=hidden-key#debug",
            },
        },
    },
    {"eventName": "voice_session_started", "properties": {}},
]


def main():
    with mock.patch.object(server, "load_product_events", return_value=EVENTS), \
            mock.patch.object(server, "data_backend_status", return_value={"enabled": True}):
        result = server.admin_voice_diagnostics_summary({"days": 7, "limit": 10})

    assert result["ok"] is True
    assert result["count"] == 3
    assert result["successRate"] == 0.3333
    assert result["totals"]["byOutcome"] == {"completed": 1, "failed": 2}
    assert result["totals"]["byFailedStage"] == {
        "avatar_first_frame": 1,
        "voice_socket_connecting": 1,
    }
    assert result["totals"]["averageTotalMs"] == 40000
    assert result["recent"][0]["callId"] == "call-failed"
    assert result["recent"][0]["lastSuccessfulStage"] == "voice_ready"
    assert result["privacy"] == {
        "rawAudioStored": False,
        "rawTranscriptStored": False,
        "credentialsStored": False,
    }
    serialized = str(result)
    assert "stages" not in result["recent"][0]
    assert "private words" not in serialized.lower()
    assert "super-secret" not in serialized
    assert "hidden-token" not in serialized
    assert "hidden-key" not in serialized
    malformed = next(item for item in result["recent"] if item["callId"] == "call-malformed")
    assert malformed["totalMs"] == 0
    assert malformed["voiceEndpoint"] == "wss://voice.example/connect"
    assert malformed["avatarEndpoint"] == "https://avatar.example/offer"
    print("Voice call diagnostics admin summary: PASS")


if __name__ == "__main__":
    main()
