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
screenshot "01-launch-3s"
record "啟動 App（等 3 秒）" "有畫面、不是白屏或崩潰對話框" "看截圖 01" "01-launch-3s.png"

echo "== 等底部導覽列出現（最多等 40 秒，不是固定 sleep 賭運氣）=="
if python3 scripts/android-ui-tap-by-text.py --text "聊聊,Talk" --dump-path "$SHOTS_DIR/02-wait-tabbar.xml" --timeout 40; then
  screenshot "02-home-ready"
  record "等首頁渲染完成" "底部導覽列（含「聊聊」分頁）出現" "成功，看截圖 02" "02-home-ready.png"
else
  screenshot "02-home-NOTFOUND"
  record "等首頁渲染完成" "底部導覽列（含「聊聊」分頁）出現" "逾時沒等到，看截圖 02 跟上面 log 列出的可見文字" "02-home-NOTFOUND.png"
  OVERALL_OK=0
fi

echo "== 已經點過上面那次了（找「聊聊」同時完成「等待」跟「點擊」）=="
sleep 2
screenshot "03-chat-view"
record "進入聊聊／通話畫面" "畫面切到聊聊分頁" "看截圖 03" "03-chat-view.png"

echo "== 找「開始通話」按鈕並點下去 =="
if python3 scripts/android-ui-tap-by-text.py --text "開始或結束通話,Start or end call" --dump-path "$SHOTS_DIR/04-tap-call.xml" --timeout 15; then
  sleep 5
  screenshot "05-call-state"
  record "點「開始通話」＋等 5 秒" "畫面會變化；模擬器沒麥克風，預期連不上真語音——只看畫面實際顯示什麼" "看截圖 05，如實記錄" "05-call-state.png"
else
  screenshot "05-call-NOTFOUND"
  record "點「開始通話」" "找得到按鈕" "找不到「開始通話」按鈕，看截圖 05 跟上面 log" "05-call-NOTFOUND.png"
  OVERALL_OK=0
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
