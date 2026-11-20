#!/usr/bin/env bash
# 補助案 B2「提醒」流程：Android 模擬器上真的排一個提醒、關掉 App、看通知有沒有跳出來（2026-11-20）
#
# 只在 reactivecircus/android-emulator-runner 的 script 區塊跑（模擬器已開機、adb 已連上）。
# 走的是使用者真的會走的路，不是直接呼叫外掛：
#   1. App 自己的說明卡（askInContext('medication')，跟剛設定好用藥提醒時跳的同一張）→ 點「好，開通知」
#   2. Android 13+ 系統問「要不要允許通知」→ 點「允許」
#   3. 寫一筆「早餐後」的藥、把早餐時間調成「約 2 分鐘後就是早餐後 30 分」→ notify.js 照平常排程
#   4. 回桌面、把 App 行程結束（am kill＝跟從最近使用滑掉／系統回收記憶體一樣；
#      不用 force-stop：那是「設定 → 強制停止」，Android 設計上會連鬧鐘一起清掉）
#   5. 等通知跳出來 → 拉下通知列截圖 → 點通知 → 確認打開的是用藥那一頁
#   6. 再排一個 → 模擬器重開機、不開 App → 等通知跳出來（重開機後提醒還在）
#
# 執行 JS 用 scripts/android-webview-eval.mjs（debug 包的 WebView 遠端偵錯）。
# 故意不用 set -e：哪一步壞了要照實記在表上、後面能拍的照樣拍。

set -uo pipefail

APK_PATH="${1:-./apk-download/app-debug.apk}"
PKG="net.munea.app"
SHOTS_DIR="reminder-shots"
PORT=9222
OVERALL_OK=1
mkdir -p "$SHOTS_DIR"

adb logcat -c >/dev/null 2>&1 || true
adb logcat -v time > "$SHOTS_DIR/logcat.txt" 2>&1 &
LOGCAT_PID=$!
trap 'kill "$LOGCAT_PID" >/dev/null 2>&1 || true' EXIT

declare -a SUMMARY_ROWS=()
record() { SUMMARY_ROWS+=("| $1 | $2 | $3 | $4 |"); echo "[record] $1 → $3"; }
shot() { adb exec-out screencap -p > "$SHOTS_DIR/$1.png" 2>/dev/null; }
device_now() { adb shell date +%s | tr -d '\r'; }
tap_text() { python3 scripts/android-ui-tap-by-text.py --text "$1" --dump-path "$SHOTS_DIR/$2.xml" --timeout "${3:-30}"; }

connect_webview() {
  # App 每次重開 pid 都不同，devtools 的 socket 名字跟著 pid 走
  local pid="" socket="" i
  if [ -z "$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r')" ]; then
    adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
    sleep 8
  fi
  for i in $(seq 1 45); do
    pid="$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
    if [ -n "$pid" ] && adb shell cat /proc/net/unix 2>/dev/null | grep -q "webview_devtools_remote_$pid"; then
      socket="webview_devtools_remote_$pid"
      break
    fi
    sleep 2
  done
  if [ -z "$socket" ]; then echo "devtools socket not found (pid=$pid)"; return 1; fi
  adb forward --remove "tcp:$PORT" >/dev/null 2>&1 || true
  adb forward "tcp:$PORT" "localabstract:$socket" >/dev/null
  for i in $(seq 1 30); do
    if node scripts/android-webview-eval.mjs --port "$PORT" --timeout 10 --expr "!!(window.MuneaNotify && window.MuneaAndroidNotify)" 2>/dev/null | grep -q true; then
      return 0
    fi
    sleep 2
  done
  echo "MuneaNotify never appeared in the WebView"
  return 1
}

focus_line() { adb shell dumpsys window 2>/dev/null | grep -E 'mCurrentFocus' | head -1 | tr -d '\r'; }

