# -*- coding: utf-8 -*-
"""聊聊人物呼吸感 · 人物層產圖工具（2026-07-16 方案 B 分層呼吸）

把 web/flashhead/bg-aXX.png（1080x1920 全身立繪含背景）裁出「人物去背層」
person-aXX.png，尺寸版位與底圖 1:1 對齊。前端把人物層＋活臉焊同一組做
細微呼吸；底圖整張留著當背景板（呼吸只放大不縮小，底圖永遠被蓋住，
不需要另補乾淨背景）。

用法：python scripts/build_flashhead_person_layer.py
"""
import io
import os
import sys

from PIL import Image, ImageFilter
from rembg import remove, new_session

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FH_DIR = os.path.join(ROOT, "web", "flashhead")
CHARS = ["a05", "a06"]

# u2net_human_seg：人像專用模型，髮絲邊比通用版乾淨
session = new_session("u2net_human_seg")

for char in CHARS:
    src_path = os.path.join(FH_DIR, f"bg-{char}.png")
    out_path = os.path.join(FH_DIR, f"person-{char}.png")
    src = Image.open(src_path).convert("RGB")

    cut = remove(src, session=session)  # RGBA，同尺寸

    # 邊緣處理（2026-07-16 Edward 抓到呼吸時輪廓出現深色描邊後改）：
    # ① 剪裁往內收 2px（MinFilter 5）——丟掉輪廓最外圈「人＋背景混色」的髒邊，
    #    起伏時就不會有深邊滑到亮背景上形成描邊；露出的縫由底下同源原圖天然補上
    # ② 再柔邊 1.5px：過渡自然、不見硬切
    r, g, b, a = cut.split()
    a = a.filter(ImageFilter.MinFilter(5))
    a = a.filter(ImageFilter.GaussianBlur(1.5))
    cut = Image.merge("RGBA", (r, g, b, a))

    cut.save(out_path, optimize=True)
    print(f"{char}: {src.size} -> {out_path} ({os.path.getsize(out_path)//1024} KB)")

# QA 檢查圖：人物層鋪在純色底上，人眼快掃去背品質（存 scratchpad、不進程式庫）
qa_dir = sys.argv[1] if len(sys.argv) > 1 else None
if qa_dir:
    for char in CHARS:
        cut = Image.open(os.path.join(FH_DIR, f"person-{char}.png"))
        board = Image.new("RGB", cut.size, (30, 200, 60))
        board.paste(cut, (0, 0), cut)
        board.thumbnail((540, 960))
        board.save(os.path.join(qa_dir, f"qa-person-{char}.png"))
        print(f"QA sheet: qa-person-{char}.png")
