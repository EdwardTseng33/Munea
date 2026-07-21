#!/usr/bin/env python3
"""在臉機器上重建條件圖——直接跟正式 App 的立繪對答案，不靠人工搬檔案。

為什麼要有這支：
2026-07-20 之前，台灣主卡／美國備援／Modal 實驗機的條件圖是各自人工放上去的，
三台切法不一樣。主卡一忙、通話被轉去備援，寧寧的臉就換個樣子（頭被壓扁、領口疊影）。
現在改成每台機器都從 App 正在出貨的那張立繪、照同一份貼合約定自己切一次——不可能再漂。

用法（在臉機器上）：
    python3 sync-face-assets.py            # 抓正式線立繪、重建四張條件圖
    python3 sync-face-assets.py --dry-run  # 只比對、不覆蓋
    python3 sync-face-assets.py --source https://.../  # 換來源（測試機用）

跑完要讓引擎吃到新圖，記得重開一次：bash restart-flashhead.sh
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import urllib.request
from pathlib import Path

from PIL import Image

DEFAULT_SOURCE = "https://munea-brain-491603544409.asia-east1.run.app/flashhead/"

# 與 flashhead_server.py / flashhead_modal_dev.py 同一份表。
# scripts/test-avatar-render-contract.py 會比對三處，任一處漂掉就擋下。
_PROD_SQUARE = {"width": 640, "height": 640}
_DEMO_FILL = {"width": 512, "height": 512}
_CANVAS = {"width": 1080, "height": 1920}
AVATAR_RENDER_CONTRACTS = {
    "a05": {"version": "app-flashhead-square-v1", "lane": "prod", "canvas": _CANVAS,
            "source_crop": {"x": 0, "y": 190, "width": 1080, "height": 1080},
            "model_input": _PROD_SQUARE, "fit": "fill"},
    "a06": {"version": "app-flashhead-square-v1", "lane": "prod", "canvas": _CANVAS,
            "source_crop": {"x": 0, "y": 209, "width": 1080, "height": 1080},
            "model_input": _PROD_SQUARE, "fit": "fill"},
    "a05d": {"version": "demo-flashhead-portrait-v1", "lane": "demo", "canvas": _CANVAS,
             "source_crop": {"x": 0, "y": 140, "width": 1080, "height": 1440},
             "model_input": _DEMO_FILL, "fit": "fill"},
    "a06d": {"version": "demo-flashhead-portrait-v1", "lane": "demo", "canvas": _CANVAS,
             "source_crop": {"x": 0, "y": 140, "width": 1080, "height": 1440},
             "model_input": _DEMO_FILL, "fit": "fill"},
}
# 角色代號 → 立繪檔名 / 引擎讀取的路徑（與 CHAR_SRC 的預設值一致）。
BACKGROUND_OF = {"a05": "a05", "a06": "a06", "a05d": "a05", "a06d": "a06"}
TARGET_OF = {
    "a05": "/root/char-a05B.png",
    "a06": "/root/char-a06B.png",
    "a05d": "/root/char-a05B-demo.png",
    "a06d": "/root/char-a06B-demo.png",
}


def load_portrait(source: str, name: str) -> Image.Image:
    if source.startswith(("http://", "https://")):
        url = source.rstrip("/") + f"/bg-{name}.png"
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
        print(f"  抓 {url} （{len(raw)} bytes）")
        return Image.open(io.BytesIO(raw)).convert("RGB")
    path = Path(source) / f"bg-{name}.png"
    print(f"  讀 {path}")
    return Image.open(path).convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.environ.get("MUNEA_FH_PORTRAIT_SOURCE", DEFAULT_SOURCE))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target-dir", default="/root",
                        help="條件圖要放哪（預設 /root，跟 CHAR_SRC 對齊）")
    parser.add_argument("--lane", choices=("all", "prod", "demo"), default="all",
                        help="只重建指定服務線的條件圖")
    parser.add_argument("--frame-size", type=int, choices=(512, 640, 768),
                        help="依這個服務程序的實際推論尺寸輸出條件圖")
    args = parser.parse_args()

    if args.frame_size and args.lane == "all":
        parser.error("--frame-size 需要同時指定 --lane prod 或 --lane demo")

    portraits: dict[str, Image.Image] = {}
    changed, checked = 0, 0
    for char, contract in sorted(AVATAR_RENDER_CONTRACTS.items()):
        if args.lane != "all" and contract["lane"] != args.lane:
            continue
        name = BACKGROUND_OF[char]
        if name not in portraits:
            print(f"[{name}] 取立繪")
            portraits[name] = load_portrait(args.source, name)
        portrait = portraits[name]
        canvas = (contract["canvas"]["width"], contract["canvas"]["height"])
        if portrait.size != canvas:
            print(f"✗ {name}: 立繪應為 {canvas}、實際 {portrait.size}——來源不對，停手", file=sys.stderr)
            return 1

        crop = contract["source_crop"]
        model = contract["model_input"]
        if args.frame_size:
            model = {"width": args.frame_size, "height": args.frame_size}
        box = (crop["x"], crop["y"], crop["x"] + crop["width"], crop["y"] + crop["height"])
        built = portrait.crop(box).resize((model["width"], model["height"]), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        built.save(buf, format="PNG")
        payload = buf.getvalue()

        target = Path(args.target_dir) / Path(TARGET_OF[char]).name
        checked += 1
        current = target.read_bytes() if target.exists() else b""
        same = hashlib.sha256(current).hexdigest() == hashlib.sha256(payload).hexdigest()
        lane = contract["lane"]
        if same:
            print(f"  = {char} [{lane}] {target} 已經是對的")
            continue
        changed += 1
        if args.dry_run:
            print(f"  ! {char} [{lane}] {target} 需要更新（--dry-run，沒動）")
            continue
        target.write_bytes(payload)
        print(f"  ✓ {char} [{lane}] {target} 已重建"
              f"（切 y={crop['y']} {crop['width']}x{crop['height']} → {model['width']}x{model['height']}）")

    print(f"\n檢查 {checked} 張、{'需要更新' if args.dry_run else '更新'} {changed} 張")
    if changed and not args.dry_run:
        print("引擎還在用舊圖，記得重開一次：bash restart-flashhead.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
