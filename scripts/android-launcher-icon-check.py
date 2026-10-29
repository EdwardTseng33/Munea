#!/usr/bin/env python3
"""Android 桌面圖示驗證（2026-10-29）——只給 CI 的模擬器流程用，不會被打包進 APK。

為什麼要這支：PR #632 把 Android 桌面圖示從 Capacitor 範本的藍 X 換成官方沐寧圖示
（奶油底＋橘水滴＋青綠漣漪，跟 iPhone 版同一張），但 CI 的 emulator-smoke 只拍 App 開啟後
的畫面，從來沒有拍過「桌面上那顆圖示長什麼樣」——改了資源檔卻沒人親眼看過，等於沒驗。
這支在模擬器上按 HOME、打開應用程式列表，截圖、找「Munea」那一格、把它放大存檔，
再用顏色判定那格是不是官方圖示：

  - 橘水滴（R 高、G 中、B 低）跟青綠漣漪（G、B 都比 R 高）都要在；
  - Capacitor 範本藍 X 的那種藍（B 很高、R 很低）不能比橘色多。

找不到「Munea」或顏色不對就以非 0 結束、把畫面上看得到的文字印出來——不要悄悄放過。

用法（模擬器／手機已 adb 連上、Pillow 已裝）：
  python3 scripts/android-launcher-icon-check.py --out-dir launcher-icon
產出（全部留成 CI artifact）：
  <out>/home.png               按 HOME 之後的桌面
  <out>/app-drawer.png         應用程式列表
  <out>/*.xml                  對應的 accessibility tree dump
  <out>/munea-icon-closeup.png 找到「Munea」那一格放大 4 倍（給 PR 說明貼的）
  <out>/result.json            判定結果與顏色統計
"""
import argparse
import io
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

DEVICE_DUMP_PATH = '/sdcard/munea-ci-launcher-dump.xml'
APP_LABEL_CANDIDATES = ('Munea', '沐寧')  # android/app/src/main/res/values/strings.xml 的 app_name
ANR_HELPER = Path(__file__).resolve().parent / 'android-ui-tap-by-text.py'

# 顏色判定門檻（佔那一格像素的比例）。xxhdpi 手機上一格約 200×260px、圖示約 158px；
# 橘水滴在圖示裡約 2–4%、漣漪約 1–3%，換算成整格大約 1% 上下，門檻放寬到 0.3%／0.1%
# 讓不同桌面程式的格子大小都過得了，但範本藍 X（一點橘、一點青綠都沒有）絕對過不了。
MIN_ORANGE_RATIO = 0.003
MIN_TEAL_RATIO = 0.001


def adb(*args, check=True):
    return subprocess.run(['adb', *args], check=check, capture_output=True, text=True)


def screencap(path: Path) -> Image.Image:
    raw = subprocess.run(['adb', 'exec-out', 'screencap', '-p'], check=True, capture_output=True).stdout
    path.write_bytes(raw)
    return Image.open(io.BytesIO(raw)).convert('RGB')


def dump_screen(dump_path: Path):
    """撈一次 accessibility tree；撈不到回 None（桌面程式可能還在冷開機，外層會再試）。"""
    subprocess.run(['adb', 'shell', 'rm', '-f', DEVICE_DUMP_PATH], capture_output=True, text=True)
    dumped = subprocess.run(['adb', 'shell', 'uiautomator', 'dump', DEVICE_DUMP_PATH], capture_output=True, text=True)
    pulled = subprocess.run(['adb', 'pull', DEVICE_DUMP_PATH, str(dump_path)], capture_output=True, text=True)
    if dumped.returncode != 0 or pulled.returncode != 0 or not dump_path.exists():
        reason = ' | '.join(s.strip() for s in (dumped.stdout, dumped.stderr, pulled.stderr) if s and s.strip())
        print(f'[WAIT] 這次撈不到畫面（{reason[:200]}）')
        return None
    try:
        root = ET.fromstring(dump_path.read_text(encoding='utf-8', errors='replace'))
    except ET.ParseError as exc:
        print(f'[WAIT] 這次撈到的畫面不完整（{exc}）')
        return None
    nodes = []
    for node in root.iter('node'):
        bounds = node.get('bounds', '')
        if bounds:
            nodes.append({'text': node.get('text', '') or '', 'desc': node.get('content-desc', '') or '', 'bounds': bounds})
    return nodes


