#!/usr/bin/env bash
# B1 查核點：Android「登入、聊聊通話」流程自動化（2026-10-28）
#
# 只在 reactivecircus/android-emulator-runner 的 script 區塊跑，這時模擬器已經
# 開機、adb 已經連上。流程：
#   裝 APK → 開 App → 截圖 → 用 uiautomator 找底部導覽「聊聊」分頁點下去 →
#   截圖 → 找通話鈕點下去 → 等 5 秒 → 截圖
# 模擬器沒有真麥克風（emulator-options 帶 -noaudio），接不上語音是預期內——
# 這一步只看畫面實際顯示什麼，不假裝接通了。
#
# 找按鈕用的字串故意中英文都給（見下面 --text 參數）：這個 runner image 的
# Android 模擬器預設是英文 locale，試過用開機 prop 釘成 zh-TW 但這版
# emulator 不接受（只收 qemu.* 開頭的 prop），所以中英文候選字串才是真正
# 生效的那層（2026-10-28 兩輪真跑才調好，詳見 android-build.yml 裡的註解）。
# 通話鈕那個候選字串是它的 aria-label（「開始或結束通話」），不是按鈕內
# <span> 的可見字「開始通話」——Chrome 的 accessibility bridge 把 aria-label
# 暴露成 uiautomator 看到的 text，已用真實 dump 驗證過。
#
# 故意不用 `set -e`：要讓「找不到按鈕」這類失敗仍然把已經拍到的截圖留下來、
# 把這一步標成 FAIL 寫進步驟表，而不是讓整個 job 在某一步悶不吭聲中斷、
# 後面步驟的截圖全部缺席。

set -uo pipefail

APK_PATH="android/app/build/outputs/apk/debug/app-debug.apk"
PKG="net.munea.app"
SHOTS_DIR="flows-shots"
OVERALL_OK=1

mkdir -p "$SHOTS_DIR"

# 2026-10-28（PR #630 原生啟動畫面）：同一支流程連紅兩輪、兩輪長相不同（一輪是桌面程式
# Pixel Launcher「沒有回應」的系統對話框整路蓋著、一輪是 App 根本沒浮到前景），光看截圖
# 分不出是 App 自己壞還是模擬器桌面卡住。所以全程錄 logcat 進 flows-shots/（跟截圖一起
# 上傳），每個關鍵點再記一份「現在前景是誰」（dumpsys），失敗時才有東西可以查。
adb logcat -c >/dev/null 2>&1 || true
adb logcat -v time > "$SHOTS_DIR/logcat.txt" 2>&1 &
LOGCAT_PID=$!
trap 'kill "$LOGCAT_PID" >/dev/null 2>&1 || true' EXIT

foreground_state() {
  # $1 = 檔名前綴；只記、不判斷——判斷留給看紀錄的人
  {
    echo "== $(date -u +%H:%M:%S) dumpsys window（焦點在哪個視窗）=="
    adb shell dumpsys window 2>/dev/null | grep -E "mCurrentFocus|mFocusedApp|mFocusedWindow|imeInputTarget" | head -8
    echo "== dumpsys activity（哪個畫面在前景）=="
    adb shell dumpsys activity activities 2>/dev/null | grep -E "ResumedActivity|mLastPausedActivity|topResumedActivity|Hist  *#0|mVisibleRequested=true" | head -12
    echo "== App 行程 =="
    adb shell pidof "$PKG" 2>/dev/null || echo "($PKG 沒有在跑)"
  } > "$SHOTS_DIR/$1-foreground.txt" 2>&1
}

declare -a SUMMARY_ROWS=()

record() {
  SUMMARY_ROWS+=("| $1 | $2 | $3 | $4 |")
}

screenshot() {
  adb exec-out screencap -p > "$SHOTS_DIR/$1.png" 2>/dev/null
}

