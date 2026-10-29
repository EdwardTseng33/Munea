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
adb shell am force-stop "$PKG" >/dev/null 2>&1 || true
adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 3
# 截圖前清場：模擬器桌面程式（Pixel Launcher）冷開機太慢會自己「沒有回應」、對話框蓋在我們的
# 啟動畫面上（logcat 證實在 App 啟動前就發生）。先把別人的對話框關掉再拍，01 才拍得到
# 原生啟動畫面本人；App 自己的對話框不會被關（工具只關別人的）。
python3 scripts/android-ui-tap-by-text.py --dismiss-anr-only --dump-path "$SHOTS_DIR/01-pre-shot.xml" || true
sleep 1
screenshot "01-launch-3s"
foreground_state "01-launch-3s"
record "啟動 App（等 3 秒、清掉別人的「沒有回應」對話框後再拍）" "有畫面、不是白屏或崩潰對話框（原生啟動畫面＝奶油底＋沐寧標誌，PR #630 起）" "看截圖 01" "01-launch-3s.png"

# 2026-10-28 第四輪：模擬器冷到 App 啟動 15 秒後才看到啟動頁，40 秒差點不夠——放寬到 90 秒
# （找到就立刻往下走，不會真的等滿；這裡的上限只管「最糟要等多久才宣告失敗」）。
echo "== 等底部導覽列出現（最多等 90 秒，不是固定 sleep 賭運氣）=="
if python3 scripts/android-ui-tap-by-text.py --text "聊聊,Talk" --dump-path "$SHOTS_DIR/02-wait-tabbar.xml" --timeout 90; then
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
screenshot "03-chat-view"
record "進入聊聊／通話畫面" "畫面切到聊聊分頁" "看截圖 03" "03-chat-view.png"

echo "== 找「開始通話」按鈕並點下去 =="
if python3 scripts/android-ui-tap-by-text.py --text "開始或結束通話,Start or end call" --dump-path "$SHOTS_DIR/04-tap-call.xml" --timeout 30; then
  sleep 5
  screenshot "05-call-state"
  record "點「開始通話」＋等 5 秒" "畫面會變化；模擬器沒麥克風，預期連不上真語音——只看畫面實際顯示什麼" "看截圖 05，如實記錄" "05-call-state.png"
else
  screenshot "05-call-NOTFOUND"
  foreground_state "05-call-NOTFOUND"
  record "點「開始通話」" "找得到按鈕" "找不到「開始通話」按鈕，看截圖 05 跟上面 log" "05-call-NOTFOUND.png"
  OVERALL_OK=0
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
