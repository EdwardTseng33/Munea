#!/usr/bin/env python3
"""B1 查核點用的 UI 自動化小工具（2026-10-28）——只給 CI 的 Android 流程驗證用，
不是 App 邏輯的一部分，不會被打包進 APK。

用 `adb shell uiautomator dump` 抓目前畫面的 accessibility tree，照文字找可點擊
元素、算出中心座標、用 `adb shell input tap` 點下去。模擬器開機跟 WebView 渲染
速度不固定（software rendering 常常比真機慢很多），所以找不到就等一下重撈一次
畫面，而不是固定 sleep 幾秒就賭運氣。

找文字時故意「完全相同優先」：Munea 首頁同時有「開始聊聊」按鈕跟底部導覽「聊聊」
分頁，兩者都含「聊聊」兩字，若只做 contains 比對會點錯。所以先找 text 完全等於
查詢字串的節點，真的找不到才退而求其次用 contains。

--text 可以用逗號分隔給多個候選字串（例如中文跟英文各一個）：App 的語言是照
Android 系統 locale 自動切換（i18n.js），2026-10-28 第一次實測才發現 GitHub
Actions 的 Android 模擬器預設 locale 是英文，畫面上看到的是「Talk」「Start
call」不是「聊聊」「開始通話」——locale 這端已經在 workflow 裡修了（開機帶
zh-TW 的 boot prop），但留著多候選字串當保險，萬一哪天 runner image 行為又變、
這支腳本不會再整個悶掉找不到元素。

逾時仍找不到就把最後一次畫面上看得到的文字印出來方便除錯，並以非 0 結束——
不要悄悄放過、讓後面步驟假裝成功。

用法：
  python3 scripts/android-ui-tap-by-text.py --text 聊聊,Talk --dump-path flows-shots/03.xml --timeout 40
"""
import argparse
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

DEVICE_DUMP_PATH = '/sdcard/munea-ci-uidump.xml'


def adb(*args):
    return subprocess.run(['adb', *args], check=True, capture_output=True, text=True)


def parse_bounds(bounds):
    # uiautomator 的 bounds 格式："[x1,y1][x2,y2]"
    nums = bounds.replace('][', ',').strip('[]').split(',')
    x1, y1, x2, y2 = (int(n) for n in nums)
    return (x1 + x2) // 2, (y1 + y2) // 2


def collect_nodes(xml_text):
    root = ET.fromstring(xml_text)
    nodes = []
    for node in root.iter('node'):
        bounds = node.get('bounds', '')
        if not bounds:
            continue
        nodes.append({
            'text': node.get('text', '') or '',
            'desc': node.get('content-desc', '') or '',
            'bounds': bounds,
        })
    return nodes


def find_target(nodes, queries):
    # queries 是候選字串清單，依序找「完全相同」，全部候選都找不到完全相同
    # 才退而求其次用 contains（同樣依序找）。這樣不管畫面是中文還是英文，
    # 只要其中一個候選字串完全相同就不會跟別的按鈕搞混。
    for query in queries:
        exact = [n for n in nodes if n['text'] == query or n['desc'] == query]
        if exact:
            return exact[0], f'exact:{query}'
    for query in queries:
        partial = [n for n in nodes if query and (query in n['text'] or query in n['desc'])]
        if partial:
            return partial[0], f'partial:{query}'
    return None, None


# 2026-10-28（PR #630 實跑看到）：模擬器的桌面程式 Pixel Launcher 偶爾會「沒有回應」，
# 系統對話框蓋在最上面——uiautomator 只撈得到那張對話框的三行字，App 本身其實已經畫好了
# （截圖上首頁就在對話框底下）。那是模擬器桌面的事、不是 App 的錯：看到就按「等待」讓它
# 退下去、繼續撈；有按一定印出來留紀錄，不悄悄吞掉。只認「沒有回應」這種系統對話框，
# App 自己的崩潰對話框（keeps stopping）不在此列、照常算失敗。
ANR_TITLE_HINTS = ("isn't responding", "is not responding", "沒有回應", "無回應")
ANR_WAIT_LABELS = ("Wait", "等待")


