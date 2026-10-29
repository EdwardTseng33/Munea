# -*- coding: utf-8 -*-
"""轉頭角度版素材：一張正面全身圖（body）＋各角度「頭」圖層＋各角度嘴／眼貼片。
頭不做任何變形，轉頭就是換成鄰近角度的圖，所以每個角度都要有自己的嘴和眼。
用法：python build_poses.py <l2 資料夾> <輸出資料夾>
  <l2>/base.png, f-half.png, f-open.png, f-blink.png（正面）
  <l2>/poses/pose-L1.png … 與 f-L1-half.png / f-L1-open.png / f-L1-blink.png（各角度）
驗收：每個角度「正面全身圖 ＋ 該角度頭圖層」疊起來要跟該角度原圖一樣（印出 off>12 的像素數）。"""
import os, sys
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
POSES = ['L2', 'L1', 'R1', 'R2']
BG = np.array([186, 221, 214], float)
SKIN = np.array([246, 183, 150], float)
NECK_CUT = 1750                      # 領口以下一律屬身體
MOUTH_ZONE = (560, 1150, 1010, 1430)  # x0, y0, x1, y1：嘴貼片只准落在這裡面（各角度都夠用）
EYE_ZONE = (500, 930, 1070, 1130)

base = np.asarray(Image.open(f'{SRC}/base.png').convert('RGB')).astype(float)
H, W = base.shape[:2]


def rect(z):
    m = np.zeros((H, W), bool)
    m[z[1]:z[3], z[0]:z[2]] = True
    return m


def save_rgba(rgb, alpha, path, lossless=True):
    a = np.clip(alpha, 0, 1)
    rgb = np.clip(rgb, 0, 255).copy()
    rgb[a == 0] = 0
    im = Image.fromarray(np.dstack([rgb, a * 255]).astype(np.uint8), 'RGBA')
    if lossless:
        im.save(path, 'WEBP', lossless=True, method=6, quality=100)
    else:
        im.save(path, 'WEBP', quality=92, method=6)


def part(b, edit_path, zone, out, lid=False):
    """從「只改嘴／只改眼」的修圖裡，把真的有改到的像素裁成貼片（先校正整張的色偏）。"""
    v = np.asarray(Image.open(edit_path).convert('RGB')).astype(float)
    region = rect(zone)
    d = np.abs(v - b).sum(axis=2)
    calib = region & (d < 45)
    off = (v[calib] - b[calib]).mean(axis=0)
    v = v - off
    d = np.abs(v - b).sum(axis=2)
    core = ndi.binary_opening(region & (d > 40), structure=np.ones((3, 3)))
    lab, n = ndi.label(core)
    if n:
        sz = ndi.sum(core, lab, range(1, n + 1))
        core = np.isin(lab, 1 + np.where(sz > 150)[0])
    if lid:
        # 閉眼：它會把眼皮塗深一階像眼影，回填成皮膚色
        inner = ndi.binary_dilation(core, iterations=12) & region
        lum = v.mean(axis=2)
        lidpx = inner & (lum > SKIN.mean() - 70) & (np.abs(v - SKIN).sum(axis=2) < 120) & (d > 20)
        v[lidpx] = SKIN
        d = np.abs(v - b).sum(axis=2)
        core = inner & (d > 40)
    mi = Image.fromarray((core * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.5))
    a = np.asarray(mi).astype(float) / 255 * region
    save_rgba(v, a, out)
    return int(core.sum()), off.round(1)


def head_mask(img):
    """頭＝頭髮（含臉旁細髮絲）＋臉，填滿中間；領口以下只留頭髮。"""
    lum = img.mean(axis=2)
    dark = lum < 90
    lab, n = ndi.label(dark)
    sz = ndi.sum(dark, lab, range(1, n + 1))
    hair = np.zeros((H, W), bool)
    for i in range(n):
        if sz[i] < 20:
            continue
        comp = lab == i + 1
        if np.where(comp)[0].mean() > NECK_CUT:
            continue
        hair |= comp
    near_skin = np.abs(img - SKIN).sum(axis=2) < 70
    cand = near_skin.copy()
    cand[1470:, :] = False
    lab2, n2 = ndi.label(cand)
    # 臉＝畫面中央那塊最大的皮膚色區（轉頭後固定點可能落在眼睛上，不能用單一點當種子）
    center_box = rect((500, 700, 1070, 1470))
    best, best_sz = 0, 0
    for i in range(1, n2 + 1):
        comp = lab2 == i
        inside = (comp & center_box).sum()
        if inside > best_sz:
            best, best_sz = i, inside
    face = lab2 == best
    head = ndi.binary_fill_holes(hair | face)
    head[1470:, :] &= hair[1470:, :]
    # 大塊被髮絲圍住的背景不算頭
    encl = head & ~hair & ~face & (np.abs(img - BG).sum(axis=2) < 40)
    lab3, n3 = ndi.label(encl)
    if n3:
        s3 = ndi.sum(encl, lab3, range(1, n3 + 1))
        head &= ~np.isin(lab3, 1 + np.where(s3 > 2500)[0])
    ring = ndi.binary_dilation(head, iterations=3) & ~head
    head |= ring & (np.abs(img - BG).sum(axis=2) > 8)
    return head


