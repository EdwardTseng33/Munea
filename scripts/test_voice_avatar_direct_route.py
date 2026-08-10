"""Contract gate for the Voice -> Avatar direct PCM route.

The audible path must not normally bounce every model chunk through the phone.
If the direct websocket fails, the App must learn that before receiving the
same binary chunk so it can relay that exact chunk without a hole.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VOICE = (ROOT / "engine" / "live_voice_server.py").read_text(encoding="utf-8")
APP = (ROOT / "web" / "src" / "app.js").read_text(encoding="utf-8")
AVATAR = (ROOT / "deploy" / "runpod-avatar" / "flashhead_engine_core.py").read_text(
    encoding="utf-8"
)


def between(source: str, start: str, end: str) -> str:
    left = source.index(start)
    right = source.index(end, left)
    return source[left:right]


def main() -> None:
    forward = between(VOICE, "async def _forward_audio(chunk):", "async def _mark_first_audio")
    assert 'fw.send("reset")' in forward
    assert '"type": "faceaudio_turn", "turn": direct_turn' in forward
    assert 'fw.send("turn:" + str(direct_turn))' in forward
    assert 'int(st.get("face_audio_turn_seq") or 0) + 1' in forward
    assert "await asyncio.wait_for(fw.send(chunk), timeout=FACE_SEND_TIMEOUT_S)" in forward
    assert "await asyncio.wait_for(ready.wait(), timeout=FACE_SEND_TIMEOUT_S)" in forward
    assert '"type": "faceaudio_status", "on": False' in VOICE
    assert forward.index("await _face_audio_failed") < forward.index("await ws.send(chunk)"), (
        "fallback status must be sent before the App receives the failed direct chunk"
    )
    assert "async def _finish_face_audio_turn" in VOICE
    assert 'fw.send("finish")' in VOICE
    model_audio = between(VOICE, "if data and not st.get(\"language_block\")", "elif data:")
    assert "await _forward_audio(data)" in model_audio
    assert "await ws.send(data)" not in model_audio
    assert "fw.send(data)" not in model_audio

    face_control = between(VOICE, 'elif t == "faceaudio":', "async def from_live")
    status_send = face_control.index('"type": "faceaudio_status", "on": bool(direct_on)')
    ready_set = face_control.index("ready.set()")
    assert status_send < ready_set, "App direct-ready status must be sent before PCM is released"

    request = between(APP, "type: 'faceaudio', on: true", "voice_face_direct_requested")
    assert "session }" in request
    assert "const session = Avatar._session" in APP
    assert "token:" not in request, "the already-authenticated Voice socket owns the call token"
    assert "o.type === 'faceaudio_status'" in APP
    assert "o.type === 'faceaudio_turn'" in APP
    assert "Avatar.beginDirectTurn(this._faceDirectTurn)" in APP
    assert "Avatar.beginDirectTurn(timingTurn)" in APP
    assert "if (this._directAckTurn !== id) this._playoutArmedTurn = 0" in APP
    assert "if (!(this._sameLine && this._faceDirect)) Avatar.feed(audioData)" in APP
    assert "else if (!this._faceDirect) Avatar.finish()" in APP
    assert "Avatar._handlePcmAck(o, 'voice_direct_avatar_ack')" in APP

    assert "emit_audio=False" in AVATAR
    resume = between(AVATAR, "if todo is not None:", "self._gen_chunk(todo[0], todo[1], todo[2])")
    assert "self.slot.audio_out.clear()" not in resume

    print("Voice -> Avatar direct route contract: PASS")


if __name__ == "__main__":
    main()
