# 眨眼那張的睫毛線太淡 —— 縮到手機尺寸後幾乎消失，整隻眼睛看起來像「褪色」而不是「閉上」。
# 這支只做一件事：把「已經存在的睫毛筆觸」加深、順著筆觸方向補粗一點點。
# 不畫新形狀、不改位置、不動皮膚 —— 只是把原本就有的線條調回該有的濃度。
from PIL import Image, ImageFilter
import numpy as np
from scipy import ndimage

D = 'E:/Claude/Munea/tools/rive-lab/ning/'
SRC = D + 'part-eyes-closed-orig.png'
OUT = D + 'part-eyes-closed.png'
import os
if not os.path.exists(SRC):                      # 第一次跑：先把原檔留一份底
    Image.open(OUT).save(SRC)

p = np.array(Image.open(SRC).convert('RGBA')).astype(np.float32)
rgb, al = p[..., :3], p[..., 3]
lum = rgb.min(2)
solid = al > 200

# 睫毛＝貼圖裡本來就偏暗的筆觸（含它自己的柔邊）
stroke = solid & (lum < 175)
core = solid & (lum < 120)
# 順著筆觸長一圈（1 px），讓縮小後不會被平均掉
grown = ndimage.binary_dilation(core, np.array([[0,1,0],[1,1,1],[0,1,0]],bool)) & solid

# 濃度曲線：越接近筆觸中心壓得越深；原本就亮的皮膚完全不動
d = ndimage.distance_transform_edt(grown)
w = np.clip(d / 2.6, 0, 1) ** 0.9 * 0.72
w = np.where(stroke | grown, w, 0)
w = np.array(Image.fromarray((w * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(0.6))).astype(np.float32) / 255

TARGET = np.array([58.0, 42.0, 35.0])            # 原畫睫毛的深度（跟睜眼那張同一個濃度）
out = rgb * (1 - w[..., None]) + TARGET * w[..., None]
out = np.minimum(out, rgb)                       # 只准變深、不准變亮
q = np.dstack([out, al]).astype('uint8')
Image.fromarray(q, 'RGBA').save(OUT)

def darkmass(a):
    z = np.array(Image.fromarray(a).convert('RGBA'))
    bg = Image.new('RGBA', (235, 91), (252, 225, 201, 255)); bg.alpha_composite(Image.fromarray(z))
    s = np.array(bg.resize((88, 34), Image.LANCZOS).convert('RGB')).astype(np.int16)
    return (s.min(2) < 120).sum()

print('縮到手機尺寸後的「深色量」：修之前 %d ／ 修之後 %d ／ 睜眼是 %d'
      % (darkmass(np.array(Image.open(SRC).convert('RGBA'))), darkmass(q), 652))
