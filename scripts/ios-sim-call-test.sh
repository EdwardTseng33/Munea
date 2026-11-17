#!/usr/bin/env bash
# iOS simulator call test (test branch only).
# Installs the simulator build, lets the injected scenario (scripts/ios-sim-scenario.js) drive
# the App, and plays the part of the thumb: sends the App to the background and brings it back.
#
# The host runs on a FIXED TIMETABLE (seconds after launch). Run 3 showed that reading the App's
# console to decide when to act lags badly (the stream is buffered), so the timetable is the
# master and the scenario simply reacts to being hidden/shown. The console is still recorded.
# Never fails the job on a product finding: the point is to see what really happens.
set -uo pipefail

OUT="${OUT:-ios-sim-out}"
APP_PATH="${APP_PATH:?APP_PATH is required}"
BUNDLE="net.munea.app"
mkdir -p "$OUT"
CONSOLE="$OUT/app-console.txt"
: > "$CONSOLE"

echo "== pick simulator =="
UDID="$(xcrun simctl list devices available -j | python3 -c '
import json, sys
d = json.load(sys.stdin)["devices"]
best = None
for runtime, devs in d.items():
    if "iOS" not in runtime:
        continue
    ver = tuple(int(x) for x in runtime.split("iOS-")[-1].split("-") if x.isdigit())
    for dev in devs:
        name = dev.get("name", "")
        if not name.startswith("iPhone") or not dev.get("isAvailable", True):
            continue
        plain = all(tag not in name for tag in ("Pro", "Plus", "SE", "Air", "mini"))
        score = (ver, 1 if plain else 0, name)
        if best is None or score > best[0]:
            best = (score, dev["udid"], name, runtime)
print(best[1] if best else "")
sys.stderr.write("picked: %s on %s\n" % (best[2], best[3]) if best else "none\n")
')"
if [ -z "$UDID" ]; then echo "no iPhone simulator available"; xcrun simctl list devices available; exit 1; fi
echo "UDID=$UDID"

xcrun simctl boot "$UDID" || true
xcrun simctl bootstatus "$UDID" -b || true
open -a Simulator --args -CurrentDeviceUDID "$UDID" >/dev/null 2>&1 || true
sleep 5

echo "== install =="
xcrun simctl install "$UDID" "$APP_PATH" || { echo "install failed"; exit 1; }
xcrun simctl privacy "$UDID" grant microphone "$BUNDLE" || true

T0=$(date +%s)
shot() { xcrun simctl io "$UDID" screenshot "$OUT/$1.png" >/dev/null 2>&1 || echo "screenshot $1 failed"; echo "  shot $1 at $(( $(date +%s) - T0 ))s"; }
to_background() { xcrun simctl launch "$UDID" com.apple.Preferences >/dev/null 2>&1 || echo "could not open Settings"; echo "  -> background at $(( $(date +%s) - T0 ))s"; }
to_foreground() { xcrun simctl launch "$UDID" "$BUNDLE" >/dev/null 2>&1 || echo "could not bring App back"; echo "  -> foreground at $(( $(date +%s) - T0 ))s"; }
at() { # sleep until N seconds after launch
  local now=$(( $(date +%s) - T0 ))
  if [ "$now" -lt "$1" ]; then sleep $(( $1 - now )); fi
}

echo "== launch =="
# A pty around simctl keeps the console stream flowing line by line instead of in big late chunks.
python3 -c '
import pty, sys
pty.spawn(["xcrun", "simctl", "launch", "--console-pty", sys.argv[1], sys.argv[2],
           "-AppleLanguages", "(zh-Hant-TW)", "-AppleLocale", "zh_TW"])
' "$UDID" "$BUNDLE" >> "$CONSOLE" 2>&1 < /dev/null &
LAUNCH_PID=$!
T0=$(date +%s)

# --- timetable (seconds after launch). Scenario side: see scripts/ios-sim-scenario.js ---
# Two independent clocks, because on the cloud Mac a single screenshot can take many seconds
# (run 4: one took 44 s and pushed every later step off schedule):
#   control: the thumb. Only sends the App away and brings it back, at fixed times.
#   camera:  screenshots. If one is slow, only later screenshots slip, never the thumb.
(
  at 60;  to_background      # between call 1 and call 2: 25 s away
  at 85;  to_foreground
  at 180; to_background      # in the middle of call 4: 16 s away (the App hangs up after 5 s)
  at 196; to_foreground
) > "$OUT/control.log" 2>&1 &
CONTROL_PID=$!
(
  at 12;  shot 02-consent-sheet
  at 24;  shot 03-call1-live
  at 34;  shot 03b-call1-live-later
  at 48;  shot 04-call1-ended
  at 99;  shot 06a-topics-sheet
  at 114; shot 06-call2-live
  at 138; shot 08-call3-live
  at 165; shot 09-call4-live
  at 204; shot 11-call4-after-return
  at 210; shot 12-call4-after-return-later
  at 233; shot 14-status
  at 249; shot 15-settings
  at 264; shot 16-seat-code
) > "$OUT/camera.log" 2>&1 &
CAMERA_PID=$!
at 285
kill "$CONTROL_PID" "$CAMERA_PID" >/dev/null 2>&1 || true
cat "$OUT/control.log" "$OUT/camera.log"

kill "$LAUNCH_PID" >/dev/null 2>&1 || true

echo "== summary =="
grep -ao 'MUNEA_SIM .*' "$CONSOLE" | cut -c1-1400 > "$OUT/summary.txt"
wc -l "$OUT/summary.txt" "$CONSOLE"
grep -aE 'MUNEA_SIM (BOOT|NATIVE_|CLOCK_PROBE|CALL._CONNECTED|CALL._DONE|CALL._TOPICS|CALL._CONSENT|PHASE|VIS|CALL4_AFTER|SCENARIO_DONE|TOUR|JS_ERROR|JS_REJECTION|MISSING)' "$OUT/summary.txt" | cut -c1-400
ls -la "$OUT"
exit 0
