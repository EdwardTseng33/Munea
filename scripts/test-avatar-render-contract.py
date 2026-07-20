"""Guard the App, B2B demo, and FlashHead model input against visual drift."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CANVAS = (1080, 1920)
CROP = (0, 140, 1080, 1580)
MAX_MEAN_ABSOLUTE_ERROR = 5.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    for char in ("a05", "a06"):
        app_bg = ROOT / "web" / "flashhead" / f"bg-{char}.png"
        b2b_bg = ROOT / "munea-b2b" / "flashhead" / f"bg-{char}.png"
        model_input = ROOT / "deploy" / "modal-avatar" / "assets" / f"{char}-inB-512-v2.png"

        if sha256(app_bg) != sha256(b2b_bg):
            raise AssertionError(f"{char}: App and B2B backgrounds drifted")

        with Image.open(app_bg).convert("RGB") as source:
            if source.size != CANVAS:
                raise AssertionError(f"{char}: expected App canvas {CANVAS}, got {source.size}")
            expected = source.crop(CROP).resize((512, 512), Image.Resampling.LANCZOS)
        with Image.open(model_input).convert("RGB") as actual:
            if actual.size != (512, 512):
                raise AssertionError(f"{char}: expected model input 512x512, got {actual.size}")
            error = float(np.abs(np.asarray(expected, dtype=np.int16) - np.asarray(actual, dtype=np.int16)).mean())
        if error > MAX_MEAN_ABSOLUTE_ERROR:
            raise AssertionError(f"{char}: model input drifted from App crop (MAE={error:.3f})")
        print(f"{char}: contract ok (MAE={error:.3f})")

    call_html = (ROOT / "munea-b2b" / "call.html").read_text(encoding="utf-8")
    backend = (ROOT / "deploy" / "modal-avatar" / "flashhead_modal_dev.py").read_text(encoding="utf-8")
    for marker in ("app-flashhead-portrait-v1", "source_crop", "fit: 'fill'"):
        if marker not in call_html:
            raise AssertionError(f"B2B render contract missing {marker!r}")
    for marker in ("app-flashhead-portrait-v1", '"y": 140', '"height": 1440', '"fit": "fill"'):
        if marker not in backend:
            raise AssertionError(f"backend render contract missing {marker!r}")
    print("render contract markers: ok")


if __name__ == "__main__":
    main()
