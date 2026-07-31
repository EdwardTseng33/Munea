"""把商店截圖的透明圖層去掉——蘋果不收帶透明的圖（2026-07-31 蘇菲）。

7/31 實測：日文與西班牙文那兩組上傳後被蘋果打回，錯誤碼 IMAGE_ALPHA_NOT_ALLOWED。
英文與中文那兩組沒事——中文之所以有個 `-rgb` 版本，就是之前有人踩過同一個坑。

做法：把原圖疊在白底上再存成不含透明的 PNG。這些圖的背景本來就是不透明的奶油色，
所以疊白底之後畫面看起來完全一樣，只是把「其實用不到的透明通道」拿掉。
不是重新壓縮、不動任何像素顏色。

用法：python strip-alpha.py <來源資料夾> <輸出資料夾>
"""
import os
import sys

from PIL import Image

src_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

names = sorted(n for n in os.listdir(src_dir) if n.lower().endswith('.png'))
for name in names:
    src = os.path.join(src_dir, name)
    img = Image.open(src)
    had_alpha = img.mode in ('RGBA', 'LA') or 'transparency' in img.info

    if had_alpha:
        img = img.convert('RGBA')
        flat = Image.new('RGB', img.size, (255, 255, 255))
        flat.paste(img, mask=img.split()[3])   # 用 alpha 當遮罩貼上去
    else:
        flat = img.convert('RGB')

    out = os.path.join(out_dir, name)
    flat.save(out, 'PNG', optimize=True)

    before = os.path.getsize(src) / 1048576
    after = os.path.getsize(out) / 1048576
    print('  %-16s %s  %dx%d  %.1fMB -> %.1fMB' % (
        name, '有透明→已去除' if had_alpha else '本來就沒有', flat.width, flat.height, before, after))

print('共處理 %d 張，輸出到 %s' % (len(names), out_dir))
