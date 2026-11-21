#!/usr/bin/env bash
# 登入／聊聊／家人圈測試骨架在免費模擬器上的驗證（公開程式庫：不放任何帳密）。
# 情況 A：沒給帳密 → 必須乾淨 FAIL（訊息含「缺 qaEmail」），而且很快結束。
# 情況 B：fakeSession=1（本機假證，不碰帳密）→ 驗畫面流程（登入後首頁、聊聊撥號、告知頁／話題頁處理、家人頁、家人圈視窗）。
#         撥號會連不上（假證拿不到通話憑證），這是預期內；只要求測試不當機、步驟都有記錄。
set -uo pipefail
APP="$(find apks -name app-debug.apk | head -1)"
TEST="$(find apks -name '*reminder-test*.apk' | head -1)"
mkdir -p emulator-out
adb install -r "$APP" && adb install -r "$TEST" || exit 1
OVERALL=0
run() {
  local name="$1"; shift
  adb shell rm -rf /sdcard/screenshots
  adb logcat -c || true
  adb logcat -v time > "emulator-out/$name-logcat.txt" 2>&1 &
  local LOG=$!
  adb shell am instrument -w "$@" net.munea.app.remindertest/androidx.test.runner.AndroidJUnitRunner | tee "emulator-out/$name-instrument.txt"
  kill $LOG 2>/dev/null || true
  adb pull /sdcard/screenshots "emulator-out/$name-screenshots" || true
  grep MuneaQa "emulator-out/$name-logcat.txt" | cut -c1-420
}
echo "=== A: no credentials ==="
START=$(date +%s)
run no-creds -e class net.munea.app.remindertest.LoginChatFamilyTest#test1_login
ELAPSED=$(( $(date +%s) - START ))
grep -q "缺 qaEmail" emulator-out/no-creds-logcat.txt || { echo "FAIL: A 沒有乾淨的缺帳密訊息"; OVERALL=1; }
grep -q "FAILURES" emulator-out/no-creds-instrument.txt || { echo "FAIL: A 應該要失敗"; OVERALL=1; }
[ "$ELAPSED" -lt 120 ] || { echo "FAIL: A 太慢 ($ELAPSED s)"; OVERALL=1; }
echo "=== B: fake session ==="
run fake-session -e class net.munea.app.remindertest.LoginChatFamilyTest -e fakeSession 1 -e inviteOnModel none -e callSeconds 5
grep -q "PASS 登入" emulator-out/fake-session-logcat.txt || { echo "FAIL: B 假證登入沒過"; OVERALL=1; }
grep -q "CALL-STATE" emulator-out/fake-session-logcat.txt || { echo "FAIL: B 沒跑到撥號"; OVERALL=1; }
grep -q "PASS 家人頁打得開" emulator-out/fake-session-logcat.txt || { echo "FAIL: B 家人頁沒開"; OVERALL=1; }
exit $OVERALL