ensure_front() {
  # 第一輪 CI（#735 abcef7a229）App 在步驟中間被換到背景、偵錯連線跟著斷；
  # 每次跑 JS 前確認 App 在最前面，不在就叫回來（singleTask，不會重開），並記下來。
  local focus
  focus="$(focus_line)"
  if ! echo "$focus" | grep -q "$PKG"; then
    echo "$(date -u +%H:%M:%S) App 不在前景（$focus），叫回來" | tee -a "$SHOTS_DIR/foreground-log.txt"
    adb shell am start -n "$PKG/.MainActivity" >/dev/null 2>&1
    sleep 4
  fi
}

js() {
  local out
  ensure_front
  if out="$(node scripts/android-webview-eval.mjs --port "$PORT" --timeout "${2:-60}" --expr "$1" 2>>"$SHOTS_DIR/js-errors.txt")"; then
    echo "$out"; return 0
  fi
  # 偵錯連線斷了（App 重開 pid 變了之類）→ 重接一次再試
  connect_webview >/dev/null 2>&1 || true
  node scripts/android-webview-eval.mjs --port "$PORT" --timeout "${2:-60}" --expr "$1" 2>>"$SHOTS_DIR/js-errors.txt"
}

wait_for_notification() {
  # $1 = 不早於這個裝置時間（秒）才算；$2 = 最多等到這個裝置時間；$3 = 存檔前綴
  local since="$1" until_ts="$2" prefix="$3" now
  while true; do
    now="$(device_now)"
    adb shell dumpsys notification --noredact 2>/dev/null > "$SHOTS_DIR/$prefix-dumpsys.txt"
    if grep -q "pkg=$PKG" "$SHOTS_DIR/$prefix-dumpsys.txt" && grep -q "munea-reminders" "$SHOTS_DIR/$prefix-dumpsys.txt"; then
      echo "$now"
      return 0
    fi
    if [ "$now" -ge "$until_ts" ]; then return 1; fi
    sleep 5
  done
}

schedule_breakfast_reminder() {
  # 回傳 JSON：{ targetEpoch, pendingCount, earliest }
  js "
    const now = new Date();
    const target = new Date(now.getTime() + ${1:-150} * 1000); target.setSeconds(0, 0);
    if (target.getTime() - now.getTime() < 90000) target.setMinutes(target.getMinutes() + 1);
    const meal = new Date(target.getTime() - 30 * 60000);
    const hhmm = (d) => String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    localStorage.setItem('munea.meds', JSON.stringify([{ id: 'ci-med', name: 'CI 測試藥', time: '早餐後' }]));
    localStorage.setItem('munea.routine', JSON.stringify(Object.assign(JSON.parse(localStorage.getItem('munea.routine') || '{}'), { b: hhmm(meal) })));
    MuneaNotify.sync();
    await new Promise((r) => setTimeout(r, 4000));
    const pending = await Capacitor.Plugins.LocalNotifications.getPending();
    const ours = (pending.notifications || []).filter((n) => n.extra && n.extra.source === 'munea.local');
    const times = ours.map((n) => new Date(n.schedule.at).getTime()).sort((a, b) => a - b);
    return { targetEpoch: Math.round(target.getTime() / 1000), targetLocal: target.toString(), pendingCount: ours.length,
             earliest: times.length ? new Date(times[0]).toString() : null, sample: ours[0] || null };
  "
}

echo "== 裝 APK、開 App =="
adb install -r "$APK_PATH" && record "裝 APK" "裝得上" "成功" "-" || { record "裝 APK" "裝得上" "失敗" "-"; OVERALL_OK=0; }
adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 8
python3 scripts/android-ui-tap-by-text.py --dismiss-anr-only --dump-path "$SHOTS_DIR/00-pre.xml" || true

if connect_webview; then
  STATE="$(js "({ platform: Capacitor.getPlatform(), available: MuneaNotify.available(), permission: await Capacitor.Plugins.LocalNotifications.checkPermissions(), sdk: navigator.userAgent })")"
  echo "$STATE" > "$SHOTS_DIR/00-state.json"
  record "App 起來、提醒橋接上" "platform=android、available=true、權限還沒問（prompt）" "\`$(echo "$STATE" | head -c 160)\`" "00-state.json"
  echo "$STATE" | grep -q '"available":true' || OVERALL_OK=0