def dismiss_anr_dialog(nodes):
    titles = [n['text'] for n in nodes if any(h in n['text'] for h in ANR_TITLE_HINTS)]
    if not titles:
        return False
    for n in nodes:
        if n['text'] in ANR_WAIT_LABELS:
            x, y = parse_bounds(n['bounds'])
            print(f'[WARN] 畫面上有系統「沒有回應」對話框 {titles}，按「{n["text"]}」({x},{y}) 讓它退下去再繼續撈')
            adb('shell', 'input', 'tap', str(x), str(y))
            return True
    print(f'[WARN] 畫面上有系統「沒有回應」對話框 {titles}，但找不到「等待」鍵可按')
    return False


def dump_current_screen(dump_path):
    """撈一次畫面；撈不到就回 None（＝「畫面還沒好」，交給外層照 timeout 重試）。

    2026-10-28 第四輪紅的真因：模擬器這次開得特別慢，App 啟動 6 秒後 WebView 還是
    一片白、15 秒後才看到啟動頁。這種時候 `uiautomator dump` 會印 ERROR（拿不到
    idle state／root node）卻以 0 結束、檔案根本沒產出，接著 `adb pull` 才炸——
    等於第一次撈畫面就把整個「等 40 秒」的重試迴圈炸掉，跟固定 sleep 賭運氣沒兩樣。
    所以這裡不把「撈不到」當失敗，印出原因、回 None，讓外層繼續等。
    """
    subprocess.run(['adb', 'shell', 'rm', '-f', DEVICE_DUMP_PATH], capture_output=True, text=True)
    dumped = subprocess.run(['adb', 'shell', 'uiautomator', 'dump', DEVICE_DUMP_PATH],
                            capture_output=True, text=True)
    pulled = subprocess.run(['adb', 'pull', DEVICE_DUMP_PATH, str(dump_path)],
                            capture_output=True, text=True)
    if dumped.returncode != 0 or pulled.returncode != 0 or not Path(dump_path).exists():
        reason = ' | '.join(s.strip() for s in (dumped.stdout, dumped.stderr, pulled.stderr) if s and s.strip())
        print(f'[WAIT] 這次撈不到畫面（{reason[:200]}）——WebView 可能還在載入，稍後再撈')
        return None
    return Path(dump_path).read_text(encoding='utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--text', required=True, help='要找並點下去的按鈕文字，逗號分隔可給多個候選（例如不同語系的翻譯）')
    parser.add_argument('--dump-path', required=True, help='最後一次 accessibility tree dump 的存檔路徑（留證據、方便回看）')
    parser.add_argument('--timeout', type=float, default=40.0, help='最多願意等幾秒（預設 40 秒；模擬器 software rendering 常常比真機慢）')
    parser.add_argument('--poll-interval', type=float, default=2.0, help='每隔幾秒重撈一次畫面（預設 2 秒）')
    args = parser.parse_args()
    queries = [q.strip() for q in args.text.split(',') if q.strip()]
    if not queries:
        print('[FAIL] --text 沒有給出任何候選字串', file=sys.stderr)
        sys.exit(2)

    Path(args.dump_path).parent.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + args.timeout
    attempt = 0
    nodes = []
    while True:
        attempt += 1
        xml_text = dump_current_screen(args.dump_path)
        try:
            nodes = collect_nodes(xml_text) if xml_text else []
        except ET.ParseError as exc:
            # dump 到一半被畫面更新打斷也會給出殘缺的 XML——同樣當「還沒好」處理
            print(f'[WAIT] 這次撈到的畫面不完整（{exc}）——稍後再撈')
            nodes = []
        if dismiss_anr_dialog(nodes):
            time.sleep(1.0)
            continue
        target, match_kind = find_target(nodes, queries)
        if target is not None:
            x, y = parse_bounds(target['bounds'])
            print(f'[OK] 第 {attempt} 次撈畫面找到候選「{queries}」中的「{match_kind}」bounds={target["bounds"]} 中心=({x},{y})')
            adb('shell', 'input', 'tap', str(x), str(y))
            print(f'[OK] 已點下去 ({x},{y})')
            return
        if time.monotonic() >= deadline:
            break
        time.sleep(args.poll_interval)

    visible_texts = sorted({n['text'] for n in nodes if n['text']})
    print(f'[FAIL] 等了約 {args.timeout:.0f} 秒（共撈 {attempt} 次畫面）還是找不到候選文字 {queries} 裡的任何一個可點擊元素。', file=sys.stderr)
    print('最後一次畫面上看得到的文字：', file=sys.stderr)
    for t in visible_texts:
        print(f'  - {t}', file=sys.stderr)
    sys.exit(1)


if __name__ == '__main__':
    main()