# ── 2026-11-27：確認 App 真的在前景、不在就重開 ───────────────────────────────
# 11/26–27 連兩次紅都是模擬器環境的事、不是 App 壞：
#   - Run 45886062502（PR #706）：monkey 送出啟動那一刻桌面程式 Pixel Launcher「沒有回應」，
#     logcat 根本沒有 `Start proc ... net.munea.app`——App 從頭到尾沒被開起來，畫面停在桌面
#     長按選單，腳本卻白等 90 秒才宣告找不到「聊聊」。
#   - Run 45814586559（PR #755）：點完「聊聊」後畫面變回桌面（沒有崩潰），接著白等 30 秒找通話鈕。
# 兩次重跑都過、同時段別的分支也都過。所以每個「等畫面上的字」之前先確認前景是不是我們：
# 不是就清掉桌面的對話框／選單、用 `am start -n` 指名重開，最多重開 3 次才宣告失敗。
# 不放水的地方：App 自己崩潰或自己「沒有回應」不重開（那是真的 bug，直接 FAIL）；
# 「聊聊」分頁、通話鈕還是一定要找到並點得下去；有重開過會寫進步驟表，不悄悄吞掉。
MAX_RELAUNCH=3
RELAUNCH_COUNT=0
RELAUNCHED_SINCE_CHECK=0
LAUNCH_ACTIVITY=""

resolve_launch_activity() {
  # 例：net.munea.app/.MainActivity；查不到就退回 manifest 裡寫的名字
  LAUNCH_ACTIVITY=$(adb shell cmd package resolve-activity --brief \
      -a android.intent.action.MAIN -c android.intent.category.LAUNCHER "$PKG" 2>/dev/null \
    | tr -d '\r' | grep -E "^$PKG/" | tail -n 1)
  if [ -z "$LAUNCH_ACTIVITY" ]; then
    LAUNCH_ACTIVITY="$PKG/.MainActivity"
    echo "[WARN] 查不到 $PKG 的啟動畫面，退回用 $LAUNCH_ACTIVITY"
  else
    echo "[OK] App 的啟動畫面是 $LAUNCH_ACTIVITY"
  fi
}

launch_app() {
  adb shell am start -W -n "$LAUNCH_ACTIVITY" >/dev/null 2>&1 \
    || adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
}

current_focus() {
  adb shell dumpsys window 2>/dev/null | tr -d '\r' | grep -E "mCurrentFocus" | head -1
}

resumed_activity() {
  adb shell dumpsys activity activities 2>/dev/null | tr -d '\r' \
    | grep -E "topResumedActivity|mResumedActivity|ResumedActivity:" | head -1
}

app_crashed() {
  # logcat 裡有本 App 的 FATAL EXCEPTION ＝ 真的崩潰，不能用重開蓋過去
  [ -s "$SHOTS_DIR/logcat.txt" ] && grep -A2 "FATAL EXCEPTION" "$SHOTS_DIR/logcat.txt" | grep -q "Process: $PKG"
}

# $1 = 檔名前綴（記證據用）。回 0 = App 在前景且沒有對話框擋著；回 1 = 重開 3 次還是不行，或 App 自己壞了
ensure_foreground() {
  local label="$1" try focus resumed
  for try in $(seq 0 "$MAX_RELAUNCH"); do
    focus=$(current_focus)
    resumed=$(resumed_activity)
    case "$focus" in
      *"Not Responding"*"$PKG"*)
        echo "[FAIL] $label：App 自己「沒有回應」（$focus）——這是真的問題，不重開蓋掉"
        foreground_state "$label-app-anr"
        return 1 ;;
      *"Not Responding"*)
        echo "[WARN] $label：別的程式「沒有回應」的系統對話框擋在前面（$focus），先關掉"
        python3 scripts/android-ui-tap-by-text.py --dismiss-anr-only --dump-path "$SHOTS_DIR/$label-anr.xml" || true
        sleep 2
        focus=$(current_focus)
        resumed=$(resumed_activity) ;;
    esac
    if [[ "$resumed" == *"$PKG/"* && "$focus" != *"Not Responding"* ]]; then
      [ "$try" -gt 0 ] && echo "[OK] $label：App 回到前景了（重開 $try 次）"
      return 0
    fi
    if app_crashed; then
      echo "[FAIL] $label：logcat 有 $PKG 的 FATAL EXCEPTION——App 真的崩潰，不重開蓋掉"
      foreground_state "$label-crashed"
      return 1
    fi
    if [ "$try" -ge "$MAX_RELAUNCH" ]; then
      break
    fi
    echo "[WARN] $label：App 不在前景（前景是「${resumed:-看不出來}」、焦點「${focus:-無}」、行程 $(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r' || true)），第 $((try + 1))/$MAX_RELAUNCH 次重開"
    screenshot "$label-relaunch$((try + 1))-before"
    foreground_state "$label-relaunch$((try + 1))-before"
    # 收掉桌面長按選單之類的東西，再回桌面、指名重開
    adb shell input keyevent KEYCODE_BACK >/dev/null 2>&1 || true
    adb shell input keyevent KEYCODE_HOME >/dev/null 2>&1 || true
    sleep 1
    launch_app
    RELAUNCH_COUNT=$((RELAUNCH_COUNT + 1))
    RELAUNCHED_SINCE_CHECK=1
    sleep 3
  done
  echo "[FAIL] $label：重開 $MAX_RELAUNCH 次 App 還是不在前景"
  screenshot "$label-NOT-FOREGROUND"
  foreground_state "$label-NOT-FOREGROUND"
  return 1
}

