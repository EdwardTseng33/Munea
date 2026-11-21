#!/usr/bin/env bash
# 在模擬器上跑 android/reminder-test 的 ReminderFlowTest（跟送 Firebase Test Lab 的是同一組 APK）。
# 兩種情況都要過：
#   normal       ＝ 直向、通知權限還沒給（要真的跳系統視窗點「允許」）
#   granted-land ＝ 螢幕被轉成橫向、通知權限一開始就已給（Firebase Test Lab 預設就是這樣）
set -uo pipefail
APP="$(find apks -name app-debug.apk | head -1)"
TEST="$(find apks -name '*reminder-test*.apk' | head -1)"
echo "app=$APP test=$TEST"
mkdir -p emulator-out
OVERALL=0

run_case() {
  local name="$1" pregrant="$2" landscape="$3"
  echo "=== case: $name (pregrant=$pregrant landscape=$landscape) ==="
  adb uninstall net.munea.app >/dev/null 2>&1 || true
  adb uninstall net.munea.app.remindertest >/dev/null 2>&1 || true
  adb install -r "$APP" && adb install -r "$TEST" || { OVERALL=1; return; }
  adb shell rm -rf /sdcard/screenshots
  if [ "$pregrant" = 1 ]; then adb shell pm grant net.munea.app android.permission.POST_NOTIFICATIONS; fi
  if [ "$landscape" = 1 ]; then
    adb shell settings put system accelerometer_rotation 0
    adb shell settings put system user_rotation 1
  else
    adb shell settings put system accelerometer_rotation 0
    adb shell settings put system user_rotation 0
  fi
  sleep 3
  adb logcat -c || true
  adb logcat -v time > "emulator-out/$name-logcat.txt" 2>&1 &
  local LOG=$!
  adb shell am instrument -w -e class net.munea.app.remindertest.ReminderFlowTest \
    net.munea.app.remindertest/androidx.test.runner.AndroidJUnitRunner | tee "emulator-out/$name-instrument.txt"
  kill $LOG 2>/dev/null || true
  adb pull /sdcard/screenshots "emulator-out/$name-screenshots" || true
  grep MuneaQa "emulator-out/$name-logcat.txt" | cut -c1-400
  grep -q "OK (" "emulator-out/$name-instrument.txt" || OVERALL=1
}

run_case normal 0 0
run_case granted-land 1 1
exit $OVERALL
