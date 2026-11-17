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
echo "== warm up Settings (it is what we switch to when sending the App away) =="
xcrun simctl launch "$UDID" com.apple.Preferences >/dev/null 2>&1 || true
sleep 20

# perl alarm = a timeout that exists on every Mac: a hung simulator command gets cut off.
sc() { perl -e 'alarm shift; exec @ARGV' "$1" xcrun simctl "${@:2}"; }
T0=$(date +%s)
shot() { sc 45 io "$UDID" screenshot "$OUT/$1.png" >/dev/null 2>&1 || echo "screenshot $1 failed"; echo "  shot $1 at $(( $(date +%s) - T0 ))s"; }
to_background() { sc 90 launch "$UDID" com.apple.Preferences >/dev/null 2>&1 || echo "could not open Settings"; echo "  -> background at $(( $(date +%s) - T0 ))s"; }
to_foreground() { sc 90 launch "$UDID" "$BUNDLE" >/dev/null 2>&1 || echo "could not bring App back"; echo "  -> foreground at $(( $(date +%s) - T0 ))s"; }
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

# --- sequence. Scenario side: see scripts/ios-sim-scenario.js ---
# One loop, timed RELATIVE to each step finishing, because on the cloud Mac the simulator
# commands themselves are slow and uneven (run 5: opening Settings the first time took ~90 s,
# bringing the App back 10-16 s). The scenario waits up to 4 minutes at each of the two points
# where it needs to be sent away, so the host only has to be "late enough", never exact.
after() { sleep "$1"; }
after 8;  shot 02-consent-sheet
after 10; shot 03-call1-live
after 30                                  # call 1 has ended by now (connected ~15 s, held 20 s)
shot 04-call1-ended
to_background                             # between call 1 and call 2
after 20
to_foreground                             # returns once the App is in front again
after 2;  shot 06a-topics-sheet           # asked once before an early call (stays up 16 s)
after 14; shot 06-call2-live              # first call after coming back
after 24; shot 08-call3-live              # call right after the native audio pulse
after 26; shot 09-call4-live              # call 4 is up and waiting to be left
to_background                             # leave the screen in the middle of call 4
after 14                                  # the App hangs up after 5 s away
to_foreground
after 1;  shot 11-call4-after-return      # the notice card
after 5;  shot 12-call4-after-return-later
after 22; shot 14-status
after 17; shot 15-settings
after 14; shot 16-seat-code
after 14

kill "$LAUNCH_PID" >/dev/null 2>&1 || true

echo "== summary =="
grep -ao 'MUNEA_SIM .*' "$CONSOLE" | cut -c1-1400 > "$OUT/summary.txt"
wc -l "$OUT/summary.txt" "$CONSOLE"
grep -aE 'MUNEA_SIM (BOOT|NATIVE_|CLOCK_PROBE|CALL._CONNECTED|CALL._DONE|CALL._TOPICS|CALL._CONSENT|PHASE|VIS|CALL4_AFTER|SCENARIO_DONE|TOUR|JS_ERROR|JS_REJECTION|MISSING)' "$OUT/summary.txt" | cut -c1-400
ls -la "$OUT"
exit 0
