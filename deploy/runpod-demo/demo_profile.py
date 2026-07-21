"""Single source of truth for the isolated B2B Demo 720P render profile.

The production App keeps using the shared ``a05/a06`` contracts. This module
is imported only by the RunPod Demo launcher and asset builder, so the Demo can
iterate on its own ``a05d/a06d`` condition images without changing App assets
or the production FlashHead selector.
"""

from __future__ import annotations


CANVAS = {"width": 1080, "height": 1920}
MODEL_INPUT = {"width": 768, "height": 768}
PROFILE_VERSION = "demo-flashhead-square-768-v2"

# Use the same proven square composition principle as the App, but keep
# separate character codes, files and runtime paths for the Demo R&D lane.
DEMO_RENDER_CONTRACTS = {
    "a05d": {
        "version": PROFILE_VERSION,
        "lane": "demo",
        "canvas": CANVAS,
        "source_crop": {"x": 0, "y": 190, "width": 1080, "height": 1080},
        "model_input": MODEL_INPUT,
        "fit": "fill",
    },
    "a06d": {
        "version": PROFILE_VERSION,
        "lane": "demo",
        "canvas": CANVAS,
        "source_crop": {"x": 0, "y": 209, "width": 1080, "height": 1080},
        "model_input": MODEL_INPUT,
        "fit": "fill",
    },
}

SOURCE_NAMES = {"a05d": "a05", "a06d": "a06"}
TARGET_NAMES = {
    "a05d": "char-a05B-demo-square-768.png",
    "a06d": "char-a06B-demo-square-768.png",
}
