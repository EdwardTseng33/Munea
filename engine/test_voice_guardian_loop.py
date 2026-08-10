import asyncio
import os

os.environ.setdefault("GEMINI_API_KEY", "test")

import live_voice_server as voice


class FakeSession:
    def __init__(self):
        self.sent = []

    async def send_client_content(self, turns=None, turn_complete=None):
        self.sent.append(turns.parts[0].text if turns and turns.parts else "")


def _risk(category):
    return {
        "risk": {
            "level": "high",
            "categories": [category],
            "requiresAuditEvent": True,
            "requiresHumanEscalation": True,
        },
        "responsePolicy": {},
    }


async def _recursive_followup_scenario():
    state = voice._new_call_state()
    session = FakeSession()
    state["guardian_real_turn_id"] = 1
    original_scan = voice.guardian_scan_text
    original_record = voice.guardian_record_and_alert
    results = iter([
        _risk("medical_emergency_signal"),
        _risk("medical_emergency_signal"),
        _risk("self_harm_crisis"),
        _risk("medical_emergency_signal"),
    ])
    voice.guardian_scan_text = lambda text: next(results)
    voice.guardian_record_and_alert = lambda *args, **kwargs: None
    try:
        await voice.guardian_watch(1, "ai", "unsafe answer", state, session,
                                   turn_id=1, allow_cue=True)
        await voice.guardian_flush_pending_cue(1, session, state)
        assert len(session.sent) == 1

        await voice.guardian_watch(1, "user", "unsafe user turn", state, session,
                                   turn_id=1, allow_cue=True)
        await voice.guardian_flush_pending_cue(1, session, state)
        assert len(session.sent) == 2
        assert state["guardian_internal_followup_active"] is True

        await voice.guardian_watch(1, "ai", "hidden correction", state, session,
                                   turn_id=1, allow_cue=False)
        await voice.guardian_flush_pending_cue(1, session, state)
        assert len(session.sent) == 2

        next_turn = voice._guardian_begin_real_user_turn(state)
        assert next_turn == 2
        await voice.guardian_watch(1, "user", "new unsafe turn", state, session,
                                   turn_id=next_turn, allow_cue=True)
        await voice.guardian_flush_pending_cue(1, session, state)
        assert len(session.sent) == 3
    finally:
        voice.guardian_scan_text = original_scan
        voice.guardian_record_and_alert = original_record


async def _routine_health_match_does_not_speak_scenario():
    state = voice._new_call_state()
    session = FakeSession()
    state["pending_health_cue"] = "hidden routine health guidance"
    state["pending_health_record"] = ("phlegm", "有痰", {}, 12)
    await voice.guardian_flush_pending_cue(1, session, state)
    assert session.sent == []
    assert state["pending_health_cue"] is None
    assert state["pending_health_record"] is None


def test_guardian_internal_followup_cannot_recurse():
    asyncio.run(_recursive_followup_scenario())


def test_routine_health_match_does_not_open_hidden_spoken_turn():
    asyncio.run(_routine_health_match_does_not_speak_scenario())


if __name__ == "__main__":
    test_guardian_internal_followup_cannot_recurse()
    test_routine_health_match_does_not_open_hidden_spoken_turn()
    print("Voice guardian loop regression PASS")
