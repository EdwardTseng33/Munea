#!/usr/bin/env python3
"""Build the two native-768 B2B Demo condition images without touching App."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image

from demo_profile import DEMO_RENDER_CONTRACTS, SOURCE_NAMES, TARGET_NAMES


DEFAULT_TARGET_DIR = "/workspace/munea-demo/assets-720p"


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
    parser.add_argument("--target-dir", default=DEFAULT_TARGET_DIR)
    args = parser.parse_args()

    target_dir = Path(args.target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"profile": None, "assets": {}}
    for character, source_name in SOURCE_NAMES.items():
        portrait = load(args.source, source_name)
        contract = DEMO_RENDER_CONTRACTS[character]
        canvas = contract["canvas"]
        expected_canvas = (canvas["width"], canvas["height"])
        if portrait.size != expected_canvas:
            raise SystemExit(f"{source_name}: expected {expected_canvas}, got {portrait.size}")
        crop = contract["source_crop"]
        model = contract["model_input"]
        if crop["width"] != crop["height"] or model["width"] != model["height"]:
            raise SystemExit(f"{character}: Demo 720P profile must stay square")
        box = (
            crop["x"],
            crop["y"],
            crop["x"] + crop["width"],
            crop["y"] + crop["height"],
        )
        # One resample only: 1080-square source -> 768-square model condition.
        # The old path squeezed a 1080x1440 portrait through 512x512 and then
        # stretched it back in CSS, which reduced effective detail below App 640.
        built = portrait.crop(box).resize(
            (model["width"], model["height"]), Image.Resampling.LANCZOS
        )
        target = target_dir / TARGET_NAMES[character]
        built.save(target, format="PNG")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest["profile"] = contract["version"]
        manifest["assets"][character] = {
            "source": f"bg-{source_name}.png",
            "source_crop": crop,
            "model_input": model,
            "target": target.name,
            "sha256": digest,
        }
        print(
            f"built {character}: {target} {model['width']}x{model['height']} "
            f"sha256={digest[:12]}"
        )
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
