# 用 See-through 的分層 + 原畫像素，組出正規的前後層骨架
#
# 鐵律（Edward 8/7 定）：看得見的地方一律用「原畫像素」；
# See-through 只負責它擅長也是我們做不到的那一段——把「被遮住、原畫根本沒畫」的部分補上。
# 所以每一件都是：原畫優先，補畫墊底。
from PIL import Image, ImageFilter
import numpy as np
from scipy import ndimage

D = 'E:/Claude/Munea/tools/rive-lab/ning/'
W = Image.open(D + 'whole.png').convert('RGBA')
a = np.array(W).astype(np.int16)
r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
real = (al > 40) & (~((g - r > 60) & (g - b > 60)))
rgb = a[..., :3].astype(np.uint8)
mx = a[..., :3].max(2)
H, Wd = real.shape
yy = np.arange(H)[:, None].repeat(Wd, 1)

# 原畫的頭髮遮罩（跟 _split.py 同一套）
core = real & (mx < 135); core[830:, :] = False
grow = ndimage.binary_dilation(core, np.ones((25, 25)))
hair = core | (grow & real & (mx < 205) & ((r - b) < 62))
hair = ndimage.binary_closing(hair, np.ones((7, 7)))
hair = ndimage.binary_opening(hair, np.ones((3, 3))) & real
hair[840:, :] = False
hair = ndimage.binary_fill_holes(hair) & real


def load(n):
    return np.array(Image.open(D + n).convert('RGBA')).astype(np.int16)


def merge(st_name, keep_mask, out_name, feather=0):
    """st = See-through 那層（決定形狀／補畫）；keep_mask = 該用原畫像素的地方。"""
    st = load(st_name)
    alpha = st[..., 3].astype(np.float32)
    if feather:
        alpha = np.array(Image.fromarray(alpha.astype('uint8')).filter(ImageFilter.GaussianBlur(feather))).astype(np.float32)
    use_orig = keep_mask & (alpha > 8)
    out_rgb = np.where(use_orig[..., None], rgb, st[..., :3].astype(np.uint8))
    # 原畫有、補畫層漏掉的邊角，補回去（免得比原畫少一圈）
    add = keep_mask & (alpha <= 8)
    alpha = np.where(add, 255.0, alpha)
    out_rgb = np.where(add[..., None], rgb, out_rgb)
    q = np.dstack([out_rgb, np.clip(alpha, 0, 255).astype(np.uint8)]).astype(np.int16)
    cap = np.maximum(q[..., 0], q[..., 2])
    sp = (q[..., 1] > cap) & (q[..., 3] > 0)
    q[..., 1] = np.where(sp, cap, q[..., 1])
    Image.fromarray(q.astype('uint8'), 'RGBA').save(D + out_name)
    ys, xs = np.where(q[..., 3] > 20)
    print('  %-20s 原畫像素 %6d ／ 補畫像素 %6d   bbox y %d-%d' %
          (out_name, use_orig.sum(), (q[..., 3] > 20).sum() - use_orig.sum(), ys.min(), ys.max()))


print('組骨架（原畫優先、補畫墊底）：')

# ①＋④ 前後髮「硬分家」：同一撮頭髮只能存在一層，否則兩層彈簧不同步就會飄出殘影。
#      See-through 本來就分好了（瀏海 y251-569、後髮 y234-790），照它的分界切。
st_f = load('st-hair-front.png')
st_b = load('st-hair-back.png')
front_m = st_f[..., 3] > 60
# 後髮＝「整片頭髮」，含瀏海底下那一塊（塗り足し）。
# 硬分家會讓兩層一分開就見底裂縫；讓後髮墊在瀏海底下，分開時看到的是頭髮不是背景。
back_m = (st_b[..., 3] > 60) | hair

def hair_layer(mask, st, out_name):
    alpha = np.where(mask, np.maximum(st[..., 3], np.where(hair & mask, 255, 0)), 0).astype(np.float32)
    use_orig = hair & mask
    out_rgb = np.where(use_orig[..., None], rgb, st[..., :3].astype(np.uint8))
    q = np.dstack([out_rgb, np.clip(alpha, 0, 255).astype(np.uint8)]).astype(np.int16)
    cap = np.maximum(q[..., 0], q[..., 2]); sp = (q[..., 1] > cap) & (q[..., 3] > 0)
    q[..., 1] = np.where(sp, cap, q[..., 1])
    Image.fromarray(q.astype('uint8'), 'RGBA').save(D + out_name)
    ys, xs = np.where(q[..., 3] > 20)
    print('  %-20s 原畫像素 %6d ／ 補畫像素 %6d   bbox y %d-%d' %
          (out_name, use_orig.sum(), (q[..., 3] > 20).sum() - use_orig.sum(), ys.min(), ys.max()))

# See-through 會在脖子後面補畫「其實不存在的長髮」——不挖掉就會變成脖子上長鬍子。
# 這一步一定要留在組裝流程裡，否則重跑一次就長回來（2026-08-10 踩過）。
CX_N = 430
neckcol = np.zeros_like(hair)
for y in range(600, 900):
    if not real[y, CX_N]: continue
    Lx = CX_N
    while Lx > 0 and real[y, Lx-1] and not hair[y, Lx-1]: Lx -= 1
    Rx = CX_N
    while Rx < Wd-1 and real[y, Rx+1] and not hair[y, Rx+1]: Rx += 1
    if Rx - Lx > 420: continue
    neckcol[y, max(0, Lx-16):min(Wd, Rx+17)] = True
