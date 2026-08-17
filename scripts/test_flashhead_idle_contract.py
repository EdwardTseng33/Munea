"""Contract test for FlashHead idle-feed gating.

Keeps burst-delivered TTS speech from being interleaved with generated idle silence.

2026-07-12 卡西法：N 槽改造把這段邏輯搬進 deploy/runpod-avatar/flashhead_engine_core.py
（原本在 flashhead_server.py 裡）——SOURCE 改指過去。同時修正一個改造前就已經存在的
過期斷言（"finish" flush 功能上線後 self._gen_chunk(todo) 已改成
self._gen_chunk(todo[0], todo[1], todo[2])，測試需跟現行輸出 PCM 參數同步）。
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "deploy" / "runpod-avatar" / "flashhead_engine_core.py"
CHUNK_SAMPLES = 15_360


def idle_allowed(last_input_age_s: float, queued_samples: int) -> bool:
    return last_input_age_s > 1.0 and queued_samples < CHUNK_SAMPLES


def main() -> None:
    assert not idle_allowed(1.2, CHUNK_SAMPLES * 5), "queued speech must block idle feed"
    assert not idle_allowed(0.5, 0), "recent input must block idle feed"
    assert idle_allowed(1.2, CHUNK_SAMPLES - 1), "drained speech may resume idle feed"

    source = SOURCE.read_text(encoding="utf-8")
    assert "(now - self.last_in) > 1.0 and len(self.acc) < cs" in source
    resume_block = source[
        source.index("if todo is not None:") :
        source.index("self._gen_chunk(todo[0], todo[1], todo[2], timeline_start_s=todo[3],")
    ]
    assert "self.slot.audio_out.clear()" not in resume_block, (
        "idle-to-speech must not reset the audio clock or re-arm a mid-turn prebuffer"
    )
    assert "emit_audio=False" in source, (
        "idle motion must not enqueue generated silence into the speech buffer"
    )
    finish_block = source[source.index("def finish(self):") : source.index("def _on_fault", source.index("def finish(self):"))]
    assert "self.slot.audio_out.queue(pcm_int16)" in source, (
        "original Voice PCM must enter the audible queue before lip rendering"
    )
    assert "self.slot.audio_out.release_playout()" in source, (
        "first rendered video must release the shared start gate without re-queueing PCM"
    )
    assert "self.slot.audio_out.mark_input_complete()" in finish_block, (
        "after audio/render decoupling, input EOF must classify post-speech silence immediately"
    )
    assert "self._complete_pending = False" in finish_block
    print("FlashHead idle contract: PASS")


if __name__ == "__main__":
    main()
