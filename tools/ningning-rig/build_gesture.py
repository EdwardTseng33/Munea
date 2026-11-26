# -*- coding: utf-8 -*-
"""寧寧手勢貼片（2026-11-21 草稿）：從定稿底圖「只改手臂與手」的修圖，切出「身體＋手臂」那一層的全畫布透明貼片。
頭（頭髮＋臉＋脖子上半）整塊排除——不管修圖有沒有偷動到臉，貼片在頭的範圍一律透明，臉的嘴眼貼片照樣疊在上面。
只收「成片」的改動（手臂、手、被手臂擋住後補上的衣服）；零星的雜訊（修圖時衣服紋路微微不同）不收，換手勢時才不會整件衣服閃一下。

用法：python build_gesture.py <底圖 base.png> <修圖資料夾> <輸出資料夾>
  修圖資料夾裡 f-<名稱>.png → 輸出 gesture-<名稱>.webp
驗收：印出每張貼片「頭的範圍內改到的像素」（要 0）與覆蓋面積。"""
import sys, os, glob
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

SRC, PARTS, OUT = sys.argv[1:4]
base = np.asarray(Image.open(SRC).convert('RGB')).astype(float)
H, W = base.shape[:2]
BG = np.array([186, 221, 214], float)


def head_mask():
    # 頭＝臉中心的大橢圓（頭髮最外圈到下巴、含垂下的細髮絲）；手勢貼片在這裡面一律不准動
    m = Image.new('L', (W, H), 0)
    ImageDraw.Draw(m).ellipse((780 - 370, 990 - 450, 780 + 370, 990 + 450), fill=255)
    return np.asarray(m) > 0


HEAD = head_mask()
os.makedirs(OUT, exist_ok=True)
for src in sorted(glob.glob(os.path.join(PARTS, 'f-*.png'))):
    name = os.path.basename(src)[2:-4]
    v = np.asarray(Image.open(src).convert('RGB')).astype(float)
    # 整體色偏：用背景（離人很遠的上方角落）對回底圖
    calib = np.zeros((H, W), bool); calib[40:500, 40:300] = True; calib[40:500, W - 300:W - 40] = True
    off = (v[calib] - base[calib]).mean(axis=0)
    v -= off
    d = np.abs(v - base).sum(axis=2)
    core = (d > 36) & ~HEAD
    core = ndi.binary_opening(core, structure=np.ones((5, 5)))
    lab, n = ndi.label(core)
    if n:
        sizes = ndi.sum(core, lab, range(1, n + 1))
        keep = np.isin(lab, 1 + np.where(sizes >= 4000)[0])
    else:
        keep = core
    keep = ndi.binary_fill_holes(ndi.binary_closing(keep, structure=np.ones((15, 15))))
    keep = ndi.binary_dilation(keep, iterations=5) & ~HEAD
    a = np.asarray(Image.fromarray((keep * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))).astype(float) / 255
    a[HEAD] = 0
    rgb = np.clip(v, 0, 255); rgb[a == 0] = 0
    im = Image.fromarray(np.dstack([rgb, a * 255]).astype(np.uint8), 'RGBA')
    out = os.path.join(OUT, f'gesture-{name}.webp')
    im.save(out, 'WEBP', quality=90, method=6)
    head_touched = int((a[HEAD] > 0).sum())
    print(f'gesture-{name}.webp: 頭的範圍內改到 {head_touched} 像素｜覆蓋 {int((a > 0.5).sum())} 像素｜{os.path.getsize(out) // 1024} KB｜色偏 {np.round(off, 1)}')
