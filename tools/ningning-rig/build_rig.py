# -*- coding: utf-8 -*-
"""把一張純色塊寧寧拆成可動的三層＋嘴眼零件（全畫布透明 PNG，疊回去零誤差）。
body＝原圖；head＝頭髮＋臉（五官處填回皮膚色）；feat＝五官＋腮紅；half/open/eyes＝嘴兩段與閉眼。"""
import sys, json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi
SRC, PARTS, OUTDIR = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.load(open(sys.argv[4], encoding='utf-8'))
base = Image.open(SRC).convert('RGB'); b = np.asarray(base).astype(float); H, W = b.shape[:2]
lum = b.mean(axis=2)
skin = np.array(cfg['skin'], float)

def ell(ells, scale=1.0):
    m = Image.new('L', (W, H), 0); d = ImageDraw.Draw(m)
    for cx, cy, rx, ry in ells: d.ellipse((cx-rx*scale, cy-ry*scale, cx+rx*scale, cy+ry*scale), fill=255)
    return np.asarray(m) > 0

# 頭髮＝最大的一塊深色
dark = lum < 90
lab, n = ndi.label(dark)
sizes = ndi.sum(dark, lab, range(1, n+1))
hair = lab == (1 + int(np.argmax(sizes)))
if cfg.get('hair_all_pieces'):
    # 臉旁垂下的細髮絲常跟主頭髮沒連在一起：凡是不在五官範圍裡的深色塊都算頭髮，轉頭時才會一起動
    featz = ell(cfg['features'])
    for i in range(1, n + 1):
        comp = lab == i
        if sizes[i - 1] < 20: continue
        ys_, xs_ = np.where(comp)
        if ys_.mean() > cfg['chin_y'] + 200: continue
        if (comp & featz).sum() / comp.sum() > 0.5: continue
        hair |= comp
hair &= ~ell(cfg['brows'])            # 眉毛碰到瀏海也算五官
bgc = np.array(cfg['bg'], float); is_bg = np.abs(b - bgc).sum(axis=2) < 30
# 臉＝從臉中央長出去的皮膚色，限制在下巴以上
near_skin = (np.abs(b - skin).sum(axis=2) < 70)
cut = cfg['chin_y']
cand = near_skin.copy(); cand[cut:, :] = False
lab2, _ = ndi.label(cand)
face = lab2 == lab2[cfg['face_center'][1], cfg['face_center'][0]]
face = ndi.binary_fill_holes(face)
head = ndi.binary_fill_holes(hair | face)   # 頭髮之間夾的細縫也算頭，要跟著頭一起動
head[cut:, :] &= hair[cut:, :]          # 下巴以下只留頭髮，脖子歸身體
# 頭髮外緣半透明的那一圈也算頭（不是純背景色的就收進來），不然轉頭時會在原位留一條淡線
bgc0 = np.array(cfg['bg'], float)
ring = ndi.binary_dilation(head, iterations=3) & ~head
head |= ring & (np.abs(b - bgc0).sum(axis=2) > 8) & (np.arange(H)[:, None] < cut + 400)
feat_m = ell(cfg['features']) & ~hair & head

def save(arr_rgb, alpha, name):
    a = np.clip(alpha, 0, 1)
    out = np.dstack([np.clip(arr_rgb, 0, 255), a * 255]).astype(np.uint8)
    Image.fromarray(out, 'RGBA').save(f'{OUTDIR}/{name}', optimize=True)

# 身體層原本頭的位置：頭髮處填一致的髮色、臉處填皮膚色——頭轉開時露出來的只是一點點同色邊，不會出現兩條髮絲線
hair_col = np.median(b[hair & (lum < 60)], axis=0)
# 臉底下墊脖子陰影色：轉頭時下巴邊若露出一點，看起來就是下巴的影子
neck_col = np.array(cfg.get('neck_shadow', cfg['skin']), float)
body = b.copy()
# 頭髮底下：每一點墊「同一列左右最近、不屬於頭的那個顏色」——外側就是背景、靠脖子那側就是脖子／衣服，
# 頭轉開時露出來的跟原本旁邊一樣，不會出現兩條髮線
cols = np.arange(W)
far_out = ~ndi.binary_dilation(head, iterations=4)   # 跳過頭髮邊緣半透明那一圈，取乾淨的鄰居色
for y in range(H):
    m = head[y]
    if not m.any(): continue
    out = far_out[y]
    li = np.where(out, cols, -1); li = np.maximum.accumulate(li)
    ri = np.where(out, cols, W); ri = np.minimum.accumulate(ri[::-1])[::-1]
    dl = np.where(li >= 0, cols - li, 10**6); dr = np.where(ri < W, ri - cols, 10**6)
    src = np.where(dl <= dr, li, ri); src = np.clip(src, 0, W - 1)
    body[y, m] = b[y, src[m]]