back_m = back_m & ~((~hair) & neckcol & (yy > 690))

# 瀏海底下不可以再藏一份頭髮，否則瀏海一飄就露出殘影。
# 只在「額頭上方」挖掉（那裡頭層有補畫好的皮膚，飄起來看到的是額頭＝對的）；
# 瀏海與髮團相接的上緣保留重疊，才不會裂。
_hd = load('st-head-bald.png')
back_m = back_m & ~(front_m & (_hd[..., 3] > 60))

hair_layer(back_m,  st_b, 'rig2-hair.png')   # 後髮／側髮：重、慢
hair_layer(front_m, st_f, 'rig2-bang.png')   # 瀏海：輕、快
print('  瀏海底下有後髮墊著的像素 %d（要 >0 才不會裂）｜原畫頭髮沒被分到的 %d'
      % ((front_m & back_m).sum(), (hair & ~front_m & ~back_m).sum()))

# ② 頭：臉 100% 用原畫（連形狀都用原畫的，不吃 See-through 那顆重畫的頭），
#    只有「原本被頭髮蓋住的頭皮」才用補畫填。這樣鼻子嘴巴不會被換成另一張臉。
HEAD_CUT, HEAD_FEA = 745, 20          # 切在下巴陰影帶正中間（亮度平坦、看不出接縫）
def band(v, edge, fea):
    t = np.clip((v - (edge - fea)) / fea, 0, 1)
    return 1 - t * t * (3 - 2 * t)

st_head = load('st-head-bald.png')
face_orig = real & (~hair) & (yy < HEAD_CUT + 40)          # 原畫看得見的臉／耳／下巴
scalp = hair & (st_head[..., 3] > 60) & (yy < 700)         # 頭髮底下的頭皮，只到眉心以上
head_a = np.where(face_orig, 255.0, 0.0) * band(yy, HEAD_CUT, HEAD_FEA)
head_a = np.maximum(head_a, np.where(scalp, 255.0, 0.0))
head_rgb = np.where(scalp[..., None] & ~face_orig[..., None], st_head[..., :3].astype(np.uint8), rgb)
q = np.dstack([head_rgb, np.clip(head_a, 0, 255).astype(np.uint8)]).astype(np.int16)
cap = np.maximum(q[..., 0], q[..., 2]); sp = (q[..., 1] > cap) & (q[..., 3] > 0)
q[..., 1] = np.where(sp, cap, q[..., 1])
Image.fromarray(q.astype('uint8'), 'RGBA').save(D + 'rig2-head.png')
print('  %-20s 原畫像素 %6d ／ 補畫頭皮 %6d' % ('rig2-head.png', face_orig.sum(), (scalp & ~face_orig).sum()))

# ③ 上衣＋肩：看得見的衣服用原畫；肩膀被頭髮蓋住的部分用補畫
body_visible = real & (~hair) & (yy >= 700)
merge('st-topwear.png', body_visible, 'rig2-topwear.png')

# --- 驗收：照層序疊回去，跟原畫比覆蓋率 ---
order = ['p-chest.png', 'p-neck.png', 'rig2-topwear.png', 'rig2-hair.png',
         'rig2-head.png', 'rig2-bang.png', 'rig2-strand.png']   # 跟頁面上的層序一致
comp = Image.new('RGBA', (Wd, H), (0, 0, 0, 0))
for n in order:
    comp.alpha_composite(Image.open(D + n).convert('RGBA'))
ca = np.array(comp)
zone = real & (yy >= 200) & (yy <= 1080)
miss = zone & (ca[..., 3] <= 40)
print('\n上半身 %d px ｜ 重組後沒蓋到 %d px (%.3f%%)' % (zone.sum(), miss.sum(), 100 * miss.sum() / zone.sum()))
diff = np.abs(ca[..., :3].astype(np.int16) - rgb.astype(np.int16)).max(2)
bad = zone & (ca[..., 3] > 200) & (diff > 40)
print('跟原畫顏色差很多的像素 %d (%.3f%%)（越低表示越像原畫）' % (bad.sum(), 100 * bad.sum() / zone.sum()))

bg = Image.new('RGBA', comp.size, (0xF6, 0xEF, 0xE3, 255))
bg.alpha_composite(comp)
bg.convert('RGB').crop((40, 180, 820, 1200)).save(D + '_rig2_check.png')

# --- 出貨前守門：原畫是皮膚的地方，重組後不准變成深色（＝脖子長鬍子那類錯誤）---
skin_zone = real & (~hair) & (yy >= 640) & (yy <= 900)
comp2 = Image.new('RGBA', (Wd, H), (0, 0, 0, 0))
for n in order:
    comp2.alpha_composite(Image.open(D + n).convert('RGBA'))
c2 = np.array(comp2).astype(np.int16)
orig_bright = rgb.astype(np.int16).max(2)
now_bright = c2[..., :3].max(2)
beard = skin_zone & (orig_bright > 170) & (now_bright < 120) & (c2[..., 3] > 200)
print('守門｜原畫是亮膚色、重組後卻變深色的像素：%d（>200 就是有東西蓋在臉或脖子上）' % beard.sum())
if beard.sum() > 200:
    ys2, xs2 = np.where(beard)
    print('   位置 y %d-%d x %d-%d' % (ys2.min(), ys2.max(), xs2.min(), xs2.max()))