else
  record "App 起來、提醒橋接上" "接得上 WebView" "接不上" "logcat.txt"
  OVERALL_OK=0
fi
shot "00-launch"
# 新裝的 App 第一次打開會先播三頁開場介紹，蓋在所有畫面上面（第一輪 CI 說明卡就是被它蓋住）。
# 真人是看完介紹、設定好用藥之後才會遇到說明卡，這裡記成「介紹看過了」再往下。
js "localStorage.setItem('munea.onboardingIntroSeen.v1', 'true'); const intro = document.getElementById('onboarding'); if (intro) intro.hidden = true; return true" > /dev/null
sleep 2
shot "00-home"

echo "== 1. App 自己的說明卡（設定提醒時才問，不是一開 App 就問）=="
js "localStorage.removeItem('munea.notification.askInContext.medication'); await MuneaNotify.askInContext('medication'); return !!document.querySelector('#pushAskModal.show')" > "$SHOTS_DIR/01-card.json" 2>&1
sleep 2
shot "01-ask-card"
CARD_OK=0
# 說明卡的「好，開通知」用 JS 按（按鈕的字「Yes, turn on」有逗號，點字工具會拆錯；第一輪就點到別的東西）。
# 按下去之後跳的系統權限視窗照樣用真的點擊。
if grep -q true "$SHOTS_DIR/01-card.json" && js "const b = document.getElementById('pushAskAccept'); if (!b) return false; b.click(); return true" | grep -q true; then
  CARD_OK=1
  record "App 說明卡" "跳出「要在吃藥時間提醒你，需要先打開通知」＋按「好，開通知」" "成功" "01-ask-card.png"
else
  record "App 說明卡" "跳出說明卡並點得到「好，開通知」" "沒找到，改直接請 App 要權限（MuneaNotify.requestPermission）" "01-ask-card.png"
  js "window.__ciPerm = MuneaNotify.requestPermission(); return 'asked'" >/dev/null 2>&1
  OVERALL_OK=0
fi

echo "== 2. 系統通知權限視窗 =="
sleep 3
shot "02-system-permission"
if tap_text "Allow,允許" "02-tap-allow" 30; then
  record "Android 系統問通知權限" "出現系統視窗、點「允許」" "成功" "02-system-permission.png"
else
  record "Android 系統問通知權限" "出現系統視窗、點「允許」" "沒找到「允許」按鈕" "02-system-permission.png"
  OVERALL_OK=0
fi
sleep 3
PERM="$(js "({ permission: await MuneaNotify.permissionStatus(), settings: JSON.parse(localStorage.getItem('munea.notification.settings.v1') || 'null') })")"
echo "$PERM" > "$SHOTS_DIR/02-permission.json"
if echo "$PERM" | grep -q '"granted":true' && echo "$PERM" | grep -q '"pushEnabled":true'; then
  record "權限結果" "granted＝true、App 通知總開關打開" "成功" "02-permission.json"
else
  record "權限結果" "granted＝true、App 通知總開關打開" "\`$(echo "$PERM" | head -c 160)\`" "02-permission.json"
  # 說明卡沒走成時，直接把 App 的通知開關打開再往下測排程
  js "localStorage.setItem('munea.notification.settings.v1', JSON.stringify({ pushEnabled: true, categories: { medication: true, clinic: true, family: true, safety: true } })); await MuneaNotify.boot(); return true" >/dev/null 2>&1
  OVERALL_OK=0
fi

