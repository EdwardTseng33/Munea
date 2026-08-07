# 把額前那條細髮束拆成獨立一件（釘住髮根、髮梢可左右擺）
# 執行順序：_split.py → _build_rig.py → 這支
from PIL import Image
import numpy as np
from scipy import ndimage

D = 'E:/Claude/Munea/tools/rive-lab/ning/'
W = np.array(Image.open(D + 'whole.png').convert('RGBA')).astype(np.int16)
r, g, b, al = W[..., 0], W[..., 1], W[..., 2], W[..., 3]
real = (al > 40) & (~((g - r > 60) & (g - b > 60)))
mx = W[..., :3].max(2); rgb = W[..., :3].astype(np.uint8)
core = real & (mx < 135); core[830:, :] = False
grow = ndimage.binary_dilation(core, np.ones((25, 25)))
hair = core | (grow & real & (mx < 205) & ((r - b) < 62))
hair = ndimage.binary_closing(hair, np.ones((7, 7)))
hair = ndimage.binary_opening(hair, np.ones((3, 3))) & real
hair[840:, :] = False
hair = ndimage.binary_fill_holes(hair) & real

# 沿著瀏海與額頭的交界取一條上寬下窄的帶子＝視覺上那條斜掃的髮束
Y0, Y1 = 344, 510
strand = np.zeros_like(hair)
for y in range(Y0, Y1):
    row = hair[y]; x = 345
    while x < 430 and row[x]: x += 1
    edge = x - 1
    if edge < 330 or edge > 425: continue
    t = (y - Y0) / (Y1 - Y0)
    w = int(54 * (1 - t) + 12 * t)
    strand[y, max(0, edge - w):edge + 1] = row[max(0, edge - w):edge + 1]
strand = ndimage.binary_opening(strand, np.ones((3, 3))) & hair

yy = np.arange(1844)[:, None].repeat(853, 1)
a = np.where(strand, 255.0, 0.0)
t = np.clip((yy - Y0) / 34.0, 0, 1)
a *= t * t * (3 - 2 * t)                       # 髮根柔化，跟瀏海融在一起
q = np.dstack([rgb, np.clip(a, 0, 255).astype('uint8')]).astype(np.int16)
cap = np.maximum(q[..., 0], q[..., 2]); sp = (q[..., 1] > cap) & (q[..., 3] > 0)
q[..., 1] = np.where(sp, cap, q[..., 1])
Image.fromarray(q.astype('uint8'), 'RGBA').save(D + 'rig2-strand.png')

# 從瀏海挖掉——但只挖很裡面那一小塊，四周留厚重疊，
# 髮束擺動時只會露出一條細縫（真髮束翹起來就是這樣），不會破一個洞
bang = np.array(Image.open(D + 'rig2-bang.png').convert('RGBA')).astype(np.float32)
cut = ndimage.binary_erosion(strand, np.ones((19, 19)))
bang[..., 3] = np.where(cut, 0, bang[..., 3])
Image.fromarray(np.clip(bang, 0, 255).astype('uint8'), 'RGBA').save(D + 'rig2-bang.png')
print('細髮束 %d px ｜ 從瀏海挖掉 %d px（其餘留作重疊）' % (strand.sum(), cut.sum()))

for n, out in [('rig2-strand.png', 'rig2-strand-crop.png'), ('rig2-bang.png', 'rig2-bang-crop.png')]:
    im = Image.open(D + n).convert('RGBA'); z = np.array(im)
    ys, xs = np.where(z[..., 3] > 6); M = 70
    x0, x1 = max(0, xs.min() - M), min(853, xs.max() + M)
    y0, y1 = max(0, ys.min() - M), min(1844, ys.max() + M)
    im.crop((x0, y0, x1, y1)).save(D + out)
    print('%-24s { left:%.4f, top:%.4f, w:%.4f, h:%.4f }'
          % (out, 100 * x0 / 853, 100 * y0 / 1844, 100 * (x1 - x0) / 853, 100 * (y1 - y0) / 1844))
