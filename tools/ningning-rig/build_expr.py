# -*- coding: utf-8 -*-
"""寧寧表情零件（2026-11-21 草稿）：從定稿底圖的「只改嘴／只改眼／只改眉」修圖，切出全畫布透明貼片。
做法跟 build_rig.py 的 part() 同一套：先把修圖整體色偏對回底圖，再只留「跟底圖不一樣」的地方，
而且只准落在指定的橢圓範圍裡——範圍外的像素一律透明，疊上去不會改到別處。
關心的眉毛也是修圖（只改眉頭角度）；11/21 試過把底圖眉毛用程式轉角度，邊緣毛糙，不用。

用法：python build_expr.py <底圖 base.png> <修圖資料夾> <輸出資料夾> rig-updo.json
  修圖資料夾裡要有 f-m-ee / f-m-oo / f-m-oh / f-m-smile / f-e-smile / f-e-soft / f-b-concern .png
驗收：每張貼片印出「範圍外改到的像素數」（要 0）與「疊回去跟修圖差多少」。"""
import sys, json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

SRC, PARTS, OUT, CFG = sys.argv[1:5]
cfg = json.load(open(CFG, encoding='utf-8'))
os.makedirs(OUT, exist_ok=True)
base = np.asarray(Image.open(SRC).convert('RGB')).astype(float)
H, W = base.shape[:2]
skin = np.array(cfg['skin'], float)


def ell(ells, scale=1.0):
    m = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(m)
    for cx, cy, rx, ry in ells:
        d.ellipse((cx - rx * scale, cy - ry * scale, cx + rx * scale, cy + ry * scale), fill=255)
    return np.asarray(m) > 0


def save(rgb, alpha, name):
    a = np.clip(alpha, 0, 1)
    rgb = np.clip(rgb, 0, 255).copy()
    rgb[a == 0] = 0
    im = Image.fromarray(np.dstack([rgb, a * 255]).astype(np.uint8), 'RGBA')
    im.save(os.path.join(OUT, name), 'WEBP', lossless=True, method=6, quality=100)
    return a


def report(name, rgb, a, zone, ref=None):
    comp = base * (1 - a[..., None]) + np.clip(rgb, 0, 255) * a[..., None]
    outside = int(((np.abs(comp - base).sum(axis=2) > 0) & ~zone).sum())
    msg = f'{name}: 範圍外改到 {outside} 像素'
    if ref is not None:
        d = np.abs(comp - ref).sum(axis=2)
        msg += f'｜範圍內跟修圖差>40 的像素 {int(((d > 40) & zone).sum())}／{int(zone.sum())}'
    print(msg)


def part(src, ells, name, scale_zone=1.0, lid=False, grow=5, soft=2, only_dark=False):
    v = np.asarray(Image.open(src).convert('RGB')).astype(float)
    region = ell(ells, 1.6)
    d = np.abs(v - base).sum(axis=2)
    calib = region & (d < 45)
    off = (v[calib] - base[calib]).mean(axis=0)
    v -= off
    inner = ell(ells, scale_zone)
    if lid:
        lidpx = inner & (v.mean(axis=2) > skin.mean() - 70) & (np.abs(v - skin).sum(axis=2) < 120)
        v[lidpx] = skin
    d = np.abs(v - base).sum(axis=2)
    core = inner & (d > 40)
    if only_dark:
        # 眉毛：只收「新眉毛」與「舊眉毛要蓋掉的地方」；修圖順手多畫的淡淡皺紋（中間調）不收
        dk = (v.mean(axis=2) < 110) | (base.mean(axis=2) < 110)
        core &= ndi.binary_dilation(dk, iterations=3)
    mi = Image.fromarray((core * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(grow)).filter(ImageFilter.GaussianBlur(soft))
    a = np.asarray(mi).astype(float) / 255 * inner
    a = save(v, a, name)
    report(name, v, a, inner, v)
    return off


mouth = cfg['mouth']
wide_mouth = [[cx, cy, rx * 1.04, ry * 1.1] for cx, cy, rx, ry in mouth]    # 嘴角上揚一點點；修圖多畫的酒窩不收（只收得到一邊、會不對稱）
eyes = [[cx, cy, rx * 1.08, ry * 1.25] for cx, cy, rx, ry in cfg['eyes']]      # 柔和眼多一條眼皮線
for k in ('ee', 'oo', 'oh'):
    part(f'{PARTS}/f-m-{k}.png', mouth, f'mouth-{k}.webp', grow=9)
part(f'{PARTS}/f-m-smile.png', wide_mouth, 'mouth-smile.webp', grow=9)
part(f'{PARTS}/f-e-smile.png', eyes, 'eyes-smile.webp', lid=True, grow=9, soft=1)
part(f'{PARTS}/f-e-soft.png', eyes, 'eyes-soft.webp', grow=7, soft=1)

# ---- 關心的眉毛：同一套修圖（只把眉頭抬高），範圍只到眉毛上下，不收額頭 ----
brows = [[cx, cy - 6, rx * 1.2, ry * 1.8] for cx, cy, rx, ry in cfg['brows']]
part(f'{PARTS}/f-b-concern.png', brows, 'brows-concern.webp', grow=7, soft=1, only_dark=True)

# ---- 檢查圖：底圖＋每張貼片，臉部特寫並排 ----
box = (560, 900, 1010, 1340)
names = ['mouth-ee', 'mouth-oo', 'mouth-oh', 'mouth-smile', 'eyes-smile', 'eyes-soft', 'brows-concern']
tiles = [Image.fromarray(base.astype(np.uint8)).crop(box)]
b_im = Image.fromarray(base.astype(np.uint8)).convert('RGBA')
for k in names:
    p = Image.open(os.path.join(OUT, k + '.webp'))
    tiles.append(Image.alpha_composite(b_im, p).convert('RGB').crop(box))
tw, th = tiles[0].size
sheet = Image.new('RGB', (tw * 4, th * 2), 'white')
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % 4) * tw, (i // 4) * th))
sheet.save(os.path.join(PARTS, '_expr-check.jpg'), quality=88)
print('check sheet', os.path.join(PARTS, '_expr-check.jpg'))