# 正面：全身圖就是底
Image.fromarray(base.astype(np.uint8)).save(f'{OUT}/body.webp', 'WEBP', quality=90, method=6)
print('C parts', part(base, f'{SRC}/f-half.png', MOUTH_ZONE, f'{OUT}/mouth-half-C.webp'),
      part(base, f'{SRC}/f-open.png', MOUTH_ZONE, f'{OUT}/mouth-open-C.webp'),
      part(base, f'{SRC}/f-blink.png', EYE_ZONE, f'{OUT}/eyes-closed-C.webp', lid=True))

rows = np.arange(H)[:, None]
for p in POSES:
    pose = np.asarray(Image.open(f'{SRC}/poses/pose-{p}.png').convert('RGB')).astype(float)
    # 每張角度圖整體色調都會漂一點：用純身體區（領口以下）算出偏移、整張扣回，身體才跟正面圖對得上
    off0 = np.median((pose - base)[1900:], axis=(0, 1))
    pose = np.clip(pose - off0, 0, 255)
    # 領口以上凡是跟正面圖不一樣的都算頭（轉頭後嘴巴貼著下巴陰影、不再被皮膚包住，光靠輪廓會漏掉）
    changed = ndi.binary_dilation(np.abs(pose - base).sum(axis=2) > 40, iterations=2) & (rows < NECK_CUT)
    head = head_mask(pose) | changed
    print(p, 'color offset', off0.round(1), 'outside-head px off>40:', int(((np.abs(pose - base).sum(axis=2) > 40) & ~head).sum()))
    save_rgba(pose, head.astype(float), f'{OUT}/head-{p}.webp', lossless=False)
    comp = base.copy()
    comp[head] = pose[head]
    off = (np.abs(comp - pose).sum(axis=2) > 12).sum()
    ys, xs = np.where(head)
    print(p, 'head bbox', xs.min(), xs.max(), ys.min(), ys.max(), 'px', int(head.sum()), 'compose off>12:', int(off),
          'parts', part(pose, f'{SRC}/poses/f-{p}-half.png', MOUTH_ZONE, f'{OUT}/mouth-half-{p}.webp'),
          part(pose, f'{SRC}/poses/f-{p}-open.png', MOUTH_ZONE, f'{OUT}/mouth-open-{p}.webp'),
          part(pose, f'{SRC}/poses/f-{p}-blink.png', EYE_ZONE, f'{OUT}/eyes-closed-{p}.webp', lid=True))

print('total KB', sum(os.path.getsize(f'{OUT}/{f}') for f in os.listdir(OUT) if f.endswith('.webp')) // 1024)

bodyI = Image.open(f'{OUT}/body.webp').convert('RGBA')
def comp(p):
    c = bodyI.copy()
    if p != 'C': c = Image.alpha_composite(c, Image.open(f'{OUT}/head-{p}.webp').convert('RGBA'))
    return c
tiles = [comp(p) for p in ['L2', 'L1', 'C', 'R1', 'R2']]
mid = Image.blend(comp('C'), comp('L1'), 0.5)
mid2 = Image.blend(comp('L1'), comp('L2'), 0.5)
tiles += [mid, mid2]
box = (330, 450, 1230, 1700)
sheet = Image.new('RGB', (900 * 7 + 60, 1250), 'white')
for i, im in enumerate(tiles): sheet.paste(im.convert('RGB').crop(box), (i * 910, 0))
sheet.resize((sheet.width // 3, sheet.height // 3)).save(f'{SRC}/poses/_build-check.jpg', quality=90)
