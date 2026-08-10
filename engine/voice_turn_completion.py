"""Fail-safe policy for a Live provider turn that never reports completion."""

DEFAULT_IDLE_MS = 2500
MIN_AUDIO_MS = 200
PCM_BYTES_PER_SECOND = 24000 * 2


def provider_turn_stalled(
    now,
    *,
    active=False,
    last_audio_at=0.0,
    out_bytes=0,
    blocked=False,
    idle_ms=DEFAULT_IDLE_MS,
    min_audio_ms=MIN_AUDIO_MS,
):
    """Return True only after a real spoken turn has gone implausibly quiet.

    Gemini normally emits ``turn_complete`` after the last PCM chunk.  A rare
    missing event used to leave the App permanently in the assistant-speaking
    state.  Tool waits and intentional suppression must never trip this guard;
    short spoken acknowledgements still need recovery.
    """
    if not active or blocked or not last_audio_at:
        return False
    audio_ms = max(0.0, float(out_bytes)) * 1000.0 / PCM_BYTES_PER_SECOND
    if audio_ms < max(0.0, float(min_audio_ms)):
        return False
    quiet_ms = max(0.0, float(now) - float(last_audio_at)) * 1000.0
    return quiet_ms >= max(0.0, float(idle_ms))
