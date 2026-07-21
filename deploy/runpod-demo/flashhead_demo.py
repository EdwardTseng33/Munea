#!/usr/bin/env python3
"""B2B Demo-only FlashHead launcher.

This wrapper deliberately narrows the shared engine to the Demo character lane.
The App launcher and its a05/a06 defaults remain untouched.
"""

from __future__ import annotations

import os

import flashhead_server as server


DEMO_CHARACTERS = {
    "a05d": os.environ.get("MUNEA_FH_CHAR_A05D", "/workspace/munea-demo/assets/char-a05B-demo.png"),
    "a06d": os.environ.get("MUNEA_FH_CHAR_A06D", "/workspace/munea-demo/assets/char-a06B-demo.png"),
}


def install_demo_idle_barrier() -> None:
    """Drop an in-flight idle chunk as soon as real speech reaches the Demo.

    Idle motion is useful while the visitor is silent, but a GPU chunk may be
    mid-flight when the first real PCM packet arrives. Clearing only after that
    chunk finishes lets a few idle frames leak into the opening. Bump Feeder's
    existing generation epoch immediately so the old chunk is discarded, then
    re-arm the shared audio/video opening gate for the real utterance.
    """

    original = server.Feeder.push24k
    if getattr(original, "_munea_demo_idle_barrier", False):
        return

    def push24k_with_idle_barrier(feeder, pcm_bytes):
        interrupted_idle = False
        with feeder.lock:
            if feeder._idle_on:
                feeder._idle_on = False
                feeder._epoch += 1
                interrupted_idle = True
        if interrupted_idle:
            feeder.slot.sink.clear()
            feeder.slot.audio_out.clear()
            feeder.slot.audio_out.arm_prebuffer(server.OPENING_PREBUFFER_S)
            print(
                "[demo-sync] real audio invalidated in-flight idle chunk epoch="
                + str(feeder._epoch),
                flush=True,
            )
        return original(feeder, pcm_bytes)

    push24k_with_idle_barrier._munea_demo_idle_barrier = True
    server.Feeder.push24k = push24k_with_idle_barrier


def main() -> None:
    import uvicorn

    server.CHAR_SRC = DEMO_CHARACTERS
    server.DEFAULT_CHAR = "a05d"
    server.AVATAR_RENDER_CONTRACTS = {
        key: value
        for key, value in server.AVATAR_RENDER_CONTRACTS.items()
        if key in DEMO_CHARACTERS
    }
    install_demo_idle_barrier()

    fh = server.FlashHead()
    fh.load()
    fh.wake()
    app = fh.web()
    print(
        "[demo-main] serving on 0.0.0.0:"
        + str(server.PORT)
        + " slots="
        + str(server.N_SLOTS)
        + " chars=a05d,a06d",
        flush=True,
    )
    uvicorn.run(app, host="0.0.0.0", port=server.PORT, log_level="warning")


if __name__ == "__main__":
    main()
