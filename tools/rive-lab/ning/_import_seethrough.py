# 把 See-through 分出來的圖層搬回原畫 853x1844 的座標系
#
# See-through 的輸入是原畫裁下來的上半身 (0,150)-(853,1080)，再等比塞進 1024x1024 的方畫布。
# 這裡把它反推回去：畫布 → 去掉左右留白 → 縮回 853x930 → 貼回 y=150 的位置。
# 對位驗證：角色頂端反推得 y=233.6，原畫實際是 234 → 誤差 <1px。
from PIL import Image
import numpy as np
import os

SRC = 'E:/Claude/see-through-lab/see-through/workspace/layerdiff_output/ning-upper'
DST = 'E:/Claude/Munea/tools/rive-lab/ning'
CROP_X0, CROP_Y0, CROP_W, CROP_H = 0, 150, 853, 930
ART_W, ART_H = 853, 1844
CANVAS = 1024

scale = CANVAS / CROP_H                      # 1.1011：以高度貼合
inner_w = CROP_W * scale                     # 939.2
off_x = (CANVAS - inner_w) / 2               # 42.4

def bring_back(name, out_name):
    p = os.path.join(SRC, name)
    if not os.path.exists(p):
        print('  跳過（沒有這層）', name); return None
    im = Image.open(p).convert('RGBA')
    im = im.crop((round(off_x), 0, round(off_x + inner_w), CANVAS))   # 去掉左右留白
    im = im.resize((CROP_W, CROP_H), Image.LANCZOS)                   # 縮回原畫尺度
    canvas = Image.new('RGBA', (ART_W, ART_H), (0, 0, 0, 0))
    canvas.paste(im, (CROP_X0, CROP_Y0))
    a = np.array(canvas)
    # 去綠邊殘留（原畫是綠幕去背來的）
    cap = np.maximum(a[..., 0].astype(np.int16), a[..., 2].astype(np.int16))
    sp = (a[..., 1] > cap) & (a[..., 3] > 0)
    a[..., 1] = np.where(sp, cap, a[..., 1])
    out = Image.fromarray(a, 'RGBA')
    out.save(os.path.join(DST, out_name))
    ys, xs = np.where(a[..., 3] > 20)
    print('  %-22s → %-22s bbox y %d-%d x %d-%d' % (name, out_name, ys.min(), ys.max(), xs.min(), xs.max()))
    return out

if __name__ == '__main__':
    print('搬回原畫座標：')
    pairs = [
        ('head.png',        'st-head-bald.png'),    # 光頭＋臉（頭皮補畫完整）
        ('front hair.png',  'st-hair-front.png'),   # 瀏海
        ('back hair.png',   'st-hair-back.png'),    # 後髮（完整、含被遮住的部分）
        ('topwear.png',     'st-topwear.png'),      # 上衣＋肩（肩膀補完整）
        ('neck.png',        'st-neck.png'),
        ('face.png',        'st-face.png'),
        ('ears.png',        'st-ears.png'),
        ('earwear.png',     'st-earring.png'),
        ('eyebrow.png',     'st-brow.png'),
        ('eyelash.png',     'st-eyelash.png'),
        ('irides.png',      'st-iris.png'),
        ('eyewhite.png',    'st-eyewhite.png'),
        ('mouth.png',       'st-mouth.png'),
        ('nose.png',        'st-nose.png'),
        ('src_img.png',     'st-src.png'),
    ]
    for a_, b_ in pairs:
        bring_back(a_, b_)

    # 對位驗收：把搬回來的原圖跟真原畫相減
    st = np.array(Image.open(os.path.join(DST, 'st-src.png')).convert('RGBA')).astype(np.int16)
    wh = np.array(Image.open(os.path.join(DST, 'whole.png')).convert('RGBA')).astype(np.int16)
    g = (wh[..., 1] - wh[..., 0] > 60) & (wh[..., 1] - wh[..., 2] > 60)
    real = (wh[..., 3] > 40) & (~g)
    both = real & (st[..., 3] > 200)
    print('\n對位驗收：重疊 %d px，平均色差 %.1f（<25 表示位置對得上）'
          % (both.sum(), np.abs(st[..., :3] - wh[..., :3])[both].mean()))