echo "== 3. 排一個約 2 分鐘後的用藥提醒（走 notify.js 平常的排程）=="
SCHED="$(schedule_breakfast_reminder 150)"
echo "$SCHED" > "$SHOTS_DIR/03-scheduled.json"
TARGET="$(echo "$SCHED" | python3 -c 'import json,sys; print(json.load(sys.stdin)["targetEpoch"])' 2>/dev/null || echo 0)"
adb shell dumpsys alarm 2>/dev/null | grep -B1 -A6 "$PKG" > "$SHOTS_DIR/03-alarms.txt" || true
shot "03-scheduled"
if [ "$TARGET" -gt 0 ] && echo "$SCHED" | grep -q '"pendingCount":1[0-9]'; then
  record "排程" "早餐後的藥展開成未來 14 天、最近一則在約 2 分鐘後" "成功：\`$(echo "$SCHED" | head -c 200)\`" "03-scheduled.json / 03-alarms.txt"
else
  record "排程" "早餐後的藥展開成未來 14 天" "\`$(echo "$SCHED" | head -c 200)\`" "03-scheduled.json"
  OVERALL_OK=0
fi

echo "== 4. 回桌面、結束 App 行程 =="
adb shell input keyevent KEYCODE_HOME
sleep 2
adb shell am kill "$PKG"
sleep 3
# 第二輪 CI：am kill 在模擬器上沒收掉（App 還在跑），App 只是「在背景」不算「關著」。
# 改用 App 自己的身分把行程結束（debug 包才能 run-as）——等同系統回收記憶體把它清掉，
# 一樣不是 force-stop，鬧鐘不會被清。
APP_PID="$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
if [ -n "$APP_PID" ]; then
  adb shell run-as "$PKG" kill -9 $APP_PID >/dev/null 2>&1 || true
  sleep 3
fi
if [ -z "$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r')" ]; then
  record "關掉 App" "App 行程不在了（等同滑掉／被系統回收；不是強制停止）" "成功：pidof 查不到 App" "-"
else
  record "關掉 App" "App 行程不在了" "還在跑（收不掉），這一輪只證明得了「在背景」" "-"
  OVERALL_OK=0
fi
shot "04-home-app-closed"

echo "== 5. 等通知跳出來 =="
if [ "$TARGET" -gt 0 ] && SEEN="$(wait_for_notification "$TARGET" $((TARGET + 420)) 05)"; then
  DELAY=$((SEEN - TARGET))
  FOCUS="$(adb shell dumpsys window 2>/dev/null | grep -E 'mCurrentFocus' | head -1 | tr -d '\r')"
  adb shell cmd statusbar expand-notifications >/dev/null 2>&1
  sleep 3
  shot "05-notification-fired"
  record "App 關著，提醒時間到" "通知跳出來（沐寧提醒／解鎖後查看，不顯示藥名）" "成功：比預定晚 ${DELAY} 秒（每 5 秒查一次）；當時前景：${FOCUS}" "05-notification-fired.png / 05-dumpsys.txt"
  echo "== 點通知 =="
  if tap_text "Munea reminder,沐寧提醒" "05-tap-notification" 20; then
    sleep 10
    shot "06-opened-from-notification"
    if connect_webview; then
      VIEW="$(js "({ activeTab: (document.querySelector('.tab-btn.active') || {}).dataset ? document.querySelector('.tab-btn.active').dataset.view : null, activeScreen: (document.querySelector('.screen.active') || {}).id || null })")"
      echo "$VIEW" > "$SHOTS_DIR/06-view.json"
      if echo "$VIEW" | grep -q '"status"'; then
        record "點通知" "打開 App、直接到用藥那一頁（status）" "成功：\`$VIEW\`" "06-opened-from-notification.png"
      else
        record "點通知" "打開 App、直接到用藥那一頁（status）" "App 打開了，但頁面是 \`$VIEW\`" "06-opened-from-notification.png"
        OVERALL_OK=0
      fi
    else
      record "點通知" "打開 App" "接不上 WebView" "06-opened-from-notification.png"
      OVERALL_OK=0
    fi
  else
    record "點通知" "通知列找得到「沐寧提醒」並點得下去" "沒找到" "05-notification-fired.png"
    OVERALL_OK=0
  fi
