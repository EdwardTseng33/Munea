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
        source.index("self._gen_chunk(todo[0], todo[1], todo[2])")
    ]
    assert "self.slot.audio_out.clear()" in resume_block
    print("FlashHead idle contract: PASS")


if __name__ == "__main__":
    main()