body[head & face] = neck_col
body_a = np.ones((H, W))
if cfg.get('table'):
    # 桌子單獨一層、不跟著人晃：每一列桌面都是一條純色帶，用最左邊那一格的顏色整列鋪滿（手臂底下也補齊）
    bgv = np.array(cfg['bg'], float)
    ty = next(y for y in range(H // 2, H) if np.abs(b[y, 4] - bgv).sum() > 40)
    y0 = ty - 24
    wood = np.unique(b[ty:, 4].round().astype(int), axis=0).astype(float)
    table = np.zeros((H, W, 3)); table_a = np.zeros((H, W))
    for y in range(y0, H):
        row = b[y]
        dwood = np.min(np.abs(row[:, None, :] - wood[None, :, :]).sum(axis=2), axis=1)
        isbg = np.abs(row - bgv).sum(axis=1) < 30
        tp = (dwood < 40) | isbg
        # 桌面那幾列：原圖像素照抄（斜邊也照抄），手臂擋住的地方用同一列最近的桌面色補
        idx = np.where(tp, np.arange(W), -1); idx = np.maximum.accumulate(idx)
        first = np.argmax(tp) if tp.any() else 0
        idx[idx < 0] = first
        table[y] = row[idx]; table_a[y] = 1
        body_a[y, tp] = 0
    save(table, table_a, 'r-table.png')
    print('table top', ty, 'pivot y %.2f%%' % (100 * ty / H))
save(body, body_a, 'r-body.png')
blank = b.copy(); blank[feat_m] = skin
save(blank, head.astype(float), 'r-head.png')
save(b, feat_m.astype(float), 'r-feat.png')
# 臉的範圍（頭層扣掉頭髮）：五官層只准畫在這裡面，轉頭時跑出臉邊的部分自動藏起來
facezone = head & ~hair
save(np.full((H, W, 3), 255.0), facezone.astype(float), 'r-facemask.png')

def part(src, ells, name, lid=False, grow=5, soft=2):
    v = np.asarray(Image.open(src).convert('RGB')).astype(float)
    region = ell(ells, 1.6); d = np.abs(v - b).sum(axis=2)
    calib = region & (d < 45); off = (v[calib] - b[calib]).mean(axis=0); v -= off
    inner = ell(ells)
    if lid:
        lidpx = inner & (v.mean(axis=2) > skin.mean() - 70) & (np.abs(v - skin).sum(axis=2) < 120)
        v[lidpx] = skin
    d = np.abs(v - b).sum(axis=2)
    core = inner & (d > 40)
    mi = Image.fromarray((core * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(grow)).filter(ImageFilter.GaussianBlur(soft))
    a = np.asarray(mi).astype(float) / 255 * inner
    save(v, a, name)
    return off
print('offsets', part(f'{PARTS}/f-half.png', cfg['mouth'], 'r-half.png'),
      part(f'{PARTS}/f-open.png', cfg['mouth'], 'r-open.png'),
      part(f'{PARTS}/f-blink.png', cfg['eyes'], 'r-eyes.png', lid=True, grow=11, soft=1))

# 不動時疊回去要跟原圖一模一樣
L = [Image.open(f'{OUTDIR}/r-{k}.png') for k in ('body', 'head', 'feat')]
comp = Image.alpha_composite(Image.new('RGBA', (W, H), tuple(cfg['bg']) + (255,)), Image.open(f'{OUTDIR}/r-table.png')) if cfg.get('table') else Image.new('RGBA', (W, H), tuple(cfg['bg']) + (255,))
comp = Image.alpha_composite(comp, L[0])
for l in L[1:]: comp = Image.alpha_composite(comp, l)
rest = np.abs(np.asarray(comp.convert('RGB')).astype(int) - b.astype(int))
print('rest-pose pixels off by >12:', int((rest.sum(axis=2) > 12).sum()))
diff = np.abs(np.asarray(comp.convert('RGB')).astype(int) - b.astype(int)).max()
ys, xs = np.where(head)
print('head bbox', xs.min(), xs.max(), ys.min(), ys.max(), 'feat px', int(feat_m.sum()), 'rest-pose max diff', diff)
# 檢查圖：頭層（五官空白）與五官層
prev = Image.new('RGB', (W * 2 // 3, H // 3), 'white')
hv = Image.alpha_composite(Image.new('RGBA', (W, H), (60, 200, 120, 255)), Image.open(f'{OUTDIR}/r-head.png'))
fv = Image.alpha_composite(Image.new('RGBA', (W, H), (60, 200, 120, 255)), Image.open(f'{OUTDIR}/r-feat.png'))
prev.paste(hv.convert('RGB').resize((W // 3, H // 3)), (0, 0)); prev.paste(fv.convert('RGB').resize((W // 3, H // 3)), (W // 3, 0))
prev.save(f'{PARTS}/_rig-check.jpg', quality=88)