else
  shot "05-notification-NOTFOUND"
  record "App 關著，提醒時間到" "通知跳出來" "預定時間後 7 分鐘內沒看到" "05-notification-NOTFOUND.png / 05-dumpsys.txt"
  OVERALL_OK=0
fi

echo "== 6. 重開機後提醒還在 =="
if connect_webview; then
  SCHED2="$(schedule_breakfast_reminder 300)"
  echo "$SCHED2" > "$SHOTS_DIR/07-scheduled-before-reboot.json"
  TARGET2="$(echo "$SCHED2" | python3 -c 'import json,sys; print(json.load(sys.stdin)["targetEpoch"])' 2>/dev/null || echo 0)"
  adb shell cmd notification cancel_all "$PKG" >/dev/null 2>&1 || true
  adb shell input keyevent KEYCODE_HOME
  echo "reboot at $(device_now), target $TARGET2"
  adb reboot
  sleep 10
  adb wait-for-device
  for i in $(seq 1 90); do
    [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ] && break
    sleep 2
  done
  sleep 15
  python3 scripts/android-ui-tap-by-text.py --dismiss-anr-only --dump-path "$SHOTS_DIR/08-pre.xml" || true
  APP_PID="$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r')"
  echo "booted at $(device_now); app pid after boot: ${APP_PID:-none}"
  if [ "$TARGET2" -gt 0 ] && SEEN2="$(wait_for_notification "$TARGET2" $((TARGET2 + 420)) 08)"; then
    adb shell cmd statusbar expand-notifications >/dev/null 2>&1
    sleep 3
    shot "08-notification-after-reboot"
    record "重開機（沒有打開 App）" "提醒照樣跳出來" "成功：比預定晚 $((SEEN2 - TARGET2)) 秒" "08-notification-after-reboot.png / 08-dumpsys.txt"
  else
    shot "08-after-reboot-NOTFOUND"
    record "重開機（沒有打開 App）" "提醒照樣跳出來" "預定時間後 7 分鐘內沒看到" "08-after-reboot-NOTFOUND.png / 08-dumpsys.txt"
    OVERALL_OK=0
  fi
else
  record "重開機" "先排一個提醒" "接不上 WebView，這段沒跑" "-"
  OVERALL_OK=0
fi

sleep 1
kill "$LOGCAT_PID" >/dev/null 2>&1 || true
grep -E "Capacitor/LocalNotification|LN|LocalNotification|FATAL EXCEPTION|AndroidRuntime" "$SHOTS_DIR/logcat.txt" 2>/dev/null | head -80 > "$SHOTS_DIR/logcat-reminder-lines.txt" || true

{
  echo "## Android 提醒流程（補助案 B2）：排提醒 → 關 App → 通知跳出 → 點開 → 重開機"
  echo ""
  echo "環境：API 34 模擬器（google_apis / x86_64 / Pixel 6）、正式設定的 debug APK（沒登入、沒用任何鑰匙）。"
  echo "權限是真的從 App 說明卡→系統視窗點「允許」，不是 adb 直接給。"
  echo ""
  echo "| 步驟 | 預期 | 實際 | 證據 |"
  echo "|---|---|---|---|"
  for row in "${SUMMARY_ROWS[@]}"; do echo "$row"; done
  echo ""
  if [ -s "$SHOTS_DIR/foreground-log.txt" ]; then
    echo "App 中途不在前景、被叫回來的紀錄（測試環境狀況，照實列出）："
    sed 's/^/- /' "$SHOTS_DIR/foreground-log.txt"
    echo ""
  fi
  if [ "$OVERALL_OK" -eq 1 ]; then echo "**整體：每一步都照預期。**"; else echo "**整體：至少一步沒照預期，看上表與截圖，不要當成全部通過。**"; fi
} | tee "$SHOTS_DIR/summary.md" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

[ "$OVERALL_OK" -eq 1 ] || exit 1