# 找字並點下去，但每 15 秒確認一次前景——App 中途被丟到背景就重開，不白等到逾時。
# $1 = 候選字串、$2 = dump 檔名前綴、$3 = 最多等幾秒、$4（選填）= 重開過的話要先重點一次的分頁字串
wait_and_tap() {
  local texts="$1" prefix="$2" total="$3" reenter="${4:-}" chunk=15 waited=0
  while [ "$waited" -lt "$total" ]; do
    RELAUNCHED_SINCE_CHECK=0
    if ! ensure_foreground "$prefix"; then
      return 1
    fi
    if [ "$RELAUNCHED_SINCE_CHECK" -eq 1 ] && [ -n "$reenter" ]; then
      echo "[WARN] $prefix：剛重開過 App，先重新點一次「$reenter」分頁"
      python3 scripts/android-ui-tap-by-text.py --text "$reenter" --dump-path "$SHOTS_DIR/$prefix-reenter.xml" --timeout 60 || true
      sleep 2
    fi
    if [ $((total - waited)) -lt "$chunk" ]; then
      chunk=$((total - waited))
    fi
    if python3 scripts/android-ui-tap-by-text.py --text "$texts" --dump-path "$SHOTS_DIR/$prefix.xml" --timeout "$chunk"; then
      return 0
    fi
    waited=$((waited + chunk))
    [ "$waited" -lt "$total" ] && echo "[WAIT] $prefix：已等 ${waited}/${total} 秒還沒找到，先確認 App 還在前景再繼續等"
  done
  foreground_state "$prefix-timeout"
  return 1
}

echo "== 裝 APK =="
if adb install -r "$APK_PATH"; then
  record "裝 APK" "APK 裝得上" "成功" "-"
else
  record "裝 APK" "APK 裝得上" "失敗：adb install 噴錯，看上面 log" "-"
  OVERALL_OK=0
fi

# 錄音是 dangerous permission，第一次呼叫會跳系統對話框擋住畫面。這裡預先
# grant 掉，讓自動化流程看到的是「App 內的通話畫面」而不是「系統權限詢問」——
# 這跟真人第一次點「開始通話」的體驗不同，所以在測試紀錄裡會特別註明這一點，
# 不是要假裝這個系統對話框不存在。
adb shell pm grant "$PKG" android.permission.RECORD_AUDIO >/dev/null 2>&1 || true

echo "== 啟動 App =="
resolve_launch_activity
adb shell am force-stop "$PKG" >/dev/null 2>&1 || true
launch_app
sleep 3
# 截圖前清場：模擬器桌面程式（Pixel Launcher）冷開機太慢會自己「沒有回應」、對話框蓋在我們的
# 啟動畫面上（logcat 證實在 App 啟動前就發生）。先把別人的對話框關掉再拍，01 才拍得到
# 原生啟動畫面本人；App 自己的對話框不會被關（工具只關別人的）。
python3 scripts/android-ui-tap-by-text.py --dismiss-anr-only --dump-path "$SHOTS_DIR/01-pre-shot.xml" || true
sleep 1
# 確認真的開起來了（11/26 那次 App 根本沒被開，畫面停在桌面長按選單）
ensure_foreground "01-launch" || true
screenshot "01-launch-3s"
foreground_state "01-launch-3s"
record "啟動 App（等 3 秒、清掉別人的「沒有回應」對話框後再拍）" "有畫面、不是白屏或崩潰對話框（原生啟動畫面＝奶油底＋沐寧標誌，PR #630 起）" "看截圖 01" "01-launch-3s.png"

