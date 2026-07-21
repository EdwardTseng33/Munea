"""Verify the Demo 720P profile without importing Torch or touching App files."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "deploy" / "runpod-demo"


def load_profile():
    spec = importlib.util.spec_from_file_location("demo_profile", DEMO_DIR / "demo_profile.py")
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load Demo profile")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    profile = load_profile()
    contracts = profile.DEMO_RENDER_CONTRACTS
    assert set(contracts) == {"a05d", "a06d"}
    for contract in contracts.values():
        crop = contract["source_crop"]
        model = contract["model_input"]
        assert contract["lane"] == "demo"
        assert contract["version"] == "demo-flashhead-square-768-v2"
        assert crop["width"] == crop["height"] == 1080
        assert model == {"width": 768, "height": 768}
        assert contract["fit"] == "fill"

    with tempfile.TemporaryDirectory(prefix="munea-demo-720p-") as temp:
        target_dir = Path(temp)
        subprocess.run(
            [
                sys.executable,
                str(DEMO_DIR / "build-demo-assets.py"),
                "--source",
                str(ROOT / "munea-b2b" / "flashhead"),
                "--target-dir",
                str(target_dir),
            ],
            check=True,
        )
        for char, contract in contracts.items():
            source_name = profile.SOURCE_NAMES[char]
            source_path = ROOT / "munea-b2b" / "flashhead" / f"bg-{source_name}.png"
            target_path = target_dir / profile.TARGET_NAMES[char]
            crop = contract["source_crop"]
            box = (
                crop["x"],
                crop["y"],
                crop["x"] + crop["width"],
                crop["y"] + crop["height"],
            )
            with Image.open(source_path).convert("RGB") as source:
                expected = source.crop(box).resize((768, 768), Image.Resampling.LANCZOS)
            with Image.open(target_path).convert("RGB") as actual:
                assert actual.size == (768, 768)
                mae = float(
                    np.abs(
                        np.asarray(expected, dtype=np.int16)
                        - np.asarray(actual, dtype=np.int16)
                    ).mean()
                )
            assert mae == 0.0, f"{char}: generated condition image drifted (MAE={mae})"
            print(f"{char}: native 768 square asset PASS (MAE={mae:.3f})")

        assert (target_dir / "manifest.json").is_file()
    print("Demo 720P profile is isolated and deterministic")


if __name__ == "__main__":
    main()
