#!/usr/bin/env python3
"""Build the two B2B Demo condition images without writing App assets."""

from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

from PIL import Image


SOURCE_CROP = (0, 140, 1080, 1580)
SOURCE_NAMES = {"a05d": "a05", "a06d": "a06"}
TARGET_NAMES = {"a05d": "char-a05B-demo.png", "a06d": "char-a06B-demo.png"}


def load(source: str, name: str) -> Image.Image:
    if source.startswith(("http://", "https://")):
        url = source.rstrip("/") + f"/bg-{name}.png"
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read()
        return Image.open(io.BytesIO(payload)).convert("RGB")
    return Image.open(Path(source) / f"bg-{name}.png").convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default="https://munea-brain-491603544409.asia-east1.run.app/flashhead/",
    )
    parser.add_argument("--target-dir", default="/workspace/munea-demo/assets")
    args = parser.parse_args()

    target_dir = Path(args.target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for character, source_name in SOURCE_NAMES.items():
        portrait = load(args.source, source_name)
        if portrait.size != (1080, 1920):
            raise SystemExit(f"{source_name}: expected 1080x1920, got {portrait.size}")
        # FlashHead accepts this Demo-only 3:4 crop as a 512 square condition image.
        built = portrait.crop(SOURCE_CROP).resize((512, 512), Image.Resampling.LANCZOS)
        target = target_dir / TARGET_NAMES[character]
        built.save(target, format="PNG")
        print(f"built {character}: {target} 512x512")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