def parse_bounds(bounds: str):
    nums = bounds.replace('][', ',').strip('[]').split(',')
    return tuple(int(n) for n in nums)  # x1, y1, x2, y2


def find_app_cell(nodes):
    """桌面／應用程式列表裡 App 那一格：uiautomator 看到的是一個 text=App 名稱的節點，
    bounds 涵蓋圖示＋名稱（Launcher3 的 BubbleTextView 把圖示當文字框的上方圖畫）。"""
    for label in APP_LABEL_CANDIDATES:
        for n in nodes:
            if n['text'] == label or n['desc'] == label:
                return n
    return None


def dismiss_other_apps_anr(dump_path: Path):
    """模擬器桌面程式冷開機會自己「沒有回應」（#630 看到的）；借既有工具只關別人的對話框。"""
    if ANR_HELPER.exists():
        subprocess.run([sys.executable, str(ANR_HELPER), '--dismiss-anr-only', '--dump-path', str(dump_path)])


def screen_size():
    out = adb('shell', 'wm', 'size').stdout
    # 例：「Physical size: 1080x2400」（有 Override size 就以它為準）
    size = None
    for line in out.splitlines():
        if 'size:' in line and 'x' in line:
            w, h = line.split(':', 1)[1].strip().split('x')
            size = (int(w), int(h))
    return size or (1080, 2400)


