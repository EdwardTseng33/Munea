# 寧寧三件式骨架拆件：頭 / 脖 / 胸
# 全部從原畫 whole.png 幾何切分 —— 三層 union 必須 100% 蓋回原畫（零缺口）
from PIL import Image, ImageFilter
import numpy as np
from scipy import ndimage

W = Image.open('whole.png').convert('RGBA')
a = np.array(W).astype(np.int16)
r, g, b, al = a[...,0], a[...,1], a[...,2], a[...,3]
green = (g-r > 60) & (g-b > 60)
real  = (al > 40) & (~green)
mx = a[...,:3].max(2)
H, Wd = real.shape
yy = np.arange(H)[:,None].repeat(Wd, 1)

# --- 頭髮遮罩：暗核心 → 沿亮髮絲長出去 → 補內部小洞（深色裙子排除）---
core = real & (mx < 135); core[830:,:] = False
grow = ndimage.binary_dilation(core, np.ones((25,25)))
hair = core | (grow & real & (mx < 205) & ((r-b) < 62))
hair = ndimage.binary_closing(hair, np.ones((7,7)))
hair = ndimage.binary_opening(hair, np.ones((3,3))) & real
hair[840:,:] = False
hair = ndimage.binary_fill_holes(hair) & real     # 髮絲間的亮點歸頭髮，不留孤島

# --- 脖子皮膚欄（每列從中線往外延伸的連續非髮區）---
CX = 430
neckcol = np.zeros_like(real)
for y in range(600, 900):
    if not real[y, CX]: continue
    L = CX
    while L > 0 and real[y, L-1] and not hair[y, L-1]: L -= 1
    R = CX
    while R < Wd-1 and real[y, R+1] and not hair[y, R+1]: R += 1
    if R - L > 420: continue                       # 已到胸口，不算脖子
    neckcol[y, max(0, L-14):min(Wd, R+15)] = True

HEAD_CUT, HEAD_FEA = 745, 20      # 切在下巴陰影帶正中間（y715-758 亮度平坦），不切到下巴輪廓線
NECK_TOP, NECK_BOT, NECK_FEA = 703, 848, 34
LIP = 60                                            # 胸層塗り足し的唇邊寬度

def band(v, edge, fea):
    t = np.clip((v-(edge-fea))/fea, 0, 1)
    return 1 - t*t*(3-2*t)

rgb  = a[...,:3].astype(np.uint8)
base = np.where(real, 255, 0).astype(np.float32)

def despill(arr):
    q = arr.astype(np.int16)
    cap = np.maximum(q[...,0], q[...,2])
    sp = (q[...,1] > cap) & (q[...,3] > 0)
    q[...,1] = np.where(sp, cap, q[...,1])
    return q.astype('uint8')

# ① 頭＝下巴以上 ∪ 全部頭髮；底緣羽化後蓋在脖子上，動起來不露線
head_a = base * np.maximum(band(yy, HEAD_CUT, HEAD_FEA), hair.astype(np.float32))
Image.fromarray(despill(np.dstack([rgb, np.clip(head_a,0,255).astype('uint8')])), 'RGBA').save('p-head.png')

# ② 脖＝皮膚欄，上緣藏在頭底下，下緣與左右柔化
neck_a = base * neckcol * band(yy, NECK_BOT, NECK_FEA) * (yy >= NECK_TOP)
neck_a = np.array(Image.fromarray(np.clip(neck_a,0,255).astype('uint8')).filter(ImageFilter.GaussianBlur(7))).astype(np.float32) * real
Image.fromarray(despill(np.dstack([rgb, np.clip(neck_a,0,255).astype('uint8')])), 'RGBA').save('p-neck.png')

# ③ 胸＝下巴以下的整個身體（含胸口皮膚／雙臂／裙），只留最大連通塊；
#    外緣往頭髮底下補一圈 LIP 寬的唇邊＝正規 2D Live 的「塗り足し」
# 底版＝body-nohead.png（Codex 補畫的無頭身體：肩膀、衣領在頭髮底下都是完整的，
# 且與原畫重疊區色差 0.0）。再把原畫的身體像素疊上去，確保看得見的地方都是原畫。
nh = np.array(Image.open('body-nohead.png').convert('RGBA'))
painted = nh[...,3] > 200
body = real & (yy >= 770) & (~hair)      # 胸層不含下巴／脖子，免得多一條下巴輪廓
sil = painted | body                                           # 身體完整輪廓（含被頭髮遮住的肩）
chest_rgb = np.where(body[...,None], rgb, nh[...,:3])
chest_a = np.where(sil, 255.0, 0.0)
# 只在輪廓外緣做一點點柔化，避免硬切邊
edge = sil & ~ndimage.binary_erosion(sil, np.ones((3,3)))
chest_a = np.where(edge, 235.0, chest_a)
Image.fromarray(despill(np.dstack([chest_rgb.astype('uint8'), chest_a.astype('uint8')])), 'RGBA').save('p-chest.png')

# --- 補漏：三層都沒接到的零星像素（羽化帶邊角）歸頭層，保證零缺口 ---
comp = Image.new('RGBA', (Wd, H), (0,0,0,0))
for f in ['p-chest.png','p-neck.png','p-head.png']:
    comp.alpha_composite(Image.open(f).convert('RGBA'))
leftover = ndimage.binary_dilation(real & (np.array(comp)[...,3] <= 40), np.ones((3,3))) & real
to_head  = leftover.copy()                     # 碎片一律跟著頭走，胸層不留靜止髮絲
to_chest = leftover & ~to_head                                           # 其餘歸靜止的胸層
if to_head.any():
    head_a = np.maximum(head_a, np.where(to_head, 255.0, 0.0))
    Image.fromarray(despill(np.dstack([rgb, np.clip(head_a,0,255).astype('uint8')])), 'RGBA').save('p-head.png')
if to_chest.any():
    chest_a = np.maximum(chest_a, np.where(to_chest, 255.0, 0.0))
    chest_rgb = np.where(to_chest[...,None], rgb, chest_rgb)
    Image.fromarray(despill(np.dstack([chest_rgb.astype('uint8'), chest_a.astype('uint8')])), 'RGBA').save('p-chest.png')

# --- 驗收：union 覆蓋率 ---
comp = Image.new('RGBA', (Wd, H), (0,0,0,0))
for f in ['p-chest.png','p-neck.png','p-head.png']:
    comp.alpha_composite(Image.open(f).convert('RGBA'))
miss = real & (np.array(comp)[...,3] <= 40)
print('原畫 %d px ｜ 未覆蓋 %d px (%.4f%%)' % (real.sum(), miss.sum(), 100*miss.sum()/real.sum()))

# --- 頭層裁成貼圖 + 輸出 CSS 位置 ---
hd = Image.open('p-head.png').convert('RGBA')
ys, xs = np.where(np.array(hd)[...,3] > 8); M = 70
x0, x1 = max(0, xs.min()-M), min(Wd, xs.max()+M)
y0, y1 = max(0, ys.min()-M), min(H,  ys.max()+M)
hd.crop((x0, y0, x1, y1)).save('p-head-crop.png')
print('TEX = { left:%.4f, top:%.4f, w:%.4f, h:%.4f }' % (100*x0/Wd, 100*y0/H, 100*(x1-x0)/Wd, 100*(y1-y0)/H))
