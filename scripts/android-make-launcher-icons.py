# -*- coding: utf-8 -*-
"""Android 桌面圖示：從 App 官方圖示原檔產生各密度的 launcher icon（2026-10-29）。

為什麼要這支：Android 殼（#617）一直沿用 Capacitor 範本的藍色 X 圖示。
iOS 已有官方圖示（web/icons/peining-app-icon-source-preserved-1024.png，奶油底＋橘水滴＋青綠漣漪），
Android 直接沿用同一張圖——不重畫、不改色，只是照 Android 的規格重新排版：

- Android 8+ 是「自適應圖示」：背景一層純色＋前景一層透明圖，系統再裁成圓形／圓角方形／水滴形。
  前景畫布 108dp，只有中間直徑 66dp 的圓保證看得到 → 水滴＋漣漪要縮進這個圓裡。
- 背景色＝原圖奶油底實測色（#FEF5EB）；前景把奶油底摳成透明，只留水滴＋漣漪。
- Android 7 以下用固定圖（ic_launcher.png 圓角方形、ic_launcher_round.png 圓形）。

用法（在程式庫根目錄）：python scripts/android-make-launcher-icons.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web/icons/peining-app-icon-source-preserved-1024.png"
RES = ROOT / "android/app/src/main/res"

BG = (254, 245, 235)  # 原圖奶油底實測（10 點取樣 ±2）
BG_HEX = "#FEF5EB"
# 水滴＋漣漪在原圖的範圍（實測 x 136–883、y 204–829），四周各多留一點邊
ART_BOX = (116, 184, 904, 850)

DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def artwork_rgba() -> Image.Image:
    """把奶油底摳成透明：跟底色差越多越不透明（柔邊，不會鋸齒）。"""
    im = Image.open(SRC).convert("RGB").crop(ART_BOX)
    a = np.asarray(im).astype(np.int32)
    diff = np.abs(a - np.array(BG)).sum(axis=2)
    alpha = np.clip((diff - 6) * 255 / 40, 0, 255).astype(np.uint8)
    rgba = np.dstack([a.astype(np.uint8), alpha])
    return Image.fromarray(rgba, "RGBA")


def place(canvas_px: int, art: Image.Image, art_width_ratio: float) -> Image.Image:
    """把作品等比縮到畫布寬的 art_width_ratio，置中（水滴尖到漣漪底的視覺中心）。"""
    w = round(canvas_px * art_width_ratio)
    h = round(art.height * w / art.width)
    scaled = art.resize((w, h), Image.LANCZOS)
    out = Image.new("RGBA", (canvas_px, canvas_px), (0, 0, 0, 0))
    out.alpha_composite(scaled, ((canvas_px - w) // 2, (canvas_px - h) // 2))
    return out


def main() -> None:
    art = artwork_rgba()
    for name, scale in DENSITIES.items():
        folder = RES / f"mipmap-{name}"
        # 自適應前景：108dp 畫布，作品寬 56dp（安全圓 66dp 內，漣漪左右兩端離圓邊還有餘裕）
        fg_px = round(108 * scale)
        place(fg_px, art, 56 / 108).save(folder / "ic_launcher_foreground.png", optimize=True)

        # Android 7 以下的固定圖：48dp
        px = round(48 * scale)
        big = px * 4  # 先畫大再縮，邊緣才平滑
        square = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(square).rounded_rectangle([0, 0, big - 1, big - 1], radius=round(big * 0.22), fill=BG + (255,))
        square.alpha_composite(place(big, art, 0.74))
        square.resize((px, px), Image.LANCZOS).save(folder / "ic_launcher.png", optimize=True)

        rnd = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(rnd).ellipse([0, 0, big - 1, big - 1], fill=BG + (255,))
        rnd.alpha_composite(place(big, art, 0.66))
        rnd.resize((px, px), Image.LANCZOS).save(folder / "ic_launcher_round.png", optimize=True)
        print(f"{name}: foreground {fg_px}px, legacy {px}px")

    bg_xml = RES / "values/ic_launcher_background.xml"
    bg_xml.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        f'    <color name="ic_launcher_background">{BG_HEX}</color>\n</resources>\n',
        encoding="utf-8",
        newline="\n",
    )
    print("background", BG_HEX)


if __name__ == "__main__":
    main()