# 2026-10-28 第四輪：模擬器冷到 App 啟動 15 秒後才看到啟動頁，40 秒差點不夠——放寬到 90 秒
# （找到就立刻往下走，不會真的等滿；這裡的上限只管「最糟要等多久才宣告失敗」）。
echo "== 等底部導覽列出現（最多等 90 秒，不是固定 sleep 賭運氣）=="
if wait_and_tap "聊聊,Talk" "02-wait-tabbar" 90; then
  screenshot "02-home-ready"
  foreground_state "02-home-ready"
  record "等首頁渲染完成" "底部導覽列（含「聊聊」分頁）出現" "成功，看截圖 02" "02-home-ready.png"
else
  screenshot "02-home-NOTFOUND"
  foreground_state "02-home-NOTFOUND"
  record "等首頁渲染完成" "底部導覽列（含「聊聊」分頁）出現" "逾時沒等到，看截圖 02 跟上面 log 列出的可見文字" "02-home-NOTFOUND.png"
  OVERALL_OK=0
fi

echo "== 已經點過上面那次了（找「聊聊」同時完成「等待」跟「點擊」）=="
sleep 2
# 11/27 那次點完「聊聊」畫面變回桌面：重開後回到聊聊分頁再拍
RELAUNCHED_SINCE_CHECK=0
if ensure_foreground "03-chat-view" && [ "$RELAUNCHED_SINCE_CHECK" -eq 1 ]; then
  python3 scripts/android-ui-tap-by-text.py --text "聊聊,Talk" --dump-path "$SHOTS_DIR/03-reenter.xml" --timeout 60 || true
  sleep 2
fi
screenshot "03-chat-view"
record "進入聊聊／通話畫面" "畫面切到聊聊分頁" "看截圖 03" "03-chat-view.png"

echo "== 找「開始通話」按鈕並點下去 =="
if wait_and_tap "開始或結束通話,Start or end call" "04-tap-call" 30 "聊聊,Talk"; then
  sleep 5
  screenshot "05-call-state"
  record "點「開始通話」＋等 5 秒" "畫面會變化；模擬器沒麥克風，預期連不上真語音——只看畫面實際顯示什麼" "看截圖 05，如實記錄" "05-call-state.png"
else
  screenshot "05-call-NOTFOUND"
  foreground_state "05-call-NOTFOUND"
  record "點「開始通話」" "找得到按鈕" "找不到「開始通話」按鈕，看截圖 05 跟上面 log" "05-call-NOTFOUND.png"
  OVERALL_OK=0
fi

if [ "$RELAUNCH_COUNT" -gt 0 ]; then
  record "模擬器環境：App 被丟到背景" "App 一直在前景" "過程中 App 不在前景、腳本重開了 ${RELAUNCH_COUNT} 次（模擬器桌面卡住，不是 App 崩潰；崩潰不會重開），看 *-relaunch*-before 截圖" "-"
fi

# 讓 logcat 把最後幾行寫完再收；失敗時順手把 ANR／崩潰／啟動畫面相關的行印進 job log，
# 不用先下載 artifact 才看得到
sleep 1
kill "$LOGCAT_PID" >/dev/null 2>&1 || true
if [ "$OVERALL_OK" -ne 1 ] && [ -s "$SHOTS_DIR/logcat.txt" ]; then
  echo "== logcat 裡跟 ANR／崩潰／啟動畫面／本 App 有關的行（完整檔在 artifact flows-shots/logcat.txt）=="
  grep -E "ANR in|FATAL EXCEPTION|AndroidRuntime|SplashScreen|StartingSurface|StartingWindow|net\.munea|Capacitor|chromium" "$SHOTS_DIR/logcat.txt" | head -150
fi

{
  echo "## Android 登入／聊聊通話流程測試（B1 查核點）"
  echo ""
  echo "環境：API 34 模擬器（google_apis / x86_64）、direct 測試機開發包（autoSignIn，"
  echo "本機合成 session，沒呼叫真 Supabase、沒用任何密碼或金鑰）、brain/voice 指向 staging。"
  echo ""
  echo "| 步驟 | 預期 | 實際 | 截圖 |"
  echo "|---|---|---|---|"
  for row in "${SUMMARY_ROWS[@]}"; do
    echo "$row"
  done
  echo ""
  if [ "$OVERALL_OK" -eq 1 ]; then
    echo "**整體：每一步都找得到按鈕、點得下去，UI 自動化這層沒有卡住。**"
  else
    echo "**整體：至少一步找不到元素或裝不上，詳情看上表跟截圖、不要當作全部通過。**"
  fi
} >> "$GITHUB_STEP_SUMMARY"

if [ "$OVERALL_OK" -ne 1 ]; then
  exit 1
fi
