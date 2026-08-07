# 把「雙手」從身體拆出來，讓手可以自己擺（不再跟身體黏成一塊）
# 執行順序：_split.py → _build_rig.py → _strand.py → 這支
#
# 產出四件：
#   rig6-armL.png / rig6-armR.png  兩隻手（原畫像素、肩關節為旋轉中心）
#   rig6-torso.png                 上半身（呼吸＋腰傾）
#   rig6-lower.png                 下半身（固定不動）
#
# 鐵律：看得見的一律原畫像素；手拿掉之後身體會缺一塊 →
#      往手底下補一圈「塗り足し」（手一擺不會見底）。
from PIL import Image, ImageFilter
import numpy as np
from scipy import ndimage

D = 'E:/Claude/Munea/tools/rive-lab/ning/'
W = np.array(Image.open(D + 'whole.png').convert('RGBA')).astype(np.int16)
r, g, b, al = W[..., 0], W[..., 1], W[..., 2], W[..., 3]
real = (al > 40) & (~((g - r > 60) & (g - b > 60)))
rgb = W[..., :3].astype(np.uint8)
H, Wd = real.shape
yy = np.arange(H)[:, None].repeat(Wd, 1)
xx = np.arange(Wd)[None, :].repeat(H, 0)

CUT, FEA = 1397, 16       # 褲頭（腰帶）＝上下半身的分界；切在這裡動起來看不出接縫
LIP = 42                  # 手底下的塗り足し寬度
SHOULDER_Y = 810          # 這條線以上不算手（肩線以上是衣領／脖子）


def despill(q):
    q = q.astype(np.int16)
    cap = np.maximum(q[..., 0], q[..., 2])
    sp = (q[..., 1] > cap) & (q[..., 3] > 0)
    q[..., 1] = np.where(sp, cap, q[..., 1])
    return np.clip(q, 0, 255).astype('uint8')


# ── ① 找出兩隻手 ────────────────────────────────────────────
# 外套袖子是米白 (251,230,203)、裡面襯衫是珊瑚色 (213,132,125)、下半身是深色。
# 只認米白＝袖子；深色不能一起收（會把裙子連進來、三塊黏成一塊分不開）。
cream = real & (r > 205) & (g > 175) & (b > 140) & ((r - b) < 95)
sleeve = cream & (yy > SHOULDER_Y) & (yy < 1841)
sleeve = ndimage.binary_closing(sleeve, np.ones((11, 11)))
sleeve = ndimage.binary_opening(sleeve, np.ones((9, 9))) & real
sleeve = ndimage.binary_fill_holes(sleeve) & real

lab, n = ndimage.label(sleeve)
armL = np.zeros_like(real)
armR = np.zeros_like(real)
for i in range(1, n + 1):
    m = lab == i
    if m.sum() < 12000:
        continue
    cx = xx[m].mean()
    if cx < 250:
        armL |= m
    elif cx > 640:
        armR |= m
    # 中間那一塊是襯衫（x 314-606），不是手，跳過
print('左臂 %d px ／ 右臂 %d px' % (armL.sum(), armR.sum()))

armM = armL | armR


def pivot(m, left):
    """肩關節＝手的『內上角』（靠身體那一側、肩線附近最靠內的一點）"""
    ys = np.where(m.any(1))[0]
    y0 = ys.min()
    row = np.where(m[y0:y0 + 90].any(0))[0]
    x = row.max() if left else row.min()
    return x, y0 + 40


for nm, m, left in [('armL', armL, True), ('armR', armR, False)]:
    px, py = pivot(m, left)
    a = np.where(m, 255.0, 0.0)
    a = np.array(Image.fromarray(a.astype('uint8')).filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32)
    a = np.where(m, 255.0, a)                      # 核心不透明，只柔化外緣
    Image.fromarray(despill(np.dstack([rgb, a.astype('uint8')])), 'RGBA').save(D + 'rig6-%s.png' % nm[-4:])
    print('  %s 肩關節 (%d,%d) → CSS transform-origin %.3f%% %.3f%%'
          % (nm, px, py, 100 * px / Wd, 100 * py / H))