def open_app_drawer(w: int, h: int):
    # 從桌面中下方往上滑＝打開應用程式列表（Launcher3／Pixel Launcher 通用手勢）。
    # 起點刻意不貼螢幕底邊（底邊往上滑是「回桌面」的系統手勢）。
    adb('shell', 'input', 'swipe', str(w // 2), str(int(h * 0.80)), str(w // 2), str(int(h * 0.25)), '500')


def colour_stats(cell: Image.Image):
    total = cell.width * cell.height
    orange = teal = cream = template_blue = 0
    px = cell.tobytes()
    for r, g, b in zip(px[0::3], px[1::3], px[2::3]):
        if r >= 200 and 120 <= g <= 195 and b <= 135 and r - b >= 80:
            orange += 1  # 橘水滴（實測 240,160,96 一帶）
        elif b >= 215 and r <= 140 and 150 <= g <= 215:
            template_blue += 1  # Capacitor 範本藍 X（實測 80–112,176–192,240）：藍遠高於綠，先判它
        elif g >= 130 and b >= 130 and g - r >= 30 and b - r >= 20 and r < 170 and abs(g - b) <= 40:
            teal += 1  # 青綠漣漪（實測 96–128,160–176,160–176）：綠藍差不多高
        elif abs(r - 254) <= 8 and abs(g - 245) <= 8 and abs(b - 235) <= 8:
            cream += 1  # 奶油底 #FEF5EB
    return {
        'pixels': total,
        'orange_ratio': round(orange / total, 4),
        'teal_ratio': round(teal / total, 4),
        'cream_ratio': round(cream / total, 4),
        'template_blue_ratio': round(template_blue / total, 4),
    }


def capture_cell(shot: Image.Image, node, out_png: Path):
    x1, y1, x2, y2 = parse_bounds(node['bounds'])
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(shot.width, x2), min(shot.height, y2)
    cell = shot.crop((x1, y1, x2, y2))
    cell.resize((cell.width * 4, cell.height * 4), Image.NEAREST).save(out_png, optimize=True)
    return colour_stats(cell)


def wait_for_cell(dump_path: Path, timeout: float, poll: float):
    deadline = time.monotonic() + timeout
    nodes = []
    while True:
        got = dump_screen(dump_path)
        if got is not None:
            nodes = got
            cell = find_app_cell(nodes)
            if cell is not None:
                return cell, nodes
        if time.monotonic() >= deadline:
            return None, nodes
        time.sleep(poll)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out-dir', default='launcher-icon', help='截圖、dump、判定結果都放這裡')
    parser.add_argument('--timeout', type=float, default=30.0, help='應用程式列表裡等「Munea」出現最多幾秒（預設 30）')
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = {'pass': False, 'home': None, 'app_drawer': None, 'problems': []}

    # 1. 回桌面、清掉別人的「沒有回應」對話框、拍桌面
    adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
    time.sleep(3)
    dismiss_other_apps_anr(out / 'home-pre-dump.xml')
    time.sleep(1)
    home_shot = screencap(out / 'home.png')
    home_nodes = dump_screen(out / 'home.xml') or []
    home_cell = find_app_cell(home_nodes)
    if home_cell is not None:
        result['home'] = {'bounds': home_cell['bounds'], **capture_cell(home_shot, home_cell, out / 'munea-icon-closeup-home.png')}
        print(f'[OK] 桌面上有「Munea」捷徑 bounds={home_cell["bounds"]}')
    else:
        print('[INFO] 桌面上沒有「Munea」捷徑（adb 安裝的 App 桌面程式不一定會自動加捷徑，正常），到應用程式列表找')

    # 2. 打開應用程式列表、等「Munea」出現、拍下來
    w, h = screen_size()
    open_app_drawer(w, h)
    time.sleep(2)
    drawer_cell, drawer_nodes = wait_for_cell(out / 'app-drawer.xml', args.timeout, 2.0)
    if drawer_cell is None:
        # 有些桌面程式吃 ALL_APPS intent；手勢沒開成就再試這條路
        subprocess.run(['adb', 'shell', 'am', 'start', '-a', 'android.intent.action.ALL_APPS'], capture_output=True, text=True)
        time.sleep(2)
        drawer_cell, drawer_nodes = wait_for_cell(out / 'app-drawer.xml', 10.0, 2.0)
    drawer_shot = screencap(out / 'app-drawer.png')
    if drawer_cell is not None:
        result['app_drawer'] = {'bounds': drawer_cell['bounds'], **capture_cell(drawer_shot, drawer_cell, out / 'munea-icon-closeup.png')}
        print(f'[OK] 應用程式列表裡找到「Munea」bounds={drawer_cell["bounds"]}')
    else:
        visible = sorted({n['text'] for n in drawer_nodes if n['text']})
        result['problems'].append('app drawer 找不到 Munea')
        print(f'[FAIL] 等了約 {args.timeout:.0f} 秒，應用程式列表裡找不到「Munea」。最後畫面上看得到的文字：', file=sys.stderr)
        for t in visible:
            print(f'  - {t}', file=sys.stderr)

    # 3. 判定：至少一格（桌面或列表）要有橘水滴＋青綠漣漪、而且範本藍不能比橘多
    verdicts = []
    for where in ('home', 'app_drawer'):
        stats = result[where]
        if not stats:
            continue
        ok = (stats['orange_ratio'] >= MIN_ORANGE_RATIO
              and stats['teal_ratio'] >= MIN_TEAL_RATIO
              and stats['template_blue_ratio'] < stats['orange_ratio'])
        verdicts.append(ok)
        print(f'[{"OK" if ok else "FAIL"}] {where}：橘 {stats["orange_ratio"]:.2%}／青綠 {stats["teal_ratio"]:.2%}／'
              f'奶油底 {stats["cream_ratio"]:.2%}／範本藍 {stats["template_blue_ratio"]:.2%}'
              f'（門檻：橘 ≥ {MIN_ORANGE_RATIO:.1%}、青綠 ≥ {MIN_TEAL_RATIO:.1%}、範本藍 < 橘）')
        if not ok:
            result['problems'].append(f'{where} 那格顏色不像官方圖示')
    result['pass'] = bool(verdicts) and any(verdicts)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if result['pass']:
        print('[PASS] 桌面看到的是 Munea 官方圖示（橘水滴＋青綠漣漪），不是範本藍 X')
        return
    print(f'[FAIL] 桌面圖示驗證沒過：{result["problems"]}', file=sys.stderr)
    sys.exit(1)


if __name__ == '__main__':
    main()
