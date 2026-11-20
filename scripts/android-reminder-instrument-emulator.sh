#!/usr/bin/env bash
# 在模擬器上跑 android/reminder-test 的 ReminderFlowTest（跟送 Firebase Test Lab 的是同一組 APK）。
set -uo pipefail
APP="$(find apks -name app-debug.apk | head -1)"
TEST="$(find apks -name '*reminder-test*.apk' | head -1)"
echo "app=$APP test=$TEST"
mkdir -p emulator-out
adb install -r "$APP" && adb install -r "$TEST"
adb logcat -c || true
adb logcat -v time > emulator-out/logcat.txt 2>&1 &
LOG=$!
adb shell am instrument -w -e class net.munea.app.remindertest.ReminderFlowTest \
  net.munea.app.remindertest/androidx.test.runner.AndroidJUnitRunner | tee emulator-out/instrument.txt
RC=${PIPESTATUS[0]}
kill $LOG 2>/dev/null || true
adb pull /sdcard/screenshots emulator-out/screenshots || true
cat emulator-out/screenshots/result.txt 2>/dev/null || true
grep -q "OK (" emulator-out/instrument.txt