# ── ② 身體＝原本的身體減掉手，再往手底下補一圈 ─────────────
chest = np.array(Image.open(D + 'p-chest.png').convert('RGBA'))
topw = np.array(Image.open(D + 'rig2-topwear.png').convert('RGBA'))
body_m = ((chest[..., 3] > 40) | (topw[..., 3] > 40)) & (yy >= 700)
body_rgb = np.where((topw[..., 3:4] > 40) & (yy[..., None] >= 700), topw[..., :3], chest[..., :3])
body_rgb = np.where(real[..., None], rgb, body_rgb)      # 看得見的一律原畫

keep = body_m & (~armM)
# 塗り足し：從身體邊界往手底下長 LIP 寬，顏色取最近的身體像素。
# 取樣時避開輪廓線（深色描邊），否則會把黑邊抹成一大片髒色。
src = ndimage.binary_erosion(keep, np.ones((7, 7))) & (body_rgb.max(2) > 165)
dist, idx = ndimage.distance_transform_edt(~src, return_indices=True)
lip = armM & (dist <= LIP + 12)
fill_rgb = body_rgb[idx[0], idx[1]]
out_rgb = np.where(lip[..., None], fill_rgb, body_rgb)
out_a = np.where(keep, 255.0, 0.0)
out_a = np.maximum(out_a, np.where(lip, np.clip(255 * (1 - (dist - 12) / LIP), 0, 255), 0))
Image.fromarray(despill(np.dstack([out_rgb, out_a.astype('uint8')])), 'RGBA').save(D + 'rig6-body.png')
print('身體（去手）%d px ｜ 手底下補畫 %d px' % (keep.sum(), (lip & (out_a > 8)).sum()))


# ── ③ 身體切成上下：上半身會呼吸／側傾，下半身釘死 ─────────
def band(v, edge, fea):
    t = np.clip((v - (edge - fea)) / fea, 0, 1)
    return 1 - t * t * (3 - 2 * t)


bd = np.array(Image.open(D + 'rig6-body.png').convert('RGBA')).astype(np.float32)
# 上半身：褲頭以上（下緣柔化，塞進褲頭裡）
ta = bd[..., 3] * band(yy, CUT + FEA, FEA)
Image.fromarray(despill(np.dstack([bd[..., :3], ta])), 'RGBA').save(D + 'rig6-torso.png')
# 下半身：褲頭以下，往上多留一段藏在上半身底下（上半身一傾也不會露出背景）
la = bd[..., 3] * (1 - band(yy, CUT - 90, 60))
Image.fromarray(despill(np.dstack([bd[..., :3], la])), 'RGBA').save(D + 'rig6-lower.png')
print('上半身 %d px ｜ 下半身 %d px ｜ 兩者重疊（塗り足し）%d px'
      % ((ta > 20).sum(), (la > 20).sum(), ((ta > 20) & (la > 20)).sum()))

# ── ④ 驗收：照層序疊回去，身體區不准有洞 ────────────────────
order = ['rig6-lower.png', 'rig6-torso.png', 'rig6-armL.png', 'rig6-armR.png']
comp = Image.new('RGBA', (Wd, H), (0, 0, 0, 0))
for nfile in order:
    comp.alpha_composite(Image.open(D + nfile).convert('RGBA'))
ca = np.array(comp)
zone = real & (yy >= 860)
miss = zone & (ca[..., 3] <= 40)
print('\n身體區 %d px ｜ 未覆蓋 %d px (%.3f%%)' % (zone.sum(), miss.sum(), 100 * miss.sum() / zone.sum()))
diff = np.abs(ca[..., :3].astype(np.int16) - rgb.astype(np.int16)).max(2)
bad = zone & (ca[..., 3] > 200) & (diff > 40)
print('跟原畫顏色差很多的像素 %d (%.3f%%)' % (bad.sum(), 100 * bad.sum() / zone.sum()))
