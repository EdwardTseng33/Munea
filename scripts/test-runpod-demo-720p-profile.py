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


def psnr(actual: np.ndarray, reference: np.ndarray) -> float:
    error = float(np.mean((actual.astype(np.float32) - reference.astype(np.float32)) ** 2))
    if error == 0:
        return float("inf")
    return float(20 * np.log10(255 / np.sqrt(error)))


def edge_retention(actual: np.ndarray, reference: np.ndarray) -> float:
    def energy(image: np.ndarray) -> float:
        gray = image.astype(np.float32).mean(axis=2)
        horizontal = np.abs(np.diff(gray, axis=1)).mean()
        vertical = np.abs(np.diff(gray, axis=0)).mean()
        return float(horizontal + vertical)

    return energy(actual) / energy(reference)


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
                square_reference = source.crop(box)
                expected = square_reference.resize((768, 768), Image.Resampling.LANCZOS)
                legacy_reference = source.crop((0, 140, 1080, 1580))
                legacy_display = legacy_reference.resize(
                    (512, 512), Image.Resampling.LANCZOS
                ).resize((1080, 1440), Image.Resampling.LANCZOS)
            with Image.open(target_path).convert("RGB") as actual:
                assert actual.size == (768, 768)
                mae = float(
                    np.abs(
                        np.asarray(expected, dtype=np.int16)
                        - np.asarray(actual, dtype=np.int16)
                    ).mean()
                )
                native_display = actual.resize((1080, 1080), Image.Resampling.LANCZOS)
            assert mae == 0.0, f"{char}: generated condition image drifted (MAE={mae})"
            legacy_psnr = psnr(np.asarray(legacy_display), np.asarray(legacy_reference))
            native_psnr = psnr(np.asarray(native_display), np.asarray(square_reference))
            legacy_edges = edge_retention(
                np.asarray(legacy_display), np.asarray(legacy_reference)
            )
            native_edges = edge_retention(
                np.asarray(native_display), np.asarray(square_reference)
            )
            assert native_psnr >= legacy_psnr + 5.0
            assert native_edges >= legacy_edges + 0.20
            print(
                f"{char}: native 768 square asset PASS (MAE={mae:.3f}, "
                f"PSNR {legacy_psnr:.2f}->{native_psnr:.2f}dB, "
                f"edge retention {legacy_edges:.3f}->{native_edges:.3f})"
            )

        assert (target_dir / "manifest.json").is_file()
    print("Demo 720P profile is isolated and deterministic")


if __name__ == "__main__":
    main()
